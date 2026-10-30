#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
  Universal Pro Downloader (YouTube & Instagram) | دانلودر پیشرفته یوتیوب و اینستاگرام
  نسخه بهینه‌سازی‌شده و ارتقایافته - طراحی مدرن، رفع باگ‌ها و پشتیبانی چندپلتفرمه
=============================================================================
"""

import os
import sys
import json
import shutil
import socket
import urllib.request
import threading
from io import BytesIO
from pathlib import Path
from datetime import timedelta

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import yt_dlp
except ImportError:
    yt_dlp = None


# =============================================================================
# مسیرهای پیش‌فرض و فایل‌ها
# =============================================================================
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent.resolve()
else:
    BASE_DIR = Path(__file__).parent.resolve()

DEFAULT_DOWNLOAD_DIR = BASE_DIR / "downloads"
DEFAULT_DOWNLOAD_DIR.mkdir(exist_ok=True)
CONFIG_FILE = BASE_DIR / "downloader_config.json"
DEFAULT_COOKIE_FILE = BASE_DIR / "cookies.txt"


# =============================================================================
# کلاس مدیریت تنظیمات (Config Manager)
# =============================================================================
class ConfigManager:
    """ذخیره و بازیابی تنظیمات کاربر به صورت خودکار در قالب JSON"""
    DEFAULT_CONFIG = {
        "download_dir": str(DEFAULT_DOWNLOAD_DIR),
        "proxy_enabled": False,
        "proxy_url": "socks5://127.0.0.1:10808",
        "cookie_mode": "خودکار (cookies.txt)",
        "custom_cookie_path": "",
        "video_quality": "1080",
        "video_container": "MP4",
        "audio_format": "MP3",
        "audio_bitrate": "320",
        "embed_metadata": True,
        "embed_thumbnail": True,
        "audio_embed_thumbnail": True,
        "subtitle_enabled": False,
        "subtitle_langs": "fa,en",
        "subtitle_auto": True,
        "subtitle_mode": "embed",
        "playlist_subfolder": True,
        "auto_open_folder": False,
        "speed_limit_kb": 0,
        "use_aria2": False
    }

    @classmethod
    def load(cls):
        if not CONFIG_FILE.exists():
            return dict(cls.DEFAULT_CONFIG)
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            cfg = dict(cls.DEFAULT_CONFIG)
            cfg.update(data)
            return cfg
        except Exception:
            return dict(cls.DEFAULT_CONFIG)

    @classmethod
    def save(cls, config_dict):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config_dict, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}", file=sys.stderr)


# =============================================================================
# توابع تشخیص و جستجوی FFmpeg (پشتیبانی کامل از ویندوز، لینوکس و مک)
# =============================================================================
def find_ffmpeg():
    """
    جستجوی هوشمند ابزار FFmpeg در اولویت‌ها، پوشه برنامه و سیستم
    """
    is_win = sys.platform == "win32"
    exe_name = "ffmpeg.exe" if is_win else "ffmpeg"

    # ۱. اولویت اول: پوشه‌های کنار اسکریپت
    local_candidates = [
        BASE_DIR / "ffmpeg" / "bin",
        BASE_DIR / "ffmpeg",
        BASE_DIR / "ffmpeg-9.0.2" / "bin",
        BASE_DIR / "ffmpeg-9.0.2",
        BASE_DIR / "bin",
        BASE_DIR
    ]
    for d in local_candidates:
        if (d / exe_name).exists():
            return str(d.resolve())

    # ۲. اولویت دوم: جستجوی بازگشتی در پوشه اسکریپت
    try:
        found = list(BASE_DIR.rglob(exe_name))
        if found:
            found.sort(key=lambda p: len(str(p)))
            return str(found[0].parent.resolve())
    except Exception:
        pass

    # ۳. اولویت سوم: مسیر سیستمی PATH
    system_path = shutil.which("ffmpeg")
    if system_path:
        return str(Path(system_path).parent.resolve())

    # ۴. اولویت چهارم: مسیرهای رایج در ویندوز
    if is_win:
        win_dirs = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "ffmpeg" / "bin",
            Path(os.environ.get("PROGRAMFILES", "")) / "ffmpeg" / "bin",
            Path(os.environ.get("ProgramFiles(x86)", "")) / "ffmpeg" / "bin",
            Path("C:/ffmpeg/bin"),
            Path("C:/ffmpeg")
        ]
        for wd in win_dirs:
            if (wd / exe_name).exists():
                return str(wd.resolve())

    return None


FFMPEG_PATH = find_ffmpeg()


# =============================================================================
# توابع کمکی و فرمت‌بندی رشته‌ها
# =============================================================================
class CancelledError(Exception):
    """خطای پرتاب‌شده هنگام لغو عملیات دانلود توسط کاربر"""
    pass


def fmt_bytes(b):
    if not b:
        return "-"
    try:
        b = float(b)
    except Exception:
        return "-"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


def fmt_speed(s):
    return f"{fmt_bytes(s)}/s" if s else "-"


def fmt_eta(sec):
    if not sec:
        return "-"
    try:
        sec = int(sec)
    except Exception:
        return "-"
    if sec < 60:
        return f"{sec} ثانیه"
    return str(timedelta(seconds=sec))


def fmt_duration(sec):
    if not sec:
        return "-"
    try:
        sec = int(sec)
        m, s = divmod(sec, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"
    except Exception:
        return str(sec)


def fmt_views(count):
    if not count:
        return "-"
    try:
        count = int(count)
        if count >= 1_000_000_000:
            return f"{count / 1_000_000_000:.2f}B"
        if count >= 1_000_000:
            return f"{count / 1_000_000:.2f}M"
        if count >= 1_000:
            return f"{count / 1_000:.1f}K"
        return f"{count:,}"
    except Exception:
        return str(count)


# =============================================================================
# کلاس اصلی برنامه و رابط کاربری (GUI)
# =============================================================================
class YouTubeProDownloaderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube & Instagram Pro Downloader | دانلودر یوتیوب و اینستاگرام")
        self.root.geometry("1040x900")
        self.root.minsize(940, 750)

        # رنگ‌بندی مدرن و دارک (Modern Dark Theme)
        self.colors = {
            "bg": "#121216",
            "card_bg": "#1a1a24",
            "card_border": "#282836",
            "accent": "#4f46e5",
            "accent_hover": "#4338ca",
            "success": "#059669",
            "success_hover": "#047857",
            "danger": "#dc2626",
            "danger_hover": "#b91c1c",
            "text": "#f4f4f5",
            "text_muted": "#a1a1aa",
            "input_bg": "#252533",
            "header_bg": "#181822"
        }
        self.root.configure(bg=self.colors["bg"])

        # بارگذاری تنظیمات
        self.cfg = ConfigManager.load()
        self.download_dir = Path(self.cfg.get("download_dir", str(DEFAULT_DOWNLOAD_DIR)))
        self.download_dir.mkdir(exist_ok=True)

        # وضعیت‌ها و پرچم‌ها
        self.current_info = None
        self.current_formats_data = []
        self.cancel_flag = False
        self.is_downloading = False
        self._current_files = {}
        self.thumb_photo = None
        self.ffmpeg_path = FFMPEG_PATH

        # ساخت استایل‌ها و رابط
        self._setup_styles()
        self._build_ui()
        self._apply_initial_settings()
        self._startup_checks()

        # اتصال رویداد بستن پنجره
        self.root.protocol("WM_DELETE_WINDOW", self._on_close_window)

    # -------------------------------------------------------------------------
    # استایل‌بندی مدرن TTK
    # -------------------------------------------------------------------------
    def _setup_styles(self):
        self.style = ttk.Style(self.root)
        try:
            self.style.theme_use("clam")
        except Exception:
            pass

        c = self.colors
        fn = "Segoe UI" if sys.platform == "win32" else "DejaVu Sans"

        self.style.configure(".", background=c["bg"], foreground=c["text"], font=(fn, 9))
        self.style.configure("TFrame", background=c["bg"])
        self.style.configure("Card.TFrame", background=c["card_bg"], relief="flat")
        self.style.configure("Header.TFrame", background=c["header_bg"], relief="flat")

        self.style.configure("TLabel", background=c["bg"], foreground=c["text"])
        self.style.configure("Card.TLabel", background=c["card_bg"], foreground=c["text"])
        self.style.configure("Muted.TLabel", background=c["card_bg"], foreground=c["text_muted"], font=(fn, 8))
        self.style.configure("Header.TLabel", background=c["card_bg"], foreground="#ffffff", font=(fn, 10, "bold"))

        # دکمه استاندارد
        self.style.configure("TButton", background="#2a2a3a", foreground="#ffffff", borderwidth=0, padding=6, font=(fn, 9))
        self.style.map("TButton",
                       background=[("active", "#38384e"), ("disabled", "#1c1c24")],
                       foreground=[("disabled", "#666677")])

        # دکمه اصلی (Primary / بنفش-نیلی)
        self.style.configure("Primary.TButton", background=c["accent"], foreground="#ffffff", borderwidth=0, padding=(10, 6), font=(fn, 9, "bold"))
        self.style.map("Primary.TButton",
                       background=[("active", c["accent_hover"]), ("disabled", "#292652")],
                       foreground=[("disabled", "#6b7280")])

        # دکمه سبز (Success)
        self.style.configure("Success.TButton", background=c["success"], foreground="#ffffff", borderwidth=0, padding=(10, 6), font=(fn, 9, "bold"))
        self.style.map("Success.TButton",
                       background=[("active", c["success_hover"]), ("disabled", "#193529")],
                       foreground=[("disabled", "#6b7280")])

        # دکمه قرمز (Danger)
        self.style.configure("Danger.TButton", background=c["danger"], foreground="#ffffff", borderwidth=0, padding=(10, 6), font=(fn, 9, "bold"))
        self.style.map("Danger.TButton",
                       background=[("active", c["danger_hover"]), ("disabled", "#3b1e1e")],
                       foreground=[("disabled", "#6b7280")])

        # چک‌باکس‌ها
        self.style.configure("TCheckbutton", background=c["card_bg"], foreground=c["text"], font=(fn, 9))
        self.style.map("TCheckbutton", background=[("active", c["card_bg"])])

        # تب‌ها (Notebook)
        self.style.configure("TNotebook", background=c["bg"], borderwidth=0)
        self.style.configure("TNotebook.Tab", background=c["card_bg"], foreground=c["text_muted"], padding=[14, 7], font=(fn, 9, "bold"))
        self.style.map("TNotebook.Tab",
                       background=[("selected", c["accent"])],
                       foreground=[("selected", "#ffffff")])

        # کامبوباکس‌ها (Combobox)
        self.style.configure("TCombobox",
                             fieldbackground=c["input_bg"],
                             background="#333344",
                             foreground="#ffffff",
                             darkcolor=c["input_bg"],
                             lightcolor=c["input_bg"],
                             bordercolor=c["card_border"],
                             arrowcolor="#ffffff",
                             padding=4)
        self.style.map("TCombobox",
                       fieldbackground=[("readonly", c["input_bg"]), ("active", "#2e2e40")],
                       foreground=[("readonly", "#ffffff")])

        # نوار پیشرفت (Progressbar)
        self.style.configure("Horizontal.TProgressbar",
                             background=c["accent"],
                             troughcolor="#252533",
                             borderwidth=0)

        # جدول (Treeview)
        self.style.configure("Treeview",
                             background=c["card_bg"],
                             foreground=c["text"],
                             fieldbackground=c["card_bg"],
                             rowheight=25,
                             borderwidth=0,
                             font=(fn, 9))
        self.style.configure("Treeview.Heading",
                             background="#252536",
                             foreground="#ffffff",
                             font=(fn, 9, "bold"),
                             relief="flat",
                             padding=5)
        self.style.map("Treeview",
                       background=[("selected", c["accent"])],
                       foreground=[("selected", "#ffffff")])

    # -------------------------------------------------------------------------
    # ساخت بخش‌های رابط کاربری
    # -------------------------------------------------------------------------
    def _build_ui(self):
        self._build_top_header()

        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        self.tab_main = ttk.Frame(self.nb)
        self.tab_table = ttk.Frame(self.nb)
        self.tab_settings = ttk.Frame(self.nb)
        self.tab_log = ttk.Frame(self.nb)

        self.nb.add(self.tab_main, text="   دانلود مدیا (یوتیوب / اینستاگرام)   ")
        self.nb.add(self.tab_table, text="   جدول کیفیت‌ها و فرمت‌ها   ")
        self.nb.add(self.tab_settings, text="   تنظیمات، شبکه و پروکسی   ")
        self.nb.add(self.tab_log, text="   گزارشات و لاگ   ")

        self._build_tab_main()
        self._build_tab_table()
        self._build_tab_settings()
        self._build_tab_log()

    # ---------- هدر بالای صفحه ----------
    def _build_top_header(self):
        c = self.colors
        header = tk.Frame(self.root, bg=c["header_bg"], height=48)
        header.pack(fill="x", padx=12, pady=(10, 8))

        title_box = tk.Frame(header, bg=c["header_bg"])
        title_box.pack(side="left", padx=12, pady=6)

        tk.Label(title_box, text="► YouTube & Instagram Downloader",
                 bg=c["header_bg"], fg="#ffffff", font=("Segoe UI", 12, "bold")).pack(side="left")
        tk.Label(title_box, text=" | نسخه بهینه‌سازی‌شده چندمنظوره",
                 bg=c["header_bg"], fg=c["text_muted"], font=("Segoe UI", 9)).pack(side="left")

        # نشان‌های وضعیت (Badges)
        self.badges_frame = tk.Frame(header, bg=c["header_bg"])
        self.badges_frame.pack(side="right", padx=12, pady=6)

        self.badge_ffmpeg = tk.Label(
            self.badges_frame, text="FFmpeg: در حال بررسی...",
            bg="#27272a", fg="#a1a1aa", font=("Segoe UI", 8, "bold"), padx=8, pady=3)
        self.badge_ffmpeg.pack(side="left", padx=4)

        self.badge_proxy = tk.Label(
            self.badges_frame, text="پروکسی: غیرفعال",
            bg="#27272a", fg="#a1a1aa", font=("Segoe UI", 8, "bold"), padx=8, pady=3)
        self.badge_proxy.pack(side="left", padx=4)

        self.badge_pot = tk.Label(
            self.badges_frame, text="POT Server: در حال بررسی...",
            bg="#27272a", fg="#a1a1aa", font=("Segoe UI", 8, "bold"), padx=8, pady=3)
        self.badge_pot.pack(side="left", padx=4)

    # ---------- تب ۱: دانلود اصلی و پیش‌نمایش ----------
    def _build_tab_main(self):
        c = self.colors

        # کادر لینک
        f_url = ttk.Frame(self.tab_main, style="Card.TFrame", padding=12)
        f_url.pack(fill="x", padx=10, pady=(10, 6))

        ttk.Label(f_url, text="آدرس اینترنتی ویدیو یوتیوب، ریلز اینستاگرام (Reels/Post)، شورتس یا پلی‌لیست:",
                  style="Header.TLabel").pack(anchor="w", pady=(0, 6))

        url_row = ttk.Frame(f_url, style="Card.TFrame")
        url_row.pack(fill="x")

        self.url_var = tk.StringVar()
        self.url_entry = tk.Entry(
            url_row, textvariable=self.url_var,
            bg=c["input_bg"], fg="#ffffff", insertbackground="#ffffff",
            relief="flat", font=("Segoe UI", 10))
        self.url_entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 6))
        self.url_entry.bind("<Return>", lambda e: self.on_fetch_info())

        ttk.Button(url_row, text="پیست لینک", style="TButton",
                   command=self.paste_url).pack(side="left", padx=3)
        self.fetch_btn = ttk.Button(
            url_row, text="دریافت مشخصات و کیفیت‌ها",
            style="Primary.TButton", command=self.on_fetch_info)
        self.fetch_btn.pack(side="left", padx=3)

        # کارت مشخصات مدیا و کاور
        f_meta = ttk.Frame(self.tab_main, style="Card.TFrame", padding=12)
        f_meta.pack(fill="x", padx=10, pady=6)

        # پیش‌نمایش کاور (Thumbnail)
        self.thumb_label = tk.Label(
            f_meta, text="پیش‌نمایش کاور مدیا\n[Thumbnail]",
            bg="#14141c", fg="#71717a", width=26, height=7, font=("Segoe UI", 9))
        self.thumb_label.pack(side="left", padx=(0, 14))

        meta_info = ttk.Frame(f_meta, style="Card.TFrame")
        meta_info.pack(side="left", fill="both", expand=True)

        self.video_title_var = tk.StringVar(value="هنوز رسانه‌ای دریافت نشده است. لینک یوتیوب یا اینستاگرام را وارد کرده و دکمه دریافت را بزنید.")
        self.title_label = ttk.Label(
            meta_info, textvariable=self.video_title_var,
            style="Header.TLabel", font=("Segoe UI", 10, "bold"), wraplength=620)
        self.title_label.pack(anchor="w", pady=(0, 4))

        self.video_details_var = tk.StringVar(value="منبع: -  |  ناشر: -  |  زمان: -  |  بازدید: -")
        ttk.Label(meta_info, textvariable=self.video_details_var,
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 4))

        self.video_extra_var = tk.StringVar(value="تاریخ انتشار: -  |  شناسه: -")
        ttk.Label(meta_info, textvariable=self.video_extra_var,
                  style="Muted.TLabel").pack(anchor="w")

        # کارت دکمه‌های دانلود سریع (ویدیو و صوت)
        f_actions = ttk.Frame(self.tab_main, style="Card.TFrame", padding=12)
        f_actions.pack(fill="x", padx=10, pady=6)

        # ستون ویدیو
        col_video = ttk.Frame(f_actions, style="Card.TFrame")
        col_video.pack(side="left", fill="both", expand=True, padx=(0, 8))

        ttk.Label(col_video, text="دانلود ویدیو (تصویر + صدا)",
                  style="Header.TLabel").pack(anchor="w", pady=(0, 6))

        v_opt = ttk.Frame(col_video, style="Card.TFrame")
        v_opt.pack(fill="x", pady=2)
        ttk.Label(v_opt, text="کیفیت:", style="Card.TLabel").pack(side="left", padx=(0, 4))
        self.video_quality = ttk.Combobox(
            v_opt, values=["best", "2160", "1440", "1080", "720", "480", "360", "worst"],
            width=9, state="readonly")
        self.video_quality.set(self.cfg.get("video_quality", "1080"))
        self.video_quality.pack(side="left", padx=(0, 8))

        ttk.Label(v_opt, text="فرمت:", style="Card.TLabel").pack(side="left", padx=(0, 4))
        self.video_container = ttk.Combobox(
            v_opt, values=["MP4", "MKV"], width=6, state="readonly")
        self.video_container.set(self.cfg.get("video_container", "MP4"))
        self.video_container.pack(side="left")

        # چک‌باکس‌های دانلود سریع ویدیو
        v_sub_frame = ttk.Frame(col_video, style="Card.TFrame")
        v_sub_frame.pack(fill="x", pady=(6, 2))
        self.subtitle_var = tk.BooleanVar(value=self.cfg.get("subtitle_enabled", False))
        ttk.Checkbutton(v_sub_frame, text="دانلود زیرنویس (fa/en)",
                        variable=self.subtitle_var).pack(side="left", padx=(0, 8))
        self.playlist_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(v_sub_frame, text="کل پلی‌لیست / اسلایدها",
                        variable=self.playlist_var).pack(side="left")

        ttk.Button(col_video, text="دانلود ویدیو + صدا",
                   style="Primary.TButton",
                   command=self.on_download_video).pack(fill="x", pady=(8, 0))

        # ستون صوت
        col_audio = ttk.Frame(f_actions, style="Card.TFrame")
        col_audio.pack(side="left", fill="both", expand=True, padx=(8, 0))

        ttk.Label(col_audio, text="دانلود فقط صدا (موزیک/پادکست/ریلز)",
                  style="Header.TLabel").pack(anchor="w", pady=(0, 6))

        a_opt = ttk.Frame(col_audio, style="Card.TFrame")
        a_opt.pack(fill="x", pady=2)
        ttk.Label(a_opt, text="فرمت:", style="Card.TLabel").pack(side="left", padx=(0, 4))
        self.audio_format = ttk.Combobox(
            a_opt, values=["MP3", "M4A (اصلی)", "FLAC", "WAV", "OPUS"],
            width=11, state="readonly")
        self.audio_format.set(self.cfg.get("audio_format", "MP3"))
        self.audio_format.pack(side="left", padx=(0, 8))

        ttk.Label(a_opt, text="بیت‌ریت:", style="Card.TLabel").pack(side="left", padx=(0, 4))
        self.audio_quality = ttk.Combobox(
            a_opt, values=["320", "256", "192", "128"],
            width=6, state="readonly")
        self.audio_quality.set(self.cfg.get("audio_bitrate", "320"))
        self.audio_quality.pack(side="left")

        a_sub_frame = ttk.Frame(col_audio, style="Card.TFrame")
        a_sub_frame.pack(fill="x", pady=(6, 2))
        self.audio_embed_thumb_var = tk.BooleanVar(value=self.cfg.get("audio_embed_thumbnail", True))
        ttk.Checkbutton(a_sub_frame, text="افزودن کاور و تگ به فایل موزیک",
                        variable=self.audio_embed_thumb_var).pack(side="left")

        ttk.Button(col_audio, text="دانلود فایل صوتی",
                   style="Success.TButton",
                   command=self.on_download_audio).pack(fill="x", pady=(8, 0))

        # کارت پیشرفت دانلود
        f_prog = ttk.Frame(self.tab_main, style="Card.TFrame", padding=12)
        f_prog.pack(fill="x", padx=10, pady=6)

        prog_top = ttk.Frame(f_prog, style="Card.TFrame")
        prog_top.pack(fill="x")

        self.stage_var = tk.StringVar(value="وضعیت: آماده برای دانلود")
        ttk.Label(prog_top, textvariable=self.stage_var,
                  style="Header.TLabel", foreground="#818cf8").pack(side="left")

        self.cancel_btn = ttk.Button(
            prog_top, text="لغو دانلود [✕]",
            style="Danger.TButton", command=self.on_cancel, state="disabled")
        self.cancel_btn.pack(side="right")

        self.progress = ttk.Progressbar(
            f_prog, style="Horizontal.TProgressbar",
            orient="horizontal", mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=8)

        prog_bot = ttk.Frame(f_prog, style="Card.TFrame")
        prog_bot.pack(fill="x")

        self.stats_var = tk.StringVar(
            value="پیشرفت: -   |   حجم: - / -   |   سرعت: -   |   زمان باقی‌مانده: -")
        ttk.Label(prog_bot, textvariable=self.stats_var,
                  style="Muted.TLabel", font=("Consolas", 9)).pack(side="left")

        btn_box = ttk.Frame(prog_bot, style="Card.TFrame")
        btn_box.pack(side="right")

        ttk.Button(btn_box, text="باز کردن پوشه دانلود",
                   style="TButton", command=self.open_output_folder).pack(side="left", padx=2)

    # ---------- تب ۲: جدول تمام کیفیت‌ها ----------
    def _build_tab_table(self):
        f_filter = ttk.Frame(self.tab_table, style="Card.TFrame", padding=10)
        f_filter.pack(fill="x", padx=10, pady=(10, 6))

        ttk.Label(f_filter, text="فیلتر نوع: ", style="Card.TLabel").pack(side="left", padx=(0, 5))
        self.filter_type_var = ttk.Combobox(
            f_filter, values=["همه فرمت‌ها", "فقط ویدیو+صدا", "فقط تصویر (DASH)", "فقط صدا (DASH)"],
            state="readonly", width=18)
        self.filter_type_var.set("همه فرمت‌ها")
        self.filter_type_var.pack(side="left", padx=(0, 15))
        self.filter_type_var.bind("<<ComboboxSelected>>", lambda e: self._filter_treeview())

        ttk.Label(f_filter, text="جستجو در جدول: ", style="Card.TLabel").pack(side="left", padx=(0, 5))
        self.search_filter_var = tk.StringVar()
        self.search_entry = tk.Entry(
            f_filter, textvariable=self.search_filter_var,
            bg=self.colors["input_bg"], fg="#ffffff", insertbackground="#ffffff",
            relief="flat", width=20, font=("Segoe UI", 9))
        self.search_entry.pack(side="left", ipady=3)
        self.search_filter_var.trace_add("write", lambda *args: self._filter_treeview())

        ttk.Button(f_filter, text="بازخوانی جدول",
                   style="TButton", command=self._populate_treeview).pack(side="right")

        # ساخت جدول Treeview
        f_tree = ttk.Frame(self.tab_table, style="Card.TFrame", padding=6)
        f_tree.pack(fill="both", expand=True, padx=10, pady=6)

        cols = ("id", "type", "res", "ext", "vcodec", "acodec", "fps", "abr", "size")
        self.tree = ttk.Treeview(f_tree, columns=cols, show="headings")

        col_configs = {
            "id": ("شناسه (ID)", 90),
            "type": ("نوع جریان", 140),
            "res": ("کیفیت", 110),
            "ext": ("فرمت", 75),
            "vcodec": ("کدک تصویر", 110),
            "acodec": ("کدک صدا", 100),
            "fps": ("نرخ فریم", 70),
            "abr": ("بیت‌ریت صدا", 100),
            "size": ("حجم تخمینی", 100),
        }
        for c, (text, w) in col_configs.items():
            self.tree.heading(c, text=text,
                              command=lambda _c=c: self._sort_tree_column(_c, False))
            self.tree.column(c, width=w, anchor="center")

        tree_scroll_y = ttk.Scrollbar(f_tree, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll_y.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll_y.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda e: self.on_download_selected())

        # ردیف دکمه‌های پایین جدول
        f_bottom = ttk.Frame(self.tab_table, style="Card.TFrame", padding=8)
        f_bottom.pack(fill="x", padx=10, pady=(4, 10))

        ttk.Label(f_bottom, text="راهنما: روی هر سطر دو بار کلیک کنید یا آن را انتخاب کرده و دکمه دانلود را بزنید. (با کلیک روی سرستون‌ها، جدول مرتب می‌شود)",
                  style="Muted.TLabel").pack(side="left")

        ttk.Button(f_bottom, text="دانلود فرمت انتخاب‌شده",
                   style="Primary.TButton", command=self.on_download_selected).pack(side="right")

    # ---------- تب ۳: تنظیمات، شبکه و پروکسی ----------
    def _build_tab_settings(self):
        c = self.colors

        scroll_container = ttk.Frame(self.tab_settings, style="Card.TFrame", padding=12)
        scroll_container.pack(fill="both", expand=True, padx=10, pady=10)

        # ۱. بخش پروکسی و ضد فیلتر
        f_proxy = ttk.Frame(scroll_container, style="Card.TFrame", padding=10)
        f_proxy.pack(fill="x", pady=6)

        ttk.Label(f_proxy, text="تنظیمات پروکسی و شبکه (حیاتی برای دور زدن فیلترینگ یوتیوب و اینستاگرام)",
                  style="Header.TLabel").pack(anchor="w", pady=(0, 6))

        p_toggle = ttk.Frame(f_proxy, style="Card.TFrame")
        p_toggle.pack(fill="x", pady=2)
        self.proxy_enabled_var = tk.BooleanVar(value=self.cfg.get("proxy_enabled", False))
        ttk.Checkbutton(p_toggle, text="فعال‌سازی پروکسی برای تمام ارتباطات و دانلودها",
                        variable=self.proxy_enabled_var,
                        command=self._update_proxy_badge).pack(side="left")

        p_row = ttk.Frame(f_proxy, style="Card.TFrame")
        p_row.pack(fill="x", pady=6)
        ttk.Label(p_row, text="آدرس پروکسی:", style="Card.TLabel").pack(side="left", padx=(0, 6))
        self.proxy_url_var = tk.StringVar(value=self.cfg.get("proxy_url", "socks5://127.0.0.1:10808"))
        p_entry = tk.Entry(p_row, textvariable=self.proxy_url_var,
                           bg=c["input_bg"], fg="#ffffff", insertbackground="#ffffff",
                           relief="flat", width=36, font=("Segoe UI", 9))
        p_entry.pack(side="left", ipady=4, padx=(0, 8))

        ttk.Button(p_row, text="تست اتصال به سرور با پروکسی",
                   style="TButton", command=self.on_test_proxy).pack(side="left", padx=3)

        # دکمه‌های پیش‌تنظیم پروکسی (Presets)
        preset_row = ttk.Frame(f_proxy, style="Card.TFrame")
        preset_row.pack(fill="x", pady=4)
        ttk.Label(preset_row, text="پروکسی‌های متداول:", style="Muted.TLabel").pack(side="left", padx=(0, 6))

        presets = [
            ("v2ray / Xray (SOCKS5 :10808)", "socks5://127.0.0.1:10808"),
            ("v2ray (HTTP :10809)", "http://127.0.0.1:10809"),
            ("Clash / Mihomo (Mixed :7890)", "http://127.0.0.1:7890"),
            ("Psiphon (:8080)", "http://127.0.0.1:8080"),
        ]
        for label, url in presets:
            ttk.Button(preset_row, text=label, style="TButton",
                       command=lambda u=url: self._set_proxy_preset(u)).pack(side="left", padx=2)

        # ۲. پوشه ذخیره‌سازی
        f_dir = ttk.Frame(scroll_container, style="Card.TFrame", padding=10)
        f_dir.pack(fill="x", pady=6)

        ttk.Label(f_dir, text="پوشه ذخیره‌سازی فایل‌ها",
                  style="Header.TLabel").pack(anchor="w", pady=(0, 6))

        dir_row = ttk.Frame(f_dir, style="Card.TFrame")
        dir_row.pack(fill="x", pady=4)
        self.dir_display_var = tk.StringVar(value=str(self.download_dir))
        d_lbl = tk.Entry(dir_row, textvariable=self.dir_display_var,
                         bg=c["input_bg"], fg="#ffffff", relief="flat", state="readonly",
                         font=("Segoe UI", 9))
        d_lbl.pack(side="left", fill="x", expand=True, ipady=4, padx=(0, 6))
        ttk.Button(dir_row, text="انتخاب پوشه...",
                   style="TButton", command=self.on_choose_folder).pack(side="left")

        dir_opts = ttk.Frame(f_dir, style="Card.TFrame")
        dir_opts.pack(fill="x", pady=4)
        self.playlist_subfolder_var = tk.BooleanVar(value=self.cfg.get("playlist_subfolder", True))
        ttk.Checkbutton(dir_opts, text="ساخت پوشه مجزا برای پلی‌لیست‌ها یا پست‌های چنداسلایدی",
                        variable=self.playlist_subfolder_var).pack(side="left", padx=(0, 12))

        self.auto_open_folder_var = tk.BooleanVar(value=self.cfg.get("auto_open_folder", False))
        ttk.Checkbutton(dir_opts, text="باز کردن خودکار پوشه پس از اتمام موفق دانلود",
                        variable=self.auto_open_folder_var).pack(side="left")

        # ۳. تنظیمات زیرنویس و متادیتا
        f_sub = ttk.Frame(scroll_container, style="Card.TFrame", padding=10)
        f_sub.pack(fill="x", pady=6)

        ttk.Label(f_sub, text="زیرنویس، کاور و متادیتا",
                  style="Header.TLabel").pack(anchor="w", pady=(0, 6))

        sub_row = ttk.Frame(f_sub, style="Card.TFrame")
        sub_row.pack(fill="x", pady=3)
        ttk.Label(sub_row, text="زبان‌های زیرنویس (با کاما):", style="Card.TLabel").pack(side="left", padx=(0, 5))
        self.sub_langs_var = tk.StringVar(value=self.cfg.get("subtitle_langs", "fa,en"))
        tk.Entry(sub_row, textvariable=self.sub_langs_var,
                 bg=c["input_bg"], fg="#ffffff", relief="flat", width=14, font=("Segoe UI", 9)).pack(side="left", ipady=3, padx=(0, 12))

        self.sub_auto_var = tk.BooleanVar(value=self.cfg.get("subtitle_auto", True))
        ttk.Checkbutton(sub_row, text="دریافت زیرنویس خودکار (Auto-generated AI)",
                        variable=self.sub_auto_var).pack(side="left", padx=(0, 12))

        ttk.Label(sub_row, text="نحوه ذخیره زیرنویس:", style="Card.TLabel").pack(side="left", padx=(0, 5))
        self.sub_mode_var = ttk.Combobox(sub_row, values=["تعبیه در ویدیو (Embed)", "فایل جداگانه SRT"],
                                         state="readonly", width=18)
        self.sub_mode_var.set("تعبیه در ویدیو (Embed)" if self.cfg.get("subtitle_mode") == "embed" else "فایل جداگانه SRT")
        self.sub_mode_var.pack(side="left")

        sub_meta_row = ttk.Frame(f_sub, style="Card.TFrame")
        sub_meta_row.pack(fill="x", pady=4)
        self.embed_meta_var = tk.BooleanVar(value=self.cfg.get("embed_metadata", True))
        ttk.Checkbutton(sub_meta_row, text="ثبت متادیتای ویدیو و صوت (عنوان، آرتیست، تاریخ)",
                        variable=self.embed_meta_var).pack(side="left", padx=(0, 15))

        self.embed_thumb_var = tk.BooleanVar(value=self.cfg.get("embed_thumbnail", True))
        ttk.Checkbutton(sub_meta_row, text="تعبیه تصویر کاور داخل فایل‌های ویدیویی (MKV/MP4)",
                        variable=self.embed_thumb_var).pack(side="left")

        # ۴. کوکی و محدودیت سرعت
        f_more = ttk.Frame(scroll_container, style="Card.TFrame", padding=10)
        f_more.pack(fill="x", pady=6)

        ttk.Label(f_more, text="تنظیمات کوکی و کنترل سرعت (کوکی برای اینستاگرام و ویدیوهای دارای محدودیت سن توصیه می‌شود)",
                  style="Header.TLabel").pack(anchor="w", pady=(0, 6))

        more_row = ttk.Frame(f_more, style="Card.TFrame")
        more_row.pack(fill="x", pady=4)
        ttk.Label(more_row, text="منبع کوکی:", style="Card.TLabel").pack(side="left", padx=(0, 5))
        self.cookies_mode_var = ttk.Combobox(
            more_row,
            values=["خودکار (cookies.txt)", "هیچ‌کدام", "chrome", "firefox", "edge", "brave", "opera"],
            state="readonly", width=18)
        self.cookies_mode_var.set(self.cfg.get("cookie_mode", "خودکار (cookies.txt)"))
        self.cookies_mode_var.pack(side="left", padx=(0, 12))

        ttk.Label(more_row, text="محدودیت سرعت دانلود:", style="Card.TLabel").pack(side="left", padx=(0, 5))
        self.speed_limit_var = ttk.Combobox(
            more_row, values=["نامحدود", "500 KB/s", "1 MB/s", "2 MB/s", "5 MB/s", "10 MB/s"],
            state="readonly", width=12)
        cur_limit = self.cfg.get("speed_limit_kb", 0)
        self.speed_limit_var.set(f"{cur_limit // 1024} MB/s" if cur_limit >= 1024 else ("نامحدود" if cur_limit == 0 else f"{cur_limit} KB/s"))
        self.speed_limit_var.pack(side="left")

        # دکمه ذخیره تنظیمات
        f_save = ttk.Frame(scroll_container, style="Card.TFrame", padding=6)
        f_save.pack(fill="x", pady=(10, 0))
        ttk.Button(f_save, text="ذخیره تنظیمات در سیستم",
                   style="Primary.TButton", command=self.on_save_settings).pack(side="left")

    # ---------- تب ۴: لاگ و تاریخچه ----------
    def _build_tab_log(self):
        c = self.colors

        f_log_wrap = ttk.Frame(self.tab_log, style="Card.TFrame", padding=10)
        f_log_wrap.pack(fill="both", expand=True, padx=10, pady=10)

        # دکمه‌های کنترل لاگ
        btn_row = ttk.Frame(f_log_wrap, style="Card.TFrame")
        btn_row.pack(side="bottom", fill="x", pady=(8, 0))

        ttk.Button(btn_row, text="پاک کردن لاگ", style="TButton",
                   command=self.clear_log).pack(side="left", padx=3)
        ttk.Button(btn_row, text="کپی کردن لاگ", style="TButton",
                   command=self.copy_log).pack(side="left", padx=3)
        ttk.Button(btn_row, text="ذخیره در فایل متنی", style="TButton",
                   command=self.save_log_to_file).pack(side="left", padx=3)

        # جعبه متن لاگ
        text_container = ttk.Frame(f_log_wrap, style="Card.TFrame")
        text_container.pack(fill="both", expand=True)

        self.log_text = tk.Text(
            text_container, wrap="word",
            bg="#14141c", fg="#d4d4d8", font=("Consolas", 9),
            insertbackground="#ffffff", relief="flat", padx=8, pady=8)

        log_scroll = ttk.Scrollbar(text_container, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)

        self.log_text.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

        # رنگ‌بندی تگ‌های لاگ
        self.log_text.tag_config("error", foreground="#f87171")
        self.log_text.tag_config("success", foreground="#4ade80")
        self.log_text.tag_config("info", foreground="#67e8f9")
        self.log_text.tag_config("warn", foreground="#facc15")
        self.log_text.tag_config("stage", foreground="#c084fc", font=("Consolas", 9, "bold"))

    # =========================================================================
    # تشخیص هوشمند پلتفرم و پاک‌سازی URL
    # =========================================================================
    def _detect_platform(self, url):
        """تشخیص پلتفرم ویدیو از روی آدرس اینترنتی"""
        u = url.lower()
        if "instagram.com" in u or "instagr.am" in u:
            return "instagram"
        elif "youtube.com" in u or "youtu.be" in u:
            return "youtube"
        elif "tiktok.com" in u:
            return "tiktok"
        elif "twitter.com" in u or "x.com" in u:
            return "twitter"
        elif "aparat.com" in u:
            return "aparat"
        return "generic"

    def _clean_url(self, url):
        """پاک‌سازی پارامترهای ردیابی اضافی از لینک‌های اینستاگرام و یوتیوب"""
        url = url.strip()
        # حذف پارامترهای ردیابی اینستاگرام مثل ?igsh=...
        if "instagram.com" in url or "instagr.am" in url:
            if "?" in url and any(p in url for p in ["/p/", "/reel/", "/reels/", "/tv/"]):
                url = url.split("?")[0]
                if not url.endswith("/"):
                    url += "/"
        return url

    # =========================================================================
    # بررسی‌ها و راه‌اندازی اولیه
    # =========================================================================
    def _check_pot_server(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.3)
            res = s.connect_ex(("127.0.0.1", 4416))
            s.close()
            return res == 0
        except Exception:
            return False

    def _apply_initial_settings(self):
        self._update_proxy_badge()

    def _update_proxy_badge(self):
        if self.proxy_enabled_var.get():
            self.badge_proxy.configure(
                text="پروکسی: فعال [✓]", bg="#064e3b", fg="#6ee7b7")
        else:
            self.badge_proxy.configure(
                text="پروکسی: غیرفعال", bg="#27272a", fg="#a1a1aa")

    def _startup_checks(self):
        if self.ffmpeg_path:
            self.badge_ffmpeg.configure(
                text="FFmpeg: فعال [✓]", bg="#064e3b", fg="#6ee7b7")
            self.log(f"[✓] FFmpeg با موفقیت شناسایی شد: {self.ffmpeg_path}", "success")
        else:
            self.badge_ffmpeg.configure(
                text="FFmpeg: ناموجود [!]", bg="#7f1d1d", fg="#fca5a5")
            self.log("[!] هشدار: FFmpeg در سیستم پیدا نشد! برای ترکیب صدا+تصویر یا استخراج MP3 به آن نیاز است.", "warn")

        # بررسی سرور POT Token (bgutil-ytdlp-pot-provider)
        if self._check_pot_server():
            self.badge_pot.configure(text="POT Token: فعال [✓]", bg="#064e3b", fg="#6ee7b7")
            self.log("[✓] سرور ضد ربات یوتیوب (POT Token Provider) روی پورت 4416 متصل است.", "success")
        else:
            self.badge_pot.configure(text="POT Token: خاموش", bg="#27272a", fg="#a1a1aa")

        if DEFAULT_COOKIE_FILE.exists():
            kb = DEFAULT_COOKIE_FILE.stat().st_size / 1024
            self.log(f"[i] فایل cookies.txt شناسایی شد ({kb:.1f} KB)", "info")
        else:
            self.log("[i] فایل cookies.txt یافت نشد -> دریافت در حالت عمومی انجام خواهد شد.", "info")

        if not HAS_PIL:
            self.log("[i] کتابخانه Pillow نصب نیست -> پیش‌نمایش تصویر کاور غیرفعال خواهد بود.", "info")

        self.log(f"[i] پوشه ذخیره‌سازی: {self.download_dir}", "info")
        self.log("[✓] برنامه با موفقیت بارگذاری شد. آماده دریافت لینک یوتیوب یا اینستاگرام...", "success")

    # =========================================================================
    # مدیریت لاگ و ابزارهای رابط
    # =========================================================================
    def log(self, msg, tag=None):
        self.log_text.insert("end", msg + "\n", tag)
        self.log_text.see("end")

    def log_async(self, msg, tag=None):
        self.root.after(0, lambda: self.log(msg, tag))

    def clear_log(self):
        self.log_text.delete("1.0", "end")

    def copy_log(self):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.log_text.get("1.0", "end"))
            messagebox.showinfo("موفقیت", "متن لاگ در کلیپ‌بورد کپی شد.")
        except Exception as e:
            self.log(f"خطا در کپی لاگ: {e}", "error")

    def save_log_to_file(self):
        try:
            fp = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
                title="ذخیره لاگ")
            if fp:
                with open(fp, "w", encoding="utf-8") as f:
                    f.write(self.log_text.get("1.0", "end"))
                messagebox.showinfo("موفقیت", "فایل لاگ با موفقیت ذخیره شد.")
        except Exception as e:
            messagebox.showerror("خطا", f"خطا در ذخیره فایل لاگ: {e}")

    def paste_url(self):
        try:
            txt = self.root.clipboard_get().strip()
            if txt:
                self.url_var.set(self._clean_url(txt))
                self.on_fetch_info()
        except Exception:
            pass

    def on_choose_folder(self):
        d = filedialog.askdirectory(initialdir=self.download_dir, title="انتخاب پوشه دانلود")
        if d:
            self.download_dir = Path(d)
            self.dir_display_var.set(str(self.download_dir))
            self.log(f"[i] مسیر دانلود تغییر یافت: {self.download_dir}", "info")
            self.on_save_settings()

    def open_output_folder(self):
        try:
            self.download_dir.mkdir(exist_ok=True)
            if sys.platform == "win32":
                os.startfile(self.download_dir)
            elif sys.platform == "darwin":
                os.system(f'open "{self.download_dir}"')
            else:
                os.system(f'xdg-open "{self.download_dir}"')
        except Exception as e:
            self.log(f"[X] خطا در باز کردن پوشه: {e}", "error")

    def _set_proxy_preset(self, url):
        self.proxy_url_var.set(url)
        self.proxy_enabled_var.set(True)
        self._update_proxy_badge()

    def on_save_settings(self):
        speed_str = self.speed_limit_var.get()
        kb = 0
        if "500 KB" in speed_str:
            kb = 500
        elif "1 MB" in speed_str:
            kb = 1024
        elif "2 MB" in speed_str:
            kb = 2048
        elif "5 MB" in speed_str:
            kb = 5120
        elif "10 MB" in speed_str:
            kb = 10240

        data = {
            "download_dir": str(self.download_dir),
            "proxy_enabled": self.proxy_enabled_var.get(),
            "proxy_url": self.proxy_url_var.get().strip(),
            "cookie_mode": self.cookies_mode_var.get(),
            "video_quality": self.video_quality.get(),
            "video_container": self.video_container.get(),
            "audio_format": self.audio_format.get(),
            "audio_bitrate": self.audio_quality.get(),
            "embed_metadata": self.embed_meta_var.get(),
            "embed_thumbnail": self.embed_thumb_var.get(),
            "audio_embed_thumbnail": self.audio_embed_thumb_var.get(),
            "subtitle_enabled": self.subtitle_var.get(),
            "subtitle_langs": self.sub_langs_var.get().strip(),
            "subtitle_auto": self.sub_auto_var.get(),
            "subtitle_mode": "embed" if "Embed" in self.sub_mode_var.get() else "srt",
            "playlist_subfolder": self.playlist_subfolder_var.get(),
            "auto_open_folder": self.auto_open_folder_var.get(),
            "speed_limit_kb": kb
        }
        ConfigManager.save(data)
        self._update_proxy_badge()
        self.log("[✓] تنظیمات با موفقیت ذخیره شدند.", "success")

    def on_test_proxy(self):
        url = self.proxy_url_var.get().strip()
        if not url:
            messagebox.showwarning("توجه", "لطفاً آدرس پروکسی را وارد کنید.")
            return

        self.log(f"[~] در حال آزمایش اتصال از طریق پروکسی {url}...", "info")
        threading.Thread(target=self._do_test_proxy, args=(url,), daemon=True).start()

    def _do_test_proxy(self, proxy_url):
        try:
            # ۱. تست اتصال سوکت محلی ابتدا
            if "://" in proxy_url:
                _, rest = proxy_url.split("://", 1)
                host_port = rest.split("/")[0]
            else:
                host_port = proxy_url

            if ":" in host_port:
                h, p = host_port.split(":")
                p = int(p)
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3)
                res = sock.connect_ex((h, p))
                sock.close()
                if res != 0:
                    self.log_async(f"[X] پورت پروکسی در {h}:{p} پاسخگو نیست! آیا فیلترشکن شما روشن است؟", "error")
                    return

            # ۲. تست از طریق urllib
            handler = urllib.request.ProxyHandler({'http': proxy_url, 'https': proxy_url})
            opener = urllib.request.build_opener(handler)
            req = urllib.request.Request("https://www.google.com", headers={'User-Agent': 'Mozilla/5.0'})
            with opener.open(req, timeout=8) as resp:
                status = resp.status

            if status in (200, 301, 302):
                self.log_async("[✓] ارتباط با موفقیت برقرار شد! پروکسی به درستی کار می‌کند.", "success")
                self.root.after(0, lambda: messagebox.showinfo("موفقیت", "ارتباط اینترنتی با پروکسی با موفقیت برقرار شد!"))
            else:
                self.log_async(f"[!] دریافت پاسخ غیرعادی از سرور: کد {status}", "warn")
        except Exception as e:
            self.log_async(f"[X] اتصال ناموفق بود: {e}", "error")
            self.root.after(0, lambda: messagebox.showerror("خطای پروکسی", f"اتصال ناموفق بود:\n{e}"))

    # =========================================================================
    # ساخت پیکربندی yt-dlp
    # =========================================================================
    def _apply_cookies(self, opts):
        choice = self.cookies_mode_var.get()
        if choice == "هیچ‌کدام":
            return
        if choice == "خودکار (cookies.txt)":
            if DEFAULT_COOKIE_FILE.exists():
                opts['cookiefile'] = str(DEFAULT_COOKIE_FILE)
            return

        # مرورگرها (chrome, firefox, edge, brave, opera)
        opts['cookiesfrombrowser'] = (choice,)

    def _get_rate_limit(self):
        speed_str = self.speed_limit_var.get()
        if "500 KB" in speed_str:
            return 500 * 1024
        if "1 MB" in speed_str:
            return 1024 * 1024
        if "2 MB" in speed_str:
            return 2 * 1024 * 1024
        if "5 MB" in speed_str:
            return 5 * 1024 * 1024
        if "10 MB" in speed_str:
            return 10 * 1024 * 1024
        return None

    def _base_opts(self, extra=None, url=""):
        platform = self._detect_platform(url) if url else "generic"

        if self.playlist_var.get() and self.playlist_subfolder_var.get():
            outtmpl = str(self.download_dir / "%(playlist_title,playlist,uploader)s" / "%(playlist_index|01)02d - %(title,id)s.%(ext)s")
        else:
            if platform == "instagram":
                outtmpl = str(self.download_dir / "%(uploader|)s%(uploader| - )s%(title,id)s.%(ext)s")
            else:
                outtmpl = str(self.download_dir / "%(title,id)s.%(ext)s")

        opts = {
            'outtmpl': outtmpl,
            'quiet': True,
            'no_warnings': True,
            'noprogress': True,
            'progress_hooks': [self._progress_hook],
            'postprocessor_hooks': [self._pp_hook],
            'retries': 10,
            'fragment_retries': 10,
            'socket_timeout': 30,
            'windowsfilenames': True,
        }

        # پارامترهای ضد ربات مختص یوتیوب
        if platform == "youtube":
            opts['extractor_args'] = {
                'youtube': {
                    'player_client': ['android', 'web']
                }
            }

        if self.ffmpeg_path:
            opts['ffmpeg_location'] = self.ffmpeg_path

        if not self.playlist_var.get():
            opts['noplaylist'] = True

        # زیرنویس
        if self.subtitle_var.get():
            langs = [l.strip() for l in self.sub_langs_var.get().split(',') if l.strip()]
            opts['writesubtitles'] = True
            opts['subtitleslangs'] = langs if langs else ['fa', 'en']
            if self.sub_auto_var.get():
                opts['writeautomaticsub'] = True

        # پروکسی
        if self.proxy_enabled_var.get() and self.proxy_url_var.get().strip():
            opts['proxy'] = self.proxy_url_var.get().strip()

        # محدودیت سرعت
        rl = self._get_rate_limit()
        if rl:
            opts['ratelimit'] = rl

        # کوکی
        self._apply_cookies(opts)

        if extra:
            opts.update(extra)
        return opts

    def _info_opts(self, url=""):
        platform = self._detect_platform(url) if url else "generic"
        opts = {
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 20,
        }
        if platform == "youtube":
            opts['extractor_args'] = {
                'youtube': {
                    'player_client': ['android', 'web']
                }
            }
        if self.ffmpeg_path:
            opts['ffmpeg_location'] = self.ffmpeg_path
        if self.proxy_enabled_var.get() and self.proxy_url_var.get().strip():
            opts['proxy'] = self.proxy_url_var.get().strip()
        self._apply_cookies(opts)
        return opts

    # =========================================================================
    # هوک‌های پیشرفت (Progress Hooks)
    # =========================================================================
    def _progress_hook(self, d):
        if self.cancel_flag:
            raise CancelledError("لغو شد")

        status = d.get('status')
        if status == 'downloading':
            fn = d.get('filename', '')
            info = d.get('info_dict', {})

            if fn not in self._current_files:
                self._current_files[fn] = {
                    'total': 0,
                    'vcodec': info.get('vcodec', 'none'),
                    'acodec': info.get('acodec', 'none'),
                }
                v = info.get('vcodec', 'none') != 'none'
                a = info.get('acodec', 'none') != 'none'
                kind = "ویدیو+صدا" if (v and a) else ("ویدیو" if v else "صدا")
                self.log_async(f"[~] شروع دانلود جریان {kind}: {Path(fn).name}", "info")

            cur = self._current_files[fn]
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or cur['total']
            cur['total'] = total
            dl = d.get('downloaded_bytes', 0)
            pct = (dl / total * 100) if total else 0

            v = cur['vcodec'] != 'none'
            a = cur['acodec'] != 'none'
            kind = "ویدیو+صدا" if (v and a) else ("تصویر" if v else "صدا")
            n = list(self._current_files.keys()).index(fn) + 1

            self.root.after(0, lambda: self._update_progress_ui(
                pct, dl, total, d.get('speed') or 0,
                d.get('eta') or 0, kind, n))

        elif status == 'finished':
            self.log_async("[✓] دانلود جریان فایل انجام شد، در حال پردازش نهایی...", "success")
            self.root.after(0, lambda: self._set_stage("پردازش نهایی با FFmpeg..."))
            self.root.after(0, self._start_indeterminate)

    def _pp_hook(self, d):
        if self.cancel_flag:
            raise CancelledError("لغو شد")
        pp = d.get('postprocessor', '')
        names = {
            'FFmpegExtractAudio': "تبدیل و استخراج فایل صوتی",
            'FFmpegMerger': "ترکیب تصویر و صدا با FFmpeg",
            'FFmpegVideoConvertor': "تبدیل کانتینر ویدیو",
            'MoveFiles': "انتقال فایل به پوشه مقصد",
            'FFmpegMetadata': "ثبت متادیتا و تگ‌ها",
            'EmbedThumbnail': "تعبیه کاور و تصویر آرت‌ورک",
            'FFmpegEmbedSubtitle': "الحاق زیرنویس به ویدیو",
            'FFmpegSubtitlesConvertor': "تبدیل فرمت زیرنویس به SRT"
        }
        label = names.get(pp, f"پردازش {pp}")
        status = d.get('status')
        if status == 'started':
            self.root.after(0, lambda: self._set_stage(f"{label}..."))
            self.root.after(0, self._start_indeterminate)
        elif status == 'finished':
            self.root.after(0, lambda: self._set_stage(f"{label} تکمیل شد"))

    # =========================================================================
    # آپدیت وضعیت و رابط کاربری
    # =========================================================================
    def _update_progress_ui(self, pct, dl, total, sp, eta, kind, n):
        self._stop_indeterminate()
        self.progress['value'] = pct
        self._set_stage(f"در حال دانلود جریان {kind} (فایل {n})")
        self.stats_var.set(
            f"پیشرفت: {pct:5.1f}%   |   حجم: {fmt_bytes(dl)} / {fmt_bytes(total)}   |   "
            f"سرعت: {fmt_speed(sp)}   |   زمان باقی‌مانده: {fmt_eta(eta)}")

    def _set_stage(self, text):
        self.stage_var.set(f"وضعیت: {text}")

    def _start_indeterminate(self):
        self.progress.configure(mode="indeterminate")
        self.progress.start(15)

    def _stop_indeterminate(self):
        try:
            self.progress.stop()
        except Exception:
            pass
        self.progress.configure(mode="determinate")

    def _reset_progress(self):
        self._current_files = {}
        self._stop_indeterminate()
        self.progress['value'] = 0
        self.stats_var.set("پیشرفت: -   |   حجم: - / -   |   سرعت: -   |   زمان باقی‌مانده: -")
        self._set_stage("آماده برای دانلود")

    def _start_download(self):
        self.is_downloading = True
        self.cancel_flag = False
        self.cancel_btn.configure(state="normal")
        self.fetch_btn.configure(state="disabled")

    def _finish_download(self):
        self.is_downloading = False
        self.cancel_btn.configure(state="disabled")
        self.fetch_btn.configure(state="normal")
        self._stop_indeterminate()

    def _cleanup_partial_files(self):
        """پاک‌سازی فایل‌های موقت در صورت لغو دانلود"""
        try:
            for p in list(self._current_files.keys()):
                base = Path(p)
                for cand in [base, Path(str(base) + ".part"), Path(str(base) + ".ytdl")]:
                    if cand.exists():
                        try:
                            cand.unlink()
                        except Exception:
                            pass
        except Exception:
            pass

    # =========================================================================
    # عملیات دریافت اطلاعات و مشخصات (Fetch Info)
    # =========================================================================
    def _check_url(self):
        raw_url = self.url_var.get().strip()
        if not raw_url:
            messagebox.showwarning("توجه", "لطفاً لینک ویدیو، ریلز یا پست را وارد کنید.")
            return None
        cleaned = self._clean_url(raw_url)
        self.url_var.set(cleaned)
        return cleaned

    def on_fetch_info(self):
        if self.is_downloading:
            messagebox.showinfo("توجه", "یک عملیات دانلود در حال اجرا است.")
            return
        url = self._check_url()
        if not url:
            return

        self.tree.delete(*self.tree.get_children())
        self.current_formats_data = []
        self.video_title_var.set("در حال ارتباط با سرور و استخراج اطلاعات...")
        self.video_details_var.set("لطفاً شکیبا باشید...")
        self.video_extra_var.set("-")
        self.log(f"\n[~] دریافت اطلاعات: {url}", "info")
        self._set_stage("در حال استخراج مشخصات از سرور...")
        self._start_indeterminate()

        threading.Thread(target=self._do_fetch_info, args=(url,), daemon=True).start()

    def _do_fetch_info(self, url):
        try:
            platform = self._detect_platform(url)
            platform_names = {
                "instagram": "اینستاگرام (Instagram)",
                "youtube": "یوتیوب (YouTube)",
                "tiktok": "تیک‌تاک (TikTok)",
                "twitter": "توییتر/ایکس (Twitter/X)",
                "aparat": "آپارات (Aparat)"
            }
            plat_name = platform_names.get(platform, "وب‌سایت پشتیبانی‌شده")
            self.root.after(0, lambda: self._set_stage(f"در حال استخراج از {plat_name}..."))

            opts = self._info_opts(url)
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)

            is_playlist = 'entries' in info
            if is_playlist:
                entries = [e for e in info['entries'] if e]
                self.current_info = entries[0] if entries else None
                count = len(entries)
                if platform == "instagram":
                    uploader = info.get('uploader') or (entries[0].get('uploader') if entries else 'اینستاگرام')
                    title = f"پست چنداسلایدی اینستاگرام @{uploader} ({count} مدیا/اسلاید)"
                else:
                    title = f"پلی‌لیست: {info.get('title', 'مجموعه')} ({count} ویدیو)"

                self.root.after(0, lambda: self.video_title_var.set(title))
                self.root.after(0, lambda: self.video_details_var.set(f"پلتفرم: {plat_name}   |   تعداد آیتم‌ها: {count}"))
                self.root.after(0, lambda: self.playlist_var.set(True))
                self.log_async(f"[✓] {title} با موفقیت شناسایی شد.", "success")
                info = entries[0] if entries else info
            else:
                self.current_info = info
                uploader = info.get('uploader') or info.get('channel') or info.get('uploader_id') or '-'
                if platform == "instagram" and uploader != '-' and not uploader.startswith('@'):
                    uploader = f"@{uploader}"

                raw_title = info.get('title')
                caption = (info.get('description') or '').strip()

                if platform == "instagram":
                    if caption:
                        first_line = caption.split('\n')[0].strip()
                        title = f"{uploader}: {first_line[:80]}"
                    elif raw_title:
                        title = f"{uploader}: {raw_title}"
                    else:
                        title = f"پست اینستاگرام {uploader}"
                else:
                    title = raw_title or 'بدون عنوان'

                duration = fmt_duration(info.get('duration'))
                views = fmt_views(info.get('view_count'))
                likes = fmt_views(info.get('like_count'))
                date = info.get('upload_date')
                if date and len(date) == 8:
                    date = f"{date[:4]}-{date[4:6]}-{date[6:]}"
                vid = info.get('id', '-')

                self.root.after(0, lambda: self.video_title_var.set(title))

                details_parts = [f"منبع: {plat_name}", f"ناشر: {uploader}"]
                if duration and duration != "-":
                    details_parts.append(f"زمان: {duration}")
                if views and views != "-":
                    details_parts.append(f"بازدید: {views}")
                if likes and likes != "-":
                    details_parts.append(f"لایک: {likes}")

                self.root.after(0, lambda: self.video_details_var.set("   |   ".join(details_parts)))
                self.root.after(0, lambda: self.video_extra_var.set(
                    f"تاریخ انتشار: {date or '-'}   |   شناسه: {vid}"))
                self.log_async(f"[✓] رسانه از {plat_name} دریافت شد: {title}", "success")

            # بارگذاری پیش‌نمایش تصویر کاور (Thumbnail)
            thumb_url = info.get('thumbnail')
            if thumb_url and HAS_PIL:
                self._load_thumbnail_async(thumb_url)

            # پردازش و دسته‌بندی فرمت‌ها
            raw_formats = info.get('formats', [])
            self.current_formats_data = []

            for f in raw_formats:
                fid = str(f.get('format_id', '?'))
                vc = f.get('vcodec', 'none')
                ac = f.get('acodec', 'none')

                if vc == 'none' and ac == 'none':
                    continue

                if vc != 'none' and ac != 'none':
                    ftype = "ویدیو+صدا"
                elif vc != 'none':
                    ftype = "فقط تصویر"
                else:
                    ftype = "فقط صدا"

                height = f.get('height')
                if height:
                    res = f"{height}p"
                elif f.get('resolution'):
                    res = str(f.get('resolution'))
                elif vc == 'none':
                    res = "صوتی"
                else:
                    res = f.get('format_note') or '-'

                ext = f.get('ext', '-')
                fps = str(f.get('fps') or '-')
                abr = f"{int(f.get('abr'))} kbps" if f.get('abr') else '-'
                size = f.get('filesize') or f.get('filesize_approx')
                size_s = fmt_bytes(size)

                vc_clean = vc.split('.')[0] if vc != 'none' else '-'
                ac_clean = ac.split('.')[0] if ac != 'none' else '-'

                item = (fid, ftype, res, ext, vc_clean, ac_clean, fps, abr, size_s)
                self.current_formats_data.append(item)

            self.root.after(0, self._populate_treeview)
            self.log_async(f"[✓] تعداد {len(self.current_formats_data)} کیفیت/فرمت استخراج شد.", "success")
            self.root.after(0, lambda: self._set_stage("آماده برای دانلود"))
        except Exception as e:
            msg = str(e)
            self.log_async(f"[X] خطا در دریافت اطلاعات: {e}", "error")
            if "login required" in msg.lower() or "checkpoint" in msg.lower():
                self.log_async("[!] این پست اینستاگرام نیاز به ورود دارد. از تب تنظیمات، گزینه کوکی را روی مرورگر خود (مانند Chrome یا Firefox) تنظیم کنید.", "warn")
            self.root.after(0, lambda: self._set_stage("خطا در برقراری ارتباط"))
            self.root.after(0, lambda: self.video_title_var.set("خطا در دریافت اطلاعات رسانه"))
        finally:
            self.root.after(0, self._stop_indeterminate)

    def _load_thumbnail_async(self, thumb_url):
        threading.Thread(target=self._do_fetch_thumb, args=(thumb_url,), daemon=True).start()

    def _do_fetch_thumb(self, url):
        try:
            handlers = []
            if self.proxy_enabled_var.get() and self.proxy_url_var.get().strip():
                p_url = self.proxy_url_var.get().strip()
                handlers.append(urllib.request.ProxyHandler({'http': p_url, 'https': p_url}))

            opener = urllib.request.build_opener(*handlers)
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with opener.open(req, timeout=10) as resp:
                raw_data = resp.read()

            img = Image.open(BytesIO(raw_data))
            img = img.resize((210, 118), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)

            def update_thumb():
                self.thumb_photo = photo
                self.thumb_label.configure(image=photo, text="", width=210, height=118)

            self.root.after(0, update_thumb)
        except Exception:
            pass

    # =========================================================================
    # مدیریت جدول فرمت‌ها و فیلترها (Treeview)
    # =========================================================================
    def _populate_treeview(self):
        self.tree.delete(*self.tree.get_children())
        filter_type = self.filter_type_var.get()
        search_kw = self.search_filter_var.get().strip().lower()

        for item in self.current_formats_data:
            fid, ftype, res, ext, vc, ac, fps, abr, size_s = item

            # فیلتر نوع
            if filter_type == "فقط ویدیو+صدا" and "ویدیو+صدا" not in ftype:
                continue
            if filter_type == "فقط تصویر (DASH)" and "فقط تصویر" not in ftype:
                continue
            if filter_type == "فقط صدا (DASH)" and "فقط صدا" not in ftype:
                continue

            # فیلتر جستجو
            if search_kw:
                combined = f"{fid} {ftype} {res} {ext} {vc} {ac} {fps} {abr} {size_s}".lower()
                if search_kw not in combined:
                    continue

            self.tree.insert("", "end", values=item)

    def _filter_treeview(self):
        self._populate_treeview()

    def _sort_tree_column(self, col, reverse):
        items = [(self.tree.set(k, col), k) for k in self.tree.get_children("")]

        def parse_val(v):
            v_clean = v.strip().lower()
            for unit, mult in [("tb", 1024**4), ("gb", 1024**3), ("mb", 1024**2), ("kb", 1024), ("b", 1)]:
                if v_clean.endswith(unit):
                    try:
                        return float(v_clean[:-len(unit)].strip()) * mult
                    except Exception:
                        pass
            if v_clean.endswith("p") and v_clean[:-1].isdigit():
                return int(v_clean[:-1])
            if "kbps" in v_clean:
                try:
                    return int(v_clean.replace("kbps", "").strip())
                except Exception:
                    pass
            try:
                return float(v_clean)
            except Exception:
                return v_clean

        items.sort(key=lambda t: parse_val(t[0]), reverse=reverse)
        for index, (_, k) in enumerate(items):
            self.tree.move(k, "", index)

        self.tree.heading(col, command=lambda: self._sort_tree_column(col, not reverse))

    # =========================================================================
    # عملیات‌های دانلود (ویدیو، صوت و فرمت انتخابی)
    # =========================================================================

    # ---------- ۱. دانلود ویدیو + صدا ----------
    def on_download_video(self):
        url = self._check_url()
        if not url:
            return
        if self.is_downloading:
            messagebox.showinfo("توجه", "یک دانلود دیگر در حال اجراست.")
            return

        q = self.video_quality.get()
        cont = self.video_container.get()

        self._start_download()
        self._reset_progress()
        self.log(f"\n[~] شروع دانلود ویدیو (کیفیت: {q} | کانتینر: {cont})", "info")
        threading.Thread(target=self._do_download_video,
                         args=(url, q, cont), daemon=True).start()

    def _do_download_video(self, url, quality, container):
        platform = self._detect_platform(url)

        # در اینستاگرام فرمت‌ها یکپارچه (Progressive MP4) هستند
        if platform == "instagram":
            formats = [
                "best",
                "best[ext=mp4]",
                "bestvideo+bestaudio/best"
            ]
        elif quality in ("best", "بهترین"):
            formats = [
                f"bestvideo[ext={container.lower()}]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
                "bestvideo+bestaudio/best",
                "best"
            ]
        elif quality in ("worst", "کمترین"):
            formats = ["worstvideo+worstaudio/worst", "worst"]
        else:
            formats = [
                f"bestvideo[height<={quality}][ext={container.lower()}]+bestaudio[ext=m4a]/bestvideo[height<={quality}]+bestaudio/best[height<={quality}]",
                f"bestvideo[height<={quality}]+bestaudio/best",
                f"best[height<={quality}]/best",
                "bestvideo+bestaudio/best",
                "best"
            ]

        postprocessors = []
        if self.embed_meta_var.get():
            postprocessors.append({'key': 'FFmpegMetadata', 'add_metadata': True})
        if self.embed_thumb_var.get():
            postprocessors.append({'key': 'EmbedThumbnail', 'already_have_thumbnail': False})
        if self.subtitle_var.get():
            if "Embed" in self.sub_mode_var.get():
                postprocessors.append({'key': 'FFmpegEmbedSubtitle'})
            else:
                postprocessors.append({'key': 'FFmpegSubtitlesConvertor', 'format': 'srt'})

        extra = {
            'merge_output_format': container.lower(),
        }
        if self.embed_thumb_var.get():
            extra['writethumbnail'] = True
        if postprocessors:
            extra['postprocessors'] = postprocessors

        last_error = None
        try:
            for fmt in formats:
                try:
                    self.log_async(f"-> آزمایش فرمت: {fmt}", "info")
                    opts = self._base_opts(dict({'format': fmt}, **extra), url=url)
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        ydl.download([url])
                    self._handle_finish(f"[✓] رسانه با موفقیت ذخیره شد: {self.download_dir}")
                    return
                except CancelledError:
                    self.log_async("[X] دانلود ویدیو لغو شد.", "warn")
                    self.root.after(0, lambda: self._set_stage("دانلود لغو شد"))
                    self._cleanup_partial_files()
                    return
                except Exception as e:
                    last_error = e
                    msg = str(e)
                    if "Requested format is not available" in msg or "format not available" in msg.lower():
                        self.log_async("[!] کیفیت انتخابی یافت نشد، تلاش با کیفیت جایگزین...", "warn")
                        continue
                    else:
                        self.log_async(f"[X] خطا: {e}", "error")
                        if "login required" in msg.lower():
                            self.log_async("[!] اینستاگرام نیاز به ورود دارد. در تب تنظیمات گزینه کوکی مرورگر را فعال کنید.", "warn")
                        self.root.after(0, lambda: self._set_stage("خطا در دانلود"))
                        return

            self.log_async(f"[X] امکان دانلود فرمت‌های ویدیویی میسر نشد. آخرین خطا: {last_error}", "error")
            self.root.after(0, lambda: self._set_stage("خطا در دانلود"))
        finally:
            self.root.after(0, self._finish_download)

    # ---------- ۲. دانلود فقط صدا ----------
    def on_download_audio(self):
        url = self._check_url()
        if not url:
            return
        if self.is_downloading:
            messagebox.showinfo("توجه", "یک دانلود دیگر در حال اجراست.")
            return

        fmt = self.audio_format.get()
        br = self.audio_quality.get()

        self._start_download()
        self._reset_progress()
        self.log(f"\n[~] شروع استخراج فایل صوتی ({fmt} - {br}kbps)", "info")
        threading.Thread(target=self._do_download_audio,
                         args=(url, fmt, br), daemon=True).start()

    def _do_download_audio(self, url, audio_fmt, bitrate):
        try:
            postprocessors = []
            codec = "mp3"
            if "M4A" in audio_fmt:
                codec = "m4a"
            elif "FLAC" in audio_fmt:
                codec = "flac"
            elif "WAV" in audio_fmt:
                codec = "wav"
            elif "OPUS" in audio_fmt:
                codec = "opus"

            extract_pp = {
                'key': 'FFmpegExtractAudio',
                'preferredcodec': codec
            }
            if codec == "mp3":
                extract_pp['preferredquality'] = bitrate
            postprocessors.append(extract_pp)

            if self.embed_meta_var.get():
                postprocessors.append({'key': 'FFmpegMetadata', 'add_metadata': True})
            if self.audio_embed_thumb_var.get():
                postprocessors.append({'key': 'EmbedThumbnail', 'already_have_thumbnail': False})

            extra = {
                'format': 'bestaudio/best',
                'postprocessors': postprocessors
            }
            if self.audio_embed_thumb_var.get():
                extra['writethumbnail'] = True

            opts = self._base_opts(extra, url=url)
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            self._handle_finish(f"[✓] فایل صوتی ({codec.upper()}) با موفقیت ذخیره شد: {self.download_dir}")
        except CancelledError:
            self.log_async("[X] دانلود صوت لغو شد.", "warn")
            self.root.after(0, lambda: self._set_stage("دانلود لغو شد"))
            self._cleanup_partial_files()
        except Exception as e:
            self.log_async(f"[X] خطا در دانلود صوت: {e}", "error")
            self.root.after(0, lambda: self._set_stage("خطا در دانلود"))
        finally:
            self.root.after(0, self._finish_download)

    # ---------- ۳. دانلود کیفیت انتخاب‌شده از جدول ----------
    def on_download_selected(self):
        url = self._check_url()
        if not url:
            return
        if self.is_downloading:
            messagebox.showinfo("توجه", "یک دانلود در حال اجراست.")
            return

        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("توجه", "لطفاً ابتدا یک سطر از جدول کیفیت‌ها را انتخاب کنید.")
            return

        vals = self.tree.item(sel[0], "values")
        fid, ftype, res, ext, vc, ac = vals[0], vals[1], vals[2], vals[3], vals[4], vals[5]

        self._start_download()
        self._reset_progress()
        self.log(f"\n[~] دانلود فرمت اختصاصی: شناسه {fid} ({ftype} - {res} - {ext})", "info")
        threading.Thread(target=self._do_download_selected_format,
                         args=(url, fid, ftype, ac), daemon=True).start()

    def _do_download_selected_format(self, url, fid, ftype, ac):
        try:
            extra = {}
            if "فقط صدا" in ftype:
                fmt = fid
            elif "فقط تصویر" in ftype or ac == "-":
                fmt = f"{fid}+bestaudio/{fid}/best"
                extra['merge_output_format'] = self.video_container.get().lower()
            else:
                fmt = fid
                extra['merge_output_format'] = self.video_container.get().lower()

            opts = self._base_opts(dict({'format': fmt}, **extra), url=url)
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            self._handle_finish(f"[✓] فایل با موفقیت ذخیره شد: {self.download_dir}")
        except CancelledError:
            self.log_async("[X] عملیات لغو شد.", "warn")
            self.root.after(0, lambda: self._set_stage("دانلود لغو شد"))
            self._cleanup_partial_files()
        except Exception as e:
            self.log_async(f"[X] خطا در دانلود فرمت انتخابی: {e}", "error")
            self.root.after(0, lambda: self._set_stage("خطا در دانلود"))
        finally:
            self.root.after(0, self._finish_download)

    # ---------- مدیریت تکمیل و لغو دانلود ----------
    def _handle_finish(self, success_msg):
        if self.cancel_flag:
            return
        self.log_async(success_msg, "success")
        self.root.after(0, lambda: self._set_stage("دانلود با موفقیت پایان یافت"))
        self.root.after(0, lambda: self.progress.configure(value=100))

        if self.auto_open_folder_var.get():
            self.root.after(500, self.open_output_folder)

    def on_cancel(self):
        if self.is_downloading:
            self.cancel_flag = True
            self.cancel_btn.configure(state="disabled")
            self.log("[!] در حال ارسال سیگنال لغو به موتور دانلود...", "warn")

    def _on_close_window(self):
        if self.is_downloading:
            if messagebox.askyesno("تأیید خروج", "یک عملیات دانلود در حال انجام است. آیا می‌خواهید آن را متوقف کرده و خارج شوید؟"):
                self.cancel_flag = True
                self.root.destroy()
        else:
            self.root.destroy()


# =============================================================================
# تابع اصلی اجرای برنامه (Main Entry Point)
# =============================================================================
def main():
    root = tk.Tk()

    # فعال‌سازی وضوح DPI بالا در ویندوزهای ۱۰ و ۱۱ در صورت وجود
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

    app = YouTubeProDownloaderGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
