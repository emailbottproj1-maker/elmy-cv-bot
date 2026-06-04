"""
Main desktop window (Tkinter) — Arabic RTL.

Layout (single scrollable window):
  1. الإعدادات: Gmail + App Password + اسم المرسِل + Subject
  2. الملفات: Excel + CV + Cover letters (AR/EN)
  3. خيارات الإرسال: الحد اليومي + الفواصل الزمنية + رابط البكسل
  4. التحكم: تحميل القائمة / ابدأ / إيقاف مؤقت / إيقاف / تحديث الإحصائيات
  5. التقدّم: progress bar + عدادات
  6. السجل: منطقة نصية للأحداث

All long-running work (sending, stats fetch) runs off the UI thread; the engine
calls back via thread-safe `root.after(...)` to update widgets.
"""
from __future__ import annotations

import os
import queue
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from bot.campaign import CampaignCallbacks, CampaignEngine
from bot.config import Settings
from bot.database import Database
from bot.email_sender import EmailConfigError, EmailSender
from bot.excel_reader import read_companies
from bot.language_handler import LanguageHandler
from bot.rate_limiter import RateLimiter
from bot.tracker import Tracker

APP_TITLE = "Elmy CV Bot — بوت إرسال السير الذاتية"
DB_PATH = "data/tracking.db"

BG = "#f4f6f9"
CARD = "#ffffff"
ACCENT = "#2563eb"
OK = "#16a34a"
ERR = "#dc2626"
WARN = "#d97706"
MUTED = "#6b7280"


class MainWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.settings = Settings.load()
        self.db: Database | None = None
        self.engine: CampaignEngine | None = None
        self._ui_queue: "queue.Queue[tuple]" = queue.Queue()

        root.title(APP_TITLE)
        root.geometry("760x820")
        root.minsize(680, 700)
        root.configure(bg=BG)

        self._build_styles()
        self._build_scrollable_container()
        self._build_settings_section()
        self._build_files_section()
        self._build_sending_section()
        self._build_control_section()
        self._build_progress_section()
        self._build_log_section()

        self._load_settings_into_widgets()
        self.root.after(100, self._drain_ui_queue)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- styling ----------
    def _build_styles(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=CARD)
        style.configure("Card.TLabelframe", background=CARD, borderwidth=1, relief="solid")
        style.configure("Card.TLabelframe.Label", background=CARD,
                        font=("Segoe UI", 11, "bold"), foreground=ACCENT)
        style.configure("TLabel", background=CARD, font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=6)
        style.configure("Accent.TButton", foreground="#fff", background=ACCENT)
        style.map("Accent.TButton", background=[("active", "#1d4ed8")])
        style.configure("Start.TButton", foreground="#fff", background=OK)
        style.map("Start.TButton", background=[("active", "#15803d")])
        style.configure("Stop.TButton", foreground="#fff", background=ERR)
        style.map("Stop.TButton", background=[("active", "#b91c1c")])
        style.configure("TEntry", padding=4)
        style.configure("Horizontal.TProgressbar", thickness=22)

    def _build_scrollable_container(self) -> None:
        outer = tk.Frame(self.root, bg=BG)
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        self.body = tk.Frame(canvas, bg=BG)
        self.body.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        win = canvas.create_window((0, 0), window=self.body, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=e.width))
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        # mouse wheel
        canvas.bind_all(
            "<MouseWheel>",
            lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"),
        )

    def _card(self, title: str) -> ttk.LabelFrame:
        lf = ttk.LabelFrame(self.body, text=title, style="Card.TLabelframe")
        lf.pack(fill="x", padx=14, pady=8, ipadx=8, ipady=6)
        return lf

    def _row(self, parent, label: str) -> ttk.Frame:
        fr = ttk.Frame(parent)
        fr.pack(fill="x", padx=10, pady=4)
        ttk.Label(fr, text=label, width=20, anchor="e").pack(side="right", padx=(8, 0))
        return fr

    # ---------- sections ----------
    def _build_settings_section(self) -> None:
        card = self._card("١) إعدادات الإرسال (Gmail)")

        r = self._row(card, "إيميل Gmail:")
        self.var_gmail = tk.StringVar()
        ttk.Entry(r, textvariable=self.var_gmail, justify="left").pack(
            side="right", fill="x", expand=True)

        r = self._row(card, "App Password:")
        self.var_apppw = tk.StringVar()
        self.entry_apppw = ttk.Entry(r, textvariable=self.var_apppw, show="•", justify="left")
        self.entry_apppw.pack(side="right", fill="x", expand=True)
        self.var_showpw = tk.BooleanVar(value=False)
        ttk.Checkbutton(r, text="إظهار", variable=self.var_showpw,
                        command=self._toggle_pw).pack(side="right", padx=6)

        r = self._row(card, "اسم المرسِل:")
        self.var_sender = tk.StringVar()
        ttk.Entry(r, textvariable=self.var_sender, justify="right").pack(
            side="right", fill="x", expand=True)

        r = self._row(card, "عنوان (عربي):")
        self.var_subar = tk.StringVar()
        ttk.Entry(r, textvariable=self.var_subar, justify="right").pack(
            side="right", fill="x", expand=True)

        r = self._row(card, "عنوان (English):")
        self.var_suben = tk.StringVar()
        ttk.Entry(r, textvariable=self.var_suben, justify="left").pack(
            side="right", fill="x", expand=True)

        btn = ttk.Frame(card)
        btn.pack(fill="x", padx=10, pady=(6, 4))
        ttk.Button(btn, text="🔑 اختبار تسجيل الدخول", command=self._test_login).pack(side="right")

    def _build_files_section(self) -> None:
        card = self._card("٢) الملفات")
        self.var_excel = tk.StringVar()
        self.var_cv = tk.StringVar()
        self.var_lar = tk.StringVar()
        self.var_len = tk.StringVar()
        self._file_picker(card, "ملف الشركات (Excel):", self.var_excel,
                          [("Excel", "*.xlsx")])
        self._file_picker(card, "السيرة الذاتية (PDF):", self.var_cv,
                          [("PDF", "*.pdf")])
        self._file_picker(card, "رسالة عربية (txt):", self.var_lar,
                          [("Text", "*.txt")])
        self._file_picker(card, "رسالة إنجليزية (txt):", self.var_len,
                          [("Text", "*.txt")])

    def _file_picker(self, parent, label, var, filetypes):
        r = self._row(parent, label)
        ttk.Entry(r, textvariable=var, justify="left").pack(
            side="right", fill="x", expand=True)
        ttk.Button(r, text="📁", width=3,
                   command=lambda: self._browse(var, filetypes)).pack(side="right", padx=4)

    def _browse(self, var, filetypes):
        path = filedialog.askopenfilename(filetypes=filetypes + [("All", "*.*")])
        if path:
            var.set(path)

    def _build_sending_section(self) -> None:
        card = self._card("٣) خيارات الإرسال")
        r = self._row(card, "الحد اليومي:")
        self.var_cap = tk.IntVar(value=50)
        ttk.Spinbox(r, from_=1, to=500, textvariable=self.var_cap, width=8).pack(side="right")

        r = self._row(card, "أقل فاصل (ثانية):")
        self.var_min = tk.IntVar(value=60)
        ttk.Spinbox(r, from_=0, to=3600, textvariable=self.var_min, width=8).pack(side="right")

        r = self._row(card, "أكبر فاصل (ثانية):")
        self.var_max = tk.IntVar(value=180)
        ttk.Spinbox(r, from_=0, to=3600, textvariable=self.var_max, width=8).pack(side="right")

        r = self._row(card, "رابط البكسل (Vercel):")
        self.var_pixel = tk.StringVar()
        ttk.Entry(r, textvariable=self.var_pixel, justify="left").pack(
            side="right", fill="x", expand=True)

        r = self._row(card, "Stats Token:")
        self.var_token = tk.StringVar()
        ttk.Entry(r, textvariable=self.var_token, justify="left").pack(
            side="right", fill="x", expand=True)

    def _build_control_section(self) -> None:
        card = self._card("٤) التحكم")
        bar = ttk.Frame(card)
        bar.pack(fill="x", padx=10, pady=6)
        self.btn_load = ttk.Button(bar, text="📥 تحميل القائمة", style="Accent.TButton",
                                   command=self._load_list)
        self.btn_load.pack(side="right", padx=4)
        self.btn_start = ttk.Button(bar, text="▶️ ابدأ الإرسال", style="Start.TButton",
                                    command=self._start, state="disabled")
        self.btn_start.pack(side="right", padx=4)
        self.btn_pause = ttk.Button(bar, text="⏸️ إيقاف مؤقت", command=self._pause,
                                    state="disabled")
        self.btn_pause.pack(side="right", padx=4)
        self.btn_stop = ttk.Button(bar, text="⏹️ إيقاف", style="Stop.TButton",
                                   command=self._stop, state="disabled")
        self.btn_stop.pack(side="right", padx=4)
        self.btn_stats = ttk.Button(bar, text="📊 تحديث الإحصائيات", command=self._refresh_stats)
        self.btn_stats.pack(side="right", padx=4)

    def _build_progress_section(self) -> None:
        card = self._card("٥) التقدّم")
        self.progress = ttk.Progressbar(card, style="Horizontal.TProgressbar",
                                        mode="determinate")
        self.progress.pack(fill="x", padx=12, pady=(8, 4))

        grid = ttk.Frame(card)
        grid.pack(fill="x", padx=12, pady=4)
        self.lbl_counts = ttk.Label(grid, text="لم يتم التحميل بعد.",
                                    font=("Segoe UI", 11, "bold"))
        self.lbl_counts.pack(side="right")
        self.lbl_state = ttk.Label(grid, text="●  متوقف", foreground=MUTED,
                                   font=("Segoe UI", 10, "bold"))
        self.lbl_state.pack(side="left")
        self.lbl_count = ttk.Label(card, text="", foreground=MUTED)
        self.lbl_count.pack(padx=12, pady=(0, 6), anchor="e")

    def _build_log_section(self) -> None:
        card = self._card("٦) السجل")
        self.log = scrolledtext.ScrolledText(card, height=11, font=("Consolas", 9),
                                             wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True, padx=10, pady=8)
        for tag, color in (("success", OK), ("error", ERR),
                           ("warn", WARN), ("info", MUTED)):
            self.log.tag_config(tag, foreground=color)

    # ---------- settings <-> widgets ----------
    def _load_settings_into_widgets(self) -> None:
        s = self.settings
        self.var_gmail.set(s.gmail_address)
        self.var_apppw.set(s.app_password)
        self.var_sender.set(s.sender_name)
        self.var_subar.set(s.subject_ar)
        self.var_suben.set(s.subject_en)
        self.var_excel.set(s.companies_xlsx)
        self.var_cv.set(s.cv_path)
        self.var_lar.set(s.cover_letter_ar)
        self.var_len.set(s.cover_letter_en)
        self.var_cap.set(s.daily_cap)
        self.var_min.set(s.min_delay)
        self.var_max.set(s.max_delay)
        self.var_pixel.set(s.pixel_base_url)
        self.var_token.set(s.stats_token)

    def _collect_settings(self) -> Settings:
        s = self.settings
        s.gmail_address = self.var_gmail.get().strip()
        s.app_password = self.var_apppw.get().strip()
        s.sender_name = self.var_sender.get().strip()
        s.subject_ar = self.var_subar.get().strip()
        s.subject_en = self.var_suben.get().strip()
        s.companies_xlsx = self.var_excel.get().strip()
        s.cv_path = self.var_cv.get().strip()
        s.cover_letter_ar = self.var_lar.get().strip()
        s.cover_letter_en = self.var_len.get().strip()
        s.daily_cap = int(self.var_cap.get())
        s.min_delay = int(self.var_min.get())
        s.max_delay = int(self.var_max.get())
        s.pixel_base_url = self.var_pixel.get().strip()
        s.stats_token = self.var_token.get().strip()
        s.save()
        return s

    # ---------- thread-safe UI updates ----------
    def _post(self, fn, *args) -> None:
        """Queue a UI update to run on the main thread."""
        self._ui_queue.put((fn, args))

    def _drain_ui_queue(self) -> None:
        try:
            while True:
                fn, args = self._ui_queue.get_nowait()
                try:
                    fn(*args)
                except Exception:
                    pass
        except queue.Empty:
            pass
        self.root.after(100, self._drain_ui_queue)

    def _append_log(self, level: str, msg: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n", level)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_state_label(self, state: str) -> None:
        mapping = {
            "running": ("●  يعمل الآن", OK),
            "waiting": ("●  ينتظر الفاصل الزمني", WARN),
            "paused": ("●  متوقف مؤقتًا", WARN),
            "stopped": ("●  متوقف", MUTED),
            "cap": ("●  تم الوصول للحد اليومي", ACCENT),
            "done": ("●  اكتملت الحملة", OK),
        }
        text, color = mapping.get(state, ("●  —", MUTED))
        self.lbl_state.config(text=text, foreground=color)
        if state in ("stopped", "done", "cap"):
            self._set_controls_idle()

    def _update_counts(self, counts: dict) -> None:
        total = counts.get("total", 0)
        sent = counts.get("sent", 0)
        failed = counts.get("failed", 0)
        pending = counts.get("pending", 0)
        opened = counts.get("opened", 0)
        self.lbl_counts.config(
            text=f"مُرسَل: {sent}  |  فشل: {failed}  |  متبقٍ: {pending}  |  "
                 f"فُتح: {opened}  |  الإجمالي: {total}"
        )
        if total:
            self.progress["maximum"] = total
            self.progress["value"] = sent + failed

    def _set_countdown(self, secs: int) -> None:
        self.lbl_count.config(text=f"الإيميل التالي بعد {secs} ثانية...")

    # ---------- actions ----------
    def _toggle_pw(self) -> None:
        self.entry_apppw.config(show="" if self.var_showpw.get() else "•")

    def _test_login(self) -> None:
        s = self._collect_settings()
        try:
            sender = EmailSender(s.gmail_address, s.app_password, s.sender_name,
                                 self._dummy_cv())
            sender.verify_login()
            messagebox.showinfo("نجاح", "تم تسجيل الدخول إلى Gmail بنجاح ✅")
        except EmailConfigError as exc:
            messagebox.showerror("فشل", str(exc))
        except Exception as exc:
            messagebox.showerror("خطأ", f"تعذّر الاتصال: {exc}")

    def _dummy_cv(self) -> str:
        """Login test doesn't need the real CV; make a tiny temp file if missing."""
        cv = self.var_cv.get().strip()
        if cv and os.path.exists(cv):
            return cv
        os.makedirs("data", exist_ok=True)
        tmp = "data/_login_test.pdf"
        with open(tmp, "wb") as f:
            f.write(b"%PDF-1.4 test")
        return tmp

    def _validate_for_send(self, s: Settings) -> str | None:
        if not s.gmail_address or "@" not in s.gmail_address:
            return "أدخل إيميل Gmail صحيح."
        if not s.app_password:
            return "أدخل App Password."
        if not s.cv_path or not os.path.exists(s.cv_path):
            return "اختر ملف CV صالح."
        if not s.companies_xlsx or not os.path.exists(s.companies_xlsx):
            return "اختر ملف Excel صالح."
        if not os.path.exists(s.cover_letter_en):
            return "ملف الرسالة الإنجليزية غير موجود."
        if s.min_delay > s.max_delay:
            return "أقل فاصل يجب أن يكون أصغر من أكبر فاصل."
        return None

    def _load_list(self) -> None:
        s = self._collect_settings()
        err = self._validate_for_send(s)
        if err:
            messagebox.showerror("بيانات ناقصة", err)
            return
        result = read_companies(s.companies_xlsx, default_lang=s.default_lang)
        if result.valid_count == 0:
            messagebox.showerror("لا توجد بيانات",
                                 "لم يتم العثور على شركات صالحة.\n" +
                                 "\n".join(result.errors[:8]))
            return
        if self.db is None:
            self.db = Database(DB_PATH)
        inserted = self.db.import_recipients(result.recipients, s.companies_xlsx)
        counts = self.db.counts()
        self._update_counts(counts)
        self._append_log("info",
                         f"تم تحميل {result.valid_count} شركة "
                         f"({inserted} جديدة، {counts['sent']} مُرسلة سابقًا).")
        if result.errors:
            self._append_log("warn", f"تم تخطّي {result.error_count} صف:")
            for e in result.errors[:15]:
                self._append_log("warn", "  • " + e)
        self.btn_start.config(state="normal")

    def _build_engine(self, s: Settings) -> CampaignEngine:
        sender = EmailSender(s.gmail_address, s.app_password, s.sender_name,
                             s.cv_path, s.subject_ar, s.subject_en)
        language = LanguageHandler(s.cover_letter_ar, s.cover_letter_en, s.default_lang)
        tracker = Tracker(s.pixel_base_url, s.stats_token)
        limiter = RateLimiter(s.min_delay, s.max_delay, s.daily_cap)
        cb = CampaignCallbacks(
            on_progress=lambda c: self._post(self._update_counts, c),
            on_log=lambda lvl, m: self._post(self._append_log, lvl, m),
            on_state=lambda st: self._post(self._set_state_label, st),
            on_countdown=lambda n: self._post(self._set_countdown, n),
        )
        return CampaignEngine(self.db, sender, language, tracker, limiter,
                              s.sender_name, cb)

    def _start(self) -> None:
        if self.engine and self.engine.is_running:
            return
        s = self._collect_settings()
        err = self._validate_for_send(s)
        if err:
            messagebox.showerror("بيانات ناقصة", err)
            return
        if self.db is None:
            messagebox.showwarning("تنبيه", "حمّل القائمة أولًا.")
            return
        try:
            self.engine = self._build_engine(s)
        except EmailConfigError as exc:
            messagebox.showerror("خطأ في الإعداد", str(exc))
            return
        self.engine.start()
        self.btn_start.config(state="disabled")
        self.btn_load.config(state="disabled")
        self.btn_pause.config(state="normal", text="⏸️ إيقاف مؤقت")
        self.btn_stop.config(state="normal")

    def _pause(self) -> None:
        if not self.engine:
            return
        if self.engine._pause_event.is_set():
            self.engine.resume()
            self.btn_pause.config(text="⏸️ إيقاف مؤقت")
        else:
            self.engine.pause()
            self.btn_pause.config(text="▶️ استئناف")

    def _stop(self) -> None:
        if self.engine:
            self.engine.stop()

    def _set_controls_idle(self) -> None:
        self.btn_start.config(state="normal")
        self.btn_load.config(state="normal")
        self.btn_pause.config(state="disabled", text="⏸️ إيقاف مؤقت")
        self.btn_stop.config(state="disabled")

    def _refresh_stats(self) -> None:
        if self.db is None:
            self.db = Database(DB_PATH)
        s = self._collect_settings()
        tracker = Tracker(s.pixel_base_url, s.stats_token)
        if not tracker.enabled:
            messagebox.showinfo("غير مفعّل", "أدخل رابط البكسل أولًا.")
            return

        def work():
            opens = tracker.fetch_opens()
            self.db.upsert_opens(opens)
            counts = self.db.counts()
            companies = self.db.opened_companies(50)
            self._post(self._show_stats, counts, companies)

        import threading
        threading.Thread(target=work, daemon=True).start()

    def _show_stats(self, counts: dict, companies: list) -> None:
        self._update_counts(counts)
        self._append_log("info", f"تحديث الإحصائيات: {counts['opened']} شركة فتحت الإيميل.")
        for c in companies[:20]:
            self._append_log("success",
                             f"  👁 {c['company_name']} — {c['open_count']} مرة")

    # ---------- shutdown ----------
    def _on_close(self) -> None:
        if self.engine and self.engine.is_running:
            if not messagebox.askyesno("تأكيد",
                                       "الحملة قيد التشغيل. هل تريد الإيقاف والخروج؟"):
                return
            self.engine.stop()
            self.engine.join(5)
        if self.db:
            self.db.close()
        self.root.destroy()
