import customtkinter as ctk
from tkinterdnd2 import *
from pathlib import Path
import threading
from tkinter import filedialog, messagebox

from pdf2epubx.converter import convert_pdf_to_epub

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class Pdf2EpubGUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("pdf2epubx — PDF → EPUB (Advanced)")
        self.geometry("1280x860")
        self.minsize(1100, 700)

        header = ctk.CTkLabel(self, text="pdf2epubx Converter", font=ctk.CTkFont(size=26, weight="bold"))
        header.pack(pady=12)

        main = ctk.CTkFrame(self)
        main.pack(fill="both", expand=True, padx=15, pady=10)

        # Левая панель
        left = ctk.CTkFrame(main, width=460)
        left.pack(side="left", fill="y", padx=(0, 12))
        left.pack_propagate(False)

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
        self.profile_menu = ctk.CTkOptionMenu(left, values=["novel", "technical", "programming", "hybrid", "facsimile"],
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
        self.log_message("-" * 50)

        try:
            result_path = convert_pdf_to_epub(
                input_pdf=input_path,
                output_epub=output_path,
                profile_name=self.profile_var.get(),
                aggressive_level=aggressive_level,
                preserve_images=self.preserve_images_var.get(),
                preserve_figure_references=self.preserve_figure_references_var.get(),
                programming_language=self.programming_lang_var.get() if self.profile_var.get() == "programming" else "General",
                # Поддерживаемые параметры из твоего converter.py
                optimize_images=self.optimize_images_var.get(),
                image_quality=image_quality,
                image_format=self.image_format_var.get(),
                enable_tables=self.improved_tables_var.get(),
                enable_formulas=self.detect_formulas_var.get(),
                cache_enabled=self.cache_enabled_var.get(),
                validate_output=self.validate_output_var.get(),
                verbose=self.verbose_var.get(),
                # Callback (только progress)
                progress_callback=self.update_progress,
            )

            self.log_message("\n✅ Конвертация завершена успешно!")
            self.log_message(f"📚 Результат: {result_path}")
            self.progress_label.configure(text="Готово!")
            messagebox.showinfo("Успех", f"Файл создан:\n{result_path}")

        except Exception as e:
            self.log_message(f"\n❌ Ошибка:\n{str(e)}")
            self.progress_label.configure(text="Ошибка!")
            messagebox.showerror("Ошибка", str(e))

        finally:
            self.convert_btn.configure(state="normal")


if __name__ == "__main__":
    app = Pdf2EpubGUI()
    app.mainloop()