"""Video Factory AI – Film Studio Mode."""
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

import config
from script_parser import auto_parse, preview_scenes
from services.sales_prompt import (
    DEFAULT_CTA,
    build_default_sales_prompt,
    sales_goal_names,
    sales_preset_names,
)

# ── Màu sắc ──────────────────────────────────────────────────────────────────
C = {
    "bg":       "#0d0d1a",
    "bg2":      "#161628",
    "bg3":      "#1e1e38",
    "card":     "#12122a",
    "accent":   "#6d28d9",
    "accent2":  "#8b5cf6",
    "accent3":  "#a78bfa",
    "green":    "#10b981",
    "yellow":   "#f59e0b",
    "red":      "#ef4444",
    "text":     "#e2e8f0",
    "text2":    "#94a3b8",
    "border":   "#2d2d55",
    "inputbg":  "#1a1a35",
    "tab_act":  "#6d28d9",
    "tab_inact":"#1e1e38",
}

LOG_TAGS = {
    "INFO":    C["text2"],
    "SUCCESS": C["green"],
    "WARNING": C["yellow"],
    "ERROR":   C["red"],
    "STEP":    C["accent3"],
}

FONT_MONO  = ("Consolas", 9)
FONT_BODY  = ("Segoe UI", 9)
FONT_BOLD  = ("Segoe UI", 9, "bold")
FONT_TITLE = ("Segoe UI", 14, "bold")
FONT_H2    = ("Segoe UI", 10, "bold")
IMAGE_FILETYPES = [("Images", "*.png *.jpg *.jpeg *.webp *.bmp")]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Video Factory AI  •  Film Studio  v{config.VERSION}")
        self.geometry("1280x800")
        self.minsize(960, 680)
        self.configure(bg=C["bg"])
        self.after(120, lambda: self.state("zoomed"))

        self.log_queue: queue.Queue = queue.Queue(500)
        self._running = False
        self._last_output: Optional[str] = None
        self.orch = None

        # ── Variables ──
        self.var_mode           = tk.StringVar(value="batch")
        self.var_main_mode      = tk.StringVar(value="film")   # "film" | "sales"
        self.var_aspect_ratio   = tk.StringVar(value="9:16")
        self.var_script         = tk.StringVar()
        self.var_product        = tk.StringVar()
        self.var_char_desc      = tk.StringVar(value="")
        self.var_char_img       = tk.StringVar()
        self.var_product_img    = tk.StringVar()
        self.var_music          = tk.StringVar()
        self.var_output_dir     = tk.StringVar(value=str(config.OUTPUT_DIR))
        self.var_scene_dur      = tk.IntVar(value=10)
        self.var_scene_count    = tk.IntVar(value=4)
        self.var_film_style     = tk.StringVar(value="TikTok/Reels")
        self.var_grok_profile   = tk.StringVar(value="grok")
        self.var_chrome_profile  = tk.StringVar(value="")
        self.var_connect_existing = tk.BooleanVar(value=False)
        self.var_tts_voice       = tk.StringVar(value="female")
        self.var_sales_clips_per_video = tk.IntVar(value=3)
        self.var_sales_parallel_tabs   = tk.IntVar(value=2)
        self.var_sales_preset          = tk.StringVar(value="TikTok Shop")
        self.var_sales_goal            = tk.StringVar(value="Chốt đơn")
        self.var_sales_audience        = tk.StringVar(value="")
        self.var_sales_offer           = tk.StringVar(value="")
        self.var_sales_cta             = tk.StringVar(value=DEFAULT_CTA)
        self.var_sales_auto_prompt     = tk.BooleanVar(value=True)
        self._chrome_profiles    = {}
        self._batch_projects: list[dict] = []
        self._sales_clusters: list[dict] = []

        self._build_ui()
        self._poll_log()
        self._load_settings()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Tự động mở Chrome Grok khi khởi động tool
        self.after(800, self._auto_launch_chrome)

    # ──────────────────────────────────────────────────────────────────────
    # BUILD UI
    # ──────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_header()

        body = tk.Frame(self, bg=C["bg"])
        body.pack(fill="both", expand=True, padx=14, pady=(6, 6))
        body.columnconfigure(0, weight=5)
        body.columnconfigure(1, weight=4)
        body.rowconfigure(0, weight=1)

        left = tk.Frame(body, bg=C["bg"])
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self._build_left(left)

        right = tk.Frame(body, bg=C["bg"])
        right.grid(row=0, column=1, sticky="nsew")
        self._build_right(right)

        self._build_bottom()

    # ── Header ───────────────────────────────────────────────────────────

    def _build_header(self):
        hdr = tk.Frame(self, bg=C["bg3"])
        hdr.pack(fill="x")
        tk.Label(hdr, text="🎬  Video Factory AI  —  Film Studio",
                 bg=C["bg3"], fg=C["accent3"], font=FONT_TITLE,
                 padx=16, pady=10).pack(side="left")
        tk.Label(hdr, text=f"v{config.VERSION}",
                 bg=C["bg3"], fg=C["text2"], font=FONT_BODY,
                 padx=16).pack(side="right")
        tk.Frame(self, bg=C["accent"], height=2).pack(fill="x")

    # ── Left panel ───────────────────────────────────────────────────────

    def _build_left(self, parent):
        vsb = tk.Scrollbar(parent, orient="vertical")
        vsb.pack(side="right", fill="y")
        canvas = tk.Canvas(parent, bg=C["bg"], highlightthickness=0,
                           yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.configure(command=canvas.yview)

        inner = tk.Frame(canvas, bg=C["bg"])
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(win_id, width=e.width)

        canvas.bind("<Configure>", _on_configure)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        def _scroll(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _scroll))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        # ── Mode tabs: Làm phim AI | Bán hàng AI ──
        self._build_main_mode_tabs(inner)

        # ── Mode-specific content (switched by _switch_main_mode) ──
        self._mode_content = tk.Frame(inner, bg=C["bg"])
        self._mode_content.pack(fill="x")

        # ── FILM AI frame ────────────────────────────────────────────
        self.frame_film = tk.Frame(self._mode_content, bg=C["bg"])

        self._step_indicator(self.frame_film, 1, "KỊCH BẢN")
        self._build_batch_section(self.frame_film)

        self._step_indicator(self.frame_film, 2, "NHÂN VẬT")
        self._build_character_section(self.frame_film)

        self._step_indicator(self.frame_film, 3, "CÀI ĐẶT VIDEO")
        self._build_video_settings_card(self.frame_film, show_tts=True, show_duration=True)

        self.frame_film.pack(fill="x")  # visible by default

        # ── SALES AI frame ───────────────────────────────────────────
        self.frame_sales_wrap = self._build_sales_section(self._mode_content)
        # (not packed — shown when tab switches to sales)

        # ── Kết nối Grok (collapsible, always below both modes) ──────
        self._build_grok_section(inner)

    def _build_main_mode_tabs(self, parent):
        frame = tk.Frame(parent, bg=C["bg3"],
                         highlightthickness=1, highlightbackground=C["border"])
        frame.pack(fill="x", pady=(0, 6))

        self._btn_mode_film = tk.Button(
            frame, text="🎬  Làm phim AI",
            bg=C["tab_act"], fg="white", font=FONT_BOLD,
            relief="flat", padx=14, pady=6, cursor="hand2",
            activebackground=C["accent2"],
            command=lambda: self._switch_main_mode("film"),
        )
        self._btn_mode_film.pack(side="left", padx=(6, 2), pady=4)

        self._btn_mode_sales = tk.Button(
            frame, text="🛍  Bán hàng AI",
            bg=C["tab_inact"], fg=C["text2"], font=FONT_BOLD,
            relief="flat", padx=14, pady=6, cursor="hand2",
            activebackground=C["border"],
            command=lambda: self._switch_main_mode("sales"),
        )
        self._btn_mode_sales.pack(side="left", padx=(0, 6), pady=4)

        tk.Label(frame, text="Chọn chế độ sản xuất",
                 bg=C["bg3"], fg=C["text2"], font=("Segoe UI", 7)).pack(side="right", padx=10)

    def _switch_main_mode(self, mode: str):
        self.var_main_mode.set(mode)
        if mode == "film":
            # Left panel
            self.frame_sales_wrap.pack_forget()
            self.frame_film.pack(fill="x")
            # Right panel
            if hasattr(self, "frame_right_sales"):
                self.frame_right_sales.pack_forget()
            if hasattr(self, "frame_right_film"):
                self.frame_right_film.pack(fill="x")
            # Tabs
            self._btn_mode_film.config(bg=C["tab_act"], fg="white")
            self._btn_mode_sales.config(bg=C["tab_inact"], fg=C["text2"])
        else:
            # Left panel
            self.frame_film.pack_forget()
            self.frame_sales_wrap.pack(fill="x")
            # Right panel
            if hasattr(self, "frame_right_film"):
                self.frame_right_film.pack_forget()
            if hasattr(self, "frame_right_sales"):
                self.frame_right_sales.pack(fill="x")
                self._sales_refresh_results()
            # Tabs
            self._btn_mode_film.config(bg=C["tab_inact"], fg=C["text2"])
            self._btn_mode_sales.config(bg=C["tab_act"], fg="white")

    def _build_mode_tabs(self, parent):
        frame = tk.Frame(parent, bg=C["bg"])
        frame.pack(fill="x", pady=(0, 8))

        tk.Label(frame, text="CHẾ ĐỘ:", bg=C["bg"], fg=C["text2"],
                 font=FONT_BOLD).pack(side="left", padx=(0, 8))

        self.btn_tab_script = tk.Button(
            frame, text="📋  Nhập kịch bản",
            bg=C["tab_act"], fg="white", font=FONT_BOLD,
            relief="flat", padx=14, pady=5, cursor="hand2",
            command=lambda: self._set_mode("script"),
        )
        self.btn_tab_script.pack(side="left", padx=(0, 4))

        self.btn_tab_chatgpt = tk.Button(
            frame, text="🤖  ChatGPT viết",
            bg=C["tab_inact"], fg=C["text2"], font=FONT_BOLD,
            relief="flat", padx=14, pady=5, cursor="hand2",
            command=lambda: self._set_mode("chatgpt"),
        )
        self.btn_tab_chatgpt.pack(side="left", padx=(0, 4))

        self.btn_tab_batch = tk.Button(
            frame, text="📦  Hàng loạt",
            bg=C["tab_inact"], fg=C["text2"], font=FONT_BOLD,
            relief="flat", padx=14, pady=5, cursor="hand2",
            command=lambda: self._set_mode("batch"),
        )
        self.btn_tab_batch.pack(side="left")

    def _build_script_section(self, parent) -> tk.Frame:
        card = self._card(parent, "📋  Kịch bản  (dán vào / gõ trực tiếp)")

        hint = tk.Label(card,
            text="Hỗ trợ 2 format: (1) Mỗi dòng = 1 cảnh ngắn  |  (2) Kịch bản phim: các cảnh phân cách bởi ───",
            bg=C["bg2"], fg=C["text2"], font=("Segoe UI", 8), padx=10)
        hint.pack(anchor="w", pady=(0, 4))

        # Textarea lớn cho kịch bản
        ta_frame = tk.Frame(card, bg=C["bg2"])
        ta_frame.pack(fill="both", expand=True, padx=8, pady=(0, 6))

        self.script_text = tk.Text(
            ta_frame, bg=C["inputbg"], fg=C["text"],
            font=FONT_MONO, wrap="word", relief="flat",
            insertbackground=C["text"],
            selectbackground=C["accent"],
            height=14, padx=6, pady=4,
            highlightthickness=1, highlightbackground=C["border"],
            highlightcolor=C["accent"],
        )
        self.script_text.pack(side="left", fill="both", expand=True)
        ta_vsb = tk.Scrollbar(ta_frame, command=self.script_text.yview, bg=C["bg3"])
        ta_vsb.pack(side="right", fill="y")
        self.script_text.configure(yscrollcommand=ta_vsb.set)

        # Placeholder
        placeholder = (
            "Dán kịch bản vào đây...\n\n"
            "Ví dụ:\n"
            "1. Cô gái đứng trước cửa sổ nhìn mưa, vẻ mặt buồn\n"
            "2. Cô gái lật xem tập ảnh cũ, ánh mắt nhớ nhung\n"
            "3. Điện thoại đổ chuông, cô gái nhìn màn hình do dự\n"
            "4. Cô gái nhấc máy, mỉm cười nhẹ\n"
            "5. Cận cảnh khuôn mặt cô gái, ánh mắt hy vọng"
        )
        self.script_text.insert("1.0", placeholder)
        self.script_text.config(fg=C["text2"])

        def _focus_in(e):
            if self.script_text.get("1.0", "end-1c") == placeholder.strip():
                self.script_text.delete("1.0", "end")
                self.script_text.config(fg=C["text"])

        def _focus_out(e):
            if not self.script_text.get("1.0", "end-1c").strip():
                self.script_text.insert("1.0", placeholder)
                self.script_text.config(fg=C["text2"])

        self.script_text.bind("<FocusIn>",  _focus_in)
        self.script_text.bind("<FocusOut>", _focus_out)

        # Nút import từ file
        btn_row = tk.Frame(card, bg=C["bg2"])
        btn_row.pack(fill="x", padx=8, pady=(0, 8))
        self._small_btn(btn_row, "📂  Import .txt/.md", self._import_script_file).pack(side="left")
        self._small_btn(btn_row, "🔍  Preview cảnh", self._preview_scenes).pack(side="left", padx=(6, 0))
        self._small_btn(btn_row, "📖  Mở rộng", lambda: self._open_text_popup(
            "📋 Kịch bản — Xem / Sửa đầy đủ",
            get_fn=lambda: self.script_text.get("1.0", "end-1c"),
            set_fn=lambda v: (self.script_text.delete("1.0", "end"),
                              self.script_text.insert("1.0", v),
                              self.script_text.config(fg=C["text"])),
        )).pack(side="left", padx=(6, 0))
        self._small_btn(btn_row, "🗑  Xóa", lambda: self.script_text.delete("1.0", "end")).pack(side="right")

        # Preview label
        self.lbl_scene_count = tk.Label(
            card, text="",
            bg=C["bg2"], fg=C["green"], font=("Segoe UI", 8), padx=10
        )
        self.lbl_scene_count.pack(anchor="w", pady=(0, 6))

        return card

    def _build_chatgpt_section(self, parent) -> tk.Frame:
        card = self._card(parent, "🤖  ChatGPT viết kịch bản")
        self._labeled_entry(card, "Mô tả sản phẩm *", self.var_product)
        tk.Label(card, text="  Số cảnh:", bg=C["bg2"], fg=C["text2"],
                 font=FONT_BODY).pack(anchor="w", padx=10)
        row = tk.Frame(card, bg=C["bg2"])
        row.pack(fill="x", padx=10, pady=(0, 8))
        self._spin(row, "Số cảnh:", self.var_scene_count, 2, 10)
        return card

    def _build_character_section(self, parent):
        card = self._card(parent, "👤  Nhân vật")

        # ── Layout 2 cột: preview ảnh (trái) | form (phải) ──────────────────
        body = tk.Frame(card, bg=C["bg2"])
        body.pack(fill="x", padx=10, pady=(6, 8))

        # Cột trái — thumbnail preview
        left_col = tk.Frame(body, bg=C["bg2"])
        left_col.pack(side="left", padx=(0, 10))

        self._char_thumb = tk.Label(
            left_col, bg="#0a0a1a", width=10, height=6,
            cursor="hand2", relief="flat",
            highlightthickness=1, highlightbackground=C["border"],
        )
        self._char_thumb.pack()
        self._char_thumb.bind("<Button-1>", lambda e: self._char_img_open_viewer())
        tk.Label(left_col, text="Nhấn để xem", bg=C["bg2"],
                 fg=C["text2"], font=("Segoe UI", 6)).pack(pady=(2, 0))

        # Cột phải — inputs
        right_col = tk.Frame(body, bg=C["bg2"])
        right_col.pack(side="left", fill="both", expand=True)

        # Dòng đường dẫn ảnh
        tk.Label(right_col, text="Ảnh nhân vật", bg=C["bg2"], fg=C["text2"],
                 font=FONT_BOLD).pack(anchor="w")
        path_row = tk.Frame(right_col, bg=C["bg2"])
        path_row.pack(fill="x", pady=(2, 4))
        tk.Entry(path_row, textvariable=self.var_char_img, bg=C["inputbg"], fg=C["text"],
                 insertbackground=C["text"], font=("Segoe UI", 8), relief="flat",
                 highlightthickness=1, highlightbackground=C["border"]).pack(
                     side="left", fill="x", expand=True, ipady=3)

        def _pick_file():
            p = filedialog.askopenfilename(
                title="Chọn ảnh nhân vật (1 ảnh dùng cho tất cả cảnh)",
                filetypes=[("Images", "*.png *.jpg *.jpeg *.webp")]
            )
            if p:
                self.var_char_img.set(p)

        def _pick_folder():
            p = filedialog.askdirectory(
                title="Chọn thư mục ảnh (1.jpg=cảnh1, 2.jpg=cảnh2, ...)"
            )
            if p:
                self.var_char_img.set(p)

        tk.Button(path_row, text="📁", bg=C["accent"], fg="white", font=FONT_BOLD,
                  relief="flat", padx=6, cursor="hand2",
                  command=_pick_file).pack(side="left", padx=(4, 1))
        tk.Button(path_row, text="🗂", bg=C["bg3"], fg=C["text2"], font=FONT_BOLD,
                  relief="flat", padx=6, cursor="hand2",
                  command=_pick_folder).pack(side="left", padx=(1, 0))

        tk.Label(right_col,
                 text="📁 = 1 ảnh chung  |  🗂 = thư mục (1.jpg, 2.jpg, 3.jpg…)",
                 bg=C["bg2"], fg=C["text2"], font=("Segoe UI", 7)).pack(anchor="w")

        # Dòng mô tả
        tk.Label(right_col, text="Mô tả nhân vật", bg=C["bg2"], fg=C["text2"],
                 font=FONT_BOLD).pack(anchor="w", pady=(6, 2))

        desc_frame = tk.Frame(right_col, bg=C["bg2"])
        desc_frame.pack(fill="x")
        desc_txt = tk.Text(desc_frame, height=3, bg=C["inputbg"], fg=C["text"],
                           insertbackground=C["text"], font=FONT_BODY, relief="flat",
                           highlightthickness=1, highlightbackground=C["border"],
                           highlightcolor=C["accent"], wrap="word")
        desc_txt.pack(side="left", fill="x", expand=True, ipady=2)
        if self.var_char_desc.get():
            desc_txt.insert("1.0", self.var_char_desc.get())

        _save_after_id = [None]

        def _sync_var(*_):
            self.var_char_desc.set(desc_txt.get("1.0", "end-1c"))

        def _on_desc_change(*_):
            _sync_var()
            if _save_after_id[0]:
                self.after_cancel(_save_after_id[0])
            _save_after_id[0] = self.after(2000, _auto_save_desc)

        def _auto_save_desc():
            _sync_var()
            val = self.var_char_desc.get()
            config.update_user_config("char_desc", val)
            self._save_settings()
            if hasattr(self, "_lbl_desc_saved"):
                self._lbl_desc_saved.config(text="✓ Đã lưu", fg=C["green"])
                self.after(3000, lambda: self._lbl_desc_saved.config(text="", fg=C["text2"]))

        desc_txt.bind("<KeyRelease>", _on_desc_change)

        def _var_to_text(*_):
            cur = desc_txt.get("1.0", "end-1c")
            new = self.var_char_desc.get()
            if cur != new:
                desc_txt.delete("1.0", "end")
                desc_txt.insert("1.0", new)
        self.var_char_desc.trace_add("write", _var_to_text)
        self._desc_txt_widget = desc_txt

        # Nút hành động
        btn_row = tk.Frame(right_col, bg=C["bg2"])
        btn_row.pack(fill="x", pady=(4, 0))
        tk.Button(btn_row, text="💾 Lưu", font=FONT_BOLD,
                  bg=C["accent"], fg="white", relief="flat", padx=10, pady=2,
                  cursor="hand2", activebackground=C["accent2"],
                  command=_auto_save_desc).pack(side="left")
        tk.Button(btn_row, text="📖 Mở rộng", font=FONT_BODY,
                  bg=C["bg3"], fg=C["text"], relief="flat", padx=8, pady=2,
                  cursor="hand2", activebackground=C["border"],
                  command=lambda: self._open_text_popup(
                      "👤 Mô tả nhân vật — Xem / Sửa đầy đủ",
                      get_fn=lambda: self.var_char_desc.get(),
                      set_fn=lambda v: (self.var_char_desc.set(v), _auto_save_desc()),
                  )).pack(side="left", padx=(4, 0))
        self._lbl_desc_saved = tk.Label(btn_row, text="", bg=C["bg2"],
                                        fg=C["text2"], font=("Segoe UI", 7))
        self._lbl_desc_saved.pack(side="left", padx=6)

        # Trace var_char_img → cập nhật thumbnail
        self.var_char_img.trace_add("write", lambda *_: self.after(100, self._update_char_thumb))
        self.after(300, self._update_char_thumb)  # load lần đầu

        card.pack(fill="x", pady=(0, 8))

    def _build_sales_section(self, parent) -> tk.Frame:
        wrap = tk.Frame(parent, bg=C["bg"])

        # ── BƯỚC 1: PROMPT ──────────────────────────────────────────────
        self._step_indicator(wrap, 1, "PROMPT VIDEO")
        prompt_card = self._card(wrap, "📝  Prompt mặc định / prompt mẫu")
        tk.Label(prompt_card,
                 text="Khi thêm cụm, có thể dán 1 prompt dùng chung hoặc nhiều prompt theo từng ảnh sản phẩm.",
                 bg=C["bg2"], fg=C["text2"], font=("Segoe UI", 8),
                 padx=10, wraplength=380, justify="left").pack(anchor="w", pady=(4, 2))

        p_frame = tk.Frame(prompt_card, bg=C["bg2"])
        p_frame.pack(fill="x", padx=8, pady=(0, 2))
        self._sales_prompt_txt = tk.Text(
            p_frame, height=4, bg=C["inputbg"], fg=C["text"],
            font=FONT_BODY, relief="flat", wrap="word",
            insertbackground=C["text"],
            highlightthickness=1, highlightbackground=C["border"],
            highlightcolor=C["accent"], padx=4, pady=4,
        )
        self._sales_prompt_txt.pack(side="left", fill="x", expand=True)
        p_sb = tk.Scrollbar(p_frame, command=self._sales_prompt_txt.yview, bg=C["bg3"])
        p_sb.pack(side="right", fill="y")
        self._sales_prompt_txt.configure(yscrollcommand=p_sb.set)

        p_btn_row = tk.Frame(prompt_card, bg=C["bg2"])
        p_btn_row.pack(fill="x", padx=8, pady=(2, 6))
        self._small_btn(p_btn_row, "📖 Mở rộng", lambda: self._open_text_popup(
            "🛍 Prompt Bán hàng AI — Xem / Sửa đầy đủ",
            get_fn=lambda: self._sales_prompt_txt.get("1.0", "end-1c"),
            set_fn=lambda v: (self._sales_prompt_txt.delete("1.0", "end"),
                              self._sales_prompt_txt.insert("1.0", v)),
        )).pack(side="left")
        self._small_btn(p_btn_row, "🗑 Xóa prompt",
                        lambda: self._sales_prompt_txt.delete("1.0", "end")).pack(side="left", padx=(4, 0))
        self._small_btn(p_btn_row, "⚡ Mẫu bán hàng",
                        self._sales_insert_default_prompt).pack(side="left", padx=(4, 0))
        self._small_btn(p_btn_row, "➕ Điền prompt trống",
                        self._sales_fill_missing_prompts).pack(side="left", padx=(4, 0))

        # Campaign controls
        campaign_card = self._card(wrap, "🎯  Chiến dịch bán hàng")
        row = tk.Frame(campaign_card, bg=C["bg2"])
        row.pack(fill="x", padx=10, pady=(6, 4))

        tk.Label(row, text="Mẫu video:", bg=C["bg2"], fg=C["text2"],
                 font=FONT_BODY, width=12, anchor="w").pack(side="left")
        cb_preset = ttk.Combobox(
            row, textvariable=self.var_sales_preset, values=sales_preset_names(),
            state="readonly", width=18, font=("Segoe UI", 8),
        )
        cb_preset.pack(side="left", padx=(0, 8))

        tk.Label(row, text="Mục tiêu:", bg=C["bg2"], fg=C["text2"],
                 font=FONT_BODY).pack(side="left", padx=(0, 4))
        cb_goal = ttk.Combobox(
            row, textvariable=self.var_sales_goal, values=sales_goal_names(),
            state="readonly", width=15, font=("Segoe UI", 8),
        )
        cb_goal.pack(side="left", padx=(0, 8))

        tk.Checkbutton(
            row, text="Tự tạo prompt khi thiếu", variable=self.var_sales_auto_prompt,
            bg=C["bg2"], fg=C["text2"], selectcolor=C["bg3"],
            activebackground=C["bg2"], activeforeground=C["text"],
            font=("Segoe UI", 8), cursor="hand2",
        ).pack(side="left")

        row2 = tk.Frame(campaign_card, bg=C["bg2"])
        row2.pack(fill="x", padx=10, pady=(0, 4))
        self._labeled_entry(row2, "Tệp khách", self.var_sales_audience)

        row3 = tk.Frame(campaign_card, bg=C["bg2"])
        row3.pack(fill="x", padx=10, pady=(0, 4))
        self._labeled_entry(row3, "Ưu đãi", self.var_sales_offer)

        row4 = tk.Frame(campaign_card, bg=C["bg2"])
        row4.pack(fill="x", padx=10, pady=(0, 8))
        self._labeled_entry(row4, "CTA", self.var_sales_cta)

        # ── BƯỚC 2: CỤM ẢNH ─────────────────────────────────────────────
        self._step_indicator(wrap, 2, "CỤM AFF → VIDEO")
        cluster_card = self._card(wrap, "🖼️  Cụm aff  (1 nhân vật + nhiều sản phẩm)")

        tv_wrap = tk.Frame(cluster_card, bg=C["bg2"])
        tv_wrap.pack(fill="both", padx=8, pady=(4, 4))

        cols = ("idx", "name", "count", "final", "status", "time")
        self.sales_tree = ttk.Treeview(tv_wrap, columns=cols, show="headings",
                                        height=6, style="Batch.Treeview")
        self.sales_tree.heading("idx",    text="#")
        self.sales_tree.heading("name",   text="Tên cụm")
        self.sales_tree.heading("count",  text="Sản phẩm")
        self.sales_tree.heading("final",  text="Video")
        self.sales_tree.heading("status", text="Trạng thái")
        self.sales_tree.heading("time",   text="Thời gian")
        self.sales_tree.column("idx",    width=30,  anchor="center", stretch=False)
        self.sales_tree.column("name",   width=130, anchor="w")
        self.sales_tree.column("count",  width=58,  anchor="center", stretch=False)
        self.sales_tree.column("final",  width=48,  anchor="center", stretch=False)
        self.sales_tree.column("status", width=90,  anchor="center", stretch=False)
        self.sales_tree.column("time",   width=60,  anchor="center", stretch=False)
        self.sales_tree.pack(side="left", fill="both", expand=True)

        tv_vsb = ttk.Scrollbar(tv_wrap, orient="vertical", command=self.sales_tree.yview)
        tv_vsb.pack(side="right", fill="y")
        self.sales_tree.configure(yscrollcommand=tv_vsb.set)
        self.sales_tree.tag_configure("done",    foreground=C["green"])
        self.sales_tree.tag_configure("failed",  foreground=C["red"])
        self.sales_tree.tag_configure("running", foreground=C["yellow"])
        self.sales_tree.tag_configure("stopped", foreground=C["yellow"])
        self.sales_tree.tag_configure("pending", foreground=C["text2"])
        self.sales_tree.bind("<Double-Button-1>", self._sales_view_cluster_images)

        btn_row = tk.Frame(cluster_card, bg=C["bg2"])
        btn_row.pack(fill="x", padx=8, pady=(0, 4))
        self._small_btn(btn_row, "➕ Thêm cụm aff",     self._sales_add_cluster).pack(side="left")
        self._small_btn(btn_row, "✏ Sửa cụm",          self._sales_view_cluster_images).pack(side="left", padx=(4, 0))
        self._small_btn(btn_row, "🖼 Thêm sản phẩm",    self._sales_add_images).pack(side="left", padx=(4, 0))
        self._small_btn(btn_row, "🗑 Xóa cụm",          self._sales_remove_cluster).pack(side="left", padx=(4, 0))
        self._small_btn(btn_row, "↺ Reset",              self._sales_reset_status).pack(side="left", padx=(4, 0))

        # ── Hàng nút TỰ ĐỘNG HÓA HÀNG LOẠT (aff seller >50sp/ngày) ──
        btn_row2 = tk.Frame(cluster_card, bg=C["bg2"])
        btn_row2.pack(fill="x", padx=8, pady=(0, 4))
        self._small_btn(btn_row2, "⚡ Nhanh từ thư mục",  self._sales_quick_from_folder).pack(side="left")
        self._small_btn(btn_row2, "📊 Import CSV",       self._sales_import_csv).pack(side="left", padx=(4, 0))
        self._small_btn(btn_row2, "📋 Nhân bản cụm",     self._sales_duplicate_cluster).pack(side="left", padx=(4, 0))
        self._small_btn(btn_row2, "✏ Sửa hàng loạt",    self._sales_bulk_edit_prompts).pack(side="left", padx=(4, 0))

        btn_row3 = tk.Frame(cluster_card, bg=C["bg2"])
        btn_row3.pack(fill="x", padx=8, pady=(0, 4))
        self._small_btn(btn_row3, "💾 Lưu chiến dịch JSON",  self._sales_save_campaign_json).pack(side="left")
        self._small_btn(btn_row3, "📂 Tải chiến dịch JSON",  self._sales_load_campaign_json).pack(side="left", padx=(4, 0))
        self._small_btn(btn_row3, "📝 Mẫu CSV",              self._sales_export_csv_template).pack(side="left", padx=(4, 0))

        self.lbl_sales_count = tk.Label(cluster_card, text="0 cụm · 0 sản phẩm · 0 video aff",
                                         bg=C["bg2"], fg=C["text2"],
                                         font=("Segoe UI", 8), padx=10)
        self.lbl_sales_count.pack(anchor="w", pady=(0, 6))

        # ── BƯỚC 3: CÀI ĐẶT VIDEO ───────────────────────────────────────
        self._step_indicator(wrap, 3, "CÀI ĐẶT VIDEO")
        sales_opt_card = self._card(wrap, "🎛️  Cài đặt aff")
        opt_row = tk.Frame(sales_opt_card, bg=C["bg2"])
        opt_row.pack(fill="x", padx=10, pady=(6, 4))
        self._spin(opt_row, "Clip/video:", self.var_sales_clips_per_video, 1, 20)
        self._spin(opt_row, "Tab song song:", self.var_sales_parallel_tabs, 1, 6)
        tk.Label(
            sales_opt_card,
            text="Ví dụ Clip/video = 3: clip 1-3 ghép thành video aff 1, clip 4-6 ghép thành video aff 2.",
            bg=C["bg2"], fg=C["text2"], font=("Segoe UI", 7),
            padx=10, wraplength=420, justify="left",
        ).pack(anchor="w", pady=(0, 6))
        self._build_video_settings_card(wrap, show_tts=False, show_duration=False)

        return wrap

    # ── Sales cluster management ──────────────────────────────────────────

    def _sales_campaign_settings(self) -> dict:
        return {
            "sales_preset":   self.var_sales_preset.get() or "TikTok Shop",
            "sales_goal":     self.var_sales_goal.get() or "Chốt đơn",
            "sales_audience": self.var_sales_audience.get().strip(),
            "sales_offer":    self.var_sales_offer.get().strip(),
            "sales_cta":      self.var_sales_cta.get().strip() or DEFAULT_CTA,
        }

    def _sales_build_default_prompt(self, product_image_path: str = "") -> str:
        s = self._sales_campaign_settings()
        return build_default_sales_prompt(
            product_image_path=product_image_path,
            preset=s["sales_preset"],
            goal=s["sales_goal"],
            audience=s["sales_audience"],
            offer=s["sales_offer"],
            cta=s["sales_cta"],
        )

    def _sales_insert_default_prompt(self):
        prompt = self._sales_build_default_prompt("")
        self._sales_prompt_txt.delete("1.0", "end")
        self._sales_prompt_txt.insert("1.0", prompt)

    def _sales_fill_missing_prompts(self):
        filled = 0
        campaign = self._sales_campaign_settings()
        for cluster in self._sales_clusters:
            items = self._sales_get_items(cluster, "")
            changed = False
            for item in items:
                if not (item.get("prompt") or "").strip():
                    item["prompt"] = self._sales_build_default_prompt(item.get("product_image", ""))
                    filled += 1
                    changed = True
                item.update(campaign)
            if changed:
                cluster["items"] = items
                cluster["status"] = "pending"
        if filled:
            self._sales_refresh_tree()
            self._log("INFO", f"Đã điền prompt bán hàng cho {filled} sản phẩm.")
        else:
            messagebox.showinfo("Prompt", "Không có sản phẩm nào đang thiếu prompt.")

    def _sales_default_prompt(self) -> str:
        return self._sales_prompt_txt.get("1.0", "end-1c").strip()

    def _sales_split_prompts(self, text: str) -> list[str]:
        """Tách prompt theo format rõ ràng, giữ nguyên prompt dài nhiều đoạn."""
        raw = (text or "").strip()
        if not raw:
            return []

        import re as _re
        sep = r"(?m)^\s*(?:-{3,}|={3,}|#{3,}|PROMPT\s*\d+\s*:?)\s*$"
        blocks = [b.strip() for b in _re.split(sep, raw) if b.strip()]
        if len(blocks) > 1:
            return blocks

        raw_lines = raw.splitlines()
        lines = [ln.strip() for ln in raw_lines if ln.strip()]
        has_blank = any(not ln.strip() for ln in raw_lines)
        looks_like_scene_list = any(
            _re.match(r"^\s*(?:[-*•]|\d+[.)])\s+", ln) for ln in lines
        )
        short_single_line_prompts = all(len(ln) <= 260 for ln in lines)
        if len(lines) > 1 and not has_blank and short_single_line_prompts and not looks_like_scene_list:
            return lines

        return [raw]

    def _sales_make_items(self, product_paths: list[str], prompt_text: str) -> list[dict]:
        prompts = self._sales_split_prompts(prompt_text)
        campaign = self._sales_campaign_settings()
        items = []
        for i, p in enumerate(product_paths):
            item_prompt = ""
            if prompts:
                item_prompt = prompts[i] if i < len(prompts) else prompts[-1]
            elif self.var_sales_auto_prompt.get():
                item_prompt = self._sales_build_default_prompt(str(p))
            item = {
                "product_image": str(p),
                "prompt": item_prompt,
            }
            item.update(campaign)
            items.append(item)
        return items

    def _sales_get_items(self, cluster: dict, default_prompt: str = "") -> list[dict]:
        """Trả về items mới, đồng thời migrate cụm cũ chỉ có images."""
        items = cluster.get("items")
        if isinstance(items, list) and items:
            normalized = []
            for item in items:
                if isinstance(item, dict):
                    product_image = item.get("product_image") or item.get("image") or ""
                    prompt = item.get("prompt") or item.get("video_prompt") or default_prompt
                    extra = {
                        k: item.get(k)
                        for k in (
                            "sales_preset", "sales_goal", "sales_audience",
                            "sales_offer", "sales_cta", "duration",
                        )
                        if item.get(k) not in (None, "")
                    }
                else:
                    product_image = str(item)
                    prompt = default_prompt
                    extra = {}
                if product_image:
                    normalized_item = {
                        "product_image": product_image,
                        "prompt": prompt,
                    }
                    normalized_item.update(extra)
                    normalized.append(normalized_item)
            cluster["items"] = normalized
            return normalized

        legacy_images = cluster.get("images", []) or []
        campaign = self._sales_campaign_settings()
        migrated = [
            {"product_image": str(p), "prompt": default_prompt, **campaign}
            for p in legacy_images
        ]
        if migrated:
            cluster["items"] = migrated
        return migrated

    def _sales_cluster_char(self, cluster: dict) -> str:
        return cluster.get("character_image") or cluster.get("char_image") or ""

    def _sales_prepare_items_for_run(self, cluster: dict, default_prompt: str = "") -> list[dict]:
        campaign = self._sales_campaign_settings()
        prepared = []
        for item in self._sales_get_items(cluster, default_prompt):
            merged = dict(item)
            merged.update(campaign)
            if not (merged.get("prompt") or "").strip() and self.var_sales_auto_prompt.get():
                merged["prompt"] = self._sales_build_default_prompt(
                    merged.get("product_image", "")
                )
            prepared.append(merged)
        cluster["items"] = prepared
        return prepared

    def _sales_expected_final_count(self, clip_count: int) -> int:
        per_video = max(1, int(self.var_sales_clips_per_video.get() or 1))
        return (clip_count + per_video - 1) // per_video

    def _sales_prompt_dialog(
        self,
        title: str,
        product_paths: list[str],
        initial: str,
        character_path: str = "",
    ) -> Optional[str]:
        result = {"text": None}
        dlg = tk.Toplevel(self)
        dlg.title(title)
        dlg.geometry("940x600")
        dlg.configure(bg=C["bg"])
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(True, True)

        tk.Label(
            dlg,
            text=f"{len(product_paths)} ảnh sản phẩm — kiểm tra ảnh nhân vật/sản phẩm trước khi lưu prompt",
            bg=C["bg"], fg=C["accent3"], font=FONT_H2, padx=12, pady=8,
        ).pack(anchor="w")
        tk.Label(
            dlg,
            text="Nhiều prompt: mỗi dòng là 1 prompt ngắn, hoặc dùng dòng --- để ngăn prompt dài nhiều đoạn.",
            bg=C["bg"], fg=C["text2"], font=("Segoe UI", 8), padx=12,
        ).pack(anchor="w")

        body = tk.Frame(dlg, bg=C["bg"])
        body.pack(fill="both", expand=True, padx=10, pady=8)

        preview_col = tk.Frame(body, bg=C["bg"])
        preview_col.pack(side="left", fill="y", padx=(0, 10))

        tk.Label(preview_col, text="Ảnh nhân vật", bg=C["bg"], fg=C["text2"],
                 font=FONT_BOLD).pack(anchor="w")
        char_thumb = tk.Label(
            preview_col, bg="#0a0a1a", width=18, height=8, relief="flat",
            cursor="hand2", highlightthickness=1, highlightbackground=C["border"],
        )
        char_thumb.pack(fill="x", pady=(2, 3))
        self._set_image_preview(char_thumb, character_path, (150, 130), "Chưa chọn\nnhân vật")
        char_thumb.bind("<Button-1>", lambda e: self._open_image_file(character_path))
        tk.Label(
            preview_col,
            text=Path(character_path).name if character_path else "Không dùng nhân vật",
            bg=C["bg"], fg=C["text2"], font=("Segoe UI", 7),
            wraplength=180, justify="left",
        ).pack(anchor="w", pady=(0, 8))

        tk.Label(preview_col, text="Sản phẩm đang chọn", bg=C["bg"], fg=C["text2"],
                 font=FONT_BOLD).pack(anchor="w")
        product_thumb = tk.Label(
            preview_col, bg="#0a0a1a", width=18, height=8, relief="flat",
            cursor="hand2", highlightthickness=1, highlightbackground=C["border"],
        )
        product_thumb.pack(fill="x", pady=(2, 3))
        product_name_lbl = tk.Label(
            preview_col, text="", bg=C["bg"], fg=C["text2"],
            font=("Segoe UI", 7), wraplength=180, justify="left",
        )
        product_name_lbl.pack(anchor="w", pady=(0, 8))

        tk.Label(preview_col, text="Thứ tự ảnh sản phẩm", bg=C["bg"], fg=C["text2"],
                 font=FONT_BODY).pack(anchor="w")
        lb = tk.Listbox(preview_col, width=30, height=9, bg=C["inputbg"], fg=C["text"],
                        font=("Segoe UI", 8), relief="flat",
                        selectbackground=C["accent"], activestyle="none")
        lb.pack(fill="x", expand=False)
        for i, p in enumerate(product_paths, 1):
            lb.insert("end", f"{i:02d}. {Path(p).name}")

        def _selected_product_path() -> str:
            sel = list(lb.curselection())
            idx = sel[0] if sel else 0
            return product_paths[idx] if 0 <= idx < len(product_paths) else ""

        def _update_product_preview(_event=None):
            p = _selected_product_path()
            self._set_image_preview(product_thumb, p, (150, 130), "Chưa chọn\nsản phẩm")
            product_name_lbl.config(text=Path(p).name if p else "")

        lb.bind("<<ListboxSelect>>", _update_product_preview)
        product_thumb.bind("<Button-1>", lambda e: self._open_image_file(_selected_product_path()))
        if product_paths:
            lb.selection_set(0)
            lb.activate(0)
            _update_product_preview()

        txt_frame = tk.Frame(body, bg=C["bg"])
        txt_frame.pack(side="left", fill="both", expand=True)
        tk.Label(txt_frame, text="Prompt cho Grok", bg=C["bg"], fg=C["text2"],
                 font=FONT_BOLD).pack(anchor="w")
        sb = tk.Scrollbar(txt_frame, bg=C["bg3"])
        sb.pack(side="right", fill="y", pady=(20, 0))
        txt = tk.Text(
            txt_frame, bg=C["inputbg"], fg=C["text"], font=FONT_MONO,
            wrap="word", relief="flat", insertbackground=C["text"],
            selectbackground=C["accent"], padx=8, pady=6,
            highlightthickness=1, highlightbackground=C["border"],
            yscrollcommand=sb.set,
        )
        txt.pack(side="left", fill="both", expand=True, pady=(2, 0))
        sb.configure(command=txt.yview)
        if initial:
            txt.insert("1.0", initial)
        txt.focus_set()

        btn_row = tk.Frame(dlg, bg=C["bg"])
        btn_row.pack(fill="x", padx=10, pady=(0, 10))

        def _save():
            result["text"] = txt.get("1.0", "end-1c").strip()
            dlg.destroy()

        tk.Button(btn_row, text="💾 Lưu prompt", bg=C["accent"], fg="white",
                  font=FONT_BOLD, relief="flat", padx=14, pady=6, cursor="hand2",
                  activebackground=C["accent2"], command=_save).pack(side="left")
        def _insert_selected_template():
            p = _selected_product_path()
            prompt = self._sales_build_default_prompt(p)
            txt.delete("1.0", "end")
            txt.insert("1.0", prompt)

        def _insert_all_templates():
            prompts = [self._sales_build_default_prompt(p) for p in product_paths]
            txt.delete("1.0", "end")
            txt.insert("1.0", "\n---\n".join(prompts))

        tk.Button(btn_row, text="⚡ Mẫu ảnh đang chọn", bg=C["bg3"], fg=C["text"],
                  font=FONT_BODY, relief="flat", padx=12, pady=6, cursor="hand2",
                  activebackground=C["border"], command=_insert_selected_template).pack(side="left", padx=(6, 0))
        tk.Button(btn_row, text="⚡ Mẫu từng ảnh", bg=C["bg3"], fg=C["text"],
                  font=FONT_BODY, relief="flat", padx=12, pady=6, cursor="hand2",
                  activebackground=C["border"], command=_insert_all_templates).pack(side="left", padx=(6, 0))
        tk.Button(btn_row, text="✕ Hủy", bg=C["bg3"], fg=C["text"],
                  font=FONT_BODY, relief="flat", padx=14, pady=6, cursor="hand2",
                  activebackground=C["border"], command=dlg.destroy).pack(side="right")
        dlg.bind("<Control-s>", lambda e: _save())
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        self.wait_window(dlg)
        return result["text"]

    def _sales_add_cluster(self):
        char_path = filedialog.askopenfilename(
            title="Chọn 1 ảnh nhân vật cho cụm aff",
            filetypes=IMAGE_FILETYPES,
        )
        if not char_path:
            if not messagebox.askyesno(
                "Chưa chọn nhân vật",
                "Bạn chưa chọn ảnh nhân vật. Tiếp tục chỉ với ảnh sản phẩm?",
            ):
                return

        product_paths = filedialog.askopenfilenames(
            title="Chọn ảnh sản phẩm cho cụm mới (có thể chọn nhiều ảnh)",
            filetypes=IMAGE_FILETYPES,
        )
        if not product_paths:
            return

        prompt_text = self._sales_prompt_dialog(
            "Prompt cho cụm aff",
            list(product_paths),
            self._sales_default_prompt(),
            character_path=char_path,
        )
        if prompt_text is None:
            return

        cid = len(self._sales_clusters) + 1
        self._sales_clusters.append({
            "id":          cid,
            "name":        f"Cụm {cid}",
            "character_image": char_path,
            "items":       self._sales_make_items(list(product_paths), prompt_text),
            "status":      "pending",
            "done_count":  0,
            "clip_paths":   [],
            "output_paths": [],
            "elapsed_sec": 0.0,
            "error":       "",
        })
        self._sales_refresh_tree()
        self._sales_view_cluster_by_id(cid)

    def _sales_add_images(self):
        sel = self.sales_tree.selection()
        if not sel:
            messagebox.showinfo("Chưa chọn", "Hãy chọn một cụm trong danh sách trước.")
            return
        try:
            cid = int(sel[0])
        except ValueError:
            return
        cluster = next((c for c in self._sales_clusters if c["id"] == cid), None)
        if not cluster:
            return
        paths = filedialog.askopenfilenames(
            title=f"Thêm ảnh sản phẩm vào '{cluster['name']}'",
            filetypes=IMAGE_FILETYPES,
        )
        if paths:
            prompt_text = self._sales_prompt_dialog(
                f"Prompt cho ảnh mới — {cluster['name']}",
                list(paths),
                self._sales_default_prompt(),
                character_path=self._sales_cluster_char(cluster),
            )
            if prompt_text is None:
                return
            items = self._sales_get_items(cluster, self._sales_default_prompt())
            items.extend(self._sales_make_items(list(paths), prompt_text))
            cluster["items"] = items
            self._sales_mark_cluster_dirty(cluster)
            self._sales_refresh_tree()
            self._sales_view_cluster_by_id(cid)

    def _sales_remove_cluster(self):
        sel = self.sales_tree.selection()
        if not sel:
            return
        cids = set()
        for item in sel:
            try:
                cids.add(int(item))
            except ValueError:
                pass
        if not messagebox.askyesno("Xóa cụm", f"Xóa {len(cids)} cụm đã chọn?"):
            return
        self._sales_clusters = [c for c in self._sales_clusters if c["id"] not in cids]
        for i, c in enumerate(self._sales_clusters, 1):
            c["id"] = i
            c["name"] = f"Cụm {i}"
        self._sales_refresh_tree()

    def _sales_mark_cluster_dirty(self, cluster: dict):
        """Cluster đã đổi ảnh/prompt, cần chạy lại từ đầu để tránh kết quả cũ lẫn vào."""
        cluster["status"] = "pending"
        cluster["done_count"] = 0
        cluster["clip_paths"] = []
        cluster["output_paths"] = []
        cluster["elapsed_sec"] = 0.0
        cluster["error"] = ""

    def _sales_reset_status(self):
        for c in self._sales_clusters:
            if c.get("status") in ("failed", "done", "stopped"):
                self._sales_mark_cluster_dirty(c)
        self._sales_refresh_tree()

    def _sales_view_cluster_by_id(self, cid: int):
        self.sales_tree.selection_set(str(cid))
        self.sales_tree.focus(str(cid))
        self._sales_view_cluster_images()

    def _sales_view_cluster_images(self, event=None):
        sel = self.sales_tree.selection()
        if not sel:
            return
        try:
            cid = int(sel[0])
        except ValueError:
            return
        cluster = next((c for c in self._sales_clusters if c["id"] == cid), None)
        if not cluster:
            return
        items = self._sales_get_items(cluster, self._sales_default_prompt())
        dlg = tk.Toplevel(self)
        dlg.title(f"Cụm aff {cluster['name']}")
        dlg.geometry("980x640")
        dlg.configure(bg=C["bg"])
        dlg.transient(self)
        dlg.grab_set()
        title_lbl = tk.Label(dlg, text="",
                             bg=C["bg"], fg=C["accent3"], font=FONT_H2, padx=16, pady=8)
        title_lbl.pack(anchor="w")
        tk.Frame(dlg, bg=C["accent"], height=1).pack(fill="x")

        body = tk.Frame(dlg, bg=C["bg"])
        body.pack(fill="both", expand=True, padx=10, pady=8)

        # Cột trái: nhân vật + danh sách sản phẩm
        left = tk.Frame(body, bg=C["bg"])
        left.pack(side="left", fill="y", padx=(0, 10))

        tk.Label(left, text="Ảnh nhân vật", bg=C["bg"], fg=C["text2"],
                 font=FONT_BOLD).pack(anchor="w")
        char_thumb = tk.Label(
            left, bg="#0a0a1a", width=18, height=8, cursor="hand2",
            relief="flat", highlightthickness=1, highlightbackground=C["border"],
        )
        char_thumb.pack(fill="x", pady=(2, 3))
        char_name_lbl = tk.Label(left, text="", bg=C["bg"], fg=C["text2"],
                                 font=("Segoe UI", 7), wraplength=180, justify="left")
        char_name_lbl.pack(anchor="w", pady=(0, 6))

        char_btns = tk.Frame(left, bg=C["bg"])
        char_btns.pack(fill="x", pady=(0, 10))

        def _refresh_char_preview():
            cp = self._sales_cluster_char(cluster)
            self._set_image_preview(char_thumb, cp, (170, 140), "Chưa chọn\nnhân vật")
            char_name_lbl.config(text=Path(cp).name if cp else "Không dùng nhân vật")
            title_lbl.config(text=f"{cluster['name']}  -  {len(items)} sản phẩm")

        char_thumb.bind("<Button-1>", lambda e: self._open_image_file(self._sales_cluster_char(cluster)))

        def _change_char():
            p = filedialog.askopenfilename(
                title=f"Đổi ảnh nhân vật cho '{cluster['name']}'",
                filetypes=IMAGE_FILETYPES,
            )
            if p:
                cluster["character_image"] = p
                self._sales_mark_cluster_dirty(cluster)
                _refresh_char_preview()
                self._sales_refresh_tree()

        def _clear_char():
            if not self._sales_cluster_char(cluster):
                return
            if not messagebox.askyesno("Xóa ảnh nhân vật", "Xóa ảnh nhân vật khỏi cụm này?"):
                return
            cluster["character_image"] = ""
            self._sales_mark_cluster_dirty(cluster)
            _refresh_char_preview()
            self._sales_refresh_tree()

        self._small_btn(char_btns, "Đổi", _change_char).pack(side="left")
        self._small_btn(char_btns, "Xóa", _clear_char).pack(side="left", padx=(4, 0))

        tk.Label(left, text="Sản phẩm trong cụm", bg=C["bg"], fg=C["text2"],
                 font=FONT_BOLD).pack(anchor="w")
        lb_wrap = tk.Frame(left, bg=C["bg"])
        lb_wrap.pack(fill="both", expand=True)
        vsb = tk.Scrollbar(lb_wrap, bg=C["bg3"])
        vsb.pack(side="right", fill="y")
        lb = tk.Listbox(lb_wrap, width=34, height=16, bg=C["inputbg"], fg=C["text"], font=("Segoe UI", 8),
                        selectmode="extended",
                        relief="flat", selectbackground=C["accent"],
                        yscrollcommand=vsb.set, activestyle="none")
        lb.pack(side="left", fill="both", expand=True)
        vsb.configure(command=lb.yview)

        # Cột phải: preview sản phẩm + prompt
        right = tk.Frame(body, bg=C["bg"])
        right.pack(side="left", fill="both", expand=True)

        preview_row = tk.Frame(right, bg=C["bg"])
        preview_row.pack(fill="x")
        product_thumb = tk.Label(
            preview_row, bg="#0a0a1a", width=24, height=10, cursor="hand2",
            relief="flat", highlightthickness=1, highlightbackground=C["border"],
        )
        product_thumb.pack(side="left", padx=(0, 10))

        info_col = tk.Frame(preview_row, bg=C["bg"])
        info_col.pack(side="left", fill="x", expand=True)
        product_name_lbl = tk.Label(info_col, text="", bg=C["bg"], fg=C["accent3"],
                                    font=FONT_BOLD, wraplength=520, justify="left")
        product_name_lbl.pack(anchor="w")
        product_path_lbl = tk.Label(info_col, text="", bg=C["bg"], fg=C["text2"],
                                    font=("Segoe UI", 7), wraplength=520, justify="left")
        product_path_lbl.pack(anchor="w", pady=(3, 8))
        prompt_preview = tk.Text(
            info_col, height=7, bg=C["inputbg"], fg=C["text2"], font=("Consolas", 8),
            wrap="word", relief="flat", padx=6, pady=4,
            highlightthickness=1, highlightbackground=C["border"],
        )
        prompt_preview.pack(fill="x", expand=False)
        prompt_preview.configure(state="disabled")

        product_btns = tk.Frame(right, bg=C["bg"])
        product_btns.pack(fill="x", pady=(8, 0))

        def _prompt_preview(prompt: str) -> str:
            s = " ".join((prompt or "").split())
            return s[:64] + ("..." if len(s) > 64 else "")

        def _selected_index() -> Optional[int]:
            sel_idx = list(lb.curselection())
            if not sel_idx:
                return None
            idx = sel_idx[0]
            return idx if 0 <= idx < len(items) else None

        def _selected_item() -> Optional[dict]:
            idx = _selected_index()
            return items[idx] if idx is not None else None

        def _refresh_product_preview(_event=None):
            item = _selected_item()
            if not item:
                self._set_image_preview(product_thumb, "", (220, 170), "Chưa chọn\nsản phẩm")
                product_name_lbl.config(text="Chọn một sản phẩm để xem/sửa")
                product_path_lbl.config(text="")
                prompt_preview.configure(state="normal")
                prompt_preview.delete("1.0", "end")
                prompt_preview.configure(state="disabled")
                return

            p = item.get("product_image", "")
            self._set_image_preview(product_thumb, p, (220, 170), "Lỗi ảnh\nsản phẩm")
            product_name_lbl.config(text=Path(p).name if p else "(không có ảnh)")
            product_path_lbl.config(text=p)
            prompt_preview.configure(state="normal")
            prompt_preview.delete("1.0", "end")
            prompt_preview.insert("1.0", item.get("prompt", "") or "(chưa có prompt)")
            prompt_preview.configure(state="disabled")

        def _reload_list():
            lb.delete(0, "end")
            for i, item in enumerate(items, 1):
                img = Path(item.get("product_image", "")).name
                lb.insert("end", f"{i:02d} | {img} | {_prompt_preview(item.get('prompt', ''))}")
            title_lbl.config(text=f"{cluster['name']}  -  {len(items)} sản phẩm")
            if items and not lb.curselection():
                lb.selection_set(0)
                lb.activate(0)
            _refresh_product_preview()

        lb.bind("<<ListboxSelect>>", _refresh_product_preview)
        product_thumb.bind("<Button-1>", lambda e: self._open_image_file((_selected_item() or {}).get("product_image", "")))
        _reload_list()
        btn_row = tk.Frame(dlg, bg=C["bg"])
        btn_row.pack(fill="x", padx=10, pady=(0, 10))

        def _rename_cluster():
            pop = tk.Toplevel(dlg)
            pop.title("Đổi tên cụm")
            pop.configure(bg=C["bg"])
            pop.transient(dlg)
            pop.grab_set()
            tk.Label(pop, text="Tên cụm", bg=C["bg"], fg=C["text2"],
                     font=FONT_BODY, padx=10, pady=8).pack(anchor="w")
            v = tk.StringVar(value=cluster.get("name", ""))
            ent = tk.Entry(pop, textvariable=v, bg=C["inputbg"], fg=C["text"],
                           insertbackground=C["text"], font=FONT_BODY, relief="flat",
                           highlightthickness=1, highlightbackground=C["border"])
            ent.pack(fill="x", padx=10, ipady=4)
            def _save_name():
                name = v.get().strip()
                if name:
                    cluster["name"] = name
                    self._sales_mark_cluster_dirty(cluster)
                    _reload_list()
                    self._sales_refresh_tree()
                pop.destroy()
            b = tk.Frame(pop, bg=C["bg"])
            b.pack(fill="x", padx=10, pady=10)
            self._small_btn(b, "Lưu", _save_name).pack(side="left")
            self._small_btn(b, "Hủy", pop.destroy).pack(side="right")
            ent.focus_set()
            pop.bind("<Return>", lambda e: _save_name())
            pop.bind("<Escape>", lambda e: pop.destroy())

        def _edit_prompt():
            item = _selected_item()
            if not item:
                messagebox.showinfo("Chưa chọn", "Chọn 1 sản phẩm để sửa prompt.")
                return

            def _save_prompt(v):
                item["prompt"] = v.strip()
                cluster["items"] = items
                self._sales_mark_cluster_dirty(cluster)
                _reload_list()
                self._sales_refresh_tree()

            self._open_text_popup(
                f"Sửa prompt — {Path(item.get('product_image', '')).name}",
                get_fn=lambda: item.get("prompt", ""),
                set_fn=_save_prompt,
            )

        def _change_product_image():
            item = _selected_item()
            if not item:
                messagebox.showinfo("Chưa chọn", "Chọn 1 sản phẩm để đổi ảnh.")
                return
            p = filedialog.askopenfilename(
                title="Đổi ảnh sản phẩm",
                filetypes=IMAGE_FILETYPES,
            )
            if not p:
                return
            item["product_image"] = p
            if self.var_sales_auto_prompt.get() and not (item.get("prompt") or "").strip():
                item["prompt"] = self._sales_build_default_prompt(p)
            cluster["items"] = items
            self._sales_mark_cluster_dirty(cluster)
            _reload_list()
            self._sales_refresh_tree()

        def _add_products():
            paths = filedialog.askopenfilenames(
                title=f"Thêm ảnh sản phẩm vào '{cluster['name']}'",
                filetypes=IMAGE_FILETYPES,
            )
            if not paths:
                return
            prompt_text = self._sales_prompt_dialog(
                f"Prompt cho ảnh mới - {cluster['name']}",
                list(paths),
                self._sales_default_prompt(),
                character_path=self._sales_cluster_char(cluster),
            )
            if prompt_text is None:
                return
            items.extend(self._sales_make_items(list(paths), prompt_text))
            cluster["items"] = items
            self._sales_mark_cluster_dirty(cluster)
            _reload_list()
            self._sales_refresh_tree()

        def _remove_sel():
            sel_idx = list(lb.curselection())
            if not sel_idx:
                messagebox.showinfo("Chưa chọn", "Chọn sản phẩm cần xóa.")
                return
            if not messagebox.askyesno("Xóa sản phẩm", f"Xóa {len(sel_idx)} sản phẩm đã chọn?"):
                return
            for i in reversed(sel_idx):
                if 0 <= i < len(items):
                    items.pop(i)
            cluster["items"] = items
            self._sales_mark_cluster_dirty(cluster)
            _reload_list()
            self._sales_refresh_tree()

        self._small_btn(product_btns, "Đổi ảnh sản phẩm", _change_product_image).pack(side="left")
        self._small_btn(product_btns, "Sửa prompt", _edit_prompt).pack(side="left", padx=(6, 0))
        self._small_btn(product_btns, "Xóa sản phẩm", _remove_sel).pack(side="left", padx=(6, 0))
        self._small_btn(product_btns, "Thêm sản phẩm", _add_products).pack(side="left", padx=(6, 0))

        _refresh_char_preview()

        self._small_btn(btn_row, "Đổi tên cụm", _rename_cluster).pack(side="left")
        self._small_btn(btn_row, "Thêm sản phẩm", _add_products).pack(side="left", padx=(6, 0))
        self._small_btn(btn_row, "✏ Sửa prompt", _edit_prompt).pack(side="left")
        self._small_btn(btn_row, "🗑 Xóa sản phẩm đã chọn", _remove_sel).pack(side="left", padx=(6, 0))
        self._small_btn(btn_row, "Đóng", dlg.destroy).pack(side="right")

    def _sales_refresh_tree(self):
        self.sales_tree.delete(*self.sales_tree.get_children())
        status_labels = {
            "pending": "⏳ Chờ",
            "running": "⚙ Chạy",
            "done":    "✓ Xong",
            "failed":  "✗ Lỗi",
            "stopped": "■ Dừng",
        }
        for c in self._sales_clusters:
            st      = c.get("status", "pending")
            elapsed = c.get("elapsed_sec", 0.0)
            time_s  = f"{elapsed:.0f}s" if elapsed else "—"
            done    = c.get("done_count", 0)
            total   = len(self._sales_get_items(c, self._sales_default_prompt()))
            final_total = self._sales_expected_final_count(total)
            final_done  = len(c.get("output_paths", []) or [])
            count_s = f"{done}/{total}" if st == "running" else str(total)
            self.sales_tree.insert(
                "", "end", iid=str(c["id"]),
                values=(
                    c["id"], c["name"], count_s,
                    f"{final_done}/{final_total}" if st == "running" else str(final_done or final_total),
                    status_labels.get(st, st), time_s,
                ),
                tags=(st,),
            )
        n_cl  = len(self._sales_clusters)
        n_img = sum(len(self._sales_get_items(c, self._sales_default_prompt())) for c in self._sales_clusters)
        n_vid = sum(self._sales_expected_final_count(len(self._sales_get_items(c, self._sales_default_prompt())))
                    for c in self._sales_clusters)
        self.lbl_sales_count.config(text=f"{n_cl} cụm · {n_img} sản phẩm · {n_vid} video aff")

    # ── Bulk automation helpers (aff seller >50sp/day) ────────────────────

    _IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")

    def _sales_collect_images_in_folder(self, folder: str, recursive: bool = False) -> list[str]:
        """Liệt kê ảnh trong thư mục, sort theo tên."""
        p = Path(folder)
        if not p.is_dir():
            return []
        it = p.rglob("*") if recursive else p.iterdir()
        imgs = [f for f in it if f.is_file() and f.suffix.lower() in self._IMG_EXTS]
        return [str(f) for f in sorted(imgs, key=lambda x: x.name.lower())]

    def _sales_renumber_clusters(self):
        for i, c in enumerate(self._sales_clusters, 1):
            c["id"] = i

    def _sales_quick_from_folder(self):
        """⚡ Quick-create: 1 ảnh nhân vật + 1 thư mục sản phẩm → tạo cụm tự động."""
        char_path = filedialog.askopenfilename(
            title="Bước 1/2 — Chọn 1 ảnh nhân vật (có thể bỏ qua = Cancel)",
            filetypes=IMAGE_FILETYPES,
        )
        # Cho phép bỏ qua nhân vật
        if char_path is None:
            char_path = ""

        folder = filedialog.askdirectory(
            title="Bước 2/2 — Chọn thư mục chứa ảnh sản phẩm",
        )
        if not folder:
            return

        # Tùy chọn nhanh
        dlg = tk.Toplevel(self)
        dlg.title("⚡ Tạo cụm nhanh")
        dlg.geometry("500x340")
        dlg.configure(bg=C["bg"])
        dlg.transient(self)
        dlg.grab_set()

        tk.Label(dlg, text="⚡  Tạo cụm aff nhanh từ thư mục",
                 bg=C["bg"], fg=C["accent3"], font=FONT_TITLE,
                 padx=16, pady=10).pack(anchor="w")
        tk.Frame(dlg, bg=C["accent"], height=2).pack(fill="x")

        body = tk.Frame(dlg, bg=C["bg"])
        body.pack(fill="both", expand=True, padx=14, pady=8)

        var_recursive = tk.BooleanVar(value=False)
        var_split     = tk.IntVar(value=0)   # 0 = 1 cụm chung; >0 = N sp/cụm
        var_autoprmpt = tk.BooleanVar(value=True)
        var_base_name = tk.StringVar(value=Path(folder).name or "Cụm aff")

        # Đếm ảnh để hiển thị
        imgs_now    = self._sales_collect_images_in_folder(folder, False)
        imgs_recur  = self._sales_collect_images_in_folder(folder, True)
        info_lbl = tk.Label(body, text="", bg=C["bg"], fg=C["text2"], font=("Segoe UI", 8),
                            justify="left", wraplength=460)
        info_lbl.pack(anchor="w", pady=(0, 6))

        def _update_info():
            n = len(imgs_recur if var_recursive.get() else imgs_now)
            split = max(0, int(var_split.get() or 0))
            n_cl = 1 if split == 0 or split >= n else (n + split - 1) // split
            info_lbl.config(text=f"📁  {folder}\n"
                                  f"🖼  {n} ảnh sản phẩm  →  {n_cl} cụm aff\n"
                                  f"👤  Nhân vật: {Path(char_path).name if char_path else '(không có)'}")

        row = tk.Frame(body, bg=C["bg"])
        row.pack(fill="x", pady=(0, 6))
        tk.Label(row, text="Tên cơ sở:", bg=C["bg"], fg=C["text2"],
                 font=FONT_BODY, width=14, anchor="w").pack(side="left")
        tk.Entry(row, textvariable=var_base_name, bg=C["inputbg"], fg=C["text"],
                 insertbackground=C["text"], font=FONT_BODY, relief="flat",
                 highlightthickness=1, highlightbackground=C["border"]).pack(side="left", fill="x", expand=True, ipady=3)

        tk.Checkbutton(body, text="Tìm ảnh trong cả thư mục con (recursive)",
                       variable=var_recursive, bg=C["bg"], fg=C["text"],
                       selectcolor=C["bg3"], activebackground=C["bg"],
                       font=FONT_BODY, cursor="hand2",
                       command=_update_info).pack(anchor="w", pady=2)

        tk.Checkbutton(body, text="Tự động sinh prompt mặc định cho từng sản phẩm",
                       variable=var_autoprmpt, bg=C["bg"], fg=C["text"],
                       selectcolor=C["bg3"], activebackground=C["bg"],
                       font=FONT_BODY, cursor="hand2").pack(anchor="w", pady=2)

        split_row = tk.Frame(body, bg=C["bg"])
        split_row.pack(fill="x", pady=(4, 0))
        tk.Label(split_row, text="Tách thành nhiều cụm:", bg=C["bg"], fg=C["text2"],
                 font=FONT_BODY, width=22, anchor="w").pack(side="left")
        sp = tk.Spinbox(split_row, from_=0, to=200, textvariable=var_split,
                        width=8, bg=C["inputbg"], fg=C["text"], font=FONT_BODY,
                        relief="flat", insertbackground=C["text"],
                        command=_update_info)
        sp.pack(side="left")
        tk.Label(split_row, text=" sản phẩm/cụm  (0 = tất cả vào 1 cụm)",
                 bg=C["bg"], fg=C["text2"], font=("Segoe UI", 8)).pack(side="left")

        _update_info()

        result = {"ok": False}

        def _ok():
            result["ok"] = True
            dlg.destroy()

        btn = tk.Frame(dlg, bg=C["bg"])
        btn.pack(fill="x", padx=14, pady=10)
        tk.Button(btn, text="✓ Tạo cụm", bg=C["accent"], fg="white", font=FONT_BOLD,
                  relief="flat", padx=14, pady=6, cursor="hand2",
                  activebackground=C["accent2"], command=_ok).pack(side="left")
        tk.Button(btn, text="✕ Hủy", bg=C["bg3"], fg=C["text"], font=FONT_BODY,
                  relief="flat", padx=14, pady=6, cursor="hand2",
                  activebackground=C["border"], command=dlg.destroy).pack(side="right")
        dlg.bind("<Return>", lambda e: _ok())
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        self.wait_window(dlg)

        if not result["ok"]:
            return

        recursive = var_recursive.get()
        product_paths = self._sales_collect_images_in_folder(folder, recursive)
        if not product_paths:
            messagebox.showwarning("Không có ảnh", "Thư mục này không có ảnh sản phẩm nào (png/jpg/jpeg/webp/bmp).")
            return

        split = max(0, int(var_split.get() or 0))
        if split == 0 or split >= len(product_paths):
            chunks = [product_paths]
        else:
            chunks = [product_paths[i:i + split] for i in range(0, len(product_paths), split)]

        base_name = (var_base_name.get() or Path(folder).name or "Cụm aff").strip()
        # Nếu tự động prompt → prompt rỗng, _sales_make_items sẽ fallback theo var_sales_auto_prompt
        # nhưng người dùng có thể tắt var_sales_auto_prompt — ở đây ép buộc theo dialog choice.
        force_auto = var_autoprmpt.get()
        old_auto   = self.var_sales_auto_prompt.get()
        if force_auto != old_auto:
            self.var_sales_auto_prompt.set(force_auto)

        created = 0
        for idx, paths in enumerate(chunks, 1):
            cid  = len(self._sales_clusters) + 1
            name = base_name if len(chunks) == 1 else f"{base_name} {idx:02d}"
            prompt_text = "" if force_auto else self._sales_default_prompt()
            self._sales_clusters.append({
                "id":              cid,
                "name":            name,
                "character_image": char_path,
                "items":           self._sales_make_items(list(paths), prompt_text),
                "status":          "pending",
                "done_count":      0,
                "clip_paths":      [],
                "output_paths":    [],
                "elapsed_sec":     0.0,
                "error":           "",
            })
            created += 1

        if force_auto != old_auto:
            self.var_sales_auto_prompt.set(old_auto)

        self._sales_refresh_tree()
        self._log("SUCCESS",
                  f"⚡ Quick-create: {created} cụm · {len(product_paths)} sản phẩm từ {Path(folder).name}")

    def _sales_save_campaign_json(self):
        """💾 Lưu toàn bộ chiến dịch Sales (cụm + campaign settings) vào JSON."""
        if not self._sales_clusters:
            messagebox.showinfo("Trống", "Chưa có cụm aff nào để lưu.")
            return
        path = filedialog.asksaveasfilename(
            title="Lưu chiến dịch Sales",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            initialfile="sales_campaign.json",
        )
        if not path:
            return
        # Strip runtime-only keys
        clusters_save = [
            {k: v for k, v in c.items() if k not in ("done_count",)}
            for c in self._sales_clusters
        ]
        data = {
            "version":              1,
            "global": {
                "sales_preset":        self.var_sales_preset.get(),
                "sales_goal":          self.var_sales_goal.get(),
                "sales_audience":      self.var_sales_audience.get(),
                "sales_offer":         self.var_sales_offer.get(),
                "sales_cta":           self.var_sales_cta.get(),
                "sales_auto_prompt":   self.var_sales_auto_prompt.get(),
                "sales_clips_per_video": self.var_sales_clips_per_video.get(),
                "sales_parallel_tabs":   self.var_sales_parallel_tabs.get(),
                "aspect_ratio":        self.var_aspect_ratio.get(),
                "music":               self.var_music.get(),
                "output_dir":          self.var_output_dir.get(),
                "default_prompt":      self._sales_default_prompt(),
            },
            "clusters": clusters_save,
        }
        import json as _json
        try:
            Path(path).write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self._log("SUCCESS", f"💾 Đã lưu {len(clusters_save)} cụm vào {Path(path).name}")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không lưu được:\n{e}")

    def _sales_load_campaign_json(self):
        """📂 Tải chiến dịch Sales từ JSON đã lưu."""
        path = filedialog.askopenfilename(
            title="Tải chiến dịch Sales",
            filetypes=[("JSON", "*.json")],
        )
        if not path:
            return
        import json as _json
        try:
            data = _json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không đọc được JSON:\n{e}")
            return

        # Cho phép cả file lưu bằng app_settings (dạng cũ) lẫn file mới
        clusters = data.get("clusters") or data.get("sales_clusters") or []
        g        = data.get("global") or data

        replace = True
        if self._sales_clusters:
            replace = messagebox.askyesno(
                "Đã có cụm",
                f"Đã có {len(self._sales_clusters)} cụm trong tool.\n"
                f"Yes = THAY THẾ bằng {len(clusters)} cụm từ file.\n"
                f"No  = NỐI THÊM vào danh sách hiện tại.",
            )

        if replace:
            self._sales_clusters = []

        # Restore globals (tolerant — bỏ qua key thiếu)
        try:
            if "sales_preset"          in g: self.var_sales_preset.set(g["sales_preset"] or "TikTok Shop")
            if "sales_goal"            in g: self.var_sales_goal.set(g["sales_goal"] or "Chốt đơn")
            if "sales_audience"        in g: self.var_sales_audience.set(g["sales_audience"] or "")
            if "sales_offer"           in g: self.var_sales_offer.set(g["sales_offer"] or "")
            if "sales_cta"             in g: self.var_sales_cta.set(g["sales_cta"] or DEFAULT_CTA)
            if "sales_auto_prompt"     in g: self.var_sales_auto_prompt.set(bool(g["sales_auto_prompt"]))
            if "sales_clips_per_video" in g: self.var_sales_clips_per_video.set(max(1, int(g["sales_clips_per_video"] or 1)))
            if "sales_parallel_tabs"   in g: self.var_sales_parallel_tabs.set(max(1, int(g["sales_parallel_tabs"] or 1)))
            if "aspect_ratio"          in g: self.var_aspect_ratio.set(g["aspect_ratio"] or "9:16")
            if "music"                 in g: self.var_music.set(g["music"] or "")
            if "output_dir"            in g and g["output_dir"]: self.var_output_dir.set(g["output_dir"])
            default_prompt = g.get("default_prompt") or data.get("sales_prompt") or ""
            if default_prompt:
                self._sales_prompt_txt.delete("1.0", "end")
                self._sales_prompt_txt.insert("1.0", default_prompt)
        except Exception:
            pass

        for c in clusters:
            c.setdefault("status", "pending")
            c.setdefault("done_count", 0)
            c.setdefault("clip_paths", [])
            c.setdefault("output_paths", [])
            c.setdefault("elapsed_sec", 0.0)
            c.setdefault("error", "")
            self._sales_clusters.append(c)
        self._sales_renumber_clusters()
        # Migrate legacy items / cập nhật campaign
        for c in self._sales_clusters:
            self._sales_get_items(c, self._sales_default_prompt())
        self._sales_refresh_tree()
        self._log("SUCCESS", f"📂 Đã tải {len(clusters)} cụm từ {Path(path).name}")

    def _sales_export_csv_template(self):
        """📝 Xuất mẫu CSV để user điền cho Import CSV."""
        path = filedialog.asksaveasfilename(
            title="Xuất mẫu CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile="sales_products_template.csv",
        )
        if not path:
            return
        import csv as _csv
        rows = [
            {
                "cluster":         "Cụm son môi",
                "product_image":   r"D:\affilate\son_01.jpg",
                "character_image": r"D:\affilate\nguoi_dep.png",
                "name":            "Son lì matte",
                "prompt":          "Demo son trên môi, chốt deal mua 1 tặng 1",
                "audience":        "nữ 18-30 thích makeup",
                "offer":           "mua 1 tặng 1 freeship",
                "cta":             "Bấm giỏ vàng để nhận deal",
                "goal":            "Chốt đơn",
                "preset":          "TikTok Shop",
            },
            {
                "cluster":         "Cụm son môi",
                "product_image":   r"D:\affilate\son_02.jpg",
                "character_image": "",
                "name":            "Son thỏi velvet",
                "prompt":          "",
                "audience":        "",
                "offer":           "",
                "cta":             "",
                "goal":            "",
                "preset":          "",
            },
            {
                "cluster":         "Cụm dưỡng da",
                "product_image":   r"D:\affilate\toner.jpg",
                "character_image": r"D:\affilate\nguoi_dep.png",
                "name":            "Toner cấp ẩm",
                "prompt":          "",
                "audience":        "da khô tuổi 20-35",
                "offer":           "deal 99k",
                "cta":             "Link dưới bio",
                "goal":            "Demo công dụng",
                "preset":          "UGC Review",
            },
        ]
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = _csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                for r in rows:
                    w.writerow(r)
            self._log("SUCCESS", f"📝 Đã xuất mẫu CSV: {Path(path).name}")
            if messagebox.askyesno("Mở file?", "Mở file mẫu CSV để xem cấu trúc cột?"):
                os.startfile(path)
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không xuất được:\n{e}")

    def _sales_import_csv(self):
        """📊 Import CSV/Excel sản phẩm → tự gom theo cluster name → tạo cụm aff."""
        path = filedialog.askopenfilename(
            title="Chọn CSV (UTF-8 hoặc UTF-8-BOM)",
            filetypes=[("CSV", "*.csv"), ("All", "*.*")],
        )
        if not path:
            return

        import csv as _csv
        # Đọc CSV tolerant với BOM, đoán delimiter
        try:
            raw = Path(path).read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            try:
                raw = Path(path).read_text(encoding="utf-8")
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không đọc được file:\n{e}")
                return

        sample = raw[:2048]
        try:
            dialect = _csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except Exception:
            dialect = _csv.excel
        reader = _csv.DictReader(raw.splitlines(), dialect=dialect)
        rows = [{(k or "").strip().lower(): (v or "").strip() for k, v in row.items()} for row in reader]
        if not rows:
            messagebox.showerror("Trống", "File CSV không có dữ liệu.")
            return

        # Mapping alias cột (linh hoạt cho user Việt)
        def pick(row: dict, *keys: str) -> str:
            for k in keys:
                v = row.get(k, "")
                if v:
                    return v
            return ""

        clusters_by_name: dict[str, dict] = {}
        skipped_no_image = 0
        for row in rows:
            img = pick(row, "product_image", "image", "anh", "anh_san_pham", "san_pham")
            if not img:
                skipped_no_image += 1
                continue
            cname = pick(row, "cluster", "cum", "nhom") or "Cụm import"
            char  = pick(row, "character_image", "character", "nhan_vat")
            campaign = {
                "sales_preset":   pick(row, "preset", "mau", "mau_video") or self.var_sales_preset.get(),
                "sales_goal":     pick(row, "goal", "muc_tieu") or self.var_sales_goal.get(),
                "sales_audience": pick(row, "audience", "tep_khach") or self.var_sales_audience.get(),
                "sales_offer":    pick(row, "offer", "uu_dai") or self.var_sales_offer.get(),
                "sales_cta":      pick(row, "cta") or self.var_sales_cta.get() or DEFAULT_CTA,
            }
            prompt = pick(row, "prompt", "video_prompt")
            if not prompt and self.var_sales_auto_prompt.get():
                prompt = build_default_sales_prompt(
                    product_image_path=img,
                    preset=campaign["sales_preset"],
                    goal=campaign["sales_goal"],
                    audience=campaign["sales_audience"],
                    offer=campaign["sales_offer"],
                    cta=campaign["sales_cta"],
                )
            item = {"product_image": img, "prompt": prompt}
            item.update(campaign)

            if cname not in clusters_by_name:
                clusters_by_name[cname] = {
                    "name":            cname,
                    "character_image": char,
                    "items":           [],
                }
            cl = clusters_by_name[cname]
            # Cluster character_image lấy giá trị đầu tiên không rỗng
            if not cl["character_image"] and char:
                cl["character_image"] = char
            cl["items"].append(item)

        if not clusters_by_name:
            messagebox.showerror(
                "Không nhận dạng được",
                "CSV cần ít nhất cột 'product_image' (hoặc 'image' / 'anh').\n"
                f"Bỏ qua {skipped_no_image} dòng thiếu ảnh.",
            )
            return

        # Preview & confirm
        preview_lines = []
        for name, c in clusters_by_name.items():
            char_s = Path(c["character_image"]).name if c["character_image"] else "(không có)"
            preview_lines.append(f"• {name}  -  {len(c['items'])} sản phẩm  -  👤 {char_s}")
        total_items = sum(len(c["items"]) for c in clusters_by_name.values())
        msg = (
            f"Sẽ import {len(clusters_by_name)} cụm  ·  {total_items} sản phẩm:\n\n"
            + "\n".join(preview_lines[:12])
        )
        if len(preview_lines) > 12:
            msg += f"\n… và {len(preview_lines) - 12} cụm khác"
        if skipped_no_image:
            msg += f"\n\n⚠ Bỏ qua {skipped_no_image} dòng không có ảnh"
        msg += "\n\nYes = THAY THẾ danh sách hiện tại.\nNo  = NỐI THÊM."

        if not self._sales_clusters:
            ans = True
        else:
            ans = messagebox.askyesnocancel("Import CSV", msg)
            if ans is None:
                return

        if ans is True:
            self._sales_clusters = []

        for cname, c in clusters_by_name.items():
            cid = len(self._sales_clusters) + 1
            self._sales_clusters.append({
                "id":              cid,
                "name":            c["name"],
                "character_image": c["character_image"],
                "items":           c["items"],
                "status":          "pending",
                "done_count":      0,
                "clip_paths":      [],
                "output_paths":    [],
                "elapsed_sec":     0.0,
                "error":           "",
            })

        self._sales_refresh_tree()
        self._log("SUCCESS",
                  f"📊 Import CSV: {len(clusters_by_name)} cụm · {total_items} sản phẩm "
                  f"({skipped_no_image} dòng bị bỏ qua)")

    def _sales_duplicate_cluster(self):
        """📋 Nhân bản cụm đã chọn (giữ ảnh + prompt + items, reset status)."""
        sel = self.sales_tree.selection()
        if not sel:
            messagebox.showinfo("Chưa chọn", "Hãy chọn 1 cụm trong danh sách để nhân bản.")
            return
        import copy as _copy
        cloned = 0
        for iid in sel:
            try:
                cid = int(iid)
            except ValueError:
                continue
            src = next((c for c in self._sales_clusters if c["id"] == cid), None)
            if not src:
                continue
            new_c = _copy.deepcopy(src)
            new_c["id"]            = len(self._sales_clusters) + 1
            new_c["name"]          = f"{src.get('name', f'Cụm {cid}')} (copy)"
            new_c["status"]        = "pending"
            new_c["done_count"]    = 0
            new_c["clip_paths"]    = []
            new_c["output_paths"]  = []
            new_c["elapsed_sec"]   = 0.0
            new_c["error"]         = ""
            self._sales_clusters.append(new_c)
            cloned += 1
        if cloned:
            self._sales_refresh_tree()
            self._log("INFO", f"📋 Đã nhân bản {cloned} cụm")

    def _sales_bulk_edit_prompts(self):
        """✏ Sửa hàng loạt: find/replace + apply campaign + replace all prompts."""
        if not self._sales_clusters:
            messagebox.showinfo("Trống", "Chưa có cụm nào để sửa.")
            return

        sel_ids: set[int] = set()
        for iid in self.sales_tree.selection():
            try:
                sel_ids.add(int(iid))
            except ValueError:
                pass

        dlg = tk.Toplevel(self)
        dlg.title("✏ Sửa prompt hàng loạt")
        dlg.geometry("620x560")
        dlg.configure(bg=C["bg"])
        dlg.transient(self)
        dlg.grab_set()

        tk.Label(dlg, text="✏  Sửa prompt hàng loạt", bg=C["bg"], fg=C["accent3"],
                 font=FONT_TITLE, padx=16, pady=10).pack(anchor="w")
        tk.Frame(dlg, bg=C["accent"], height=2).pack(fill="x")

        body = tk.Frame(dlg, bg=C["bg"])
        body.pack(fill="both", expand=True, padx=14, pady=8)

        # Phạm vi
        scope_row = tk.Frame(body, bg=C["bg"])
        scope_row.pack(fill="x", pady=(0, 6))
        tk.Label(scope_row, text="Phạm vi:", bg=C["bg"], fg=C["text2"],
                 font=FONT_BOLD).pack(side="left", padx=(0, 8))
        var_scope = tk.StringVar(value="selected" if sel_ids else "all")
        tk.Radiobutton(scope_row, text=f"Đã chọn ({len(sel_ids)} cụm)" if sel_ids else "Đã chọn (không có)",
                       variable=var_scope, value="selected",
                       bg=C["bg"], fg=C["text"], selectcolor=C["bg3"],
                       activebackground=C["bg"], font=FONT_BODY, cursor="hand2",
                       state="normal" if sel_ids else "disabled").pack(side="left")
        tk.Radiobutton(scope_row, text=f"Tất cả ({len(self._sales_clusters)} cụm)",
                       variable=var_scope, value="all",
                       bg=C["bg"], fg=C["text"], selectcolor=C["bg3"],
                       activebackground=C["bg"], font=FONT_BODY,
                       cursor="hand2").pack(side="left", padx=(8, 0))

        nb = ttk.Notebook(body)
        nb.pack(fill="both", expand=True, pady=(4, 0))

        # ── Tab 1: Find/Replace ──
        tab1 = tk.Frame(nb, bg=C["bg2"])
        nb.add(tab1, text="  Tìm & Thay  ")
        tk.Label(tab1, text="Tìm:", bg=C["bg2"], fg=C["text2"],
                 font=FONT_BODY, padx=8, pady=4).pack(anchor="w")
        var_find = tk.StringVar()
        tk.Entry(tab1, textvariable=var_find, bg=C["inputbg"], fg=C["text"],
                 insertbackground=C["text"], font=FONT_BODY, relief="flat",
                 highlightthickness=1, highlightbackground=C["border"]
                 ).pack(fill="x", padx=8, ipady=4)
        tk.Label(tab1, text="Thay bằng:", bg=C["bg2"], fg=C["text2"],
                 font=FONT_BODY, padx=8, pady=4).pack(anchor="w")
        var_repl = tk.StringVar()
        tk.Entry(tab1, textvariable=var_repl, bg=C["inputbg"], fg=C["text"],
                 insertbackground=C["text"], font=FONT_BODY, relief="flat",
                 highlightthickness=1, highlightbackground=C["border"]
                 ).pack(fill="x", padx=8, ipady=4)
        var_case = tk.BooleanVar(value=False)
        tk.Checkbutton(tab1, text="Phân biệt chữ hoa/thường",
                       variable=var_case, bg=C["bg2"], fg=C["text"],
                       selectcolor=C["bg3"], activebackground=C["bg2"],
                       font=("Segoe UI", 8), cursor="hand2").pack(anchor="w", padx=8, pady=4)
        tk.Label(tab1, text="Quét trong prompt của TỪNG sản phẩm; cụm sẽ reset status để chạy lại.",
                 bg=C["bg2"], fg=C["text2"], font=("Segoe UI", 8),
                 padx=8, wraplength=540, justify="left").pack(anchor="w", pady=(8, 4))

        # ── Tab 2: Áp dụng campaign hiện tại ──
        tab2 = tk.Frame(nb, bg=C["bg2"])
        nb.add(tab2, text="  Áp dụng campaign  ")
        tk.Label(tab2, text="Ghi đè preset/goal/audience/offer/CTA hiện tại (panel trên) vào các sản phẩm.",
                 bg=C["bg2"], fg=C["text2"], font=("Segoe UI", 8),
                 padx=8, wraplength=540, justify="left").pack(anchor="w", pady=(8, 6))
        camp = self._sales_campaign_settings()
        for k, label in [("sales_preset", "Mẫu video"), ("sales_goal", "Mục tiêu"),
                         ("sales_audience", "Tệp khách"), ("sales_offer", "Ưu đãi"),
                         ("sales_cta", "CTA")]:
            r = tk.Frame(tab2, bg=C["bg2"])
            r.pack(fill="x", padx=8, pady=2)
            tk.Label(r, text=f"{label}:", bg=C["bg2"], fg=C["text2"],
                     font=FONT_BODY, width=12, anchor="w").pack(side="left")
            tk.Label(r, text=str(camp.get(k, "")) or "(trống)",
                     bg=C["bg2"], fg=C["text"], font=FONT_BODY,
                     wraplength=420, justify="left").pack(side="left")

        var_regen_prompt = tk.BooleanVar(value=False)
        tk.Checkbutton(
            tab2,
            text="Đồng thời tạo lại prompt mặc định cho TỪNG sản phẩm (ghi đè prompt cũ)",
            variable=var_regen_prompt, bg=C["bg2"], fg=C["text"],
            selectcolor=C["bg3"], activebackground=C["bg2"],
            font=("Segoe UI", 8), cursor="hand2", wraplength=540, justify="left",
        ).pack(anchor="w", padx=8, pady=(10, 4))

        # ── Tab 3: Replace ALL prompts ──
        tab3 = tk.Frame(nb, bg=C["bg2"])
        nb.add(tab3, text="  Đặt prompt chung  ")
        tk.Label(tab3, text="Ghi đè prompt của TẤT CẢ sản phẩm (trong phạm vi) bằng template dưới đây:",
                 bg=C["bg2"], fg=C["text2"], font=("Segoe UI", 8),
                 padx=8, wraplength=540, justify="left").pack(anchor="w", pady=(8, 4))
        new_prompt_txt = tk.Text(tab3, height=10, bg=C["inputbg"], fg=C["text"],
                                  font=FONT_MONO, relief="flat", wrap="word",
                                  insertbackground=C["text"], padx=6, pady=4,
                                  highlightthickness=1, highlightbackground=C["border"])
        new_prompt_txt.pack(fill="both", expand=True, padx=8, pady=(0, 6))
        new_prompt_txt.insert("1.0", self._sales_default_prompt())

        # ── Apply buttons ──
        def _scope_clusters():
            if var_scope.get() == "all" or not sel_ids:
                return list(self._sales_clusters)
            return [c for c in self._sales_clusters if c["id"] in sel_ids]

        def _do_find_replace():
            find = var_find.get()
            if not find:
                messagebox.showinfo("Trống", "Hãy nhập từ cần tìm.")
                return
            repl = var_repl.get()
            cs   = _scope_clusters()
            changed = 0
            n_items = 0
            for c in cs:
                items = self._sales_get_items(c, self._sales_default_prompt())
                cl_changed = False
                for it in items:
                    p = it.get("prompt", "")
                    if var_case.get():
                        if find in p:
                            it["prompt"] = p.replace(find, repl); cl_changed = True; n_items += 1
                    else:
                        import re as _re
                        new = _re.sub(_re.escape(find), lambda m: repl, p, flags=_re.IGNORECASE)
                        if new != p:
                            it["prompt"] = new; cl_changed = True; n_items += 1
                if cl_changed:
                    c["items"] = items
                    self._sales_mark_cluster_dirty(c)
                    changed += 1
            self._sales_refresh_tree()
            self._log("INFO", f"✏ Tìm & thay: {n_items} prompt sửa  ·  {changed} cụm reset")
            dlg.destroy()

        def _do_apply_campaign():
            cs = _scope_clusters()
            n_items = 0
            for c in cs:
                items = self._sales_get_items(c, self._sales_default_prompt())
                for it in items:
                    it.update(self._sales_campaign_settings())
                    if var_regen_prompt.get():
                        it["prompt"] = self._sales_build_default_prompt(it.get("product_image", ""))
                    n_items += 1
                c["items"] = items
                self._sales_mark_cluster_dirty(c)
            self._sales_refresh_tree()
            self._log("INFO", f"✏ Áp dụng campaign cho {n_items} sản phẩm  ·  {len(cs)} cụm")
            dlg.destroy()

        def _do_replace_all():
            new_prompt = new_prompt_txt.get("1.0", "end-1c").strip()
            if not new_prompt:
                messagebox.showinfo("Trống", "Hãy nhập prompt mới.")
                return
            cs = _scope_clusters()
            n_items = 0
            for c in cs:
                items = self._sales_get_items(c, self._sales_default_prompt())
                for it in items:
                    it["prompt"] = new_prompt
                    n_items += 1
                c["items"] = items
                self._sales_mark_cluster_dirty(c)
            self._sales_refresh_tree()
            self._log("INFO", f"✏ Đặt prompt chung cho {n_items} sản phẩm  ·  {len(cs)} cụm")
            dlg.destroy()

        btn_row = tk.Frame(dlg, bg=C["bg"])
        btn_row.pack(fill="x", padx=14, pady=10)

        def _apply_active_tab():
            idx = nb.index(nb.select())
            [_do_find_replace, _do_apply_campaign, _do_replace_all][idx]()

        tk.Button(btn_row, text="✓ Áp dụng", bg=C["accent"], fg="white",
                  font=FONT_BOLD, relief="flat", padx=14, pady=6, cursor="hand2",
                  activebackground=C["accent2"], command=_apply_active_tab).pack(side="left")
        tk.Button(btn_row, text="✕ Hủy", bg=C["bg3"], fg=C["text"],
                  font=FONT_BODY, relief="flat", padx=14, pady=6, cursor="hand2",
                  activebackground=C["border"], command=dlg.destroy).pack(side="right")
        dlg.bind("<Escape>", lambda e: dlg.destroy())

    # ── Sales AI runner ───────────────────────────────────────────────────

    def _on_start_sales(self):
        if not self._sales_clusters:
            messagebox.showwarning("Trống",
                "Chưa có cụm aff nào!\nBấm '➕ Thêm cụm aff' để chọn ảnh.")
            return
        default_prompt = self._sales_default_prompt()
        total_items = sum(len(self._sales_get_items(c, default_prompt)) for c in self._sales_clusters)
        if total_items == 0:
            messagebox.showwarning("Không có ảnh", "Các cụm chưa có ảnh sản phẩm nào!")
            return

        for c in self._sales_clusters:
            self._sales_prepare_items_for_run(c, default_prompt)

        # Kiểm tra có cụm nào cần chạy không
        pending = [c for c in self._sales_clusters if c.get("status") != "done"]
        if not pending:
            if not messagebox.askyesno(
                "Đã hoàn thành",
                "Tất cả cụm đã xong rồi!\nNhấn Yes để reset tất cả và chạy lại từ đầu.",
            ):
                return
            self._sales_reset_status()
            self._sales_refresh_tree()

        self._running = True
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.btn_open.config(state="disabled")
        self.pbar["value"] = 0
        self.lbl_prog.config(text=f"Bán hàng AI: {total_items} clip đang tạo…")
        self._start_gallery_poll()

        settings = {
            "output_dir":      self.var_output_dir.get() or str(config.OUTPUT_DIR),
            "grok_profile":    self.var_grok_profile.get() or "grok",
            "chrome_profile":  self._get_selected_chrome_profile(),
            "connect_existing": self.var_connect_existing.get(),
            "aspect_ratio":    self.var_aspect_ratio.get(),
            "music":           self.var_music.get(),
            "clips_per_video":  max(1, int(self.var_sales_clips_per_video.get() or 1)),
            "parallel_tabs":    max(1, int(self.var_sales_parallel_tabs.get() or 1)),
        }

        self._batch_stop_event = threading.Event()
        self.btn_stop.config(command=self._on_stop_batch)

        def _run():
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._run_sales_all(settings))
            except Exception as e:
                self._log("ERROR", f"Sales AI lỗi: {e}")
            finally:
                loop.close()
                self.after(0, self._on_batch_finished)

        threading.Thread(target=_run, daemon=True).start()

    def _sales_assemble_aff_videos(
        self,
        clip_paths: list[Path],
        cluster_dir: Path,
        safe_name: str,
        clips_per_video: int,
        music_setting: str = "",
    ) -> list[Path]:
        if not clip_paths:
            return []

        clips_per_video = max(1, int(clips_per_video or 1))
        final_paths: list[Path] = []

        for group_idx, start in enumerate(range(0, len(clip_paths), clips_per_video), 1):
            chunk = clip_paths[start:start + clips_per_video]
            result = self._sales_assemble_aff_group(
                chunk, cluster_dir, safe_name, group_idx, music_setting
            )
            if result:
                final_paths.append(result)

        return final_paths

    def _sales_assemble_aff_group(
        self,
        clip_paths: list[Path],
        cluster_dir: Path,
        safe_name: str,
        group_idx: int,
        music_setting: str = "",
    ) -> Optional[Path]:
        if not clip_paths:
            return None

        video_exts = {".mp4", ".mov", ".avi", ".webm", ".mkv"}
        if len(clip_paths) == 1 and clip_paths[0].suffix.lower() in video_exts:
            return clip_paths[0]

        from utils.logger import GUILogger
        from video.processor import VideoProcessor

        proc = VideoProcessor(GUILogger(self.log_queue, log_file=str(config.BASE_DIR / "app.log")))
        music_p = Path(music_setting) if music_setting and Path(music_setting).exists() else None
        if not music_p:
            music_p = proc.pick_random_music()

        out_file = cluster_dir / f"{safe_name}_aff_{group_idx:03d}.mp4"
        self._log("STEP", f"Ghép video aff {group_idx}: {len(clip_paths)} clip → {out_file.name}")
        result = proc.assemble(clip_paths, out_file, music_path=music_p)
        if not result:
            self._log("ERROR", f"Ghép video aff {group_idx} thất bại")
        return result

    async def _run_sales_all(self, settings: dict):
        import re as _re
        from agents.grok_agent import GrokAgent
        from utils.logger import GUILogger

        grok = GrokAgent(
            GUILogger(self.log_queue, log_file=str(config.BASE_DIR / "app.log")),
            profile_name=settings.get("grok_profile", "grok"),
            chrome_profile=settings.get("chrome_profile"),
            connect_existing=settings.get("connect_existing", False),
        )

        aspect_ratio = settings.get("aspect_ratio", "9:16")
        output_base  = Path(settings.get("output_dir") or str(config.OUTPUT_DIR))
        clips_per_video = max(1, int(settings.get("clips_per_video") or 1))
        parallel_tabs = max(1, int(settings.get("parallel_tabs") or 1))
        default_prompt = self._sales_default_prompt()

        pending = [c for c in self._sales_clusters if c.get("status") != "done"]
        if not pending:
            self._log("WARNING", "Không có cụm nào cần xử lý — tất cả đã xong hoặc bị bỏ qua")
            return

        for c in pending:
            self._sales_prepare_items_for_run(c, default_prompt)
        total_clips = sum(len(self._sales_get_items(c, default_prompt)) for c in pending)
        done_so_far  = 0

        await grok.start()
        try:
            if not await grok.ensure_logged_in():
                self._log("ERROR", "Không đăng nhập được Grok — hủy Sales AI")
                return

            self._log("SUCCESS",
                f"Bán hàng AI: {len(pending)} cụm · {total_clips} clip · "
                f"{clips_per_video} clip/video · {parallel_tabs} tab · tỷ lệ {aspect_ratio}")

            for cluster in self._sales_clusters:
                if hasattr(self, "_batch_stop_event") and self._batch_stop_event.is_set():
                    self._log("WARNING", "Dừng Sales AI theo yêu cầu")
                    break

                if cluster.get("status") == "done":
                    continue

                items = self._sales_prepare_items_for_run(cluster, default_prompt)
                if not items:
                    continue

                cname     = cluster.get("name", f"cum_{cluster['id']}")
                safe_name = _re.sub(r"[^\w\s-]", "", cname).replace(" ", "_")[:24]
                if not safe_name:
                    safe_name = f"cum_{cluster['id']}"
                cluster_dir = output_base / safe_name
                cluster_dir.mkdir(parents=True, exist_ok=True)

                cluster["status"] = "running"
                cluster["clip_paths"] = []
                cluster["output_paths"] = []
                self.after(0, self._sales_refresh_tree)

                t0 = time.time()
                try:
                    _done_ref = [done_so_far]

                    def _on_progress(done, total):
                        cluster["done_count"] = done
                        pct = int((_done_ref[0] + done) / max(total_clips, 1) * 100)
                        label = f"Cụm '{cname}': {done}/{total} clip"
                        self.after(0, lambda p=pct, l=label: self._apply_progress(p, l))
                        self.after(0, self._sales_refresh_tree)

                    def _should_stop():
                        return (
                            hasattr(self, "_batch_stop_event")
                            and self._batch_stop_event.is_set()
                        )

                    paths = await grok.generate_sales_clips(
                        items=items,
                        character_image_path=self._sales_cluster_char(cluster),
                        output_dir=cluster_dir,
                        aspect_ratio=aspect_ratio,
                        start_index=1,
                        parallel_tabs=parallel_tabs,
                        on_progress=_on_progress,
                        should_stop=_should_stop,
                    )
                    stopped = (
                        hasattr(self, "_batch_stop_event")
                        and self._batch_stop_event.is_set()
                    )
                    done_so_far += len(paths) if stopped else len(items)
                    final_paths = []
                    if paths and not stopped:
                        final_paths = self._sales_assemble_aff_videos(
                            paths, cluster_dir, safe_name, clips_per_video,
                            settings.get("music", ""),
                        )

                    cluster["status"]      = "stopped" if stopped else ("done" if paths else "failed")
                    cluster["done_count"]  = len(paths) if stopped else len(items)
                    cluster["clip_paths"]   = [str(p) for p in paths]
                    cluster["output_paths"] = [str(p) for p in (final_paths or paths)]
                    cluster["elapsed_sec"] = round(time.time() - t0, 1)
                    if final_paths:
                        self._last_output = str(final_paths[0])
                    elif paths:
                        self._last_output = str(paths[0])
                    self._log(
                        "WARNING" if stopped else ("SUCCESS" if paths else "ERROR"),
                        (
                            f"■ Đã dừng cụm '{cname}': {len(paths)}/{len(items)} clip"
                            if stopped else
                            f"✓ Cụm '{cname}': {len(paths)}/{len(items)} clip · "
                            f"{len(final_paths or paths)} video aff"
                        ),
                    )
                    self.after(0, self._sales_refresh_results)

                    if stopped:
                        break

                except Exception as e:
                    cluster["status"]      = "failed"
                    cluster["error"]       = str(e)[:200]
                    cluster["elapsed_sec"] = round(time.time() - t0, 1)
                    self._log("ERROR", f"✗ Cụm '{cname}' lỗi: {e}")

                self.after(0, self._sales_refresh_tree)

        finally:
            await grok.stop()

        done_n   = sum(1 for c in self._sales_clusters if c.get("status") == "done")
        failed_n = sum(1 for c in self._sales_clusters if c.get("status") == "failed")
        stopped_n = sum(1 for c in self._sales_clusters if c.get("status") == "stopped")
        level = "WARNING" if stopped_n else "SUCCESS"
        self._log(level,
            f"═══ Bán hàng AI kết thúc: {done_n} cụm thành công, {failed_n} lỗi, {stopped_n} dừng ═══")
        self.after(0, self._sales_refresh_results)

    def _build_settings_section(self, parent):
        card = self._card(parent, "⚙  Cài đặt")

        # Tỷ lệ khung hình
        ar_row = tk.Frame(card, bg=C["bg2"])
        ar_row.pack(fill="x", padx=10, pady=(6, 4))
        tk.Label(ar_row, text="Tỷ lệ khung:", bg=C["bg2"], fg=C["text2"],
                 font=FONT_BODY, width=14, anchor="w").pack(side="left")
        for ratio, label in [("9:16", "9:16 Dọc"), ("16:9", "16:9 Ngang"),
                              ("1:1", "1:1 Vuông"), ("3:2", "3:2 Rộng"), ("2:3", "2:3 Cao")]:
            tk.Radiobutton(
                ar_row, text=label, variable=self.var_aspect_ratio, value=ratio,
                bg=C["bg2"], fg=C["text2"], selectcolor=C["bg3"],
                activebackground=C["bg2"], activeforeground=C["text"],
                font=("Segoe UI", 8), cursor="hand2",
            ).pack(side="left", padx=(0, 6))

        # Giọng TTS
        voice_row = tk.Frame(card, bg=C["bg2"])
        voice_row.pack(fill="x", padx=10, pady=(0, 4))
        tk.Label(voice_row, text="Giọng đọc:", bg=C["bg2"], fg=C["text2"],
                 font=FONT_BODY, width=14, anchor="w").pack(side="left")
        for val, lbl in [("female", "🎙 Nữ (HoaiMy)"), ("male", "🎙 Nam (NamMinh)")]:
            tk.Radiobutton(
                voice_row, text=lbl, variable=self.var_tts_voice, value=val,
                bg=C["bg2"], fg=C["text2"], selectcolor=C["bg3"],
                activebackground=C["bg2"], activeforeground=C["text"],
                font=("Segoe UI", 8), cursor="hand2",
            ).pack(side="left", padx=(0, 10))

        # Duration (chỉ cho Film AI)
        row2 = tk.Frame(card, bg=C["bg2"])
        row2.pack(fill="x", padx=10, pady=(0, 4))
        self._spin(row2, "Giây/cảnh:", self.var_scene_dur, 3, 60)
        tk.Label(row2, text="(Film AI)", bg=C["bg2"], fg=C["text2"],
                 font=("Segoe UI", 7)).pack(side="left", padx=4)

        # Output & music
        self._file_pick(card, "Thư mục output", self.var_output_dir, [], folder=True)
        self._file_pick(card, "Nhạc nền", self.var_music,
                        [("Audio", "*.mp3 *.m4a *.wav")],
                        hint="Để trống = chọn ngẫu nhiên từ assets/music/")

        # Grok profile (tool internal)
        row3 = tk.Frame(card, bg=C["bg2"])
        row3.pack(fill="x", padx=10, pady=(0, 4))
        tk.Label(row3, text="Grok profile:", bg=C["bg2"], fg=C["text2"],
                 font=FONT_BODY, width=14, anchor="w").pack(side="left")
        tk.Entry(row3, textvariable=self.var_grok_profile, bg=C["inputbg"], fg=C["text"],
                 font=FONT_BODY, width=12, relief="flat",
                 insertbackground=C["text"],
                 highlightthickness=1, highlightbackground=C["border"]).pack(side="left")
        tk.Label(row3, text="(đổi tên = dùng TK Grok khác)",
                 bg=C["bg2"], fg=C["text2"], font=("Segoe UI", 7)).pack(side="left", padx=6)

        # ── Kết nối Chrome đang mở ★★★ ────────────────────────────────────
        tk.Frame(card, bg=C["border"], height=1).pack(fill="x", pady=(6, 0))
        tk.Label(card, text="Chống bot  ★★★ Kết nối Chrome đang mở",
                 bg=C["bg2"], fg=C["accent3"], font=FONT_BOLD,
                 padx=10, pady=4).pack(anchor="w")

        conn_row = tk.Frame(card, bg=C["bg2"])
        conn_row.pack(fill="x", padx=10, pady=(0, 4))

        tk.Checkbutton(
            conn_row, text="Dùng Chrome đang mở (port 9222)",
            variable=self.var_connect_existing,
            bg=C["bg2"], fg=C["text"], selectcolor=C["bg3"],
            activebackground=C["bg2"], activeforeground=C["text"],
            font=FONT_BOLD, cursor="hand2",
            command=self._on_connect_toggle,
        ).pack(side="left")

        self.btn_check_chrome = self._small_btn(
            conn_row, "🔍 Kiểm tra kết nối", self._check_chrome_connection
        )
        self.btn_check_chrome.pack(side="left", padx=(8, 0))

        self.lbl_connect_status = tk.Label(
            conn_row, text="", bg=C["bg2"], fg=C["text2"], font=("Segoe UI", 7)
        )
        self.lbl_connect_status.pack(side="left", padx=6)

        how_row = tk.Frame(card, bg=C["bg2"])
        how_row.pack(fill="x", padx=10, pady=(0, 4))

        self.btn_open_chrome = tk.Button(
            how_row,
            text="▶  Mở Chrome Grok",
            command=self._open_grok_chrome,
            bg=C["accent"], fg="white", font=FONT_BOLD,
            relief="flat", cursor="hand2", padx=12, pady=4,
            activebackground=C["accent2"], activeforeground="white",
        )
        self.btn_open_chrome.pack(side="left")

        self.lbl_chrome_status = tk.Label(
            how_row, text="(chưa mở)", bg=C["bg2"], fg=C["text2"],
            font=("Segoe UI", 8),
        )
        self.lbl_chrome_status.pack(side="left", padx=8)

        tk.Label(card,
                 text="Bấm 'Mở Chrome Grok' → Chrome riêng mở lên (Chrome đang dùng KHÔNG bị ảnh hưởng)\n"
                      "Lần đầu: đăng nhập X/Grok trong cửa sổ đó  |  Lần sau: tự nhớ session",
                 bg=C["bg2"], fg=C["green"], font=("Segoe UI", 7),
                 padx=10, wraplength=420, justify="left").pack(anchor="w", pady=(0, 6))

        # ── Chrome Profile thật (CDP mode) ───────────────────────────────
        tk.Frame(card, bg=C["border"], height=1).pack(fill="x", pady=(4, 0))
        tk.Label(card, text="Chrome Profile thật  ★★ (cần đóng Chrome trước)",
                 bg=C["bg2"], fg=C["accent3"], font=FONT_BOLD,
                 padx=10, pady=4).pack(anchor="w")

        hint_text = (
            "Chọn profile → tool copy cookies rồi mở Chrome qua cổng debug.\n"
            "Chrome khởi động BÌNH THƯỜNG — Cloudflare không phân biệt được.\n"
            "Quy trình: 1) Đóng Chrome  2) Chọn profile  3) Nhấn Sync  4) BẮT ĐẦU"
        )
        tk.Label(card, text=hint_text, bg=C["bg2"], fg=C["text2"],
                 font=("Segoe UI", 7), padx=10, justify="left").pack(anchor="w")

        cp_row = tk.Frame(card, bg=C["bg2"])
        cp_row.pack(fill="x", padx=10, pady=(4, 2))
        tk.Label(cp_row, text="Chrome profile:", bg=C["bg2"], fg=C["text2"],
                 font=FONT_BODY, width=14, anchor="w").pack(side="left")

        self._chrome_profiles = config.find_chrome_profiles()
        display_list = ["— Không dùng (profile riêng) —"] + list(self._chrome_profiles.keys())
        self.cb_chrome = ttk.Combobox(
            cp_row, textvariable=self.var_chrome_profile,
            values=display_list, state="readonly", width=28, font=FONT_BODY,
        )
        self.cb_chrome.set(display_list[0])
        self.cb_chrome.pack(side="left")
        self._small_btn(cp_row, "↻", self._refresh_chrome_profiles).pack(side="left", padx=(4, 0))

        sync_row = tk.Frame(card, bg=C["bg2"])
        sync_row.pack(fill="x", padx=10, pady=(2, 6))
        self._small_btn(
            sync_row, "🔄  Sync cookies (đóng Chrome trước)",
            self._sync_chrome_profile_now,
        ).pack(side="left")
        self.lbl_sync_status = tk.Label(
            sync_row, text="", bg=C["bg2"], fg=C["text2"], font=("Segoe UI", 7),
        )
        self.lbl_sync_status.pack(side="left", padx=8)

        # Hướng dẫn cổng CDP
        tk.Label(card,
                 text="ℹ  Khi chọn profile: tool tự mở Chrome riêng (port 9222), KHÔNG ảnh hưởng Chrome đang mở.",
                 bg=C["bg2"], fg=C["text2"], font=("Segoe UI", 7),
                 padx=10, wraplength=380, justify="left").pack(anchor="w", pady=(0, 4))

        # ── Cookie Import ─────────────────────────────────────────────────
        tk.Frame(card, bg=C["border"], height=1).pack(fill="x", pady=(4, 0))
        tk.Label(card, text="Nhập Cookies từ Chrome DevTools  (bypass Cloudflare ngay)",
                 bg=C["bg2"], fg=C["accent3"], font=FONT_BOLD,
                 padx=10, pady=4).pack(anchor="w")

        cookie_hint = (
            "Chrome → F12 → Application → Cookies → grok.com\n"
            "→ Chọn tất cả (Ctrl+A) → Copy → Dán vào đây → Lưu\n"
            "Tool sẽ inject cf_clearance + sso vào browser mỗi lần chạy."
        )
        tk.Label(card, text=cookie_hint, bg=C["bg2"], fg=C["text2"],
                 font=("Segoe UI", 7), padx=10, justify="left").pack(anchor="w")

        # Textarea
        ta_frame = tk.Frame(card, bg=C["bg2"])
        ta_frame.pack(fill="x", padx=10, pady=(4, 2))
        self.cookie_text = tk.Text(
            ta_frame, bg=C["inputbg"], fg=C["text"],
            font=("Consolas", 7), wrap="none", relief="flat",
            insertbackground=C["text"], height=5,
            highlightthickness=1, highlightbackground=C["border"],
            highlightcolor=C["accent"],
        )
        self.cookie_text.pack(side="left", fill="both", expand=True)
        ck_sb = tk.Scrollbar(ta_frame, command=self.cookie_text.yview, bg=C["bg3"])
        ck_sb.pack(side="right", fill="y")
        self.cookie_text.configure(yscrollcommand=ck_sb.set)

        ck_btn_row = tk.Frame(card, bg=C["bg2"])
        ck_btn_row.pack(fill="x", padx=10, pady=(2, 8))
        self._small_btn(ck_btn_row, "💾  Lưu & Inject",
                        self._save_cookies).pack(side="left")
        self._small_btn(ck_btn_row, "🗑  Xóa cookies đã lưu",
                        self._clear_cookies).pack(side="left", padx=(6, 0))
        self.lbl_cookie_status = tk.Label(
            ck_btn_row, text="", bg=C["bg2"], fg=C["text2"], font=("Segoe UI", 7),
        )
        self.lbl_cookie_status.pack(side="left", padx=8)

        # Load trạng thái cookies hiện tại
        self._refresh_cookie_status()

        card.pack(fill="x", pady=(0, 8))

    # ── Right panel: gallery + log ────────────────────────────────────────

    def _build_right(self, parent):
        # Gallery state
        self._gallery_items: list = []
        self._gallery_idx: int = -1
        self._gallery_polling: bool = False
        self._gallery_known: set = set()

        # ── Mode-specific right panels (switch with left tab) ──────────────
        self.frame_right_film = tk.Frame(parent, bg=C["bg"])
        self.frame_right_film.pack(fill="x")           # film = default

        self.frame_right_sales = tk.Frame(parent, bg=C["bg"])
        self._build_sales_results_section(self.frame_right_sales)
        # frame_right_sales is NOT packed yet — shown when user clicks Bán hàng AI tab

        # ── Gallery card (inside frame_right_film) ────────────────────────
        gc = tk.Frame(self.frame_right_film, bg=C["bg2"],
                      highlightthickness=1, highlightbackground=C["border"])
        gc.pack(fill="x", pady=(0, 6))

        gh = tk.Frame(gc, bg=C["bg2"])
        gh.pack(fill="x", padx=10, pady=(6, 4))
        tk.Label(gh, text="🎬  Video đã tạo", bg=C["bg2"], fg=C["accent3"],
                 font=FONT_H2).pack(side="left")
        self._lbl_gallery_count = tk.Label(gh, text="0 clip", bg=C["bg2"],
                                            fg=C["text2"], font=FONT_BODY)
        self._lbl_gallery_count.pack(side="right")
        tk.Frame(gc, bg=C["border"], height=1).pack(fill="x")

        # Thumbnail — double-click opens video
        self._thumb_lbl = tk.Label(gc, bg="#0a0a1a", cursor="hand2",
                                   width=38, height=11)
        self._thumb_lbl.pack(pady=(6, 0))
        self._thumb_lbl.bind("<Double-Button-1>", lambda e: self._gallery_open())

        self._lbl_gname = tk.Label(gc, text="Chưa có clip", bg=C["bg2"],
                                    fg=C["text"], font=FONT_BOLD, anchor="center")
        self._lbl_gname.pack(pady=(4, 0))
        self._lbl_ginfo = tk.Label(gc, text="Double-click để mở video", bg=C["bg2"],
                                    fg=C["text2"], font=("Segoe UI", 7), anchor="center")
        self._lbl_ginfo.pack(pady=(0, 4))

        # Nav row
        nr = tk.Frame(gc, bg=C["bg2"])
        nr.pack(fill="x", padx=8, pady=(0, 4))
        tk.Button(nr, text="◀ Trước", bg=C["bg3"], fg=C["text"], font=FONT_BODY,
                  relief="flat", padx=10, pady=3, cursor="hand2",
                  activebackground=C["border"],
                  command=self._gallery_prev).pack(side="left")
        tk.Button(nr, text="▶ Mở", bg=C["accent"], fg="white", font=FONT_BOLD,
                  relief="flat", padx=14, pady=3, cursor="hand2",
                  activebackground=C["accent2"],
                  command=self._gallery_open).pack(side="left", padx=(6, 0))
        tk.Button(nr, text="Sau ▶", bg=C["bg3"], fg=C["text"], font=FONT_BODY,
                  relief="flat", padx=10, pady=3, cursor="hand2",
                  activebackground=C["border"],
                  command=self._gallery_next).pack(side="right")

        # Action row
        ar = tk.Frame(gc, bg=C["bg2"])
        ar.pack(fill="x", padx=8, pady=(0, 4))
        tk.Button(ar, text="🗑 Xóa", bg=C["red"], fg="white", font=FONT_BODY,
                  relief="flat", padx=10, pady=3, cursor="hand2",
                  activebackground="#dc2626",
                  command=self._gallery_delete).pack(side="left")
        tk.Button(ar, text="🔗 Ghép tất cả", bg=C["green"], fg="white",
                  font=FONT_BOLD, relief="flat", padx=14, pady=3, cursor="hand2",
                  activebackground="#059669",
                  command=self._gallery_reassemble).pack(side="right")

        # Generation progress (always packed, text/bar hidden when idle)
        self._gen_frame = tk.Frame(gc, bg=C["bg2"])
        self._gen_frame.pack(fill="x")
        self._lbl_gen = tk.Label(self._gen_frame, text="", bg=C["bg2"],
                                  fg=C["accent3"], font=("Segoe UI", 8))
        self._lbl_gen.pack(anchor="w", padx=10)
        self._gen_pbar = ttk.Progressbar(self._gen_frame,
                                          style="V.Horizontal.TProgressbar",
                                          mode="determinate", maximum=100)
        self._gen_pbar.pack(fill="x", padx=10, pady=(0, 6))

        # ── Log card ──────────────────────────────────────────────────────
        log_card = self._card(parent, "📋  Nhật ký")
        log_card.pack(fill="both", expand=True)

        sb = tk.Scrollbar(log_card, bg=C["bg3"])
        sb.pack(side="right", fill="y")
        self.log_text = tk.Text(
            log_card, bg=C["bg3"], fg=C["text"],
            font=FONT_MONO, wrap="word", relief="flat",
            state="disabled", padx=8, pady=6,
            insertbackground=C["text"],
            selectbackground=C["accent"],
            yscrollcommand=sb.set,
        )
        self.log_text.pack(fill="both", expand=True, padx=4)
        sb.configure(command=self.log_text.yview)

        for tag, color in LOG_TAGS.items():
            self.log_text.tag_configure(tag, foreground=color)

        ctrl = tk.Frame(log_card, bg=C["bg2"])
        ctrl.pack(fill="x", padx=4, pady=4)
        self._small_btn(ctrl, "Xóa log",   self._clear_log).pack(side="right", padx=4)
        self._small_btn(ctrl, "Mở output", self._open_output).pack(side="right")

        self._log("INFO", "Chào mừng! Dán kịch bản và bấm BẮT ĐẦU.")
        self._log("INFO", f"Output: {self.var_output_dir.get()}")

    # ── Sales results right panel ─────────────────────────────────────────

    def _build_sales_results_section(self, parent):
        gc = tk.Frame(parent, bg=C["bg2"],
                      highlightthickness=1, highlightbackground=C["border"])
        gc.pack(fill="x", pady=(0, 6))

        gh = tk.Frame(gc, bg=C["bg2"])
        gh.pack(fill="x", padx=10, pady=(6, 4))
        tk.Label(gh, text="🛍  Video aff đã ghép",
                 bg=C["bg2"], fg=C["accent3"], font=FONT_H2).pack(side="left")
        self._lbl_sales_result_count = tk.Label(
            gh, text="0 video", bg=C["bg2"], fg=C["text2"], font=FONT_BODY)
        self._lbl_sales_result_count.pack(side="right")
        tk.Frame(gc, bg=C["border"], height=1).pack(fill="x")

        tv_wrap = tk.Frame(gc, bg=C["bg2"])
        tv_wrap.pack(fill="both", padx=8, pady=(4, 4))

        cols = ("cluster", "file", "size")
        self._sales_results_tree = ttk.Treeview(
            tv_wrap, columns=cols, show="headings",
            height=10, style="Batch.Treeview",
        )
        self._sales_results_tree.heading("cluster", text="Cụm")
        self._sales_results_tree.heading("file",    text="File video")
        self._sales_results_tree.heading("size",    text="Size")
        self._sales_results_tree.column("cluster", width=100, anchor="w")
        self._sales_results_tree.column("file",    width=180, anchor="w")
        self._sales_results_tree.column("size",    width=60,  anchor="center", stretch=False)
        self._sales_results_tree.pack(side="left", fill="both", expand=True)
        self._sales_results_tree.tag_configure("done",    foreground=C["green"])
        self._sales_results_tree.tag_configure("missing", foreground=C["red"])
        self._sales_results_tree.bind("<Double-Button-1>",
                                       lambda e: self._sales_results_open())

        tv_vsb = ttk.Scrollbar(tv_wrap, orient="vertical",
                                command=self._sales_results_tree.yview)
        tv_vsb.pack(side="right", fill="y")
        self._sales_results_tree.configure(yscrollcommand=tv_vsb.set)

        btn_row = tk.Frame(gc, bg=C["bg2"])
        btn_row.pack(fill="x", padx=8, pady=(0, 8))
        tk.Button(btn_row, text="▶  Mở video",
                  bg=C["accent"], fg="white", font=FONT_BOLD,
                  relief="flat", padx=12, pady=4, cursor="hand2",
                  activebackground=C["accent2"],
                  command=self._sales_results_open).pack(side="left")
        tk.Button(btn_row, text="📁  Mở thư mục",
                  bg=C["bg3"], fg=C["text"], font=FONT_BODY,
                  relief="flat", padx=10, pady=4, cursor="hand2",
                  activebackground=C["border"],
                  command=self._sales_results_open_folder).pack(side="left", padx=(6, 0))
        tk.Button(btn_row, text="🔄 Refresh",
                  bg=C["bg3"], fg=C["text2"], font=FONT_BODY,
                  relief="flat", padx=10, pady=4, cursor="hand2",
                  activebackground=C["border"],
                  command=self._sales_refresh_results).pack(side="right")

    def _sales_refresh_results(self):
        """Cập nhật bảng video aff kết quả Sales AI từ cluster output_paths."""
        if not hasattr(self, "_sales_results_tree"):
            return
        tree = self._sales_results_tree
        tree.delete(*tree.get_children())

        total = 0
        for c in self._sales_clusters:
            cname = c.get("name", f"Cụm {c.get('id', '?')}")
            for p_str in c.get("output_paths", []):
                p = Path(p_str)
                exists = p.exists()
                size = f"{p.stat().st_size // 1024}KB" if exists else "—"
                tag = "done" if exists else "missing"
                tree.insert("", "end",
                            values=(cname, p.name, size),
                            tags=(tag,),
                            iid=p_str)
                total += 1

        self._lbl_sales_result_count.config(
            text=f"{total} video aff" if total else "Chưa có video nào")

    def _sales_results_open(self):
        sel = self._sales_results_tree.selection()
        if not sel:
            return
        p = Path(sel[0])   # iid = path string
        if p.exists():
            os.startfile(str(p))
        else:
            messagebox.showwarning("Không tìm thấy", f"File đã bị xóa:\n{p}")

    def _sales_results_open_folder(self):
        sel = self._sales_results_tree.selection()
        if sel:
            folder = Path(sel[0]).parent
        else:
            folder = Path(self.var_output_dir.get() or str(config.OUTPUT_DIR))
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(str(folder))

    # ── Bottom ────────────────────────────────────────────────────────────

    def _build_bottom(self):
        bot = tk.Frame(self, bg=C["bg3"])
        bot.pack(fill="x")
        tk.Frame(bot, bg=C["border"], height=1).pack(fill="x")

        inner = tk.Frame(bot, bg=C["bg3"])
        inner.pack(fill="x", padx=14, pady=10)

        # Progress
        prow = tk.Frame(inner, bg=C["bg3"])
        prow.pack(fill="x", pady=(0, 6))
        self.lbl_prog = tk.Label(prow, text="Sẵn sàng",
                                  bg=C["bg3"], fg=C["text2"], font=FONT_BODY)
        self.lbl_prog.pack(side="left")
        self.lbl_pct = tk.Label(prow, text="",
                                 bg=C["bg3"], fg=C["accent3"], font=FONT_BOLD)
        self.lbl_pct.pack(side="right")

        style = ttk.Style()
        style.theme_use("default")
        style.configure("V.Horizontal.TProgressbar",
                         background=C["accent"], troughcolor=C["bg2"],
                         bordercolor=C["bg2"])
        self.pbar = ttk.Progressbar(inner, style="V.Horizontal.TProgressbar",
                                     mode="determinate", maximum=100)
        self.pbar.pack(fill="x", pady=(0, 8))

        # Buttons
        brow = tk.Frame(inner, bg=C["bg3"])
        brow.pack(fill="x")

        self.btn_start = tk.Button(
            brow, text="▶  BẮT ĐẦU",
            bg=C["accent"], fg="white", font=("Segoe UI", 11, "bold"),
            relief="flat", padx=26, pady=8, cursor="hand2",
            command=self._on_start,
            activebackground=C["accent2"], activeforeground="white",
        )
        self.btn_start.pack(side="left")

        self.btn_stop = tk.Button(
            brow, text="■  DỪNG",
            bg=C["red"], fg="white", font=("Segoe UI", 11, "bold"),
            relief="flat", padx=18, pady=8, cursor="hand2",
            command=self._on_stop, state="disabled",
            activebackground="#dc2626", activeforeground="white",
        )
        self.btn_stop.pack(side="left", padx=(8, 0))

        self.btn_open = tk.Button(
            brow, text="📁  Mở video",
            bg=C["bg2"], fg=C["text"], font=FONT_BODY,
            relief="flat", padx=14, pady=8, cursor="hand2",
            command=self._open_last, state="disabled",
        )
        self.btn_open.pack(side="right")

        tk.Button(
            brow, text="📝  File Editor",
            bg=C["bg2"], fg=C["text2"], font=FONT_BODY,
            relief="flat", padx=10, pady=8, cursor="hand2",
            command=self._open_file_editor,
            activebackground=C["bg3"],
        ).pack(side="right", padx=(0, 6))

    # ──────────────────────────────────────────────────────────────────────
    # WIDGET HELPERS
    # ──────────────────────────────────────────────────────────────────────

    def _card(self, parent, title: str) -> tk.Frame:
        outer = tk.Frame(parent, bg=C["bg2"],
                         highlightthickness=1, highlightbackground=C["border"])
        outer.pack(fill="x", pady=(0, 8))
        tk.Label(outer, text=title, bg=C["bg2"], fg=C["accent3"],
                 font=FONT_H2, padx=10, pady=6).pack(anchor="w")
        tk.Frame(outer, bg=C["border"], height=1).pack(fill="x")
        return outer

    def _step_indicator(self, parent, num: int, title: str):
        """Renders a numbered step banner above a section card."""
        row = tk.Frame(parent, bg=C["bg"])
        row.pack(fill="x", pady=(8, 2))
        tk.Label(row, text=f" BƯỚC {num} ", bg=C["accent"], fg="white",
                 font=("Segoe UI", 8, "bold"), padx=4, pady=2).pack(side="left")
        tk.Label(row, text=title, bg=C["bg"], fg=C["text2"],
                 font=("Segoe UI", 8), padx=6).pack(side="left")
        tk.Frame(row, bg=C["border"], height=1).pack(side="left", fill="x", expand=True)

    def _build_video_settings_card(self, parent, show_tts: bool = True, show_duration: bool = True):
        card = self._card(parent, "⚙️  Cài đặt video")

        # Aspect ratio
        ar_row = tk.Frame(card, bg=C["bg2"])
        ar_row.pack(fill="x", padx=10, pady=(6, 4))
        tk.Label(ar_row, text="Tỷ lệ khung:", bg=C["bg2"], fg=C["text2"],
                 font=FONT_BODY, width=14, anchor="w").pack(side="left")
        for ratio, label in [("9:16", "9:16 Dọc"), ("16:9", "16:9 Ngang"),
                              ("1:1", "1:1 Vuông"), ("3:2", "3:2 Rộng"), ("2:3", "2:3 Cao")]:
            tk.Radiobutton(
                ar_row, text=label, variable=self.var_aspect_ratio, value=ratio,
                bg=C["bg2"], fg=C["text2"], selectcolor=C["bg3"],
                activebackground=C["bg2"], activeforeground=C["text"],
                font=("Segoe UI", 8), cursor="hand2",
            ).pack(side="left", padx=(0, 6))

        if show_tts:
            voice_row = tk.Frame(card, bg=C["bg2"])
            voice_row.pack(fill="x", padx=10, pady=(0, 4))
            tk.Label(voice_row, text="Giọng đọc:", bg=C["bg2"], fg=C["text2"],
                     font=FONT_BODY, width=14, anchor="w").pack(side="left")
            for val, lbl in [("female", "🎙 Nữ (HoaiMy)"), ("male", "🎙 Nam (NamMinh)")]:
                tk.Radiobutton(
                    voice_row, text=lbl, variable=self.var_tts_voice, value=val,
                    bg=C["bg2"], fg=C["text2"], selectcolor=C["bg3"],
                    activebackground=C["bg2"], activeforeground=C["text"],
                    font=("Segoe UI", 8), cursor="hand2",
                ).pack(side="left", padx=(0, 10))

        if show_duration:
            row2 = tk.Frame(card, bg=C["bg2"])
            row2.pack(fill="x", padx=10, pady=(0, 4))
            self._spin(row2, "Giây/cảnh:", self.var_scene_dur, 3, 60)

        self._file_pick(card, "Nhạc nền", self.var_music,
                        [("Audio", "*.mp3 *.m4a *.wav")],
                        hint="Để trống = chọn ngẫu nhiên từ assets/music/")
        self._file_pick(card, "Thư mục output", self.var_output_dir, [], folder=True)

    def _build_grok_section(self, parent):
        """Collapsible 'Kết nối Grok' section — Chrome + cookies + advanced."""
        outer = tk.Frame(parent, bg=C["bg2"],
                         highlightthickness=1, highlightbackground=C["border"])
        outer.pack(fill="x", pady=(8, 4))

        # Toggle header
        hdr = tk.Frame(outer, bg=C["bg2"])
        hdr.pack(fill="x")

        content = tk.Frame(outer, bg=C["bg2"])
        # Starts collapsed

        def _toggle():
            if content.winfo_ismapped():
                content.pack_forget()
                toggle_btn.config(text="▶  🔗 Kết nối Grok  (bấm để mở rộng)")
            else:
                content.pack(fill="x")
                toggle_btn.config(text="▼  🔗 Kết nối Grok  (bấm để thu gọn)")

        toggle_btn = tk.Button(
            hdr, text="▶  🔗 Kết nối Grok  (bấm để mở rộng)",
            bg=C["bg2"], fg=C["accent3"], font=FONT_BOLD,
            relief="flat", anchor="w", padx=10, pady=6,
            cursor="hand2", activebackground=C["bg3"],
            command=_toggle,
        )
        toggle_btn.pack(fill="x")

        # ── Content: Grok profile ─────────────────────────────────────────
        row3 = tk.Frame(content, bg=C["bg2"])
        row3.pack(fill="x", padx=10, pady=(6, 4))
        tk.Label(row3, text="Grok profile:", bg=C["bg2"], fg=C["text2"],
                 font=FONT_BODY, width=14, anchor="w").pack(side="left")
        tk.Entry(row3, textvariable=self.var_grok_profile, bg=C["inputbg"], fg=C["text"],
                 font=FONT_BODY, width=12, relief="flat",
                 insertbackground=C["text"],
                 highlightthickness=1, highlightbackground=C["border"]).pack(side="left")
        tk.Label(row3, text="(đổi tên = dùng TK Grok khác)",
                 bg=C["bg2"], fg=C["text2"], font=("Segoe UI", 7)).pack(side="left", padx=6)

        # ── Kết nối Chrome đang mở ★★★ ────────────────────────────────────
        tk.Frame(content, bg=C["border"], height=1).pack(fill="x", pady=(4, 0))
        tk.Label(content, text="Chống bot  ★★★ Kết nối Chrome đang mở",
                 bg=C["bg2"], fg=C["accent3"], font=FONT_BOLD,
                 padx=10, pady=4).pack(anchor="w")

        conn_row = tk.Frame(content, bg=C["bg2"])
        conn_row.pack(fill="x", padx=10, pady=(0, 4))
        tk.Checkbutton(
            conn_row, text="Dùng Chrome đang mở (port 9222)",
            variable=self.var_connect_existing,
            bg=C["bg2"], fg=C["text"], selectcolor=C["bg3"],
            activebackground=C["bg2"], activeforeground=C["text"],
            font=FONT_BOLD, cursor="hand2",
            command=self._on_connect_toggle,
        ).pack(side="left")
        self.btn_check_chrome = self._small_btn(
            conn_row, "🔍 Kiểm tra kết nối", self._check_chrome_connection
        )
        self.btn_check_chrome.pack(side="left", padx=(8, 0))
        self.lbl_connect_status = tk.Label(
            conn_row, text="", bg=C["bg2"], fg=C["text2"], font=("Segoe UI", 7)
        )
        self.lbl_connect_status.pack(side="left", padx=6)

        how_row = tk.Frame(content, bg=C["bg2"])
        how_row.pack(fill="x", padx=10, pady=(0, 4))
        self.btn_open_chrome = tk.Button(
            how_row, text="▶  Mở Chrome Grok",
            command=self._open_grok_chrome,
            bg=C["accent"], fg="white", font=FONT_BOLD,
            relief="flat", cursor="hand2", padx=12, pady=4,
            activebackground=C["accent2"], activeforeground="white",
        )
        self.btn_open_chrome.pack(side="left")
        self.lbl_chrome_status = tk.Label(
            how_row, text="(chưa mở)", bg=C["bg2"], fg=C["text2"], font=("Segoe UI", 8),
        )
        self.lbl_chrome_status.pack(side="left", padx=8)

        tk.Label(content,
                 text="Bấm 'Mở Chrome Grok' → Chrome riêng mở lên (Chrome đang dùng KHÔNG bị ảnh hưởng)\n"
                      "Lần đầu: đăng nhập X/Grok trong cửa sổ đó  |  Lần sau: tự nhớ session",
                 bg=C["bg2"], fg=C["green"], font=("Segoe UI", 7),
                 padx=10, wraplength=420, justify="left").pack(anchor="w", pady=(0, 6))

        # ── Chrome Profile thật (CDP mode) ───────────────────────────────
        tk.Frame(content, bg=C["border"], height=1).pack(fill="x", pady=(4, 0))
        tk.Label(content, text="Chrome Profile thật  ★★ (cần đóng Chrome trước)",
                 bg=C["bg2"], fg=C["accent3"], font=FONT_BOLD,
                 padx=10, pady=4).pack(anchor="w")
        hint_text = (
            "Chọn profile → tool copy cookies rồi mở Chrome qua cổng debug.\n"
            "Chrome khởi động BÌNH THƯỜNG — Cloudflare không phân biệt được.\n"
            "Quy trình: 1) Đóng Chrome  2) Chọn profile  3) Nhấn Sync  4) BẮT ĐẦU"
        )
        tk.Label(content, text=hint_text, bg=C["bg2"], fg=C["text2"],
                 font=("Segoe UI", 7), padx=10, justify="left").pack(anchor="w")

        cp_row = tk.Frame(content, bg=C["bg2"])
        cp_row.pack(fill="x", padx=10, pady=(4, 2))
        tk.Label(cp_row, text="Chrome profile:", bg=C["bg2"], fg=C["text2"],
                 font=FONT_BODY, width=14, anchor="w").pack(side="left")
        self._chrome_profiles = config.find_chrome_profiles()
        display_list = ["— Không dùng (profile riêng) —"] + list(self._chrome_profiles.keys())
        self.cb_chrome = ttk.Combobox(
            cp_row, textvariable=self.var_chrome_profile,
            values=display_list, state="readonly", width=28, font=FONT_BODY,
        )
        self.cb_chrome.set(display_list[0])
        self.cb_chrome.pack(side="left")
        self._small_btn(cp_row, "↻", self._refresh_chrome_profiles).pack(side="left", padx=(4, 0))

        sync_row = tk.Frame(content, bg=C["bg2"])
        sync_row.pack(fill="x", padx=10, pady=(2, 6))
        self._small_btn(
            sync_row, "🔄  Sync cookies (đóng Chrome trước)",
            self._sync_chrome_profile_now,
        ).pack(side="left")
        self.lbl_sync_status = tk.Label(
            sync_row, text="", bg=C["bg2"], fg=C["text2"], font=("Segoe UI", 7),
        )
        self.lbl_sync_status.pack(side="left", padx=8)

        tk.Label(content,
                 text="ℹ  Khi chọn profile: tool tự mở Chrome riêng (port 9222), KHÔNG ảnh hưởng Chrome đang mở.",
                 bg=C["bg2"], fg=C["text2"], font=("Segoe UI", 7),
                 padx=10, wraplength=380, justify="left").pack(anchor="w", pady=(0, 4))

        # ── Cookie Import ─────────────────────────────────────────────────
        tk.Frame(content, bg=C["border"], height=1).pack(fill="x", pady=(4, 0))
        tk.Label(content, text="Nhập Cookies từ Chrome DevTools  (bypass Cloudflare ngay)",
                 bg=C["bg2"], fg=C["accent3"], font=FONT_BOLD,
                 padx=10, pady=4).pack(anchor="w")
        cookie_hint = (
            "Chrome → F12 → Application → Cookies → grok.com\n"
            "→ Chọn tất cả (Ctrl+A) → Copy → Dán vào đây → Lưu\n"
            "Tool sẽ inject cf_clearance + sso vào browser mỗi lần chạy."
        )
        tk.Label(content, text=cookie_hint, bg=C["bg2"], fg=C["text2"],
                 font=("Segoe UI", 7), padx=10, justify="left").pack(anchor="w")

        ta_frame = tk.Frame(content, bg=C["bg2"])
        ta_frame.pack(fill="x", padx=10, pady=(4, 2))
        self.cookie_text = tk.Text(
            ta_frame, bg=C["inputbg"], fg=C["text"],
            font=("Consolas", 7), wrap="none", relief="flat",
            insertbackground=C["text"], height=5,
            highlightthickness=1, highlightbackground=C["border"],
            highlightcolor=C["accent"],
        )
        self.cookie_text.pack(side="left", fill="both", expand=True)
        ck_sb = tk.Scrollbar(ta_frame, command=self.cookie_text.yview, bg=C["bg3"])
        ck_sb.pack(side="right", fill="y")
        self.cookie_text.configure(yscrollcommand=ck_sb.set)

        ck_btn_row = tk.Frame(content, bg=C["bg2"])
        ck_btn_row.pack(fill="x", padx=10, pady=(2, 8))
        self._small_btn(ck_btn_row, "💾  Lưu & Inject",
                        self._save_cookies).pack(side="left")
        self._small_btn(ck_btn_row, "🗑  Xóa cookies đã lưu",
                        self._clear_cookies).pack(side="left", padx=(6, 0))
        self.lbl_cookie_status = tk.Label(
            ck_btn_row, text="", bg=C["bg2"], fg=C["text2"], font=("Segoe UI", 7),
        )
        self.lbl_cookie_status.pack(side="left", padx=8)

        self._refresh_cookie_status()

    def _open_text_popup(self, title: str, get_fn, set_fn=None, readonly=False):
        """Popup với text area lớn có scroll — dùng chung cho kịch bản / mô tả."""
        pop = tk.Toplevel(self)
        pop.title(title)
        pop.geometry("760x540")
        pop.configure(bg=C["bg"])
        pop.transient(self)
        pop.grab_set()
        pop.resizable(True, True)

        # Text + scrollbar
        frm = tk.Frame(pop, bg=C["bg"])
        frm.pack(fill="both", expand=True, padx=10, pady=(10, 0))
        sb = tk.Scrollbar(frm, bg=C["bg3"])
        sb.pack(side="right", fill="y")
        txt = tk.Text(
            frm, bg=C["inputbg"], fg=C["text"], font=FONT_MONO,
            wrap="word", relief="flat", insertbackground=C["text"],
            selectbackground=C["accent"], padx=8, pady=6,
            highlightthickness=1, highlightbackground=C["border"],
            state="normal" if not readonly else "disabled",
            yscrollcommand=sb.set,
        )
        txt.pack(side="left", fill="both", expand=True)
        sb.configure(command=txt.yview)
        content = get_fn()
        txt.insert("1.0", content)
        txt.focus_set()

        # Buttons
        btn_row = tk.Frame(pop, bg=C["bg"])
        btn_row.pack(fill="x", padx=10, pady=8)
        if not readonly and set_fn:
            def _save():
                set_fn(txt.get("1.0", "end-1c"))
                pop.destroy()
            tk.Button(btn_row, text="💾 Lưu & Đóng", bg=C["accent"], fg="white",
                      font=FONT_BOLD, relief="flat", padx=18, pady=6, cursor="hand2",
                      activebackground=C["accent2"], command=_save).pack(side="left")
            tk.Label(btn_row, text="Ctrl+S để lưu nhanh", bg=C["bg"],
                     fg=C["text2"], font=("Segoe UI", 7)).pack(side="left", padx=8)
            pop.bind("<Control-s>", lambda e: _save())
        tk.Button(btn_row, text="✕ Đóng", bg=C["bg3"], fg=C["text"],
                  font=FONT_BODY, relief="flat", padx=14, pady=6, cursor="hand2",
                  activebackground=C["border"], command=pop.destroy).pack(side="right")
        pop.bind("<Escape>", lambda e: pop.destroy())

    def _labeled_entry(self, parent, label: str, var: tk.StringVar):
        row = tk.Frame(parent, bg=C["bg2"])
        row.pack(fill="x", padx=10, pady=(6, 2))
        tk.Label(row, text=label, bg=C["bg2"], fg=C["text2"],
                 font=FONT_BODY, width=20, anchor="w").pack(side="left")
        tk.Entry(row, textvariable=var, bg=C["inputbg"], fg=C["text"],
                 insertbackground=C["text"], font=FONT_BODY, relief="flat",
                 highlightthickness=1, highlightbackground=C["border"],
                 highlightcolor=C["accent"]).pack(side="left", fill="x", expand=True, ipady=4)

    def _file_pick(self, parent, label: str, var: tk.StringVar,
                   filetypes: list, folder: bool = False, hint: str = ""):
        row = tk.Frame(parent, bg=C["bg2"])
        row.pack(fill="x", padx=10, pady=(6, 2))
        tk.Label(row, text=label, bg=C["bg2"], fg=C["text2"],
                 font=FONT_BODY, width=20, anchor="w").pack(side="left")
        tk.Entry(row, textvariable=var, bg=C["inputbg"], fg=C["text"],
                 insertbackground=C["text"], font=("Segoe UI", 8), relief="flat",
                 highlightthickness=1, highlightbackground=C["border"]).pack(
                     side="left", fill="x", expand=True, ipady=3)
        def browse():
            p = filedialog.askdirectory() if folder else filedialog.askopenfilename(filetypes=filetypes)
            if p:
                var.set(p)
        tk.Button(row, text="...", bg=C["accent"], fg="white", font=FONT_BOLD,
                  relief="flat", padx=6, cursor="hand2", command=browse).pack(side="left", padx=(4, 0))
        if hint:
            tk.Label(parent, text=f"  ℹ {hint}", bg=C["bg2"], fg=C["text2"],
                     font=("Segoe UI", 7), padx=10).pack(anchor="w")

    def _spin(self, parent, label: str, var: tk.IntVar, lo: int, hi: int):
        tk.Label(parent, text=label, bg=parent["bg"], fg=C["text2"],
                 font=FONT_BODY).pack(side="left")
        tk.Spinbox(parent, from_=lo, to=hi, textvariable=var,
                   bg=C["inputbg"], fg=C["text"], buttonbackground=C["bg3"],
                   font=FONT_BODY, relief="flat", width=4,
                   highlightthickness=1, highlightbackground=C["border"]).pack(side="left", padx=(4, 16))

    def _small_btn(self, parent, text: str, cmd) -> tk.Button:
        return tk.Button(parent, text=text, bg=C["bg3"], fg=C["text2"],
                         font=("Segoe UI", 8), relief="flat", padx=8, pady=2,
                         cursor="hand2", command=cmd, activebackground=C["border"])

    def _make_image_thumb(self, path: str, size: tuple[int, int] = (120, 120)):
        """Tạo PhotoImage thumbnail nền tối, trả None nếu ảnh lỗi/không tồn tại."""
        if not path:
            return None
        p = Path(path)
        if not p.exists() or not p.is_file():
            return None
        try:
            from PIL import Image, ImageTk
            img = Image.open(str(p)).convert("RGBA")
            img.thumbnail(size, Image.LANCZOS)
            bg = Image.new("RGBA", size, (10, 10, 26, 255))
            bg.alpha_composite(img, ((size[0] - img.width) // 2,
                                     (size[1] - img.height) // 2))
            return ImageTk.PhotoImage(bg.convert("RGB"))
        except Exception:
            return None

    def _set_image_preview(
        self,
        label: tk.Label,
        path: str,
        size: tuple[int, int] = (120, 120),
        empty_text: str = "Chưa chọn",
    ):
        tk_img = self._make_image_thumb(path, size)
        if tk_img:
            label.configure(image=tk_img, text="")
            label._img = tk_img
        else:
            label.configure(
                image="", text=empty_text, fg=C["text2"],
                font=("Segoe UI", 8), justify="center",
            )
            label._img = None

    def _open_image_file(self, path: str):
        p = Path(path or "")
        if not p.exists():
            return
        try:
            if hasattr(os, "startfile"):
                os.startfile(str(p))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(p)])
            else:
                subprocess.Popen(["xdg-open", str(p)])
        except Exception as e:
            messagebox.showwarning("Không mở được ảnh", str(e))

    # ──────────────────────────────────────────────────────────────────────
    # LOGIC
    # ──────────────────────────────────────────────────────────────────────

    def _import_script_file(self):
        path = filedialog.askopenfilename(
            filetypes=[("Text/Markdown", "*.txt *.md"), ("All", "*.*")]
        )
        if path:
            try:
                text = Path(path).read_text(encoding="utf-8")
                self.script_text.config(fg=C["text"])
                self.script_text.delete("1.0", "end")
                self.script_text.insert("1.0", text)
                self._preview_scenes()
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không đọc được file:\n{e}")

    def _preview_scenes(self):
        text = self.script_text.get("1.0", "end-1c").strip()
        scenes, fmt = auto_parse(text, default_duration=self.var_scene_dur.get())
        if scenes:
            n = len(scenes)
            preview = preview_scenes(scenes, fmt)
            img_hint = f"\n  → Cần {n} ảnh nhân vật: 1.jpg, 2.jpg ... {n}.jpg (hoặc 1 file dùng chung)"
            display = preview[:200] + ("..." if len(preview) > 200 else "") + img_hint
            self.lbl_scene_count.config(text=display)
            self._log("INFO", f"Preview: {n} canh [{fmt}] — can {n} anh nhan vat")
        else:
            self.lbl_scene_count.config(text="Chưa nhận diện được cảnh nào")

    def _auto_launch_chrome(self):
        """Gọi khi tool khởi động: tự mở Chrome Grok + tick checkbox."""
        import socket
        # Nếu port đã mở sẵn → tick checkbox, log thông báo
        try:
            s = socket.create_connection(("127.0.0.1", 9222), timeout=0.5)
            s.close()
            self.var_connect_existing.set(True)
            self.lbl_chrome_status.config(text="✓ Đang chạy!", fg=C["green"])
            self.lbl_connect_status.config(text="✓ Port 9222 sẵn sàng", fg=C["green"])
            self._log("SUCCESS", "Chrome Grok da chay san (port 9222) – san sang!")
            return
        except OSError:
            pass

        # Chưa mở → tự mở Chrome Grok
        self._log("INFO", "Tu dong mo Chrome Grok...")
        self.var_connect_existing.set(True)   # Pre-tick để khi chrome sẵn là dùng ngay
        self._open_grok_chrome()

    def _open_grok_chrome(self):
        """Mở Chrome riêng cho Grok (không đụng Chrome chính đang dùng)."""
        import socket, subprocess
        from pathlib import Path

        # Kiểm tra port đã mở chưa
        try:
            s = socket.create_connection(("127.0.0.1", 9222), timeout=0.5)
            s.close()
            self.lbl_chrome_status.config(text="✓ Đang chạy!", fg=C["green"])
            self.lbl_connect_status.config(text="✓ Port 9222 sẵn sàng", fg=C["green"])
            self._log("SUCCESS", "Chrome Grok da mo san (port 9222 ready)")
            return
        except OSError:
            pass

        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
        chrome_exe = next((p for p in chrome_paths if Path(p).exists()), None)
        if not chrome_exe:
            self.lbl_chrome_status.config(text="✗ Không tìm thấy Chrome", fg=C["red"])
            return

        # Dùng data dir RIÊNG → chạy song song với Chrome chính
        grok_data = str(Path(__file__).parent / ".browser_data" / "grok_chrome")
        Path(grok_data).mkdir(parents=True, exist_ok=True)

        self.lbl_chrome_status.config(text="Đang mở...", fg=C["yellow"])
        self.btn_open_chrome.config(state="disabled")
        self.update()

        subprocess.Popen(
            [chrome_exe,
             "--remote-debugging-port=9222",
             f"--user-data-dir={grok_data}",
             "--no-first-run",
             "--no-default-browser-check",
             "--window-size=1200,900",
             "https://grok.com"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._log("INFO", "Chrome Grok dang mo (data dir rieng, Chrome chinh khong bi dong)")

        # Chờ port mở rồi cập nhật status
        def _wait_port():
            import time
            for _ in range(20):
                time.sleep(0.8)
                try:
                    s = socket.create_connection(("127.0.0.1", 9222), timeout=0.5)
                    s.close()
                    self.after(0, lambda: [
                        self.lbl_chrome_status.config(text="✓ Đang chạy!", fg=C["green"]),
                        self.lbl_connect_status.config(text="✓ Port 9222 sẵn sàng", fg=C["green"]),
                        self.btn_open_chrome.config(state="normal"),
                        self.var_connect_existing.set(True),
                        self._log("SUCCESS", "Chrome Grok san sang! Nhan BAT DAU la chay duoc."),
                    ])
                    return
                except OSError:
                    pass
            self.after(0, lambda: [
                self.lbl_chrome_status.config(text="✗ Không mở được", fg=C["red"]),
                self.btn_open_chrome.config(state="normal"),
            ])

        import threading
        threading.Thread(target=_wait_port, daemon=True).start()

    def _on_connect_toggle(self):
        """Khi bật/tắt checkbox 'Kết nối Chrome đang mở'."""
        if self.var_connect_existing.get():
            self._check_chrome_connection()
        else:
            self.lbl_connect_status.config(text="", fg=C["text2"])

    def _check_chrome_connection(self):
        """Kiểm tra Chrome đang chạy trên port 9222."""
        import socket
        try:
            s = socket.create_connection(("127.0.0.1", 9222), timeout=1)
            s.close()
            self.lbl_connect_status.config(
                text="✓ Chrome đang chạy trên port 9222!", fg=C["green"]
            )
            self._log("SUCCESS", "Chrome debug port 9222: READY")
        except OSError:
            self.lbl_connect_status.config(
                text="✗ Chưa thấy Chrome — bấm 'Mở Chrome Grok'", fg=C["red"]
            )
            self._log("WARNING", "Chrome debug port 9222: KHONG TIM THAY – bam 'Mo Chrome Grok'")

    def _save_cookies(self):
        """Parse cookies từ textarea và lưu vào file."""
        text = self.cookie_text.get("1.0", "end-1c").strip()
        if not text:
            self.lbl_cookie_status.config(text="Chua dan cookies vao", fg=C["yellow"])
            return
        cookies = config.parse_devtools_cookies(text)
        if not cookies:
            self.lbl_cookie_status.config(text="Khong parse duoc – kiem tra dinh dang", fg=C["red"])
            return
        config.save_cookies(cookies)
        # Highlight key cookies
        names = {c["name"] for c in cookies}
        has_cf = "cf_clearance" in names
        has_sso = "sso" in names or "sso-rw" in names
        status = f"Luu {len(cookies)} cookies"
        if has_cf:  status += " | ✓ cf_clearance"
        if has_sso: status += " | ✓ sso"
        self.lbl_cookie_status.config(text=status, fg=C["green"])
        self._log("SUCCESS", f"Cookie import: {status}")

    def _clear_cookies(self):
        """Xóa cookies đã lưu."""
        if config.GROK_COOKIES_FILE.exists():
            config.GROK_COOKIES_FILE.unlink()
        self.cookie_text.delete("1.0", "end")
        self.lbl_cookie_status.config(text="Da xoa cookies", fg=C["text2"])

    def _refresh_cookie_status(self):
        """Hiển thị trạng thái cookies đã lưu."""
        cookies = config.load_saved_cookies()
        if not cookies:
            self.lbl_cookie_status.config(text="Chua co cookies", fg=C["text2"])
            return
        names = {c["name"] for c in cookies}
        has_cf  = "cf_clearance" in names
        has_sso = "sso" in names or "sso-rw" in names
        status = f"{len(cookies)} cookies da luu"
        if has_cf:  status += " ✓ cf_clearance"
        if has_sso: status += " ✓ sso"
        self.lbl_cookie_status.config(text=status, fg=C["green"])

    # ──────────────────────────────────────────────────────────────────────
    # SETTINGS PERSISTENCE
    # ──────────────────────────────────────────────────────────────────────

    def _load_settings(self):
        s = config.load_app_settings()
        # user_config.py (Python source) ghi đè JSON cho các key user-facing
        uc = config.load_user_config()
        for k, v in uc.items():
            s[k] = v  # user_config.py takes precedence
        if not s:
            return
        if "char_desc" in s:      self.var_char_desc.set(s["char_desc"])
        if "char_img" in s:       self.var_char_img.set(s["char_img"])
        if "product" in s:        self.var_product.set(s["product"])
        if "product_img" in s:    self.var_product_img.set(s["product_img"])
        if "music" in s:          self.var_music.set(s["music"])
        if "output_dir" in s:     self.var_output_dir.set(s["output_dir"])
        if "scene_dur" in s:      self.var_scene_dur.set(s["scene_dur"])
        if "scene_count" in s:    self.var_scene_count.set(s["scene_count"])
        if "grok_profile" in s:   self.var_grok_profile.set(s["grok_profile"])
        if "aspect_ratio" in s:   self.var_aspect_ratio.set(s["aspect_ratio"])
        if "tts_voice" in s:      self.var_tts_voice.set(s["tts_voice"])
        if "main_mode" in s:      self._switch_main_mode(s["main_mode"])
        if "connect_existing" in s:
            self.var_connect_existing.set(s["connect_existing"])
        if "sales_clips_per_video" in s:
            self.var_sales_clips_per_video.set(max(1, int(s.get("sales_clips_per_video") or 3)))
        if "sales_parallel_tabs" in s:
            self.var_sales_parallel_tabs.set(max(1, int(s.get("sales_parallel_tabs") or 2)))
        if "sales_preset" in s:
            self.var_sales_preset.set(s.get("sales_preset") or "TikTok Shop")
        if "sales_goal" in s:
            self.var_sales_goal.set(s.get("sales_goal") or "Chốt đơn")
        if "sales_audience" in s:
            self.var_sales_audience.set(s.get("sales_audience") or "")
        if "sales_offer" in s:
            self.var_sales_offer.set(s.get("sales_offer") or "")
        if "sales_cta" in s:
            self.var_sales_cta.set(s.get("sales_cta") or DEFAULT_CTA)
        if "sales_auto_prompt" in s:
            self.var_sales_auto_prompt.set(bool(s.get("sales_auto_prompt")))
        if "chrome_profile_display" in s and s["chrome_profile_display"]:
            display = s["chrome_profile_display"]
            if display in list(self.cb_chrome["values"]):
                self.cb_chrome.set(display)
        if "batch_projects" in s and s["batch_projects"]:
            from script_parser import auto_parse
            self._batch_projects.clear()
            for i, p in enumerate(s["batch_projects"], 1):
                p["id"] = i
                if "_n_scenes" not in p:
                    try:
                        sf = p.get("script_file", "")
                        st = p.get("script_text", "")
                        text = (Path(sf).read_text(encoding="utf-8")
                                if sf and Path(sf).exists() else st)
                        sc, _ = auto_parse(text, default_duration=self.var_scene_dur.get())
                        p["_n_scenes"] = len(sc)
                    except Exception:
                        p["_n_scenes"] = 0
                self._batch_projects.append(p)
            self._batch_refresh_tree()
        if "sales_clusters" in s and s["sales_clusters"]:
            self._sales_clusters = s["sales_clusters"]
            for i, c in enumerate(self._sales_clusters, 1):
                c["id"] = i
            self._sales_refresh_tree()
        if "sales_prompt" in s and s["sales_prompt"]:
            self._sales_prompt_txt.delete("1.0", "end")
            self._sales_prompt_txt.insert("1.0", s["sales_prompt"])
            for c in self._sales_clusters:
                self._sales_get_items(c, self._sales_default_prompt())
            self._sales_refresh_tree()

    def _save_settings(self):
        s = config.load_app_settings()
        # Strip internal-only keys before saving batch projects
        batch_save = [
            {k: v for k, v in p.items() if not k.startswith("_")}
            for p in self._batch_projects
        ]
        sales_clusters_save = [
            {k: v for k, v in c.items() if k not in ("done_count",)}
            for c in self._sales_clusters
        ]
        user_data = {
            "char_desc":    self.var_char_desc.get(),
            "char_img":     self.var_char_img.get(),
            "scene_dur":    self.var_scene_dur.get(),
            "output_dir":   self.var_output_dir.get(),
            "music":        self.var_music.get(),
            "aspect_ratio": self.var_aspect_ratio.get(),
            "tts_voice":    self.var_tts_voice.get(),
            "sales_preset": self.var_sales_preset.get(),
            "sales_goal":   self.var_sales_goal.get(),
            "sales_cta":    self.var_sales_cta.get(),
        }
        s.update({
            "main_mode":              self.var_main_mode.get(),
            "aspect_ratio":           self.var_aspect_ratio.get(),
            "tts_voice":              self.var_tts_voice.get(),
            "char_desc":              self.var_char_desc.get(),
            "char_img":               self.var_char_img.get(),
            "product":                self.var_product.get(),
            "product_img":            self.var_product_img.get(),
            "music":                  self.var_music.get(),
            "output_dir":             self.var_output_dir.get(),
            "scene_dur":              self.var_scene_dur.get(),
            "scene_count":            self.var_scene_count.get(),
            "grok_profile":           self.var_grok_profile.get(),
            "chrome_profile_display": self.cb_chrome.get(),
            "connect_existing":       self.var_connect_existing.get(),
            "batch_projects":         batch_save,
            "sales_clusters":         sales_clusters_save,
            "sales_prompt":           self._sales_prompt_txt.get("1.0", "end-1c").strip(),
            "sales_clips_per_video":  self.var_sales_clips_per_video.get(),
            "sales_parallel_tabs":    self.var_sales_parallel_tabs.get(),
            "sales_preset":           self.var_sales_preset.get(),
            "sales_goal":             self.var_sales_goal.get(),
            "sales_audience":         self.var_sales_audience.get(),
            "sales_offer":            self.var_sales_offer.get(),
            "sales_cta":              self.var_sales_cta.get(),
            "sales_auto_prompt":      self.var_sales_auto_prompt.get(),
        })
        config.save_app_settings(s)
        # Lưu song song vào user_config.py (Python source, đọc/chỉnh tay được)
        config.save_user_config(user_data)

    def _on_close(self):
        self._save_settings()
        self.destroy()

    def _open_prompts_dialog(self):
        dlg = tk.Toplevel(self)
        dlg.title("✏ Chỉnh sửa Prompts")
        dlg.geometry("800x580")
        dlg.configure(bg=C["bg"])
        dlg.grab_set()

        tk.Label(dlg, text="✏  Chỉnh sửa Prompts",
                 bg=C["bg"], fg=C["accent3"], font=FONT_TITLE,
                 padx=16, pady=10).pack(anchor="w")
        tk.Frame(dlg, bg=C["accent"], height=2).pack(fill="x")

        notebook = ttk.Notebook(dlg)
        notebook.pack(fill="both", expand=True, padx=10, pady=8)

        st = ttk.Style()
        st.configure("TNotebook", background=C["bg"])
        st.configure("TNotebook.Tab", background=C["tab_inact"], foreground=C["text2"],
                     padding=[10, 4], font=FONT_BODY)
        st.map("TNotebook.Tab",
               background=[("selected", C["tab_act"])],
               foreground=[("selected", "white")])

        prompt_info = [
            ("film_prompt",           "Prompt Phim (Grok)"),
            ("sales_prompt_framework", "Prompt Sales AI (Grok)"),
            ("chatgpt_script_prompt", "Prompt Kịch bản (ChatGPT)"),
        ]
        prompt_tabs: dict[str, tk.Text] = {}

        for key, label in prompt_info:
            frame = tk.Frame(notebook, bg=C["bg2"])
            notebook.add(frame, text=label)
            ta_frame = tk.Frame(frame, bg=C["bg2"])
            ta_frame.pack(fill="both", expand=True, padx=8, pady=8)
            ta = tk.Text(
                ta_frame, bg=C["inputbg"], fg=C["text"],
                font=("Consolas", 8), wrap="word", relief="flat",
                insertbackground=C["text"],
                selectbackground=C["accent"],
                padx=6, pady=4,
                highlightthickness=1, highlightbackground=C["border"],
                highlightcolor=C["accent"],
            )
            ta.pack(side="left", fill="both", expand=True)
            vsb = tk.Scrollbar(ta_frame, command=ta.yview, bg=C["bg3"])
            vsb.pack(side="right", fill="y")
            ta.configure(yscrollcommand=vsb.set)
            ta.insert("1.0", config.get_prompt(key))
            prompt_tabs[key] = ta

        btn_row = tk.Frame(dlg, bg=C["bg"])
        btn_row.pack(fill="x", padx=10, pady=(0, 10))

        status_lbl = tk.Label(btn_row, text="", bg=C["bg"], fg=C["green"],
                              font=("Segoe UI", 8))
        status_lbl.pack(side="right", padx=8)

        def _save():
            s = config.load_app_settings()
            prompts = s.get("prompts", {})
            for k, ta in prompt_tabs.items():
                val = ta.get("1.0", "end-1c").strip()
                if val:
                    prompts[k] = val
            s["prompts"] = prompts
            config.save_app_settings(s)
            status_lbl.config(text="✓ Đã lưu!", fg=C["green"])
            dlg.after(2000, lambda: status_lbl.config(text=""))

        def _reset_tab():
            idx = notebook.index(notebook.select())
            key, label = prompt_info[idx]
            default = config._DEFAULT_PROMPTS.get(key, "")
            ta = prompt_tabs[key]
            ta.delete("1.0", "end")
            ta.insert("1.0", default)
            status_lbl.config(
                text=f"Reset '{label}' về mặc định (chưa lưu)",
                fg=C["yellow"]
            )
            dlg.after(3000, lambda: status_lbl.config(text=""))

        tk.Button(btn_row, text="💾  Lưu",
                  bg=C["accent"], fg="white", font=FONT_BOLD,
                  relief="flat", padx=14, pady=6, cursor="hand2",
                  activebackground=C["accent2"], activeforeground="white",
                  command=_save).pack(side="left")
        tk.Button(btn_row, text="↺  Reset tab này",
                  bg=C["bg3"], fg=C["text2"], font=FONT_BODY,
                  relief="flat", padx=10, pady=6, cursor="hand2",
                  activebackground=C["border"],
                  command=_reset_tab).pack(side="left", padx=(6, 0))
        tk.Button(btn_row, text="Đóng",
                  bg=C["bg3"], fg=C["text2"], font=FONT_BODY,
                  relief="flat", padx=10, pady=6, cursor="hand2",
                  activebackground=C["border"],
                  command=dlg.destroy).pack(side="left", padx=(6, 0))

    def _refresh_chrome_profiles(self):
        """Quét lại Chrome profiles trên máy."""
        self._chrome_profiles = config.find_chrome_profiles()
        display_list = ["— Không dùng (profile riêng) —"] + list(self._chrome_profiles.keys())
        self.cb_chrome["values"] = display_list
        if self.cb_chrome.get() not in display_list:
            self.cb_chrome.set(display_list[0])
        n = len(self._chrome_profiles)
        self.lbl_sync_status.config(
            text=f"Tìm thấy {n} profile" if n else "Không tìm thấy Chrome profile",
            fg=C["green"] if n else C["yellow"],
        )

    def _get_selected_chrome_profile(self) -> Optional[str]:
        """Trả về folder name của profile được chọn, hoặc None nếu không dùng."""
        selected = self.cb_chrome.get()
        if not selected or "Không dùng" in selected:
            return None
        return self._chrome_profiles.get(selected)

    def _sync_chrome_profile_now(self):
        """Sync Chrome cookies vào tool ngay lập tức (gọi từ UI)."""
        profile = self._get_selected_chrome_profile()
        if not profile:
            self.lbl_sync_status.config(
                text="Chọn một Chrome profile trước", fg=C["yellow"]
            )
            return
        self.lbl_sync_status.config(text="Đang sync...", fg=C["text2"])
        self.update_idletasks()

        dest = config.BROWSER_DATA_DIR / "chrome_sync"
        ok, msg = config.sync_chrome_profile(profile, dest)
        self.lbl_sync_status.config(
            text=msg[:60], fg=C["green"] if ok else C["red"]
        )
        if ok:
            self._log("SUCCESS", f"Chrome sync: {msg}")
        else:
            self._log("WARNING", f"Chrome sync: {msg}")

    def _on_start(self):
        if self.var_main_mode.get() == "sales":
            self._on_start_sales()
        else:
            self._on_start_batch()

    def _on_stop(self):
        if self.orch:
            self.orch.stop()
        self.btn_stop.config(state="disabled")

    def _on_progress(self, current: int, total: int, label: str, sub: bool = False):
        pct = int((current / max(total, 1)) * 100)
        self.after(0, lambda: self._apply_progress(pct, label))

    def _apply_progress(self, pct: int, label: str):
        self.pbar["value"] = pct
        self.lbl_prog.config(text=label)
        self.lbl_pct.config(text=f"{pct}%" if pct else "")
        if hasattr(self, "_gen_pbar"):
            if 0 < pct < 100:
                self._lbl_gen.config(text=f"⏳ {label}")
                self._gen_pbar["value"] = pct
            else:
                self._lbl_gen.config(text="")
                self._gen_pbar["value"] = 0

    def _on_status(self, status: str):
        self.after(0, lambda: self._apply_status(status))

    def _apply_status(self, status: str):
        if status == "idle" or status.startswith("done:"):
            self._running = False
            self._stop_gallery_poll()
            self.btn_start.config(state="normal")
            self.btn_stop.config(state="disabled")
            if status.startswith("done:"):
                self._last_output = status[5:]
                self.btn_open.config(state="normal")
                self.pbar["value"] = 100
                self.lbl_prog.config(text="Hoàn thành!")
                self.lbl_pct.config(text="100%")

    # ──────────────────────────────────────────────────────────────────────
    # LOG
    # ──────────────────────────────────────────────────────────────────────

    def _poll_log(self):
        try:
            while True:
                entry = self.log_queue.get_nowait()
                self._log(entry["level"], f"[{entry['time']}] {entry['message']}")
        except queue.Empty:
            pass
        self.after(200, self._poll_log)

    def _log(self, level: str, msg: str):
        self.log_text.config(state="normal")
        tag = level if level in LOG_TAGS else "INFO"
        self.log_text.insert("end", msg + "\n", tag)
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _clear_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

    def _open_output(self):
        p = self.var_output_dir.get() or str(config.OUTPUT_DIR)
        Path(p).mkdir(parents=True, exist_ok=True)
        os.startfile(p)

    def _open_last(self):
        if self._last_output and Path(self._last_output).exists():
            os.startfile(self._last_output)
        else:
            self._open_output()

    def _open_file_editor(self):
        """Mở dialog xem và sửa trực tiếp file dự án."""
        dlg = tk.Toplevel(self)
        dlg.title("📝  File Editor — Video Factory AI")
        dlg.geometry("1000x660")
        dlg.configure(bg=C["bg"])
        dlg.grab_set()

        tk.Label(dlg, text="📝  File Editor",
                 bg=C["bg"], fg=C["accent3"], font=FONT_TITLE,
                 padx=16, pady=8).pack(anchor="w")
        tk.Frame(dlg, bg=C["accent"], height=2).pack(fill="x")

        body = tk.Frame(dlg, bg=C["bg"])
        body.pack(fill="both", expand=True, padx=10, pady=8)

        # ── Left: file tree ──────────────────────────────────────────────
        left = tk.Frame(body, bg=C["bg2"],
                        highlightthickness=1, highlightbackground=C["border"])
        left.pack(side="left", fill="y", padx=(0, 6))

        tk.Label(left, text="Files dự án", bg=C["bg2"], fg=C["accent3"],
                 font=FONT_BOLD, padx=8, pady=6).pack(anchor="w")
        tk.Frame(left, bg=C["border"], height=1).pack(fill="x")

        tree_frame = tk.Frame(left, bg=C["bg2"])
        tree_frame.pack(fill="both", expand=True)

        style = ttk.Style()
        style.configure("FE.Treeview",
                        background=C["bg2"], foreground=C["text"],
                        fieldbackground=C["bg2"], rowheight=22,
                        font=("Consolas", 8))
        style.map("FE.Treeview",
                  background=[("selected", C["accent"])],
                  foreground=[("selected", "white")])

        vsb_t = tk.Scrollbar(tree_frame, orient="vertical", bg=C["bg3"])
        vsb_t.pack(side="right", fill="y")
        ftree = ttk.Treeview(tree_frame, show="tree", selectmode="browse",
                             style="FE.Treeview", yscrollcommand=vsb_t.set, width=22)
        ftree.pack(side="left", fill="both", expand=True)
        vsb_t.config(command=ftree.yview)

        # Populate tree with relevant project files
        roots = [
            ("📁 Dự án (BASE)", config.BASE_DIR),
            ("📁 Output", config.OUTPUT_DIR),
        ]
        editable_exts = {".py", ".json", ".txt", ".md", ".srt", ".ini", ".cfg", ".env"}
        _iid_path: dict[str, Path] = {}

        def _add_dir(parent_iid, folder: Path, depth=0):
            if depth > 3:
                return
            try:
                entries = sorted(folder.iterdir(),
                                 key=lambda x: (x.is_file(), x.name.lower()))
            except PermissionError:
                return
            for e in entries:
                if e.name.startswith(".") or e.name == "__pycache__":
                    continue
                if e.is_dir():
                    iid = ftree.insert(parent_iid, "end", text=f"📂 {e.name}", open=False)
                    _iid_path[iid] = e
                    _add_dir(iid, e, depth + 1)
                elif e.suffix.lower() in editable_exts and e.is_file():
                    size_kb = e.stat().st_size // 1024
                    iid = ftree.insert(parent_iid, "end",
                                       text=f"  {e.name}  ({size_kb}KB)")
                    _iid_path[iid] = e

        for label, folder in roots:
            if folder.exists():
                root_iid = ftree.insert("", "end", text=label, open=True)
                _iid_path[root_iid] = folder
                _add_dir(root_iid, folder)

        # ── Right: editor ────────────────────────────────────────────────
        right = tk.Frame(body, bg=C["bg"])
        right.pack(side="left", fill="both", expand=True)

        # Path label
        path_row = tk.Frame(right, bg=C["bg2"],
                            highlightthickness=1, highlightbackground=C["border"])
        path_row.pack(fill="x", pady=(0, 4))
        lbl_path = tk.Label(path_row, text="← Chọn file bên trái để xem/sửa",
                            bg=C["bg2"], fg=C["text2"], font=("Consolas", 8),
                            padx=8, pady=4, anchor="w")
        lbl_path.pack(side="left", fill="x", expand=True)

        # Editor
        ed_frame = tk.Frame(right, bg=C["bg"])
        ed_frame.pack(fill="both", expand=True)
        ed_vsb = tk.Scrollbar(ed_frame, orient="vertical", bg=C["bg3"])
        ed_vsb.pack(side="right", fill="y")
        ed_hsb = tk.Scrollbar(ed_frame, orient="horizontal", bg=C["bg3"])
        ed_hsb.pack(side="bottom", fill="x")
        editor = tk.Text(
            ed_frame,
            bg=C["inputbg"], fg=C["text"],
            font=("Consolas", 9), wrap="none",
            relief="flat", insertbackground=C["text"],
            selectbackground=C["accent"],
            highlightthickness=1, highlightbackground=C["border"],
            yscrollcommand=ed_vsb.set, xscrollcommand=ed_hsb.set,
            undo=True,
        )
        editor.pack(side="left", fill="both", expand=True)
        ed_vsb.config(command=editor.yview)
        ed_hsb.config(command=editor.xview)

        _current_path: list[Optional[Path]] = [None]
        lbl_status = tk.Label(right, text="", bg=C["bg"], fg=C["text2"],
                              font=("Segoe UI", 8))
        lbl_status.pack(anchor="w", pady=(2, 0))

        def _load_file(path: Path):
            if not path.is_file():
                return
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
                editor.config(state="normal")
                editor.delete("1.0", "end")
                editor.insert("1.0", content)
                editor.edit_reset()
                _current_path[0] = path
                lbl_path.config(text=str(path), fg=C["text"])
                lbl_status.config(text="", fg=C["text2"])
                # Highlight read-only non-editable files
                if path.suffix.lower() not in editable_exts:
                    editor.config(state="disabled")
            except Exception as exc:
                lbl_status.config(text=f"Lỗi đọc: {exc}", fg=C["red"])

        def _save_file():
            p = _current_path[0]
            if not p or not p.is_file():
                lbl_status.config(text="Chưa có file nào được mở", fg=C["yellow"])
                return
            try:
                content = editor.get("1.0", "end-1c")
                p.write_text(content, encoding="utf-8")
                lbl_status.config(text=f"✓ Đã lưu: {p.name}", fg=C["green"])
                dlg.after(3000, lambda: lbl_status.config(text=""))
            except Exception as exc:
                lbl_status.config(text=f"Lỗi lưu: {exc}", fg=C["red"])

        def _on_tree_select(event):
            sel = ftree.selection()
            if not sel:
                return
            iid = sel[0]
            p = _iid_path.get(iid)
            if p and p.is_file():
                _load_file(p)

        ftree.bind("<<TreeviewSelect>>", _on_tree_select)

        # Button row
        btn_row = tk.Frame(dlg, bg=C["bg"])
        btn_row.pack(fill="x", padx=10, pady=(0, 8))
        tk.Button(btn_row, text="💾  Lưu",
                  bg=C["accent"], fg="white", font=FONT_BOLD,
                  relief="flat", padx=14, pady=5, cursor="hand2",
                  activebackground=C["accent2"], activeforeground="white",
                  command=_save_file).pack(side="left")
        tk.Button(btn_row, text="↺  Reload file",
                  bg=C["bg3"], fg=C["text2"], font=FONT_BODY,
                  relief="flat", padx=10, pady=5, cursor="hand2",
                  activebackground=C["border"],
                  command=lambda: _load_file(_current_path[0]) if _current_path[0] else None,
                  ).pack(side="left", padx=(6, 0))
        tk.Button(btn_row, text="Đóng",
                  bg=C["bg3"], fg=C["text2"], font=FONT_BODY,
                  relief="flat", padx=10, pady=5, cursor="hand2",
                  activebackground=C["border"],
                  command=dlg.destroy).pack(side="left", padx=(6, 0))
        lbl_status.pack_forget()
        lbl_status = tk.Label(btn_row, text="", bg=C["bg"], fg=C["text2"],
                              font=("Segoe UI", 8))
        lbl_status.pack(side="right", padx=6)

        # Keyboard shortcut Ctrl+S
        dlg.bind("<Control-s>", lambda e: _save_file())

    # ── Gallery methods ───────────────────────────────────────────────────

    def _gallery_thumb_placeholder(self):
        try:
            from PIL import Image, ImageDraw, ImageTk
            img = Image.new("RGB", (320, 176), (10, 10, 26))
            d = ImageDraw.Draw(img)
            d.rectangle([140, 68, 180, 108], fill=(40, 40, 80))
            d.polygon([(152, 72), (152, 104), (176, 88)], fill=(100, 100, 200))
            ph = ImageTk.PhotoImage(img)
            self._thumb_lbl.configure(image=ph, text="")
            self._thumb_lbl._ph = ph
        except Exception:
            self._thumb_lbl.configure(image="", text="🎬  Chưa có video",
                                       fg=C["text2"], font=("Segoe UI", 10))

    def _extract_thumb(self, video_path: Path):
        W, H = 320, 176
        frame = None
        try:
            import cv2
            cap = cv2.VideoCapture(str(video_path))
            total = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            cap.set(cv2.CAP_PROP_POS_FRAMES, min(15, max(0, total - 1)))
            ret, fr = cap.read()
            cap.release()
            if ret:
                frame = cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)
        except Exception:
            pass
        if frame is None:
            try:
                from moviepy import VideoFileClip
                clip = VideoFileClip(str(video_path))
                t = min(0.5, clip.duration * 0.05)
                frame = clip.get_frame(t).astype("uint8")
                clip.close()
            except Exception:
                pass
        try:
            from PIL import Image, ImageTk
            img = Image.fromarray(frame) if frame is not None else Image.new("RGB", (W, H), (20, 20, 50))
            img.thumbnail((W, H), Image.LANCZOS)
            bg = Image.new("RGB", (W, H), (10, 10, 26))
            bg.paste(img, ((W - img.width) // 2, (H - img.height) // 2))
            return ImageTk.PhotoImage(bg)
        except Exception:
            return None

    def _add_clip_to_gallery(self, path: Path):
        for item in self._gallery_items:
            if item["path"] == path:
                return
        try:
            size_str = f"{path.stat().st_size / 1_048_576:.1f} MB"
        except Exception:
            size_str = ""
        def _load():
            tk_img = self._extract_thumb(path)
            item = {"path": path, "thumb_tk": tk_img, "name": path.name, "size": size_str}
            self.after(0, lambda: self._on_thumb_ready(item))
        threading.Thread(target=_load, daemon=True).start()

    def _on_thumb_ready(self, item: dict):
        self._gallery_items.append(item)
        self._gallery_items.sort(key=lambda x: x["path"].name)
        self._gallery_show(self._gallery_items.index(item))

    def _gallery_show(self, idx: int):
        n = len(self._gallery_items)
        if n == 0:
            self._lbl_gallery_count.config(text="0 clip")
            self._lbl_gname.config(text="Chưa có clip")
            self._lbl_ginfo.config(text="Double-click để mở video")
            self._gallery_thumb_placeholder()
            return
        idx = max(0, min(idx, n - 1))
        self._gallery_idx = idx
        item = self._gallery_items[idx]
        self._lbl_gallery_count.config(text=f"{idx + 1} / {n}")
        self._lbl_gname.config(text=item["name"])
        self._lbl_ginfo.config(text=item["size"])
        if item.get("thumb_tk"):
            self._thumb_lbl.configure(image=item["thumb_tk"], text="")
        else:
            self._thumb_lbl.configure(image="", text="⏳",
                                       fg=C["text2"], font=("Segoe UI", 20))

    def _gallery_prev(self):
        if self._gallery_items:
            self._gallery_show(self._gallery_idx - 1)

    def _gallery_next(self):
        if self._gallery_items:
            self._gallery_show((self._gallery_idx + 1) % len(self._gallery_items))

    def _gallery_open(self):
        if 0 <= self._gallery_idx < len(self._gallery_items):
            p = self._gallery_items[self._gallery_idx]["path"]
            if p.exists():
                os.startfile(str(p))

    def _gallery_delete(self):
        if not self._gallery_items or self._gallery_idx < 0:
            return
        item = self._gallery_items[self._gallery_idx]
        if not messagebox.askyesno("Xóa", f"Xóa file:\n{item['name']}?"):
            return
        try:
            item["path"].unlink()
        except Exception as e:
            messagebox.showerror("Lỗi", str(e))
            return
        self._gallery_known.discard(item["path"])
        self._gallery_items.pop(self._gallery_idx)
        self._gallery_show(min(self._gallery_idx, len(self._gallery_items) - 1))

    def _gallery_reassemble(self):
        if not self._gallery_items:
            messagebox.showinfo("Ghép lại", "Chưa có clip nào trong gallery.")
            return
        clip_files = [it["path"] for it in self._gallery_items]
        run_dir = clip_files[0].parent.parent
        from datetime import datetime as _dt
        out_file = run_dir / f"assembled_{_dt.now().strftime('%H%M%S')}.mp4"
        music = self.var_music.get()
        music_p = Path(music) if music and Path(music).exists() else None
        self._log("STEP", f"Ghép {len(clip_files)} clips → {out_file.name}...")
        def _do():
            from video.processor import VideoProcessor
            from utils.logger import GUILogger
            proc = VideoProcessor(GUILogger(self.log_queue, log_file=str(config.BASE_DIR / "app.log")))
            mp = music_p or proc.pick_random_music()
            result = proc.assemble(clip_files, out_file, music_path=mp)
            if result:
                self._last_output = str(result)
                self.after(0, lambda: self.btn_open.config(state="normal"))
                self._log("SUCCESS", f"✓ Ghép xong: {result.name} ({result.stat().st_size // 1_048_576} MB)")
                self.after(0, lambda: os.startfile(str(result.parent)))
            else:
                self._log("ERROR", "Ghép thất bại")
        threading.Thread(target=_do, daemon=True).start()

    def _start_gallery_poll(self):
        self._gallery_polling = True
        output_base = Path(self.var_output_dir.get() or str(config.OUTPUT_DIR))
        def _poll():
            while self._gallery_polling:
                try:
                    for mp4 in sorted(output_base.rglob("clip_*.mp4"),
                                      key=lambda f: f.stat().st_mtime):
                        if (mp4 not in self._gallery_known
                                and mp4.exists()
                                and mp4.stat().st_size > 10_000):
                            self._gallery_known.add(mp4)
                            self.after(0, lambda p=mp4: self._add_clip_to_gallery(p))
                except Exception:
                    pass
                time.sleep(2)
        threading.Thread(target=_poll, daemon=True).start()

    def _stop_gallery_poll(self):
        self._gallery_polling = False

    # ── Character thumbnail ───────────────────────────────────────────────

    def _update_char_thumb(self):
        path_str = self.var_char_img.get().strip()
        if not path_str:
            self._char_thumb.configure(image="", text="📷\nChưa chọn",
                                       fg=C["text2"], font=("Segoe UI", 7))
            return
        p = Path(path_str)
        if p.is_dir():
            imgs = (list(p.glob("*.jpg")) + list(p.glob("*.png"))
                    + list(p.glob("*.jpeg")) + list(p.glob("*.webp")))
            self._char_thumb.configure(image="", text=f"🗂\n{len(imgs)} ảnh",
                                       fg=C["accent3"], font=("Segoe UI", 8))
            return
        if not p.exists():
            self._char_thumb.configure(image="", text="❌\nKhông tìm thấy",
                                       fg=C["red"], font=("Segoe UI", 7))
            return

        def _load():
            try:
                from PIL import Image, ImageTk
                img = Image.open(str(p))
                img.thumbnail((80, 80), Image.LANCZOS)
                bg = Image.new("RGB", (80, 80), (10, 10, 26))
                bg.paste(img, ((80 - img.width) // 2, (80 - img.height) // 2))
                tk_img = ImageTk.PhotoImage(bg)
                self.after(0, lambda: self._show_char_preview(tk_img))
            except Exception:
                self.after(0, lambda: self._char_thumb.configure(
                    image="", text="🖼\nLỗi ảnh", fg=C["yellow"], font=("Segoe UI", 7)))
        threading.Thread(target=_load, daemon=True).start()

    def _show_char_preview(self, tk_img):
        self._char_thumb.configure(image=tk_img, text="")
        self._char_thumb._img = tk_img  # prevent GC

    def _char_img_open_viewer(self):
        p = Path(self.var_char_img.get().strip())
        if p.exists():
            self._open_image_file(str(p))

    # ──────────────────────────────────────────────────────────────────────
    # BATCH PRODUCTION
    # ──────────────────────────────────────────────────────────────────────

    def _build_batch_section(self, parent) -> tk.Frame:
        card = self._card(parent, "📦  Sản xuất hàng loạt")

        tk.Label(
            card,
            text="Thêm nhiều file kịch bản → tạo video lần lượt với 1 session Grok (đăng nhập 1 lần).\n"
                 "Nhân vật / Film style / Cài đặt → lấy từ panel bên trái (có thể ghi đè per-project qua JSON).",
            bg=C["bg2"], fg=C["text2"], font=("Segoe UI", 8),
            padx=10, wraplength=380, justify="left",
        ).pack(anchor="w", pady=(4, 6))

        # ── Treeview ──────────────────────────────────────────────────────
        tv_wrap = tk.Frame(card, bg=C["bg2"])
        tv_wrap.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        style = ttk.Style()
        style.configure("Batch.Treeview",
                         background=C["inputbg"], foreground=C["text"],
                         fieldbackground=C["inputbg"], rowheight=22,
                         borderwidth=0, font=FONT_BODY)
        style.configure("Batch.Treeview.Heading",
                         background=C["bg3"], foreground=C["text2"],
                         borderwidth=0, font=FONT_BODY)
        style.map("Batch.Treeview",
                  background=[("selected", C["accent"])],
                  foreground=[("selected", "white")])

        cols = ("idx", "name", "img", "scenes", "status", "time")
        self.batch_tree = ttk.Treeview(tv_wrap, columns=cols, show="headings",
                                        height=7, style="Batch.Treeview")
        self.batch_tree.heading("idx",    text="#")
        self.batch_tree.heading("name",   text="Kịch bản")
        self.batch_tree.heading("img",    text="Ảnh")
        self.batch_tree.heading("scenes", text="Cảnh")
        self.batch_tree.heading("status", text="Trạng thái")
        self.batch_tree.heading("time",   text="Thời gian")
        self.batch_tree.column("idx",    width=30,  anchor="center", stretch=False)
        self.batch_tree.column("name",   width=175, anchor="w")
        self.batch_tree.column("img",    width=45,  anchor="center", stretch=False)
        self.batch_tree.column("scenes", width=45,  anchor="center", stretch=False)
        self.batch_tree.column("status", width=90,  anchor="center", stretch=False)
        self.batch_tree.column("time",   width=60,  anchor="center", stretch=False)
        self.batch_tree.pack(side="left", fill="both", expand=True)

        tv_vsb = ttk.Scrollbar(tv_wrap, orient="vertical", command=self.batch_tree.yview)
        tv_vsb.pack(side="right", fill="y")
        self.batch_tree.configure(yscrollcommand=tv_vsb.set)

        # Status color tags
        self.batch_tree.tag_configure("done",    foreground=C["green"])
        self.batch_tree.tag_configure("failed",  foreground=C["red"])
        self.batch_tree.tag_configure("running", foreground=C["yellow"])
        self.batch_tree.tag_configure("pending", foreground=C["text2"])

        # ── Action buttons ────────────────────────────────────────────────
        btn_row = tk.Frame(card, bg=C["bg2"])
        btn_row.pack(fill="x", padx=8, pady=(0, 4))
        self._small_btn(btn_row, "➕  Thêm files",    self._batch_add_files).pack(side="left")
        self._small_btn(btn_row, "🖼  Chọn ảnh",      self._batch_pick_image).pack(side="left", padx=(4, 0))
        self._small_btn(btn_row, "🗑  Xóa đã chọn",   self._batch_remove_selected).pack(side="left", padx=(4, 0))
        self._small_btn(btn_row, "🗑  Xóa tất cả",    self._batch_clear_all).pack(side="left", padx=(4, 0))
        self._small_btn(btn_row, "↺  Reset trạng thái", self._batch_reset_status).pack(side="left", padx=(4, 0))

        cfg_row = tk.Frame(card, bg=C["bg2"])
        cfg_row.pack(fill="x", padx=8, pady=(0, 8))
        self._small_btn(cfg_row, "📂  Tải config JSON", self._batch_load_config).pack(side="left")
        self._small_btn(cfg_row, "💾  Lưu config JSON", self._batch_save_config).pack(side="left", padx=(4, 0))

        tk.Label(card,
                 text="ℹ  Cột Ảnh: 'global'=dùng ảnh panel trái  |  'file'=1 ảnh chung  |  'folder'=ảnh riêng từng cảnh (1.jpg, 2.jpg...)",
                 bg=C["bg2"], fg=C["text2"], font=("Segoe UI", 7),
                 padx=10, wraplength=380, justify="left").pack(anchor="w", pady=(0, 2))

        self.lbl_batch_count = tk.Label(
            card, text="0 dự án", bg=C["bg2"], fg=C["text2"],
            font=("Segoe UI", 8), padx=10,
        )
        self.lbl_batch_count.pack(anchor="w", pady=(0, 6))

        return card

    # ── Batch project management ──────────────────────────────────────────

    def _batch_add_files(self):
        paths = filedialog.askopenfilenames(
            title="Chọn file kịch bản (.txt / .md)",
            filetypes=[("Text/Markdown", "*.txt *.md"), ("All", "*.*")],
        )
        if not paths:
            return
        from script_parser import auto_parse
        for path in paths:
            # Tránh trùng lặp
            if any(p.get("script_file") == path for p in self._batch_projects):
                continue
            pid = len(self._batch_projects) + 1
            try:
                text = Path(path).read_text(encoding="utf-8")
                scenes, _ = auto_parse(text, default_duration=self.var_scene_dur.get())
                n_scenes = len(scenes)
            except Exception:
                n_scenes = 0
            self._batch_projects.append({
                "id":          pid,
                "name":        Path(path).stem,
                "script_file": path,
                "script_text": "",
                "char_img":    "",
                "char_desc":   "",
                "film_style":  "",
                "scene_dur":   0,
                "music":       "",
                "output_dir":  "",
                "status":      "pending",
                "error":       "",
                "output_path": "",
                "elapsed_sec": 0.0,
                "_n_scenes":   n_scenes,
            })
        self._batch_refresh_tree()

    def _batch_remove_selected(self):
        sel = self.batch_tree.selection()
        if not sel:
            return
        to_remove = set()
        for item in sel:
            vals = self.batch_tree.item(item, "values")
            if vals:
                try:
                    to_remove.add(int(vals[0]))
                except ValueError:
                    pass
        self._batch_projects = [
            p for p in self._batch_projects if p["id"] not in to_remove
        ]
        # Re-number
        for i, p in enumerate(self._batch_projects, 1):
            p["id"] = i
        self._batch_refresh_tree()

    def _batch_clear_all(self):
        if self._batch_projects and not messagebox.askyesno(
            "Xóa tất cả", f"Xóa {len(self._batch_projects)} dự án?"
        ):
            return
        self._batch_projects.clear()
        self._batch_refresh_tree()

    def _batch_reset_status(self, include_done: bool = True):
        for p in self._batch_projects:
            statuses = ("failed", "skipped", "done") if include_done else ("failed", "skipped")
            if p.get("status") in statuses:
                p["status"] = "pending"
                p["error"]  = ""
                p["output_path"] = ""
        self._batch_refresh_tree()

    def _batch_pick_image(self):
        """Chọn ảnh (file đơn hoặc thư mục) cho dự án đang chọn."""
        sel = self.batch_tree.selection()
        if not sel:
            messagebox.showinfo("Chưa chọn", "Hãy chọn một dự án trong danh sách trước.")
            return

        # Lấy project id từ treeview item
        try:
            pid = int(sel[0])
        except ValueError:
            return
        project = next((p for p in self._batch_projects if p["id"] == pid), None)
        if not project:
            return

        name = project.get("name") or Path(project.get("script_file", "?")).stem
        n_scenes = project.get("_n_scenes", 0)

        # Dialog chọn kiểu ảnh
        dlg = tk.Toplevel(self)
        dlg.title(f"Chọn ảnh – {name}")
        dlg.geometry("460x200")
        dlg.configure(bg=C["bg"])
        dlg.grab_set()

        tk.Label(dlg, text=f"Ảnh nhân vật cho: {name}  ({n_scenes} cảnh)",
                 bg=C["bg"], fg=C["accent3"], font=FONT_BOLD,
                 padx=16, pady=10).pack(anchor="w")
        tk.Frame(dlg, bg=C["accent"], height=2).pack(fill="x")

        info = tk.Label(dlg,
            text=f"Hiện tại: {project.get('char_img') or '(dùng global từ panel trái)'}",
            bg=C["bg"], fg=C["text2"], font=("Segoe UI", 8),
            padx=16, pady=6, wraplength=420, justify="left")
        info.pack(anchor="w")

        btn_row = tk.Frame(dlg, bg=C["bg"])
        btn_row.pack(fill="x", padx=14, pady=10)

        def _pick_file():
            p = filedialog.askopenfilename(
                title=f"Ảnh dùng cho TẤT CẢ cảnh của '{name}'",
                filetypes=[("Images", "*.png *.jpg *.jpeg *.webp")],
            )
            if p:
                project["char_img"] = p
                self._batch_refresh_tree()
                dlg.destroy()

        def _pick_folder():
            p = filedialog.askdirectory(
                title=f"Thư mục ảnh per-scene cho '{name}' (1.jpg=cảnh1, 2.jpg=cảnh2...)"
            )
            if p:
                project["char_img"] = p
                self._batch_refresh_tree()
                dlg.destroy()

        def _clear_img():
            project["char_img"] = ""
            self._batch_refresh_tree()
            dlg.destroy()

        tk.Button(btn_row, text=f"📄  1 file  (dùng cho tất cả {n_scenes} cảnh)",
                  bg=C["accent"], fg="white", font=FONT_BOLD,
                  relief="flat", padx=12, pady=6, cursor="hand2",
                  activebackground=C["accent2"],
                  command=_pick_file).pack(side="left")
        tk.Button(btn_row, text=f"📁  Thư mục  ({n_scenes} ảnh riêng)",
                  bg=C["bg3"], fg=C["text2"], font=FONT_BOLD,
                  relief="flat", padx=12, pady=6, cursor="hand2",
                  activebackground=C["border"],
                  command=_pick_folder).pack(side="left", padx=(8, 0))
        tk.Button(btn_row, text="✕  Xóa ảnh",
                  bg=C["bg3"], fg=C["text2"], font=FONT_BODY,
                  relief="flat", padx=10, pady=6, cursor="hand2",
                  activebackground=C["border"],
                  command=_clear_img).pack(side="right")

    def _batch_refresh_tree(self):
        self.batch_tree.delete(*self.batch_tree.get_children())
        status_labels = {
            "pending": "⏳ Chờ",
            "running": "⚙ Chạy",
            "done":    "✓ Xong",
            "failed":  "✗ Lỗi",
            "skipped": "— Bỏ",
        }
        for p in self._batch_projects:
            st      = p.get("status", "pending")
            elapsed = p.get("elapsed_sec", 0.0)
            time_s  = f"{elapsed:.0f}s" if elapsed else "—"
            # Trạng thái ảnh: folder=nhiều cảnh, file=1 ảnh chung, trống=dùng global
            ci = p.get("char_img", "")
            if not ci:
                img_s = "global"
            elif Path(ci).is_dir():
                img_s = "folder"
            else:
                img_s = "file"
            self.batch_tree.insert(
                "", "end",
                iid=str(p["id"]),
                values=(
                    p["id"],
                    p.get("name") or Path(p.get("script_file", "?")).stem,
                    img_s,
                    p.get("_n_scenes", "?"),
                    status_labels.get(st, st),
                    time_s,
                ),
                tags=(st,),
            )
        n = len(self._batch_projects)
        done   = sum(1 for p in self._batch_projects if p.get("status") == "done")
        failed = sum(1 for p in self._batch_projects if p.get("status") == "failed")
        parts  = [f"{n} dự án"]
        if done:   parts.append(f"{done} xong")
        if failed: parts.append(f"{failed} lỗi")
        self.lbl_batch_count.config(text=" · ".join(parts))

    def _batch_update_row(self, project_id: int, status: str, data: dict):
        """Called from BatchRunner callback — must be main-thread safe."""
        for p in self._batch_projects:
            if p["id"] == project_id:
                p["status"]      = status
                p["output_path"] = data.get("output_path", "")
                p["error"]       = data.get("error", "")
                p["elapsed_sec"] = data.get("elapsed_sec", 0.0)
                break
        self.after(0, self._batch_refresh_tree)

    def _batch_save_config(self):
        if not self._batch_projects:
            messagebox.showinfo("Trống", "Chưa có dự án nào để lưu.")
            return
        path = filedialog.asksaveasfilename(
            title="Lưu batch config",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            initialfile="batch_config.json",
        )
        if not path:
            return
        data = {
            "global_char_img":   self.var_char_img.get(),
            "global_char_desc":  self.var_char_desc.get(),
            "global_film_style": self.var_film_style.get(),
            "global_scene_dur":  self.var_scene_dur.get(),
            "global_music":      self.var_music.get(),
            "global_output_dir": self.var_output_dir.get(),
            "grok_profile":      self.var_grok_profile.get(),
            "connect_existing":  self.var_connect_existing.get(),
            "projects": [
                {k: v for k, v in p.items() if not k.startswith("_")}
                for p in self._batch_projects
            ],
        }
        Path(path).write_text(
            __import__("json").dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._log("SUCCESS", f"Đã lưu batch config: {Path(path).name}")

    def _batch_load_config(self):
        path = filedialog.askopenfilename(
            title="Tải batch config",
            filetypes=[("JSON", "*.json")],
        )
        if not path:
            return
        import json as _json
        try:
            data = _json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không đọc được JSON:\n{e}")
            return

        # Restore global settings nếu có
        if "global_char_img"   in data: self.var_char_img.set(data["global_char_img"])
        if "global_char_desc"  in data: self.var_char_desc.set(data["global_char_desc"])
        if "global_film_style" in data: self.var_film_style.set(data["global_film_style"])
        if "global_scene_dur"  in data: self.var_scene_dur.set(data["global_scene_dur"])
        if "global_music"      in data: self.var_music.set(data["global_music"])
        if "global_output_dir" in data: self.var_output_dir.set(data["global_output_dir"])
        if "grok_profile"      in data: self.var_grok_profile.set(data["grok_profile"])

        # Load projects
        from script_parser import auto_parse
        self._batch_projects.clear()
        for i, p in enumerate(data.get("projects", []), 1):
            p["id"] = i
            # Count scenes nếu chưa có
            if "_n_scenes" not in p:
                try:
                    sf = p.get("script_file", "")
                    st = p.get("script_text", "")
                    text = (Path(sf).read_text(encoding="utf-8") if sf and Path(sf).exists() else st)
                    sc, _ = auto_parse(text, default_duration=self.var_scene_dur.get())
                    p["_n_scenes"] = len(sc)
                except Exception:
                    p["_n_scenes"] = 0
            self._batch_projects.append(p)

        self._batch_refresh_tree()
        self._log("SUCCESS", f"Đã tải {len(self._batch_projects)} dự án từ {Path(path).name}")

    # ── Start batch ───────────────────────────────────────────────────────

    def _on_start_batch(self):
        if not self._batch_projects:
            messagebox.showwarning("Trống", "Chưa có dự án nào trong danh sách hàng loạt!\nBấm '➕ Thêm files' để thêm kịch bản.")
            return

        pending = [p for p in self._batch_projects if p.get("status") not in ("done", "skipped")]
        if not pending:
            if not messagebox.askyesno(
                "Đã hoàn thành",
                "Tất cả dự án đã xong.\nNhấn Yes để reset tất cả và chạy lại từ đầu.",
            ):
                return
            self._batch_reset_status(include_done=True)
            pending = self._batch_projects[:]

        char_img = self.var_char_img.get().strip()
        if not char_img or not Path(char_img).exists():
            if not messagebox.askyesno(
                "Thiếu ảnh nhân vật",
                "Chưa chọn ảnh nhân vật.\nNhân vật có thể không nhất quán giữa các cảnh.\nTiếp tục?"
            ):
                return

        self._running = True
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.btn_open.config(state="disabled")
        self.pbar["value"] = 0
        self.lbl_prog.config(text=f"Batch: {len(pending)} dự án…")
        self._start_gallery_poll()

        global_settings = {
            "char_img":       self.var_char_img.get(),
            "char_desc":      self.var_char_desc.get(),
            "film_style":     self.var_film_style.get(),
            "scene_dur":      self.var_scene_dur.get(),
            "music":          self.var_music.get(),
            "output_dir":     self.var_output_dir.get() or str(config.OUTPUT_DIR),
            "grok_profile":   self.var_grok_profile.get() or "grok",
            "chrome_profile": self._get_selected_chrome_profile(),
            "connect_existing": self.var_connect_existing.get(),
            "tts_voice":      self.var_tts_voice.get(),
            "aspect_ratio":   self.var_aspect_ratio.get(),
        }

        from batch.batch_runner import BatchRunner
        from utils.logger import GUILogger
        _batch_logger = GUILogger(self.log_queue, log_file=str(config.BASE_DIR / "app.log"))
        runner = BatchRunner(
            projects=self._batch_projects,
            global_settings=global_settings,
            logger=_batch_logger,
            progress_cb=self._on_batch_progress,
            project_status_cb=lambda pid, status, data: self._batch_update_row(pid, status, data),
            stop_event=threading.Event(),
        )
        self._batch_stop_event = runner.stop_event

        # Patch stop button to stop batch
        self.btn_stop.config(command=self._on_stop_batch)

        def _run():
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(runner.run_all())
            except Exception as e:
                self._log("ERROR", f"Batch lỗi: {e}")
            finally:
                loop.close()
                self.after(0, self._on_batch_finished)

        threading.Thread(target=_run, daemon=True).start()

    def _on_stop_batch(self):
        if hasattr(self, "_batch_stop_event"):
            self._batch_stop_event.set()
        self._log("WARNING", "Đang dừng... Tool sẽ hủy clip đang chạy và không cấp clip mới.")
        self.lbl_prog.config(text="Đang dừng...")
        self.btn_stop.config(state="disabled")

    def _on_batch_progress(self, done: int, total: int, label: str):
        pct = int((done / max(total, 1)) * 100)
        self.after(0, lambda: self._apply_progress(pct, label))

    def _on_batch_finished(self):
        self._running = False
        self._stop_gallery_poll()
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled", command=self._on_stop)
        if self.var_main_mode.get() == "sales":
            done   = sum(1 for c in self._sales_clusters if c.get("status") == "done")
            failed = sum(1 for c in self._sales_clusters if c.get("status") == "failed")
            stopped = sum(1 for c in self._sales_clusters if c.get("status") == "stopped")
            if stopped:
                self.lbl_prog.config(text=f"Sales AI đã dừng: {done} xong, {failed} lỗi, {stopped} dừng")
                self.lbl_pct.config(text="")
            else:
                self.pbar["value"] = 100
                self.lbl_prog.config(text=f"Sales AI xong: {done} cụm thành công, {failed} lỗi")
                self.lbl_pct.config(text="100%")
            self._sales_refresh_tree()
            self._sales_refresh_results()
            if done > 0:
                self.btn_open.config(state="normal")
            return
        done   = sum(1 for p in self._batch_projects if p.get("status") == "done")
        failed = sum(1 for p in self._batch_projects if p.get("status") == "failed")
        self.pbar["value"] = 100
        self.lbl_prog.config(text=f"Batch xong: {done} thành công, {failed} lỗi")
        self.lbl_pct.config(text="100%")
        self._batch_refresh_tree()
        if done > 0:
            self.btn_open.config(state="normal")


# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    missing = []
    for pkg in ["playwright", "moviepy"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        root = tk.Tk()
        root.withdraw()
        if messagebox.askyesno("Thiếu thư viện",
                               f"Chưa cài: {', '.join(missing)}\nCài ngay?"):
            subprocess.run([sys.executable, "-m", "pip", "install"] + missing)
        root.destroy()

    App().mainloop()
