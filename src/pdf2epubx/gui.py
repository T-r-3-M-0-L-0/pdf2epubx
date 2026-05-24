import customtkinter as ctk
from tkinterdnd2 import *
from pathlib import Path
import threading
from tkinter import filedialog, messagebox

from pdf2epubx.converter import convert_pdf_to_epub
from pdf2epubx.multiprocessing_converter import convert_pdf_to_epub_parallel
from pdf2epubx.ocr import is_ocr_available
from pdf2epubx.layoutlm_processor import HAS_LAYOUTLM
from pdf2epubx.image_preprocessor import HAS_OPENCV

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class Pdf2EpubGUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("pdf2epubx — PDF → EPUB (Advanced)")
        self.geometry("1280x900")
        self.minsize(1100, 700)

        header = ctk.CTkLabel(self, text="pdf2epubx Converter", font=ctk.CTkFont(size=26, weight="bold"))
        header.pack(pady=12)

        main = ctk.CTkFrame(self)
        main.pack(fill="both", expand=True, padx=15, pady=10)

        # Левая панель (прокручиваемая)
        left = ctk.CTkScrollableFrame(main, width=460)
        left.pack(side="left", fill="y", padx=(0, 12))

        # Правая панель (лог)
        right = ctk.CTkFrame(main)
        right.pack(side="right", fill="both", expand=True)

        pad = 18

        # PDF файл
        ctk.CTkLabel(left, text="📂 PDF файл", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=pad, pady=(pad, 4))
        self.pdf_path = ctk.StringVar()
        entry_frame = ctk.CTkFrame(left)
        entry_frame.pack(fill="x", padx=pad, pady=4)
        self.file_entry = ctk.CTkEntry(entry_frame, textvariable=self.pdf_path, placeholder_text="Выберите PDF-файл...")
        self.file_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(entry_frame, text="Обзор", width=90, command=self.browse_pdf).pack(side="right")

        # Профиль
        ctk.CTkLabel(left, text="⚙️ Профиль", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=pad, pady=(pad, 4))
        self.profile_var = ctk.StringVar(value="technical")
        self.profile_menu = ctk.CTkOptionMenu(left, values=["novel", "technical", "academic", "manga", "newspaper", "hybrid", "facsimile", "programming"],
                                              variable=self.profile_var, command=self.update_programming_options)
        self.profile_menu.pack(pady=4, padx=pad, anchor="w")

        # Язык программирования
        self.lang_frame = ctk.CTkFrame(left)
        ctk.CTkLabel(self.lang_frame, text="Язык программирования:").pack(side="left", padx=5)
        self.programming_lang_var = ctk.StringVar(value="General")
        self.lang_menu = ctk.CTkOptionMenu(self.lang_frame,
                                           values=["General", "Python", "Java", "Golang", "C++", "C#", "C", "PowerShell", "Bash"],
                                           variable=self.programming_lang_var)
        self.lang_menu.pack(side="left", padx=5)
        self.lang_frame.pack(pady=8, padx=pad, anchor="w")
        self.lang_frame.pack_forget()

        # Склейка
        ctk.CTkLabel(left, text="📝 Склейка параграфов", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=pad, pady=(pad, 4))
        self.aggressive_var = ctk.StringVar(value="Medium")
        ctk.CTkOptionMenu(left, values=["Low", "Medium", "Aggressive"], variable=self.aggressive_var).pack(pady=4, padx=pad, anchor="w")

        self.disable_join_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(left, text="Полностью отключить склейку", variable=self.disable_join_var).pack(anchor="w", padx=pad, pady=6)

        self.preserve_images_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(left, text="Сохранять изображения", variable=self.preserve_images_var).pack(anchor="w", padx=pad, pady=4)

        self.preserve_figure_references_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(left, text="Сохранять ссылки на рисунки", variable=self.preserve_figure_references_var).pack(anchor="w", padx=pad, pady=4)

        # ═══════════════════════════════════════════════
        # НОВЫЙ БЛОК: Парсинг сканов и качество
        # ═══════════════════════════════════════════════
        ctk.CTkLabel(left, text="🔍 Парсинг и качество (сканы)", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=pad, pady=(pad, 4))

        self.normalize_scan_bold_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(left, text="Нормализовать bold в сканах",
                        variable=self.normalize_scan_bold_var).pack(anchor="w", padx=pad, pady=2)
        ctk.CTkLabel(left, text="    Убирает фальшивый bold (> 40% текста bold = артефакт)",
                     font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w", padx=pad)

        self.auto_quality_fallback_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(left, text="Авто-fallback по качеству текста",
                        variable=self.auto_quality_fallback_var).pack(anchor="w", padx=pad, pady=2)
        ctk.CTkLabel(left, text="    Плохие страницы → изображение, средние → hybrid",
                     font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w", padx=pad)

        # ═══════════════════════════════════════════════
        # НОВЫЙ БЛОК: Производительность (Multiprocessing)
        # ═══════════════════════════════════════════════
        ctk.CTkLabel(left, text="⚡ Производительность", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=pad, pady=(pad, 4))

        self.use_multiprocessing_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(left, text="Включить многопроцессорную обработку",
                        variable=self.use_multiprocessing_var).pack(anchor="w", padx=pad, pady=2)
        ctk.CTkLabel(left, text="    Ускорение в 3-8 раз на многоядерных CPU",
                     font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w", padx=pad)

        mp_frame = ctk.CTkFrame(left)
        mp_frame.pack(fill="x", padx=pad, pady=4)
        ctk.CTkLabel(mp_frame, text="Workers:").pack(side="left", padx=5)
        self.num_workers_var = ctk.StringVar(value="Auto")
        self.workers_menu = ctk.CTkOptionMenu(mp_frame, values=["Auto", "1", "2", "4", "8", "16"],
                                              variable=self.num_workers_var, width=80)
        self.workers_menu.pack(side="left", padx=5)
        ctk.CTkLabel(mp_frame, text="Chunk:").pack(side="left", padx=(15, 5))
        self.chunk_size_var = ctk.StringVar(value="5")
        ctk.CTkEntry(mp_frame, textvariable=self.chunk_size_var, width=60).pack(side="left", padx=5)

        # ═══════════════════════════════════════════════
        # НОВЫЙ БЛОК: ML-улучшения (LayoutLM)
        # ═══════════════════════════════════════════════
        ctk.CTkLabel(left, text="🤖 ML-улучшения (LayoutLM)", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=pad, pady=(pad, 4))

        ml_status_text = "✅ Доступно" if HAS_LAYOUTLM else "❌ Недоступно (pip install transformers torch)"
        ctk.CTkLabel(left, text=f"    Статус: {ml_status_text}",
                     font=ctk.CTkFont(size=11), text_color="gray" if not HAS_LAYOUTLM else "green").pack(anchor="w", padx=pad)

        self.use_layoutlm_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(left, text="Использовать LayoutLM для структуры",
                        variable=self.use_layoutlm_var, state="normal" if HAS_LAYOUTLM else "disabled").pack(anchor="w", padx=pad, pady=2)

        llm_frame = ctk.CTkFrame(left)
        llm_frame.pack(fill="x", padx=pad, pady=4)
        ctk.CTkLabel(llm_frame, text="Модель:").pack(side="left", padx=5)
        self.layoutlm_model_var = ctk.StringVar(value="layoutlm")
        self.llm_model_menu = ctk.CTkOptionMenu(llm_frame, values=["layoutlm", "doclaynet"],
                                                variable=self.layoutlm_model_var, width=120,
                                                state="normal" if HAS_LAYOUTLM else "disabled")
        self.llm_model_menu.pack(side="left", padx=5)
        ctk.CTkLabel(llm_frame, text="Device:").pack(side="left", padx=(15, 5))
        self.layoutlm_device_var = ctk.StringVar(value="cpu")
        self.llm_device_menu = ctk.CTkOptionMenu(llm_frame, values=["cpu", "cuda"],
                                                 variable=self.layoutlm_device_var, width=80,
                                                 state="normal" if HAS_LAYOUTLM else "disabled")
        self.llm_device_menu.pack(side="left", padx=5)

        ctk.CTkLabel(left, text="Порог уверенности:", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=pad, pady=(4, 0))
        self.confidence_threshold_var = ctk.StringVar(value="0.7")
        conf_frame = ctk.CTkFrame(left)
        conf_frame.pack(fill="x", padx=pad, pady=4)
        ctk.CTkEntry(conf_frame, textvariable=self.confidence_threshold_var, width=80).pack(side="left", padx=5)
        ctk.CTkLabel(conf_frame, text="(0.5 - 0.95)", font=ctk.CTkFont(size=10), text_color="gray").pack(side="left", padx=5)

        # ═══════════════════════════════════════════════
        # НОВЫЙ БЛОК: Предобработка изображений
        # ═══════════════════════════════════════════════
        ctk.CTkLabel(left, text="🖼️ Предобработка изображений", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=pad, pady=(pad, 4))

        img_prep_status = "✅ OpenCV доступен" if HAS_OPENCV else "❌ OpenCV недоступен (pip install opencv-python numpy)"
        ctk.CTkLabel(left, text=f"    Статус: {img_prep_status}",
                     font=ctk.CTkFont(size=11), text_color="gray" if not HAS_OPENCV else "green").pack(anchor="w", padx=pad)

        self.use_image_preprocessing_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(left, text="Включить предобработку для OCR",
                        variable=self.use_image_preprocessing_var, state="normal" if HAS_OPENCV else "disabled").pack(anchor="w", padx=pad, pady=2)

        ip_frame = ctk.CTkFrame(left)
        ip_frame.pack(fill="x", padx=pad, pady=4)
        ctk.CTkLabel(ip_frame, text="Режим:").pack(side="left", padx=5)
        self.image_prep_mode_var = ctk.StringVar(value="balanced")
        self.ip_mode_menu = ctk.CTkOptionMenu(ip_frame, values=["speed", "balanced", "quality"],
                                              variable=self.image_prep_mode_var, width=100,
                                              state="normal" if HAS_OPENCV else "disabled")
        self.ip_mode_menu.pack(side="left", padx=5)

        self.ip_deskew_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(left, text="Deskew (выпрямление)", variable=self.ip_deskew_var,
                        state="normal" if HAS_OPENCV else "disabled").pack(anchor="w", padx=pad, pady=1)
        self.ip_denoise_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(left, text="Denoise (шумоподавление)", variable=self.ip_denoise_var,
                        state="normal" if HAS_OPENCV else "disabled").pack(anchor="w", padx=pad, pady=1)
        self.ip_enhance_contrast_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(left, text="Enhance Contrast (CLAHE)", variable=self.ip_enhance_contrast_var,
                        state="normal" if HAS_OPENCV else "disabled").pack(anchor="w", padx=pad, pady=1)
        self.ip_binarize_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(left, text="Binarize (Otsu)", variable=self.ip_binarize_var,
                        state="normal" if HAS_OPENCV else "disabled").pack(anchor="w", padx=pad, pady=1)
        self.ip_remove_borders_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(left, text="Remove Borders", variable=self.ip_remove_borders_var,
                        state="normal" if HAS_OPENCV else "disabled").pack(anchor="w", padx=pad, pady=1)

        # ═══════════════════════════════════════════════
        # НОВЫЙ БЛОК: OCR
        # ═══════════════════════════════════════════════
        ctk.CTkLabel(left, text="📷 OCR", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=pad, pady=(pad, 4))

        self.ocr_mode_var = ctk.StringVar(value="auto")
        ocr_frame = ctk.CTkFrame(left)
        ocr_frame.pack(fill="x", padx=pad, pady=4)
        ctk.CTkLabel(ocr_frame, text="Режим:").pack(side="left", padx=5)
        ctk.CTkOptionMenu(ocr_frame, values=["never", "auto", "always"],
                          variable=self.ocr_mode_var, width=120).pack(side="left", padx=5)

        self.ocr_language_var = ctk.StringVar(value="rus+eng")
        ctk.CTkLabel(ocr_frame, text="Языки:").pack(side="left", padx=(15, 5))
        ctk.CTkEntry(ocr_frame, textvariable=self.ocr_language_var, width=100).pack(side="left", padx=5)

        # Показываем доступность OCR
        ocr_status = is_ocr_available()
        status_parts = []
        if ocr_status["ocrmypdf"]:
            status_parts.append("✅ ocrmypdf")
        else:
            status_parts.append("❌ ocrmypdf")
        if ocr_status["tesseract"]:
            status_parts.append("✅ tesseract")
        else:
            status_parts.append("❌ tesseract")

        ctk.CTkLabel(left, text=f"    Доступно: {' | '.join(status_parts)}",
                     font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w", padx=pad)

        # Оптимизация изображений
        ctk.CTkLabel(left, text="🖼️ Оптимизация изображений", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=pad, pady=(pad, 4))
        self.optimize_images_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(left, text="Включить сжатие и конвертацию", variable=self.optimize_images_var).pack(anchor="w", padx=pad, pady=2)

        img_frame = ctk.CTkFrame(left)
        img_frame.pack(fill="x", padx=pad, pady=4)
        ctk.CTkLabel(img_frame, text="Качество:").pack(side="left", padx=5)
        self.image_quality_var = ctk.StringVar(value="85")
        ctk.CTkEntry(img_frame, textvariable=self.image_quality_var, width=60).pack(side="left", padx=5)
        ctk.CTkLabel(img_frame, text="Формат:").pack(side="left", padx=(15, 5))
        self.image_format_var = ctk.StringVar(value="webp")
        ctk.CTkOptionMenu(img_frame, values=["webp", "jpeg", "png"], variable=self.image_format_var, width=100).pack(side="left")

        # Таблицы и формулы
        ctk.CTkLabel(left, text="📐 Таблицы и Формулы", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=pad, pady=(pad, 4))
        self.improved_tables_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(left, text="Улучшенный парсинг таблиц", variable=self.improved_tables_var).pack(anchor="w", padx=pad, pady=2)
        self.detect_formulas_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(left, text="Распознавание формул (LaTeX)", variable=self.detect_formulas_var).pack(anchor="w", padx=pad, pady=2)

        # Сервисные опции
        ctk.CTkLabel(left, text="💾 Сервисные опции", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=pad, pady=(pad, 4))
        self.cache_enabled_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(left, text="Включить кэширование", variable=self.cache_enabled_var).pack(anchor="w", padx=pad, pady=2)
        self.validate_output_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(left, text="Валидировать выходной EPUB", variable=self.validate_output_var).pack(anchor="w", padx=pad, pady=2)
        self.verbose_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(left, text="Подробный режим логов (Debug)", variable=self.verbose_var).pack(anchor="w", padx=pad, pady=2)

        # Кнопка
        self.convert_btn = ctk.CTkButton(left, text="НАЧАТЬ КОНВЕРТАЦИЮ", font=ctk.CTkFont(size=18, weight="bold"), height=55, command=self.start_conversion)
        self.convert_btn.pack(pady=30, padx=pad, fill="x")

        # Лог
        self.log_text = ctk.CTkTextbox(right, font=ctk.CTkFont(family="Consolas", size=12))
        self.log_text.pack(fill="both", expand=True, padx=10, pady=10)
        ctk.CTkButton(right, text="Копировать лог", command=self.copy_log).pack(pady=8)

        # Прогресс-бар
        bottom = ctk.CTkFrame(self)
        bottom.pack(fill="x", padx=15, pady=10)
        self.progress_bar = ctk.CTkProgressBar(bottom, mode="determinate")
        self.progress_bar.pack(fill="x", padx=20, pady=(0, 5))
        self.progress_label = ctk.CTkLabel(bottom, text="Готов к работе", font=ctk.CTkFont(size=12))
        self.progress_label.pack()

        self.update_programming_options()

    def log_message(self, message: str):
        self.after(0, lambda: self.log_text.insert("end", message + "\n"))
        self.after(0, lambda: self.log_text.see("end"))

    def update_progress(self, current: int, total: int, message: str):
        percent = current / total if total > 0 else 0
        self.after(0, lambda: self.progress_bar.set(percent))
        self.after(0, lambda: self.progress_label.configure(text=f"{message} ({current}/{total})"))

    def copy_log(self):
        text = self.log_text.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("Готово", "Лог скопирован в буфер обмена")

    def browse_pdf(self):
        path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if path:
            self.pdf_path.set(path)

    def update_programming_options(self, *_):
        if self.profile_var.get() == "programming":
            self.lang_frame.pack(pady=8, padx=18, anchor="w")
        else:
            self.lang_frame.pack_forget()

    def start_conversion(self):
        if not self.pdf_path.get():
            messagebox.showerror("Ошибка", "Выберите PDF-файл!")
            return

        self.convert_btn.configure(state="disabled")
        self.log_text.delete("1.0", "end")
        self.progress_bar.set(0)
        self.progress_label.configure(text="Запуск...")
        self.log_message("🚀 Запуск конвертации...")

        threading.Thread(target=self.run_conversion, daemon=True).start()

    def run_conversion(self):
        input_path = Path(self.pdf_path.get())
        output_path = input_path.with_suffix(".epub")

        aggressive_level = "Off" if self.disable_join_var.get() else self.aggressive_var.get()

        try:
            image_quality = int(self.image_quality_var.get())
        except ValueError:
            image_quality = 85

        self.log_message(f"📄 Файл: {input_path.name}")
        self.log_message(f"📌 Профиль: {self.profile_var.get()}")
        if self.profile_var.get() == "programming":
            self.log_message(f"   Язык: {self.programming_lang_var.get()}")
        self.log_message(f"🖼️ Изображения: {'вкл' if self.preserve_images_var.get() else 'выкл'}")
        self.log_message(f"🔗 Ссылки на рисунки: {'сохраняются' if self.preserve_figure_references_var.get() else 'очищаются'}")
        self.log_message(f"🔍 Bold-нормализация: {'вкл' if self.normalize_scan_bold_var.get() else 'выкл'}")
        self.log_message(f"🔍 Авто-fallback: {'вкл' if self.auto_quality_fallback_var.get() else 'выкл'}")

        # Multiprocessing
        use_mp = self.use_multiprocessing_var.get()
        self.log_message(f"⚡ Multiprocessing: {'вкл' if use_mp else 'выкл'}")
        if use_mp:
            workers = self.num_workers_var.get()
            chunk = self.chunk_size_var.get()
            self.log_message(f"   Workers: {workers}, Chunk: {chunk}")

        # LayoutLM
        use_llm = self.use_layoutlm_var.get()
        self.log_message(f"🤖 LayoutLM: {'вкл' if use_llm else 'выкл'}")
        if use_llm:
            llm_model = self.layoutlm_model_var.get()
            llm_device = self.layoutlm_device_var.get()
            llm_conf = self.confidence_threshold_var.get()
            self.log_message(f"   Модель: {llm_model}, Device: {llm_device}, Confidence: {llm_conf}")

        # Image Preprocessing
        use_ip = self.use_image_preprocessing_var.get()
        self.log_message(f"🖼️ Предобработка изображений: {'вкл' if use_ip else 'выкл'}")
        if use_ip:
            ip_mode = self.image_prep_mode_var.get()
            ip_opts = []
            if self.ip_deskew_var.get(): ip_opts.append("deskew")
            if self.ip_denoise_var.get(): ip_opts.append("denoise")
            if self.ip_enhance_contrast_var.get(): ip_opts.append("enhance")
            if self.ip_binarize_var.get(): ip_opts.append("binarize")
            if self.ip_remove_borders_var.get(): ip_opts.append("borders")
            self.log_message(f"   Режим: {ip_mode}, Опции: {', '.join(ip_opts) if ip_opts else 'default'}")

        self.log_message(f"📷 OCR: {self.ocr_mode_var.get()} ({self.ocr_language_var.get()})")
        self.log_message("-" * 50)

        try:
            # Определяем num_workers для multiprocessing
            num_workers = None
            if self.num_workers_var.get() != "Auto":
                num_workers = int(self.num_workers_var.get())

            try:
                chunk_size = int(self.chunk_size_var.get())
            except ValueError:
                chunk_size = 5

            try:
                confidence_threshold = float(self.confidence_threshold_var.get())
            except ValueError:
                confidence_threshold = 0.7

            # Выбираем режим конвертации: multiprocessing или обычный
            if use_mp:
                result_path = convert_pdf_to_epub_parallel(
                    input_pdf=input_path,
                    output_epub=output_path,
                    profile_name=self.profile_var.get(),
                    aggressive_level=aggressive_level,
                    preserve_images=self.preserve_images_var.get(),
                    programming_language=self.programming_lang_var.get() if self.profile_var.get() == "programming" else "General",
                    num_workers=num_workers,
                    chunk_size=chunk_size,
                    # Scan handling
                    normalize_scan_bold=self.normalize_scan_bold_var.get(),
                    auto_quality_fallback=self.auto_quality_fallback_var.get(),
                    # Image preprocessing
                    enable_image_preprocessing=self.use_image_preprocessing_var.get(),
                    image_prep_mode=self.image_prep_mode_var.get(),
                    # OCR
                    ocr_mode=self.ocr_mode_var.get(),
                    ocr_language=self.ocr_language_var.get(),
                    # Progress
                    progress_callback=self.update_progress,
                )
            else:
                result_path = convert_pdf_to_epub(
                    input_pdf=input_path,
                    output_epub=output_path,
                    profile_name=self.profile_var.get(),
                    aggressive_level=aggressive_level,
                    preserve_images=self.preserve_images_var.get(),
                    preserve_figure_references=self.preserve_figure_references_var.get(),
                    programming_language=self.programming_lang_var.get() if self.profile_var.get() == "programming" else "General",
                    # OCR
                    ocr_mode=self.ocr_mode_var.get(),
                    ocr_language=self.ocr_language_var.get(),
                    # Scan handling
                    normalize_scan_bold=self.normalize_scan_bold_var.get(),
                    auto_quality_fallback=self.auto_quality_fallback_var.get(),
                    # Image optimization
                    optimize_images=self.optimize_images_var.get(),
                    image_quality=image_quality,
                    image_format=self.image_format_var.get(),
                    # Tables & formulas
                    enable_tables=self.improved_tables_var.get(),
                    enable_formulas=self.detect_formulas_var.get(),
                    # Image preprocessing (NEW)
                    enable_image_preprocessing=self.use_image_preprocessing_var.get(),
                    image_prep_mode=self.image_prep_mode_var.get(),
                    # LayoutLM (NEW)
                    enable_layoutlm=self.use_layoutlm_var.get(),
                    layoutlm_model=self.layoutlm_model_var.get(),
                    layoutlm_device=self.layoutlm_device_var.get(),
                    layoutlm_confidence=confidence_threshold,
                    # Service
                    cache_enabled=self.cache_enabled_var.get(),
                    validate_output=self.validate_output_var.get(),
                    verbose=self.verbose_var.get(),
                    # Progress
                    progress_callback=self.update_progress,
                )

            self.log_message("\n✅ Конвертация завершена успешно!")
            self.log_message(f"📚 Результат: {result_path}")
            self.after(0, lambda: self.progress_label.configure(text="Готово!"))
            self.after(0, lambda: messagebox.showinfo("Успех", f"Файл создан:\n{result_path}"))

        except Exception as e:
            self.log_message(f"\n❌ Ошибка:\n{str(e)}")
            self.after(0, lambda: self.progress_label.configure(text="Ошибка!"))
            self.after(0, lambda: messagebox.showerror("Ошибка", str(e)))

        finally:
            self.after(0, lambda: self.convert_btn.configure(state="normal"))


if __name__ == "__main__":
    from multiprocessing import freeze_support
    freeze_support()  # Обязательно для Windows PyInstaller с multiprocessing
    app = Pdf2EpubGUI()
    app.mainloop()