import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

APP_NAME = "Video Factory AI"
VERSION = "1.0.0"

BASE_DIR = Path(__file__).parent
APP_SETTINGS_FILE = BASE_DIR / "app_settings.json"
ASSETS_DIR = BASE_DIR / "assets"
OUTPUT_DIR = BASE_DIR / "output"
TEMP_DIR = BASE_DIR / "temp"
MUSIC_DIR = BASE_DIR / "assets" / "music"
CHARACTERS_DIR = BASE_DIR / "assets" / "characters"
BROWSER_DATA_DIR = BASE_DIR / ".browser_data"
GROK_COOKIES_FILE = BASE_DIR / "grok_cookies.json"   # lưu cookies inject

for d in [ASSETS_DIR, OUTPUT_DIR, TEMP_DIR, MUSIC_DIR, CHARACTERS_DIR, BROWSER_DATA_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# COOKIE IMPORT / INJECT  (dán từ Chrome DevTools → Application → Cookies)
# ---------------------------------------------------------------------------

def parse_devtools_cookies(text: str) -> list[dict]:
    """
    Parse cookies từ định dạng Chrome DevTools (copy all → tab-separated).
    Cột: Name | Value | Domain | Path | Expires | Size | HttpOnly | Secure | SameSite | ... | Priority
    Trả về list cookies theo định dạng Playwright context.add_cookies().
    """
    SAMESITE_VALID = {"Strict", "Lax", "None"}
    cookies: list[dict] = []

    for line in text.strip().splitlines():
        parts = line.split("\t")
        if len(parts) < 4:
            continue

        name   = parts[0].strip()
        value  = parts[1].strip() if len(parts) > 1 else ""
        domain = parts[2].strip() if len(parts) > 2 else ""
        path   = parts[3].strip() if len(parts) > 3 else "/"

        if not name or not domain:
            continue

        expires_str = parts[4].strip() if len(parts) > 4 else ""
        http_only   = "✓" in (parts[6] if len(parts) > 6 else "")
        secure      = "✓" in (parts[7] if len(parts) > 7 else "")
        samesite_raw = parts[8].strip() if len(parts) > 8 else ""
        samesite    = samesite_raw if samesite_raw in SAMESITE_VALID else "None"

        cookie: dict = {
            "name":     name,
            "value":    value,
            "domain":   domain,
            "path":     path,
            "secure":   secure,
            "httpOnly": http_only,
            "sameSite": samesite,
        }

        # Parse expires (bỏ qua "Phiên" = session cookie)
        if expires_str and expires_str not in ("Phiên", "Session", ""):
            try:
                dt = datetime.fromisoformat(expires_str.replace("Z", "+00:00"))
                cookie["expires"] = dt.timestamp()
            except Exception:
                pass

        cookies.append(cookie)

    return cookies


def save_cookies(cookies: list[dict]) -> None:
    """Lưu cookies vào file JSON để dùng lại."""
    GROK_COOKIES_FILE.write_text(
        json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_saved_cookies() -> list[dict]:
    """Tải cookies đã lưu. Trả về [] nếu chưa có."""
    if not GROK_COOKIES_FILE.exists():
        return []
    try:
        return json.loads(GROK_COOKIES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


# ---------------------------------------------------------------------------
# USER CONFIG — lưu/đọc setting dạng Python source code (user_config.py)
# ---------------------------------------------------------------------------

USER_CONFIG_FILE = BASE_DIR / "user_config.py"


def save_user_config(data: dict) -> None:
    """
    Ghi dict cấu hình thành user_config.py (Python source code hợp lệ).
    File có thể mở, đọc và chỉnh sửa trực tiếp bằng text editor.
    """
    lines = [
        "# -*- coding: utf-8 -*-\n",
        "# Cấu hình người dùng — tự động sinh bởi Video Factory AI\n",
        "# Có thể mở, đọc và chỉnh sửa file này trực tiếp\n\n",
    ]
    for key, val in sorted(data.items()):
        lines.append(f"{key} = {repr(val)}\n")
    USER_CONFIG_FILE.write_text("".join(lines), encoding="utf-8")


def load_user_config() -> dict:
    """
    Đọc cấu hình từ user_config.py bằng importlib.
    Trả về dict {key: value} hoặc {} nếu file chưa có.
    """
    if not USER_CONFIG_FILE.exists():
        return {}
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("_vid_user_cfg", USER_CONFIG_FILE)
        if not spec or not spec.loader:
            return {}
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return {k: v for k, v in vars(mod).items() if not k.startswith("_")}
    except Exception:
        return {}


def update_user_config(key: str, value) -> None:
    """Cập nhật 1 key trong user_config.py, giữ nguyên các key khác."""
    data = load_user_config()
    data[key] = value
    save_user_config(data)


# ---------------------------------------------------------------------------
# CHROME PROFILE DETECTION & SYNC
# ---------------------------------------------------------------------------

def get_chrome_user_data() -> Optional[Path]:
    """Tìm thư mục Chrome User Data trên máy Windows."""
    username = os.environ.get("USERNAME", "")
    candidates = [
        Path(f"C:/Users/{username}/AppData/Local/Google/Chrome/User Data"),
        Path(f"C:/Users/{username}/AppData/Local/Google/Chrome Beta/User Data"),
        Path(f"C:/Users/{username}/AppData/Local/Chromium/User Data"),
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def find_chrome_profiles() -> dict[str, str]:
    """
    Trả về {tên hiển thị: tên thư mục profile} cho tất cả Chrome profiles.
    Ví dụ: {"Grok [Default]": "Default", "Cá nhân [Profile 1]": "Profile 1"}
    """
    user_data = get_chrome_user_data()
    if not user_data:
        return {}

    result: dict[str, str] = {}
    try:
        dirs = sorted(user_data.iterdir())
    except Exception:
        return {}

    for d in dirs:
        if not d.is_dir():
            continue
        if d.name != "Default" and not d.name.startswith("Profile "):
            continue
        display = d.name
        try:
            prefs_file = d / "Preferences"
            if prefs_file.exists():
                data = json.loads(prefs_file.read_text(encoding="utf-8", errors="ignore"))
                name = data.get("profile", {}).get("name", "").strip()
                if name:
                    display = f"{name}  [{d.name}]"
        except Exception:
            pass
        result[display] = d.name
    return result


def _safe_copy_tree(src: Path, dst: Path) -> tuple[int, int]:
    """
    Copy thư mục đệ quy, bỏ qua từng file bị khóa thay vì abort toàn bộ.
    Trả về (số file copy được, số file bị khóa).
    """
    dst.mkdir(parents=True, exist_ok=True)
    copied = locked = 0
    for item in src.rglob("*"):
        rel = item.relative_to(src)
        target = dst / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(item), str(target))
                copied += 1
            except PermissionError:
                locked += 1
            except Exception:
                pass
    return copied, locked


def sync_chrome_profile(chrome_profile_name: str, dest_user_data: Path) -> tuple[bool, str]:
    """
    Sao chép Chrome profile vào thư mục tool để Playwright dùng.
    Dùng copy từng file → bỏ qua file bị khóa thay vì abort.
    Trả về (thành công, thông báo).
    """
    user_data = get_chrome_user_data()
    if not user_data:
        return False, "Khong tim thay Chrome User Data tren may"

    src_profile = user_data / chrome_profile_name
    if not src_profile.exists():
        return False, f"Profile '{chrome_profile_name}' khong ton tai"

    dest_user_data.mkdir(parents=True, exist_ok=True)

    # Copy Local State từ root (encryption key cho Cookies DPAPI trên Windows)
    for fname in ("Local State", "First Run"):
        src_f = user_data / fname
        if src_f.exists():
            try:
                shutil.copy2(str(src_f), str(dest_user_data / fname))
            except Exception:
                pass

    # Luôn copy vào "Default" trong tool dir
    dst_profile = dest_user_data / "Default"
    dst_profile.mkdir(parents=True, exist_ok=True)

    # File quan trọng nhất: Cookies (Chrome 147: nằm trong Network/Cookies)
    COOKIE_PATHS = [
        src_profile / "Cookies",           # Chrome cũ
        src_profile / "Network" / "Cookies",  # Chrome 96+
    ]
    cookies_ok = False
    for cp in COOKIE_PATHS:
        if cp.exists():
            rel = cp.relative_to(src_profile)
            dst_cp = dst_profile / rel
            dst_cp.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(str(cp), str(dst_cp))
                cookies_ok = True
            except PermissionError:
                pass  # Chrome đang chạy → Cookies bị khóa

    # Các file/folder phụ (session storage, preferences, history...)
    SYNC_ITEMS = [
        "Network",           # toàn bộ thư mục (đã xử lý Cookies riêng ở trên)
        "Preferences",
        "Secure Preferences",
        "Local Storage",
        "Web Data",
        "Login Data",
        "Extension Cookies",
        "Visited Links",
        "Bookmarks",
        "History",
    ]

    total_copied = total_locked = 0
    for name in SYNC_ITEMS:
        src_item = src_profile / name
        dst_item = dst_profile / name
        if not src_item.exists():
            continue
        if src_item.is_dir():
            fc, fl = _safe_copy_tree(src_item, dst_item)
            total_copied += fc; total_locked += fl
        else:
            try:
                shutil.copy2(str(src_item), str(dst_item))
                total_copied += 1
            except PermissionError:
                total_locked += 1
            except Exception:
                pass

    if not cookies_ok and total_copied == 0:
        return False, "Dong Chrome truoc khi dong bo (tat ca file dang bi khoa)"

    parts = [f"Da sao chep {total_copied} file"]
    if cookies_ok:
        parts.append("✓ Cookies (da dang nhap)")
    else:
        parts.append("⚠ THIEU Cookies – hay dong Chrome va sync lai!")
    if total_locked:
        parts.append(f"({total_locked} file bi khoa)")
    return True, " | ".join(parts)

# ---------------------------------------------------------------------------
# API KEYS — điền key vào đây hoặc để trống để dùng Grok browser automation
# ---------------------------------------------------------------------------

# Replicate (https://replicate.com/account/api-tokens)
REPLICATE_API_TOKEN: str = ""

# Kling AI (https://app.klingai.com/global/api-key)
KLING_ACCESS_KEY: str = ""
KLING_SECRET_KEY: str = ""

# Luma Dream Machine (https://lumalabs.ai/dream-machine/api)
LUMA_API_KEY: str = ""

# ElevenLabs TTS (https://elevenlabs.io/app/settings/api-keys)
ELEVENLABS_API_KEY: str = ""
ELEVENLABS_VOICE_ID: str = ""   # ID giọng clone, để trống = dùng giọng mặc định

# ComfyUI (chỉ cần nếu dùng local ComfyUI server)
COMFYUI_URL: str = "http://127.0.0.1:8188"

# Engine mặc định: "grok" | "replicate" | "kling" | "luma" | "comfyui"
VIDEO_ENGINE: str = "grok"

# TTS engine mặc định: "edge" (miễn phí) | "elevenlabs" (cần API key)
TTS_ENGINE: str = "edge"

# --- Selectors (cập nhật nếu UI web thay đổi) ---
CHATGPT_URL = "https://chatgpt.com/"
CHATGPT_SELECTORS = {
    "textarea": "#prompt-textarea",
    "send_button": '[data-testid="send-button"]',
    "response_block": '[data-message-author-role="assistant"]',
    "response_text": '[data-message-author-role="assistant"] .markdown',
    "stop_button": '[data-testid="stop-button"]',
    "regenerate": '[data-testid="regenerate-button"]',
}

GROK_URL = "https://grok.com/"
GROK_IMAGINE_URL = "https://grok.com/imagine"

# Selectors cho trang grok.com/imagine (cập nhật nếu UI thay đổi)
GROK_IMAGINE_SELECTORS = {
    "textarea":     ".tiptap.ProseMirror",          # ProseMirror contenteditable
    "placeholder":  "p.is-empty.is-editor-empty",   # placeholder paragraph bên trong
    "video_tab":    "Video",                         # text của radio button
    "image_tab":    "Image",
    "resolution_720": "720p",
    "resolution_480": "480p",
    "dur_10s":      "10s",
    "dur_6s":       "6s",
    "submit":       "button[aria-label='Submit'][type='submit']",
    "upload_btn":   "button[aria-label='Upload']",
    "file_input":   "input[type='file'][accept='image/*']",
    "save_btn":     "button[aria-label='Save']",
    "is_loading":   "[aria-label='Stop'], .animate-spin, [data-generating]",
    # Nút xóa ảnh đã upload (nhiều aria-label tuỳ version UI)
    "remove_image": (
        "button[aria-label='Remove image'], "
        "button[aria-label='Remove uploaded image'], "
        "button[aria-label='Remove attachment'], "
        "button[aria-label='Remove'], "
        "button[aria-label='Delete image']"
    ),
    # Link/button quay lại trang tạo mới (SPA nav, không reload)
    "new_creation": (
        "a[href='/imagine'], "
        "button[aria-label='New'], "
        "button[aria-label='New creation'], "
        "[aria-label='Create new'], "
        "[data-testid='new-creation-btn']"
    ),
}

# --- Hành vi giống người thật ---
TYPING_DELAY_MS = 85       # ms giữa mỗi ký tự
MIN_ACTION_DELAY = 2.0     # giây
MAX_ACTION_DELAY = 5.0     # giây
GENERATION_TIMEOUT = 300   # giây chờ Grok tạo xong (5 phút)
CHATGPT_TIMEOUT = 120      # giây chờ ChatGPT trả lời

# Viewport cố định cho browser Grok (không đổi mid-session)
# 430×932 = iPhone 14 Plus — đủ rộng để thấy tất cả nút, UI mobile Grok hoạt động tốt hơn desktop
GROK_BROWSER_VIEWPORT = {"width": 430, "height": 932}
GROK_MOBILE_VIEWPORT  = GROK_BROWSER_VIEWPORT   # alias (backward-compat)

# Vị trí cố định của cửa sổ browser trên màn hình (top-left corner)
# Giữ cố định để automation dễ thao tác và user dễ quan sát
GROK_BROWSER_POSITION = {"left": 30, "top": 30}

# --- Cài đặt video mặc định ---
DEFAULT_SCENE_COUNT = 4
DEFAULT_SCENE_DURATION = 10   # giây
DEFAULT_TOTAL_DURATION = 40   # giây
VIDEO_FPS = 30
VIDEO_RESOLUTION = (1080, 1920)  # TikTok portrait

# ---------------------------------------------------------------------------
# PROMPT HỆ THỐNG – phần này ảnh hưởng trực tiếp đến chất lượng video
# ---------------------------------------------------------------------------

# Gửi cho ChatGPT – yêu cầu trả về JSON chuẩn để Grok dùng trực tiếp
CHATGPT_SCRIPT_PROMPT = """You are an expert TikTok video scriptwriter. Create a professional {total_duration}-second product video script.

PRODUCT: {product_desc}
CHARACTER (Vietnamese): {character_desc}
CHARACTER (English visual): {character_visual}
SCENES: {scene_count} scenes × {scene_duration} seconds each

SCENE STRUCTURE (mandatory):
- Scene 1 [HOOK]     : Shocking/curiosity-grabbing opening. No product yet. Pure emotion.
- Scene 2 [PROBLEM]  : Relatable pain point. Character struggles visibly.
- Scene 3 [SOLUTION] : Product shown clearly. Character's transformation/reaction.
- Scene 4 [CTA]      : Clear call-to-action. Confident character. Urgency.

VIDEO PROMPT RULES (critical for AI video generation):
1. Start every video_prompt with the CHARACTER_ANCHOR (copy it exactly)
2. Add specific ACTION the character performs
3. Add SETTING (location, environment)
4. Add CAMERA (close-up / medium shot / wide shot / over-shoulder)
5. Add LIGHTING (natural daylight / soft studio / golden hour / dramatic)
6. End with: vertical 9:16, {scene_duration}s, smooth motion, cinematic 4K

CHARACTER_ANCHOR = "{character_visual}, wearing {character_outfit}"

Return ONLY valid JSON below. No explanation. No markdown. No extra text.

{{
  "title": "Short catchy Vietnamese title under 10 words",
  "character_anchor": "{character_visual}, wearing {character_outfit}",
  "scenes": [
    {{
      "id": 1,
      "duration": {scene_duration},
      "purpose": "HOOK",
      "script_vi": "Lời thoại/narration tiếng Việt ngắn gọn cho cảnh này",
      "emotion": "shocked / curious / relatable",
      "video_prompt": "CHARACTER_ANCHOR [paste anchor here]. [specific action]. [setting]. [camera angle]. [lighting style]. vertical 9:16, {scene_duration}s, smooth motion, cinematic 4K, TikTok style."
    }},
    {{
      "id": 2,
      "duration": {scene_duration},
      "purpose": "PROBLEM",
      "script_vi": "...",
      "emotion": "frustrated / tired / worried",
      "video_prompt": "CHARACTER_ANCHOR [paste anchor here]. [action showing problem]. [setting]. [camera angle]. [lighting]. vertical 9:16, {scene_duration}s, smooth motion, cinematic 4K."
    }},
    {{
      "id": 3,
      "duration": {scene_duration},
      "purpose": "SOLUTION",
      "script_vi": "...",
      "emotion": "happy / amazed / relieved",
      "video_prompt": "CHARACTER_ANCHOR [paste anchor here]. [action with product]. [setting]. [camera angle]. [lighting]. vertical 9:16, {scene_duration}s, smooth motion, cinematic 4K."
    }},
    {{
      "id": 4,
      "duration": {scene_duration},
      "purpose": "CTA",
      "script_vi": "...",
      "emotion": "confident / excited / persuasive",
      "video_prompt": "CHARACTER_ANCHOR [paste anchor here]. [confident action/gesture]. [setting]. [camera angle]. [bright lighting]. vertical 9:16, {scene_duration}s, smooth motion, cinematic 4K."
    }}
  ]
}}"""


# Gửi cho Grok – tạo từng clip video
GROK_VIDEO_PROMPT = """Create a {duration}-second vertical video clip.

SCENE {scene_id} of {total_scenes} — Purpose: {purpose}

VIDEO PROMPT:
{video_prompt}

CHARACTER CONSISTENCY (mandatory):
- Use the attached reference image as the character's face and appearance
- Keep IDENTICAL: face, hairstyle, eye color, skin tone, outfit from reference image
- Do NOT change character between scenes

TECHNICAL SPECS:
- Format: vertical 9:16 (1080×1920), TikTok/Reels ready
- Duration: exactly {duration} seconds
- Quality: 4K, smooth 30fps motion
- No subtitles, no text overlays, no watermarks
- Lighting: match the mood described above"""


# Mô tả visual tiếng Anh cho nhân vật (dùng trong ChatGPT prompt)
CHARACTER_VISUAL_TEMPLATE = (
    "A Vietnamese woman in her mid-20s, {features}, natural makeup, "
    "clean and modern appearance"
)
CHARACTER_OUTFIT_DEFAULT = "casual modern Vietnamese fashion"

# Fallback khi user không điền mô tả nhân vật (không hardcode trong agent code)
CHAR_DESC_FALLBACK_WITH_IMAGE = "Character: see attached reference image for appearance"
CHAR_DESC_FALLBACK_NO_IMAGE   = "No specific character — generate exactly per scene description"

# ---------------------------------------------------------------------------
# PROMPT PHIM – dùng khi user nhập kịch bản trực tiếp (không qua ChatGPT)
# ---------------------------------------------------------------------------
GROK_FILM_PROMPT = "{scene_description}{char_section}"


# Prompt framework cho Sales AI – dùng để bọc prompt ngắn thành brief bán hàng
# đầy đủ trước khi gửi vào Grok.
SALES_PROMPT_FRAMEWORK = """Create one {duration}-second vertical {aspect_ratio} sales video clip for social commerce.

REFERENCE:
{reference_block}

CAMPAIGN:
- Product: {product_name}
- Goal: {goal}
- Target audience: {audience}
- Offer/key selling point: {offer}
- Style preset: {preset} ({preset_tone})
- Shot structure: {shot_structure}
- Call to action: {cta}

USER PRODUCT BRIEF:
{product_prompt}

HUMAN SALES LOGIC:
- ATTENTION: first 0-2 seconds must stop the scroll with a close-up, surprising use case, visible problem, or strong product action.
- PRODUCT/BRANDING: product appears clearly and accurately in the first 2 seconds and stays central to the story.
- CONNECTION: show a believable human reason to care: problem, desire, convenience, taste, beauty, comfort, status, savings, or result.
- DIRECTION: end with a clear buying action through gesture, product tag/shop-card implication, packaging hero shot, or presenter pointing to the link/shop button.
- If no presenter image is attached, use realistic hands, product-in-use shots, or a natural UGC-style creator without changing the product.

TIMING BLUEPRINT:
- 0-2s: hook shot, tight framing, product visible.
- 2-6s: product demo or benefit proof; show how it solves the problem.
- 6-9s: reaction/result/comparison; make the value obvious.
- final second: clean CTA moment: {cta}.

DIRECTING RULES:
- Show the product clearly within the first 2 seconds.
- Keep the product visually accurate to the reference image.
- Make the benefit understandable through action, demonstration, expression, and camera movement.
- Use realistic hands/presenter interaction when appropriate.
- Vertical composition, centered product, TikTok/Reels ready.
- One clear message only; do not cram multiple unrelated claims.
- No subtitles, no text overlays, no watermarks, no fake logos, no random extra products.
- Smooth motion, commercial lighting, high detail, clean background."""

# ---------------------------------------------------------------------------
# APP SETTINGS PERSISTENCE
# ---------------------------------------------------------------------------

_settings_cache: Optional[dict] = None


def load_app_settings() -> dict:
    """Load cấu hình app từ JSON (có cache, đọc file 1 lần / session)."""
    global _settings_cache
    if _settings_cache is None:
        if not APP_SETTINGS_FILE.exists():
            _settings_cache = {}
        else:
            try:
                _settings_cache = json.loads(
                    APP_SETTINGS_FILE.read_text(encoding="utf-8")
                )
            except Exception:
                _settings_cache = {}
    return _settings_cache


def save_app_settings(data: dict) -> None:
    """Lưu cấu hình app vào JSON và cập nhật cache."""
    global _settings_cache
    _settings_cache = data
    try:
        APP_SETTINGS_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# PROMPT MANAGEMENT  (user có thể edit, reset về default)
# ---------------------------------------------------------------------------

# DEFAULT_PROMPTS được set sau khi các prompt string được định nghĩa bên dưới
_DEFAULT_PROMPTS: dict = {}


def get_prompt(name: str) -> str:
    """
    Lấy prompt theo tên.
    Ưu tiên: user-edited (trong app_settings.json) → default (trong code).
    """
    try:
        val = load_app_settings().get("prompts", {}).get(name, "").strip()
        if val:
            return val
    except Exception:
        pass
    return _DEFAULT_PROMPTS.get(name, "")


# Film style presets
FILM_STYLES = {
    "Phim tình cảm":    {"style": "romantic drama", "camera": "soft close-ups, gentle panning",     "lighting": "warm golden tones",      "color": "warm soft palette",          "mood": "emotional, tender"},
    "Phim hành động":   {"style": "action thriller", "camera": "dynamic angles, quick cuts ready",  "lighting": "high contrast dramatic",  "color": "cool desaturated tones",     "mood": "intense, adrenaline"},
    "Phim kinh dị":     {"style": "horror suspense", "camera": "low angle, slow push-in",           "lighting": "dim, shadows, single source","color": "dark desaturated, green tint","mood": "eerie, tense, unsettling"},
    "Phim hài":         {"style": "comedy",           "camera": "medium shots, wide reactions",     "lighting": "bright, even lighting",   "color": "vibrant natural colors",     "mood": "light, fun, expressive"},
    "Phim ngắn nghệ thuật": {"style": "art-house film","camera": "symmetrical, creative framing",  "lighting": "natural, painterly",      "color": "muted artistic palette",     "mood": "contemplative, cinematic"},
    "Tài liệu":         {"style": "documentary",      "camera": "handheld, observational",          "lighting": "natural available light", "color": "realistic natural",          "mood": "authentic, raw"},
    "TikTok/Reels":     {"style": "social media viral","camera": "POV, selfie-style, energetic",    "lighting": "bright ring light style", "color": "vibrant punchy colors",      "mood": "energetic, engaging, trendy"},
    "Quảng cáo":        {"style": "commercial ad",    "camera": "product-focused, clean angles",   "lighting": "soft studio professional","color": "clean bright palette",       "mood": "aspirational, confident"},
}

# Đăng ký prompts mặc định (phải đặt SAU khi các hằng đã được định nghĩa)
_DEFAULT_PROMPTS.update({
    "film_prompt":             GROK_FILM_PROMPT,
    "sales_prompt_framework":  SALES_PROMPT_FRAMEWORK,
    "video_prompt":            GROK_VIDEO_PROMPT,
    "chatgpt_script_prompt":   CHATGPT_SCRIPT_PROMPT,
})
