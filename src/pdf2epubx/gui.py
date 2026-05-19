import customtkinter as ctk
from tkinterdnd2 import *
from pathlib import Path
import threading
from tkinter import filedialog, messagebox

# === НОВОЕ: прямой импорт функции конвертации ===
from pdf2epubx.converter import convert_pdf_to_epub
from pdf2epubx.profiles import get_profile

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class Pdf2EpubGUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("pdf2epubx — конвертер из PDF в EPUB")
        self.geometry("920x640")
        self.resizable(False, False)

        ctk.CTkLabel(self, text="pdf2epubx Converter", font=ctk.CTkFont(size=28, weight="bold")).pack(pady=20)

        # Выбор PDF
        self.pdf_path = ctk.StringVar()
        ctk.CTkLabel(self, text="PDF файл:").pack(anchor="w", padx=40)
        self.file_entry = ctk.CTkEntry(self, textvariable=self.pdf_path, width=720)
        self.file_entry.pack(pady=8, padx=40)
        ctk.CTkButton(self, text="Выбрать PDF", command=self.browse_pdf).pack(pady=5)

        # Профиль
        ctk.CTkLabel(self, text="Профиль:").pack(anchor="w", padx=40, pady=(20, 5))
        self.profile_var = ctk.StringVar(value="technical")
        ctk.CTkOptionMenu(
            self,
            values=["novel", "technical", "hybrid", "facsimile"],
            variable=self.profile_var,
        ).pack(pady=5, padx=40)

        # Кнопка
        self.convert_btn = ctk.CTkButton(
            self,
            text="Конвертировать в EPUB",
            font=ctk.CTkFont(size=18),
            height=50,
            command=self.start_conversion,
        )
        self.convert_btn.pack(pady=30)

        self.log = ctk.CTkTextbox(self, height=220, width=840)
        self.log.pack(pady=10, padx=40)

    def browse_pdf(self):
        path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if path:
            self.pdf_path.set(path)

    def start_conversion(self):
        if not self.pdf_path.get():
            messagebox.showerror("Ошибка", "Сначала выберите PDF-файл!")
            return

        self.convert_btn.configure(state="disabled")
        self.log.insert("end", "Запуск конвертации...\n")
        self.log.see("end")

        threading.Thread(target=self.run_conversion, daemon=True).start()

    def run_conversion(self):
        input_path = Path(self.pdf_path.get())
        output_path = input_path.with_suffix(".epub")

        try:
            self.log.insert("end", f"Конвертируем: {input_path.name}\n")
            self.log.insert("end", f"Профиль: {self.profile_var.get()}\n")
            self.log.see("end")

            # ПРЯМОЙ ВЫЗОВ — работает и в .exe, и при обычном запуске
            result_path = convert_pdf_to_epub(
                input_pdf=input_path,
                output_epub=output_path,
                profile_name=self.profile_var.get(),
                title=None,
                author=None,
                language="ru",
                ocr_mode="auto",
                ocr_language="rus+eng",
                pages_per_chapter=10,
                rules_path=None,
                split_by_outline=True,
            )

            self.log.insert("end", "Конвертация завершена успешно!\n")
            self.log.insert("end", f"EPUB сохранён: {result_path.name}\n")
            self.log.insert("end", f"   Путь: {result_path}\n\n")

        except Exception as e:
            self.log.insert("end", f"Ошибка конвертации:\n{str(e)}\n\n")
        finally:
            self.convert_btn.configure(state="normal")
            self.log.see("end")


if __name__ == "__main__":
    app = Pdf2EpubGUI()
    app.mainloop()