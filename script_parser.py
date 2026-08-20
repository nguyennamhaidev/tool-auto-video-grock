"""Parse kịch bản text thành list cảnh chuẩn."""
import re
from typing import Optional

# ─── Format detection ─────────────────────────────────────────────────────────

_SEPARATOR_RE = re.compile(r'\n[ \t]*-{10,}[ \t]*\n')


def detect_format(text: str) -> str:
    """
    Phát hiện format kịch bản:
      - 'screenplay': nhiều cảnh dạng block, phân cách bởi ---...
      - 'simple': mỗi dòng/số là 1 cảnh ngắn
    """
    if not text:
        return 'simple'
    if _SEPARATOR_RE.search(text):
        return 'screenplay'
    # Nếu mỗi scene marker có nhiều dòng nội dung → screenplay
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    markers = sum(1 for l in lines if re.match(r'^\d+[.)]\s', l) or re.match(r'^\d+\.\s*$', l))
    if markers >= 2 and len(lines) / max(markers, 1) > 4:
        return 'screenplay'
    return 'simple'


# ─── Screenplay parser (multi-line blocks) ────────────────────────────────────

def parse_screenplay(text: str, default_duration: int = 10) -> list[dict]:
    """
    Parse kịch bản phim dạng block. Hỗ trợ 2 kiểu phân cách:

    Kiểu 1 – dòng gạch ngang (---...):
        1.
        CẢNH 1 – INT – PHÒNG TRỌ – ĐÊM
        Mô tả...
        --------------------------------------------------
        2.
        CẢNH 2 – ...

    Kiểu 2 – tiêu đề đánh số (không cần dòng gạch):
        1. HẮC TƯỚNG XUẤT HIỆN
        Nhân vật:
        "Thoại..."

        2. TƯỚNG ĐỊCH XIN THA
        ...
    """
    chunks = _SEPARATOR_RE.split(text)

    # Có separator (---) → dùng logic cũ
    if len(chunks) > 1:
        scenes = []
        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk:
                continue
            lines = [l.rstrip() for l in chunk.splitlines()]
            nonempty = [l for l in lines if l.strip()]
            if not nonempty:
                continue

            scene_id = None
            content_start = 0
            for i, line in enumerate(nonempty):
                stripped = line.strip()
                m = re.match(r'^(\d+)[.)]?\s*$', stripped)
                if m:
                    scene_id = int(m.group(1))
                    content_start = i + 1
                    break
                m2 = re.match(r'^(\d+)[.)]\s+(.*)', stripped)
                if m2:
                    scene_id = int(m2.group(1))
                    nonempty[i] = m2.group(2).strip()
                    content_start = i
                    break

            if scene_id is None:
                continue
            content_lines = nonempty[content_start:]
            if not content_lines:
                continue
            full_text = "\n".join(content_lines).strip()
            visual = _extract_visual(content_lines)
            scenes.append({
                "id": scene_id,
                "duration": default_duration,
                "description": full_text,
                "video_prompt": visual,
            })
        return sorted(scenes, key=lambda s: s["id"])

    # Không có separator → thử chia theo tiêu đề đánh số
    return _parse_by_numbered_headings(text, default_duration)


def _parse_by_numbered_headings(text: str, default_duration: int = 10) -> list[dict]:
    """
    Parse kịch bản đối thoại không có dòng gạch phân cách, VD:

        1. HẮC TƯỚNG XUẤT HIỆN

        Binh sĩ:
        "Hắc Tướng... là hắn!"

        Hắc Tướng:
        "Hôm nay, máu của các ngươi..."

        2. TƯỚNG ĐỊCH XIN THA
        ...
    """
    heading_re = re.compile(r'^(\d+)\.\s+(.+)$', re.MULTILINE)
    matches = list(heading_re.finditer(text))
    if not matches:
        return []

    scenes = []
    for idx, match in enumerate(matches):
        scene_id = int(match.group(1))
        title = match.group(2).strip()

        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        block = text[start:end].strip()

        lines = [l.strip() for l in block.splitlines()]

        dialogue_parts: list[str] = []
        voice_lines: list[str] = []
        visual_lines: list[str] = []
        current_speaker: Optional[str] = None

        for line in lines:
            if not line:
                current_speaker = None
                continue
            # Character cue: "Tên:" cuối dòng
            if re.match(r'^[\w\sÀ-ỹ]{1,40}:\s*$', line):
                current_speaker = re.sub(r':\s*$', '', line).strip()
                continue
            # Dialogue: bắt đầu bằng dấu ngoặc kép
            if line[0] in ('"', '“', '”', "'", '«'):
                clean = line.strip('""\'"“”«»')
                if current_speaker:
                    dialogue_parts.append(f"{current_speaker}: {clean}")
                else:
                    dialogue_parts.append(clean)
                voice_lines.append(clean)
                current_speaker = None
            else:
                visual_lines.append(line)

        # video_prompt: tiêu đề cảnh + mô tả visual (hoặc tóm tắt thoại)
        if visual_lines:
            video_prompt = f"{title}. {'. '.join(visual_lines[:3])}"
        elif dialogue_parts:
            video_prompt = f"{title}. {dialogue_parts[0]}"
        else:
            video_prompt = title

        # voice_text: toàn bộ lời thoại (cho TTS)
        voice_text = " ".join(voice_lines)

        description = title
        if block:
            description = f"{title}\n{block}"

        scenes.append({
            "id": scene_id,
            "duration": default_duration,
            "description": description,
            "video_prompt": video_prompt,
            "voice_text": voice_text,
        })

    return scenes


