"""
Điều phối workflow: Script → VideoEngine → TTS → MoviePy.

Engine hỗ trợ:
  - "grok"      : browser automation (mặc định, không cần API key)
  - "replicate" : Replicate API
  - "kling"     : Kling AI API
  - "luma"      : Luma Dream Machine
  - "comfyui"   : ComfyUI local server
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import queue
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

import config
from utils.logger import GUILogger
from agents.chatgpt_agent import ChatGPTAgent
from agents.grok_agent import GrokAgent
from video.processor import VideoProcessor, build_srt
from script_parser import auto_parse, build_video_prompt

_logger = logging.getLogger("VideoFactory")


_CLIP_EXTS = [".mp4", ".webm", ".mov", ".jpg", ".jpeg", ".png"]


def _build_images_map(char_image: Optional[str], scenes: list[dict]) -> dict[int, str]:
    """
    Xây dựng {scene_id: image_path}:
      - char_image là FILE  → cùng ảnh cho mọi cảnh
      - char_image là THƯ MỤC → tìm {id}.jpg / {id:02d}.jpg / {id:03d}.jpg
        Gap giữa các ảnh → dùng ảnh cảnh liền trước (carry-forward)
    """
    if not char_image:
        return {}
    p = Path(char_image)
    if p.is_file():
        return {s["id"]: str(p) for s in scenes}
    if p.is_dir():
        result: dict[int, str] = {}
        sorted_scenes = sorted(scenes, key=lambda x: x["id"])

        # Pass 1: tìm ảnh khớp tên
        for s in sorted_scenes:
            sid = s["id"]
            for ext in ["jpg", "jpeg", "png", "webp"]:
                for name in [f"{sid}.{ext}", f"{sid:02d}.{ext}", f"{sid:03d}.{ext}"]:
                    img = p / name
                    if img.exists():
                        result[sid] = str(img)
                        break
                if sid in result:
                    break

        # Fallback: map tuần tự nếu không tìm được bằng tên
        if not result:
            imgs = sorted(
                f for f in p.iterdir()
                if f.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
            )
            for i, s in enumerate(sorted_scenes):
                if i < len(imgs):
                    result[s["id"]] = str(imgs[i])

        # Pass 2: carry-forward — cảnh thiếu ảnh → dùng ảnh cảnh liền trước
        last_img: Optional[str] = None
        for s in sorted_scenes:
            sid = s["id"]
            if sid in result:
                last_img = result[sid]
            elif last_img:
                result[sid] = last_img  # kế thừa từ cảnh trước

        return result
    return {}


def _find_resumable_run(
    output_dir: Path, total_scenes: int
) -> Optional[tuple[Path, Path]]:
    """
    Tìm run gần nhất (trong 5 run cuối) có clips chưa hoàn thành.
    Trả về (run_dir, clip_dir) hoặc None.
    """
    try:
        runs = sorted(
            (d for d in output_dir.iterdir() if d.is_dir()),
            key=lambda d: d.stat().st_mtime,
            reverse=True,
        )
        for run in runs[:5]:
            clip_dir = run / "clips"
            if not clip_dir.exists():
                continue
            done = sum(
                1 for i in range(1, total_scenes + 1)
                if any(
                    (clip_dir / f"clip_{i:03d}{ext}").exists()
                    and (clip_dir / f"clip_{i:03d}{ext}").stat().st_size > 5_000
                    for ext in _CLIP_EXTS
                )
            )
            if 0 < done < total_scenes:
                return run, clip_dir
    except Exception:
        pass
    return None


def _build_character_visual(vi: str) -> str:
    desc = vi.lower()
    parts = []
    age = re.search(r"(\d+)\s*tuổi", vi)
    parts.append(f"a {age.group(1)}-year-old Vietnamese woman" if age else "a young Vietnamese woman in her mid-20s")
    if "tóc dài" in desc:   parts.append("long hair")
    elif "tóc ngắn" in desc: parts.append("short hair")
    elif "tóc búi" in desc:  parts.append("hair in a bun")
    if "tóc đen" in desc:   parts.append("black hair")
    elif "tóc nâu" in desc: parts.append("brown hair")
    if "đeo kính" in desc:  parts.append("wearing glasses")
    if "da trắng" in desc:  parts.append("fair skin")
    if "áo trắng" in desc:  parts.append("white top")
    elif "áo đen" in desc:  parts.append("black top")
    elif "đầm" in desc:     parts.append("dress")
    if "thanh lịch" in desc or "sang" in desc: parts.append("elegant style")
    elif "năng động" in desc: parts.append("energetic youthful style")
    else: parts.append("natural makeup, clean modern appearance")
    return ", ".join(parts)


class Orchestrator:
    def __init__(
        self,
        log_queue: queue.Queue,
        progress_callback: Optional[Callable] = None,
        status_callback: Optional[Callable] = None,
        video_engine: str = "",   # "" → dùng config.VIDEO_ENGINE
        tts_engine: str = "",     # "" → dùng config.TTS_ENGINE
    ):
        self.log_queue = log_queue
        self.progress_callback = progress_callback
        self.status_callback = status_callback
        self.logger = GUILogger(log_queue, log_file=str(config.BASE_DIR / "app.log"))
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._video_engine = video_engine or getattr(config, "VIDEO_ENGINE", "grok")
        self._tts_engine   = tts_engine   or getattr(config, "TTS_ENGINE",   "edge")

    # ─── PUBLIC API ──────────────────────────────────────────────────────

    def start_from_script(
        self,
        script_text: str,
        character_desc: str,
        character_image: Optional[str],
        music_path: Optional[str],
        output_dir: str,
        film_style: str = "TikTok/Reels",
        scene_duration: int = 10,
        grok_profile: str = "grok",
        chrome_profile: str = None,
        connect_existing: bool = False,
    ):
        """Chạy từ kịch bản sẵn (không qua ChatGPT)."""
        self._launch(
            "script",
            script_text=script_text,
            character_desc=character_desc,
            character_image=character_image,
            music_path=music_path,
            output_dir=output_dir,
            film_style=film_style,
            scene_duration=scene_duration,
            grok_profile=grok_profile,
            chrome_profile=chrome_profile,
            connect_existing=connect_existing,
        )

    def start_from_product(
        self,
        product_desc: str,
        character_desc: str,
        character_image: Optional[str],
        product_image: Optional[str],
        music_path: Optional[str],
        output_dir: str,
        scene_count: int = 4,
        scene_duration: int = 10,
        film_style: str = "Quảng cáo",
        grok_profile: str = "grok",
        chrome_profile: str = None,
        connect_existing: bool = False,
    ):
        """Chạy chế độ ChatGPT → Grok."""
        self._launch(
            "product",
            product_desc=product_desc,
            character_desc=character_desc,
            character_image=character_image,
            product_image=product_image,
            music_path=music_path,
            output_dir=output_dir,
            scene_count=scene_count,
            scene_duration=scene_duration,
            film_style=film_style,
            grok_profile=grok_profile,
            chrome_profile=chrome_profile,
            connect_existing=connect_existing,
        )

    def stop(self):
        self._stop_event.set()
        self.logger.warning("Da yeu cau dung...")

    # ─── INTERNAL ────────────────────────────────────────────────────────

    def _launch(self, mode: str, **kwargs):
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_sync, args=(mode,), kwargs=kwargs, daemon=True
        )
        self._thread.start()

    def _run_sync(self, mode: str, **kwargs):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            if mode == "script":
                loop.run_until_complete(self._run_from_script(**kwargs))
            else:
                loop.run_until_complete(self._run_from_product(**kwargs))
        except Exception as e:
            self.logger.error(f"Loi: {e}")
            import traceback
            self.logger.warning(traceback.format_exc())
        finally:
            loop.close()
            if self.status_callback:
                self.status_callback("idle")

    # ─── MODE A: Script → Grok ────────────────────────────────────────

    async def _run_from_script(
        self,
        script_text: str,
        character_desc: str,
        character_image: Optional[str],
        music_path: Optional[str],
        output_dir: str,
        film_style: str,
        scene_duration: int,
        grok_profile: str,
        chrome_profile: str = None,
        connect_existing: bool = False,
    ):
        if self.status_callback:
            self.status_callback("running")

        # --- Parse kịch bản (auto-detect format) ---
        scenes, fmt = auto_parse(script_text, default_duration=scene_duration)
        if not scenes:
            self.logger.error("Kich ban trong hoac khong doc duoc. Kiem tra lai.")
            return

        # --- Build images map ---
        images_map = _build_images_map(character_image, scenes)
        if images_map:
            unique_imgs = set(images_map.values())
            if len(unique_imgs) > 1:
                self.logger.info(f"  Per-scene images: {len(images_map)} canh / {len(unique_imgs)} anh khac nhau")
                for s in scenes:
                    img = images_map.get(s["id"])
                    name = Path(img).name if img else "KHONG CO"
                    self.logger.info(f"    Canh {s['id']:02d} → {name}")
            else:
                self.logger.info(f"  Global image: {Path(character_image).name} (dung cho tat ca {len(scenes)} canh)")
        else:
            self.logger.warning("  KHONG CO anh nhan vat — nhan vat co the khong nhat quan!")

        # --- Tìm run dang dở để resume ---
        base_out = Path(output_dir)
        resume = _find_resumable_run(base_out, len(scenes))
        if resume:
            run_dir, clip_dir = resume
            done_count = sum(
                1 for i in range(1, len(scenes) + 1)
                if any(
                    (clip_dir / f"clip_{i:03d}{ext}").exists()
                    and (clip_dir / f"clip_{i:03d}{ext}").stat().st_size > 5_000
                    for ext in _CLIP_EXTS
                )
            )
            self.logger.info("=" * 50)
            self.logger.info(f"RESUME: Tiep tuc tu {run_dir.name}")
            self.logger.info(f"  Da co: {done_count}/{len(scenes)} clips — tao tiep {len(scenes)-done_count} canh con lai")
        else:
            run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            run_dir = base_out / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            clip_dir = run_dir / "clips"
            clip_dir.mkdir(exist_ok=True)
            self.logger.info("=" * 50)

        self.logger.info(f"CHE DO PHIM: {film_style} | Format: {fmt}")
        self.logger.info(f"So canh: {len(scenes)} | Giay/canh: {scene_duration}")
        self.logger.info(f"Nhan vat: {character_desc[:60]}")
        self.logger.info(f"Output: {run_dir}")
        self.logger.info("=" * 50)

        # Preview kịch bản
        for s in scenes:
            img_name = Path(images_map.get(s["id"], "")).name if images_map.get(s["id"]) else "khong co"
            preview = (s.get("video_prompt") or s["description"])[:55]
            self.logger.info(f"  [{s['id']:02d}] [{img_name}] {preview}")

        # Lưu kịch bản đã parse
        (run_dir / "scenes.json").write_text(
            json.dumps(scenes, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        if self._stop_event.is_set():
            return

        # --- TTS: tạo voice-over cho từng cảnh ---
        voice_paths: dict[int, Path] = {}
        if any((scene.get("voice_text") if isinstance(scene, dict) else getattr(scene, "voice_text", ""))
               for scene in scenes):
            voice_paths = await self._generate_tts(scenes, run_dir)

        # --- Tạo video clips ---
        self._update_progress(0, len(scenes), "Dang tao clips...")
        clip_paths = await self._generate_clips(
            scenes=scenes,
            images_map=images_map,
            character_image=character_image,
            clip_dir=clip_dir,
            character_desc=character_desc,
            film_style=film_style,
            grok_profile=grok_profile,
            chrome_profile=chrome_profile,
            connect_existing=connect_existing,
        )

        if not clip_paths:
            self.logger.error("Khong tai duoc clip nao.")
            return

        self.logger.info(f"Da tai {len(clip_paths)}/{len(scenes)} clips")

        if self._stop_event.is_set():
            return

        # --- Ghép phim (kèm voice-over + subtitle) ---
        self._update_progress(len(scenes), len(scenes), "Dang ghep phim...")
        srt = build_srt(scenes) if voice_paths else None
        await self._assemble(clip_paths, run_dir, music_path, run_id,
                             voice_paths=voice_paths, subtitle_srt=srt)

    # ─── TTS helper ──────────────────────────────────────────────────

    async def _generate_tts(self, scenes: list, run_dir: Path) -> dict[int, Path]:
        """Tạo TTS audio cho tất cả cảnh có voice_text."""
        try:
            from services.tts import get_tts_engine
            tts = get_tts_engine(
                self._tts_engine,
                api_key=getattr(config, "ELEVENLABS_API_KEY", ""),
                voice_id=getattr(config, "ELEVENLABS_VOICE_ID", ""),
            )
            if tts is None:
                self.logger.warning("TTS engine khong kha dung — bo qua voice-over")
                return {}

            self.logger.step(f"TTS [{tts.name}]: tao voice-over cho {len(scenes)} canh...")
            voice_dir = run_dir / "voices"

            if hasattr(tts, "synthesize_batch"):
                result = await tts.synthesize_batch(scenes, voice_dir)
            else:
                result: dict[int, Path] = {}
                voice_dir.mkdir(parents=True, exist_ok=True)
                for scene in scenes:
                    text = scene.get("voice_text") if isinstance(scene, dict) else getattr(scene, "voice_text", "")
                    sid  = scene.get("id") if isinstance(scene, dict) else scene.id
                    if text:
                        out = voice_dir / f"voice_{sid:03d}.mp3"
                        path = await tts.synthesize(text, out)
                        if path:
                            result[sid] = path

            self.logger.success(f"TTS xong: {len(result)}/{len(scenes)} canh co audio")
            return result
        except Exception as e:
            self.logger.warning(f"TTS loi (bo qua): {e}")
            _logger.debug("TTS exception", exc_info=True)
            return {}

    # ─── Video clip generation (Grok hoặc API engine) ────────────────

    async def _generate_clips(
        self,
        scenes: list,
        images_map: dict,
        character_image: Optional[str],
        clip_dir: Path,
        character_desc: str,
        film_style: str,
        grok_profile: str,
        chrome_profile: Optional[str],
        connect_existing: bool,
    ) -> list[Path]:
        """Dispatch sang Grok hoặc API engine tuỳ config."""
        from services.video_gen import get_video_engine

        engine = get_video_engine(
            self._video_engine,
            api_token=getattr(config, "REPLICATE_API_TOKEN", ""),
            access_key=getattr(config, "KLING_ACCESS_KEY", ""),
            secret_key=getattr(config, "KLING_SECRET_KEY", ""),
            api_key=getattr(config, "LUMA_API_KEY", ""),
            url=getattr(config, "COMFYUI_URL", "http://127.0.0.1:8188"),
        )

        if engine is not None:
            # ── API engine ────────────────────────────────────────────
            self.logger.info(f"Video engine: {engine.name}")
            downloaded = []
            total = len(scenes)

            for i, scene in enumerate(scenes, 1):
                if self._stop_event.is_set():
                    break
                self._update_progress(i - 1, total, f"{engine.name}: canh {i}/{total}")

                sid  = scene.get("id", i) if isinstance(scene, dict) else scene.id
                ref  = images_map.get(sid) or character_image
                desc = scene.get("video_prompt") or scene.get("description", "") if isinstance(scene, dict) \
                       else (scene.video_prompt or scene.description)
                dur  = scene.get("duration", 10) if isinstance(scene, dict) else scene.duration

                out = clip_dir / f"clip_{i:03d}.mp4"
                try:
                    path = await engine.generate(
                        prompt=desc,
                        output_path=out,
                        reference_image=ref if engine.supports_reference_image else None,
                        duration=min(dur, engine.max_duration),
                    )
                    if path:
                        downloaded.append(path)
                        self.logger.success(f"Clip {i}/{total}: {path.name}")
                    else:
                        self.logger.error(f"Engine khong tao duoc clip {i}")
                except Exception as e:
                    self.logger.error(f"Clip {i} loi: {e}")
                    _logger.debug("API engine error", exc_info=True)

                self._update_progress(i, total, f"{engine.name}: canh {i}/{total}")
            return downloaded

        else:
            # ── Grok browser automation (mặc định) ───────────────────
            self.logger.info("Video engine: Grok browser automation")

            def on_clip(current, total):
                self._update_progress(current, total, f"Grok: canh {current}/{total}")

            grok = GrokAgent(
                self.logger, profile_name=grok_profile, on_progress=on_clip,
                chrome_profile=chrome_profile, connect_existing=connect_existing,
            )
            try:
                await grok.start()
                if not await grok.ensure_logged_in():
                    self.logger.error("Khong dang nhap duoc Grok.")
                    return []
                return await grok.generate_clips(
                    scenes=scenes,
                    character_image_path=character_image,
                    output_dir=clip_dir,
                    character_desc=character_desc,
                    film_style=film_style,
                    character_images_map=images_map,
                    should_stop=self._stop_event.is_set,
                )
            finally:
                await grok.stop()

    # ─── MODE B: ChatGPT → Grok ──────────────────────────────────────

    async def _run_from_product(
        self,
        product_desc: str,
        character_desc: str,
        character_image: Optional[str],
        product_image: Optional[str],
        music_path: Optional[str],
        output_dir: str,
        scene_count: int,
        scene_duration: int,
        film_style: str,
        grok_profile: str,
        chrome_profile: str = None,
        connect_existing: bool = False,
    ):
        if self.status_callback:
            self.status_callback("running")

        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = Path(output_dir) / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        clip_dir = run_dir / "clips"
        clip_dir.mkdir(exist_ok=True)

        self.logger.info("=" * 50)
        self.logger.info(f"CHE DO CHATGPT: {product_desc[:50]}")
        self.logger.info("=" * 50)

        # --- ChatGPT viết kịch bản ---
        self._update_progress(1, 3, "Buoc 1/3: ChatGPT viet kich ban...")
        character_visual = _build_character_visual(character_desc)

        chatgpt = ChatGPTAgent(self.logger)
        script_data = None
        try:
            await chatgpt.start()
            if not await chatgpt.ensure_logged_in():
                self.logger.error("Khong dang nhap ChatGPT.")
                return
            script_data = await chatgpt.generate_script(
                product_desc=product_desc,
                character_desc=character_desc,
                character_visual=character_visual,
                scene_count=scene_count,
                scene_duration=scene_duration,
            )
        finally:
            await chatgpt.stop()

        if not script_data:
            self.logger.error("Khong lay duoc kich ban tu ChatGPT.")
            return

        scenes = script_data.get("scenes", [])
        (run_dir / "script.json").write_text(
            json.dumps(script_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self.logger.success(f"Kich ban: {script_data.get('title', '?')} ({len(scenes)} canh)")
        for s in scenes:
            self.logger.info(f"  [{s['id']}] [{s.get('purpose','?')}] {s.get('script_vi','')[:60]}")

        if self._stop_event.is_set():
            return

        # --- Grok ---
        self._update_progress(2, 3, "Buoc 2/3: Grok tao clips...")
        def on_clip(cur, tot):
            self._update_progress(cur, tot, f"Grok: canh {cur}/{tot}")

        grok = GrokAgent(
            self.logger, profile_name=grok_profile, on_progress=on_clip,
            chrome_profile=chrome_profile, connect_existing=connect_existing,
        )
        clip_paths = []
        try:
            await grok.start()
            if not await grok.ensure_logged_in():
                self.logger.error("Khong dang nhap Grok.")
                return
            clip_paths = await grok.generate_clips(
                scenes=scenes,
                character_image_path=character_image,
                product_image_path=product_image,
                output_dir=clip_dir,
                character_desc=character_desc,
                film_style=film_style,
                should_stop=self._stop_event.is_set,
            )
        finally:
            await grok.stop()

        if not clip_paths:
            self.logger.error("Khong tai duoc clip nao.")
            return

        # --- Ghép ---
        self._update_progress(3, 3, "Buoc 3/3: Ghep phim...")
        safe = re.sub(r"[^\w\s-]", "", script_data.get("title", "video")).replace(" ", "_")[:40]
        await self._assemble(clip_paths, run_dir, music_path, scene_id_prefix=safe)

    # ─── Shared: assemble ────────────────────────────────────────────────

    async def _assemble(
        self,
        clip_paths: list[Path],
        run_dir: Path,
        music_path: Optional[str],
        scene_id_prefix: str = "film",
        voice_paths: Optional[dict] = None,
        subtitle_srt: Optional[str] = None,
    ):
        processor = VideoProcessor(self.logger)
        music = (
            Path(music_path)
            if music_path and Path(music_path).exists()
            else processor.pick_random_music()
        )
        final = run_dir / f"{scene_id_prefix}.mp4"

        # Map scene_id → index (1-based) cho voice paths
        indexed_voices: Optional[dict[int, Path]] = None
        if voice_paths:
            indexed_voices = {i: p for i, (_, p) in enumerate(sorted(voice_paths.items()), 1)}

        result = processor.assemble(
            clip_paths, final,
            music_path=music,
            voice_paths=indexed_voices,
            subtitle_srt=subtitle_srt,
        )
        if result:
            self.logger.success("=" * 50)
            self.logger.success(f"XONG! Phim: {result}")
            self.logger.success("=" * 50)
            if self.status_callback:
                self.status_callback(f"done:{result}")
        else:
            self.logger.error("Ghep that bai.")

    def _update_progress(self, current: int, total: int, label: str, sub: bool = False):
        if self.progress_callback:
            self.progress_callback(current, total, label, sub)
