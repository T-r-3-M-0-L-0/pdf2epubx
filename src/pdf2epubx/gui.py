import customtkinter as ctk
from tkinterdnd2 import *
from pathlib import Path
import threading
from tkinter import filedialog, messagebox
import os
import sys

# Убедитесь, что путь к модулям верный
from pdf2epubx.converter import convert_pdf_to_epub
from pdf2epubx.profiles import ProgrammingLanguage
from pdf2epubx.logger import create_logger

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class Pdf2EpubGUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("pdf2epubx — PDF → EPUB (Advanced)")
        
        # Настройка размера и адаптивности
        self.geometry("1100x900")
        self.minsize(900, 700)
        
        # Сетка основного окна для растягивания
        self.grid_rowconfigure(1, weight=1) # Лог растягивается
        self.grid_columnconfigure(0, weight=1)

        # Заголовок
        self.header_label = ctk.CTkLabel(self, text="pdf2epubx Converter", font=ctk.CTkFont(size=24, weight="bold"))
        self.header_label.grid(row=0, column=0, pady=10, sticky="ew")

        # Основной контейнер
        main_container = ctk.CTkFrame(self)
        main_container.grid(row=1, column=0, padx=20, pady=(0, 10), sticky="nsew")
        main_container.grid_rowconfigure(0, weight=1)
        main_container.grid_columnconfigure(0, weight=1)

        # Канвас со скроллом
        self.canvas = ctk.CTkCanvas(main_container, highlightthickness=0)
        self.scrollbar = ctk.CTkScrollbar(main_container, orientation="vertical", command=self.canvas.yview)
        self.scrollable_frame = ctk.CTkFrame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        # Привязка колеса мыши
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        # Чтобы контент центрировался и не сжимался слишком сильно
        self.scrollable_frame.bind("<Configure>", self._on_frame_configure)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")

        # --- Содержимое скроллируемой области ---
        content_frame = self.scrollable_frame
        
        # Отступы внутри фрейма
        pad_x = 30
        pad_y = 10

        # 1. Выбор файла
        ctk.CTkLabel(content_frame, text="📂 Входной файл PDF", font=ctk.CTkFont(weight="bold", size=16)).pack(anchor="w", padx=pad_x, pady=(pad_y, 5))
        self.pdf_path = ctk.StringVar()
        file_entry_frame = ctk.CTkFrame(content_frame)
        file_entry_frame.pack(fill="x", padx=pad_x, pady=5)
        file_entry_frame.grid_columnconfigure(0, weight=1)
        
        self.file_entry = ctk.CTkEntry(file_entry_frame, textvariable=self.pdf_path, placeholder_text="Выберите файл...")
        self.file_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        ctk.CTkButton(file_entry_frame, text="Обзор", command=self.browse_pdf, width=100).grid(row=0, column=1)

        # 2. Профиль
        ctk.CTkLabel(content_frame, text="⚙️ Профиль конвертации", font=ctk.CTkFont(weight="bold", size=16)).pack(anchor="w", padx=pad_x, pady=(pad_y*2, 5))
        self.profile_var = ctk.StringVar(value="technical")
        self.profile_menu = ctk.CTkOptionMenu(content_frame, values=["novel", "technical", "programming", "hybrid", "facsimile"], variable=self.profile_var, command=self.update_programming_options)
        self.profile_menu.pack(pady=5, padx=pad_x, anchor="w")

        # Язык программирования (скрыт по умолчанию)
        self.lang_frame = ctk.CTkFrame(content_frame)
        ctk.CTkLabel(self.lang_frame, text="Язык программирования:").pack(side="left", padx=5)
        self.programming_lang_var = ctk.StringVar(value="General")
        self.lang_menu = ctk.CTkOptionMenu(self.lang_frame, values=["General", "Python", "Java", "Golang", "C++", "C#", "C", "PowerShell", "Bash"], variable=self.programming_lang_var)
        self.lang_menu.pack(side="left", padx=5)
        # Не пакуруем сразу, вызывается в update_programming_options

        # 3. Основные настройки
        ctk.CTkLabel(content_frame, text="📝 Обработка текста", font=ctk.CTkFont(weight="bold", size=16)).pack(anchor="w", padx=pad_x, pady=(pad_y*2, 5))
        
        self.aggressive_var = ctk.StringVar(value="Medium")
        agg_frame = ctk.CTkFrame(content_frame)
        agg_frame.pack(pady=5, padx=pad_x, anchor="w")
        ctk.CTkLabel(agg_frame, text="Склейка параграфов:").pack(side="left", padx=5)
        ctk.CTkOptionMenu(agg_frame, values=["Low", "Medium", "Aggressive"], variable=self.aggressive_var, width=120).pack(side="left", padx=5)

        self.disable_join_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(content_frame, text="Полностью отключить склейку", variable=self.disable_join_var).pack(anchor="w", padx=pad_x, pady=2)

        self.preserve_images_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(content_frame, text="Сохранять изображения", variable=self.preserve_images_var).pack(anchor="w", padx=pad_x, pady=2)

        self.preserve_figure_references_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(content_frame, text="Сохранять ссылки на рисунки (на рис. 1.4)", variable=self.preserve_figure_references_var).pack(anchor="w", padx=pad_x, pady=2)

        # 4. Оптимизация изображений
        ctk.CTkLabel(content_frame, text="🖼️ Оптимизация изображений", font=ctk.CTkFont(weight="bold", size=16)).pack(anchor="w", padx=pad_x, pady=(pad_y*2, 5))
        self.optimize_images_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(content_frame, text="Включить сжатие и конвертацию (WebP/JPEG)", variable=self.optimize_images_var).pack(anchor="w", padx=pad_x, pady=2)

        img_opt_frame = ctk.CTkFrame(content_frame)
        img_opt_frame.pack(pady=5, padx=pad_x, anchor="w")
        ctk.CTkLabel(img_opt_frame, text="Качество (1-100):").pack(side="left", padx=5)
        self.image_quality_var = ctk.StringVar(value="85")
        ctk.CTkEntry(img_opt_frame, textvariable=self.image_quality_var, width=60).pack(side="left", padx=5)
        
        ctk.CTkLabel(img_opt_frame, text="Формат:").pack(side="left", padx=(15,5))
        self.image_format_var = ctk.StringVar(value="webp")
        ctk.CTkOptionMenu(img_opt_frame, values=["webp", "jpeg", "png"], variable=self.image_format_var, width=100).pack(side="left", padx=5)

        # 5. Таблицы и Формулы (РАЗБЛОКИРОВАНО)
        ctk.CTkLabel(content_frame, text="📐 Таблицы и Формулы", font=ctk.CTkFont(weight="bold", size=16)).pack(anchor="w", padx=pad_x, pady=(pad_y*2, 5))
        
        self.improved_tables_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(content_frame, text="Улучшенный парсинг таблиц (HTML <table>)", variable=self.improved_tables_var).pack(anchor="w", padx=pad_x, pady=2)
        
        self.detect_formulas_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(content_frame, text="Распознавание формул (LaTeX/Unicode)", variable=self.detect_formulas_var).pack(anchor="w", padx=pad_x, pady=2)

        # 6. Кэш и Валидация
        ctk.CTkLabel(content_frame, text="💾 Сервисные опции", font=ctk.CTkFont(weight="bold", size=16)).pack(anchor="w", padx=pad_x, pady=(pad_y*2, 5))
        
        self.cache_enabled_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(content_frame, text="Включить кэширование (ускорение повторной конвертации)", variable=self.cache_enabled_var).pack(anchor="w", padx=pad_x, pady=2)

        self.validate_output_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(content_frame, text="Валидировать выходной EPUB (медленнее)", variable=self.validate_output_var).pack(anchor="w", padx=pad_x, pady=2)

        self.verbose_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(content_frame, text="Подробный режим логов (Debug)", variable=self.verbose_var).pack(anchor="w", padx=pad_x, pady=2)

        # Лог файл
        log_file_frame = ctk.CTkFrame(content_frame)
        log_file_frame.pack(pady=10, padx=pad_x, anchor="w", fill="x")
        self.log_file_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(log_file_frame, text="Сохранять лог в файл:", variable=self.log_file_var).pack(side="left", padx=5)
        
        self.log_file_path_var = ctk.StringVar(value="")
        self.log_entry = ctk.CTkEntry(log_file_frame, textvariable=self.log_file_path_var, width=400, state="disabled")
        self.log_entry.pack(side="left", padx=5)
        ctk.CTkButton(log_file_frame, text="...", width=30, command=self.browse_log_file).pack(side="left", padx=5)
        
        self.log_file_var.trace_add("write", self.toggle_log_entry)

        # --- Нижняя панель (вне скролла) ---
        bottom_frame = ctk.CTkFrame(self)
        bottom_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 10))
        bottom_frame.grid_columnconfigure(0, weight=1)

        # Прогресс бар
        self.progress_bar = ctk.CTkProgressBar(bottom_frame, mode="determinate")
        self.progress_bar.pack(fill="x", padx=20, pady=(10, 5))
        self.progress_label = ctk.CTkLabel(bottom_frame, text="Готов к работе", font=ctk.CTkFont(size=12))
        self.progress_label.pack(pady=(0, 10))

        # Кнопка старта
        self.convert_btn = ctk.CTkButton(bottom_frame, text="НАЧАТЬ КОНВЕРТАЦИЮ", font=ctk.CTkFont(size=18, weight="bold"), height=50, command=self.start_conversion)
        self.convert_btn.pack(fill="x", padx=20, pady=10)

        # Лог вывода
        log_container = ctk.CTkFrame(self)
        log_container.grid(row=3, column=0, sticky="nsew", padx=20, pady=(0, 20))
        log_container.grid_rowconfigure(0, weight=1)
        log_container.grid_columnconfigure(0, weight=1)

        self.log_text = ctk.CTkTextbox(log_container, font=ctk.CTkFont(family="Consolas", size=11))
        self.log_text.grid(row=0, column=0, sticky="nsew")
        
        ctk.CTkButton(log_container, text="Копировать лог", width=100, command=self.copy_log).grid(row=1, column=0, pady=5)

        # Инициализация состояния
        self.update_programming_options()

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def _on_frame_configure(self, event):
        # Обновляем ширину канваса, чтобы контент растягивался
        self.canvas.itemconfig(self.canvas_window, width=event.width)

    def toggle_log_entry(self, *args):
        if self.log_file_var.get():
            self.log_entry.configure(state="normal")
        else:
            self.log_entry.configure(state="disabled")

    def browse_log_file(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".log",
            filetypes=[("Log files", "*.log"), ("All files", "*.*")],
            initialfile="pdf2epubx.log"
        )
        if path:
            self.log_file_path_var.set(path)

    def update_programming_options(self, *args):
        if self.profile_var.get() == "programming":
            self.lang_frame.pack(pady=5, padx=30, anchor="w")
        else:
            self.lang_frame.pack_forget()

    def copy_log(self):
        text = self.log_text.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("Лог", "Лог скопирован в буфер обмена")

    def browse_pdf(self):
        path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if path:
            self.pdf_path.set(path)

    def log_message(self, message: str):
        """Безопасный вывод в лог из любого потока"""
        self.after(0, lambda: self.log_text.insert("end", message + "\n"))
        self.after(0, lambda: self.log_text.see("end"))

    def update_progress(self, current: int, total: int, message: str):
        """Обновление прогресс-бара из любого потока"""
        percent = current / total
        self.after(0, lambda: self.progress_bar.set(percent))
        self.after(0, lambda: self.progress_label.configure(text=f"{message} ({current}/{total})"))

    def start_conversion(self):
        if not self.pdf_path.get():
            messagebox.showerror("Ошибка", "Выберите PDF-файл!")
            return

        self.convert_btn.configure(state="disabled")
        self.progress_bar.set(0)
        self.progress_label.configure(text="Инициализация...")
        self.log_text.delete("1.0", "end")
        self.log_message("🚀 Запуск конвертации...")

        # Запуск в потоке
        threading.Thread(target=self.run_conversion, daemon=True).start()

    def run_conversion(self):
        input_path = Path(self.pdf_path.get())
        output_path = input_path.with_suffix(".epub")

        aggressive_level = "Off" if self.disable_join_var.get() else self.aggressive_var.get()

        # Сбор параметров
        try:
            image_quality = int(self.image_quality_var.get())
        except ValueError:
            image_quality = 85

        log_file = None
        if self.log_file_var.get() and self.log_file_path_var.get():
            log_file = Path(self.log_file_path_var.get())

        # Логирование настроек
        self.log_message(f"📄 Файл: {input_path.name}")
        self.log_message(f"📌 Профиль: {self.profile_var.get()}")
        if self.profile_var.get() == "programming":
            self.log_message(f"   Язык: {self.programming_lang_var.get()}")
        self.log_message(f"🖼️ Изображения: {'Оптимизация вкл' if self.optimize_images_var.get() else 'Оригинал'}")
        self.log_message(f"📐 Таблицы: {'Вкл' if self.improved_tables_var.get() else 'Выкл'}")
        self.log_message(f"∑ Формулы: {'Вкл' if self.detect_formulas_var.get() else 'Выкл'}")
        self.log_message(f"💾 Кэш: {'Вкл' if self.cache_enabled_var.get() else 'Выкл'}")
        self.log_message("-" * 30)

        try:
            # Вызов конвертера с callback
            result_path = convert_pdf_to_epub(
                input_pdf=input_path,
                output_epub=output_path,
                profile_name=self.profile_var.get(),
                aggressive_level=aggressive_level,
                preserve_images=self.preserve_images_var.get(),
                preserve_figure_references=self.preserve_figure_references_var.get(),
                programming_language=self.programming_lang_var.get() if self.profile_var.get() == "programming" else "General",
                # Новые параметры
                optimize_images=self.optimize_images_var.get(),
                image_quality=image_quality,
                image_format=self.image_format_var.get(),
                validate_output=self.validate_output_var.get(),
                cache_enabled=self.cache_enabled_var.get(),
                verbose=self.verbose_var.get(),
                log_file=log_file,
                # Параметры нового функционала
                enable_tables=self.improved_tables_var.get(),
                enable_formulas=self.detect_formulas_var.get(),
                # Callback
                progress_callback=self.update_progress
            )

            self.log_message("\n✅ Конвертация завершена успешно!")
            self.log_message(f"📚 Результат: {result_path}")
            self.progress_label.configure(text="Готово!")
            messagebox.showinfo("Успех", f"Файл создан:\n{result_path}")

        except Exception as e:
            error_msg = str(e)
            self.log_message(f"\n❌ Ошибка:\n{error_msg}")
            self.progress_label.configure(text="Ошибка!")
            messagebox.showerror("Ошибка конвертации", error_msg)
        
        finally:
            self.convert_btn.configure(state="normal")


if __name__ == "__main__":
    app = Pdf2EpubGUI()
    app.mainloop()
    