def _extract_visual(lines: list[str]) -> str:
    """
    Lọc lấy dòng mô tả visual từ kịch bản, bỏ thoại nhân vật.

    Thoại có dạng:
        Tên nhân vật:       ← character cue (tên + dấu hai chấm, không có nội dung)
        "Câu thoại..."      ← dialogue (bắt đầu bằng dấu ngoặc)
    """
    visual = []
    skip_dialogue = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            skip_dialogue = False
            continue

        # Character cue: 1-4 từ + dấu hai chấm cuối dòng, không có nội dung sau
        if re.match(r'^[\w\sÀ-ỹ]{1,40}:\s*$', stripped):
            skip_dialogue = True
            continue

        # Dialogue: bắt đầu bằng dấu ngoặc kép (cả thẳng lẫn cong)
        if stripped[0] in ('"', '"', '"', "'", '«'):
            skip_dialogue = False
            continue

        if skip_dialogue:
            skip_dialogue = False
            continue

        # Bỏ stage directions quá ngắn (< 5 ký tự)
        if len(stripped) < 5:
            continue

        visual.append(stripped)

    return ". ".join(visual[:10])  # Giới hạn độ dài prompt


# ─── Simple parser (mỗi dòng/số = 1 cảnh ngắn) ───────────────────────────────

def parse_script(text: str, default_duration: int = 10) -> list[dict]:
    """
    Parse kịch bản đơn giản: mỗi dòng có số thứ tự = 1 cảnh.

    Hỗ trợ:
        1. Mô tả cảnh
        1) Mô tả cảnh
        Cảnh 1: Mô tả
        Scene 1 - Mô tả
        - Mô tả (gạch đầu dòng)
        Mỗi dòng là 1 cảnh (không có số)
    """
    if not text or not text.strip():
        return []

    lines = [l.strip() for l in text.strip().splitlines()]
    raw_scenes = []

    for line in lines:
        if not line or len(line) < 3:
            continue
        if re.match(r'^#{1,3}\s', line):
            continue

        desc = None
        scene_num = None

        # "1. desc" | "1) desc" | "1: desc" | "1 - desc"
        m = re.match(r'^(\d+)[.):\-–]\s*(.+)', line)
        if m:
            scene_num = int(m.group(1))
            desc = m.group(2).strip()

        # "Cảnh 1: desc" | "Scene 1. desc"
        if not desc:
            m = re.match(
                r'^(?:cảnh|canh|scene|cảnh số|shot)\s*(\d+)[.:)\-–\s]\s*(.+)',
                line, re.IGNORECASE
            )
            if m:
                scene_num = int(m.group(1))
                desc = m.group(2).strip()

        # "- desc" | "• desc"
        if not desc:
            m = re.match(r'^[-•*]\s+(.+)', line)
            if m:
                desc = m.group(1).strip()

        if not desc:
            desc = line

        raw_scenes.append((scene_num, desc))

    scenes = []
    counter = 0
    for num, desc in raw_scenes:
        counter += 1
        sid = num if num is not None else counter
        scenes.append({
            "id": sid,
            "duration": default_duration,
            "description": desc,
            "video_prompt": "",
        })

    scenes.sort(key=lambda s: s["id"])
    return scenes


# ─── Auto-detect + parse ──────────────────────────────────────────────────────

def auto_parse(text: str, default_duration: int = 10) -> tuple[list[dict], str]:
    """
    Tự động phát hiện format và parse.
    Trả về (scenes, format_name).
    """
    fmt = detect_format(text)
    if fmt == 'screenplay':
        scenes = parse_screenplay(text, default_duration)
        if scenes:
            return scenes, 'screenplay'
    scenes = parse_script(text, default_duration)
    return scenes, 'simple'


# ─── Helpers ──────────────────────────────────────────────────────────────────

def build_video_prompt(
    scene: dict,
    character_anchor: str,
    film_style: str,
    scene_index: int,
    total_scenes: int,
) -> str:
    """Tạo English video prompt từ scene description."""
    desc = scene.get("video_prompt") or scene["description"]
    return (
        f"{character_anchor}. "
        f"{desc}. "
        f"Scene {scene_index} of {total_scenes} in a continuous film. "
        f"Style: {film_style}. "
        f"Vertical 9:16, {scene['duration']}s, smooth cinematic motion, 4K."
    )


def preview_scenes(scenes: list[dict], fmt: str = 'simple') -> str:
    """Trả về chuỗi preview ngắn để hiển thị trong UI."""
    lines = [f"→ {len(scenes)} cảnh ({fmt}):\n"]
    for s in scenes:
        desc = (s.get("video_prompt") or s["description"])[:70]
        if len(desc) == 70:
            desc += "..."
        lines.append(f"  [{s['id']:02d}] {desc}")
    return "\n".join(lines)
