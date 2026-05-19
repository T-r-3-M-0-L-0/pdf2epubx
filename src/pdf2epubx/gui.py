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
        self.title("pdf2epubx — PDF → EPUB (для Xteink X3)")
        self.geometry("980x980")
        self.resizable(True, True)

        ctk.CTkLabel(self, text="pdf2epubx Converter", font=ctk.CTkFont(size=28, weight="bold")).pack(pady=20)

        # PDF файл
        self.pdf_path = ctk.StringVar()
        ctk.CTkLabel(self, text="PDF файл:").pack(anchor="w", padx=40)
        self.file_entry = ctk.CTkEntry(self, textvariable=self.pdf_path, width=760)
        self.file_entry.pack(pady=8, padx=40)
        ctk.CTkButton(self, text="Выбрать PDF", command=self.browse_pdf).pack(pady=5)

        # Профиль
        ctk.CTkLabel(self, text="Профиль:").pack(anchor="w", padx=40, pady=(20, 5))
        self.profile_var = ctk.StringVar(value="technical")
        ctk.CTkOptionMenu(self, values=["novel", "technical", "programming", "hybrid", "facsimile"],
                          variable=self.profile_var).pack(pady=5, padx=40)

        # Настройки колонтитулов
        ctk.CTkLabel(self, text="Высота верхнего колонтитула (points):", font=ctk.CTkFont(size=13)).pack(anchor="w", padx=40, pady=(20, 0))
        self.header_height = ctk.DoubleVar(value=50.0)
        ctk.CTkSlider(self, from_=20, to=120, variable=self.header_height, number_of_steps=100).pack(padx=40, pady=5, fill="x")
        ctk.CTkLabel(self, textvariable=self.header_height).pack(anchor="e", padx=40)

        ctk.CTkLabel(self, text="Высота нижнего колонтитула (points):", font=ctk.CTkFont(size=13)).pack(anchor="w", padx=40, pady=(15, 0))
        self.footer_height = ctk.DoubleVar(value=45.0)
        ctk.CTkSlider(self, from_=20, to=120, variable=self.footer_height, number_of_steps=100).pack(padx=40, pady=5, fill="x")
        ctk.CTkLabel(self, textvariable=self.footer_height).pack(anchor="e", padx=40)

        # === НОВЫЕ ОПЦИИ ===
        self.preserve_images_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(self, text="Сохранять изображения (схемы, диаграммы)", variable=self.preserve_images_var).pack(anchor="w", padx=40, pady=(20, 5))
        self.skip_toc_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(self, text="Пропускать печатное оглавление (первые страницы)", variable=self.skip_toc_var).pack(anchor="w", padx=40, pady=5)

        # Кнопка
        self.convert_btn = ctk.CTkButton(
            self, text="Конвертировать в EPUB", font=ctk.CTkFont(size=18),
            height=50, command=self.start_conversion
        )
        self.convert_btn.pack(pady=30)

        self.log = ctk.CTkTextbox(self, height=220, width=880)
        self.log.pack(pady=10, padx=40)

    def browse_pdf(self):
        path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if path:
            self.pdf_path.set(path)

    def start_conversion(self):
        if not self.pdf_path.get():
            messagebox.showerror("Ошибка", "Выберите PDF-файл!")
            return

        self.convert_btn.configure(state="disabled")
        self.log.insert("end", "Запуск конвертации...\n")
        self.log.see("end")

        threading.Thread(target=self.run_conversion, daemon=True).start()

    def run_conversion(self):
        input_path = Path(self.pdf_path.get())
        output_path = input_path.with_suffix(".epub")

        try:
            self.log.insert("end", f"Файл: {input_path.name}\n")
            self.log.insert("end", f"Профиль: {self.profile_var.get()}\n")
            self.log.insert("end", f"Изображения: {'включены' if self.preserve_images_var.get() else 'ПРОПУЩЕНЫ'}\n")
            self.log.insert("end", f"Оглавление: {'пропущено' if self.skip_toc_var.get() else 'включено'}\n")
            self.log.see("end")

            result_path = convert_pdf_to_epub(
                input_pdf=input_path,
                output_epub=output_path,
                profile_name=self.profile_var.get(),
                header_height=self.header_height.get(),
                footer_height=self.footer_height.get(),
                preserve_images=self.preserve_images_var.get(),   # ← новая передача
                skip_printed_toc=self.skip_toc_var.get(),         # ← новая передача
                title=None,
                author=None,
                language="ru",
                ocr_mode="auto",
                ocr_language="rus+eng",
                pages_per_chapter=10,
                split_by_outline=True,
            )

            self.log.insert("end", "Конвертация завершена успешно!\n")
            self.log.insert("end", f"EPUB: {result_path.name}\n\n")

        except Exception as e:
            self.log.insert("end", f"Ошибка:\n{str(e)}\n\n")
        finally:
            self.convert_btn.configure(state="normal")
            self.log.see("end")


if __name__ == "__main__":
    app = Pdf2EpubGUI()
    app.mainloop()