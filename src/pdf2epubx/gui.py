import customtkinter as ctk
from tkinterdnd2 import *
from pathlib import Path
import threading
from tkinter import filedialog, messagebox

from pdf2epubx.converter import convert_pdf_to_epub
from pdf2epubx.profiles import ProgrammingLanguage

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class Pdf2EpubGUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("pdf2epubx — PDF → EPUB (для Xteink X3)")
        self.geometry("1100x980")
        self.resizable(True, True)

        ctk.CTkLabel(self, text="pdf2epubx Converter", font=ctk.CTkFont(size=28, weight="bold")).pack(pady=15)

        main_frame = ctk.CTkFrame(self)
        main_frame.pack(padx=30, pady=10, fill="both", expand=True)

        ctk.CTkLabel(main_frame, text="PDF файл:").pack(anchor="w", padx=20, pady=(10,0))
        self.pdf_path = ctk.StringVar()
        self.file_entry = ctk.CTkEntry(main_frame, textvariable=self.pdf_path, width=850)
        self.file_entry.pack(pady=5, padx=20)
        ctk.CTkButton(main_frame, text="Выбрать PDF", command=self.browse_pdf).pack(pady=5)

        ctk.CTkLabel(main_frame, text="Профиль:").pack(anchor="w", padx=20, pady=(15,0))
        self.profile_var = ctk.StringVar(value="technical")
        self.profile_menu = ctk.CTkOptionMenu(main_frame, values=["novel", "technical", "programming", "hybrid", "facsimile"], variable=self.profile_var, command=self.update_programming_options)
        self.profile_menu.pack(pady=5, padx=20)

        self.programming_lang_var = ctk.StringVar(value="General")
        self.lang_frame = ctk.CTkFrame(main_frame)
        ctk.CTkLabel(self.lang_frame, text="Язык программирования:").pack(side="left", padx=5)
        self.lang_menu = ctk.CTkOptionMenu(self.lang_frame, values=["General", "Python", "Java", "Golang", "C++", "C#", "C", "PowerShell", "Bash"], variable=self.programming_lang_var)
        self.lang_menu.pack(side="left", padx=5)
        self.lang_frame.pack(pady=5, padx=20, anchor="w")
        self.lang_frame.pack_forget()

        ctk.CTkLabel(main_frame, text="Склейка параграфов:").pack(anchor="w", padx=20, pady=(15,0))
        self.aggressive_var = ctk.StringVar(value="Medium")
        ctk.CTkOptionMenu(main_frame, values=["Low", "Medium", "Aggressive"], variable=self.aggressive_var).pack(pady=5, padx=20)

        self.disable_join_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(main_frame, text="Полностью отключить склейку параграфов", variable=self.disable_join_var).pack(anchor="w", padx=20, pady=5)

        self.preserve_images_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(main_frame, text="Сохранять изображения", variable=self.preserve_images_var).pack(anchor="w", padx=20, pady=5)

        self.preserve_figure_references_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(main_frame, text="Сохранять ссылки на рисунки (на рис. 1.4 и т.п.)", variable=self.preserve_figure_references_var).pack(anchor="w", padx=20, pady=5)

        self.convert_btn = ctk.CTkButton(self, text="Конвертировать в EPUB", font=ctk.CTkFont(size=18), height=55, command=self.start_conversion)
        self.convert_btn.pack(pady=25)

        self.log = ctk.CTkTextbox(self, height=320, width=1050, font=ctk.CTkFont(size=13))
        self.log.pack(pady=10, padx=30)

        ctk.CTkButton(self, text="Копировать лог", command=self.copy_log).pack(pady=8)

    def update_programming_options(self, *args):
        if self.profile_var.get() == "programming":
            self.lang_frame.pack(pady=5, padx=20, anchor="w")
        else:
            self.lang_frame.pack_forget()

    def copy_log(self):
        text = self.log.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(text)

    def browse_pdf(self):
        path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if path:
            self.pdf_path.set(path)

    def start_conversion(self):
        if not self.pdf_path.get():
            messagebox.showerror("Ошибка", "Выберите PDF-файл!")
            return

        self.convert_btn.configure(state="disabled")
        self.log.insert("end", "🚀 Запуск конвертации...\n")
        self.log.see("end")

        threading.Thread(target=self.run_conversion, daemon=True).start()

    def run_conversion(self):
        input_path = Path(self.pdf_path.get())
        output_path = input_path.with_suffix(".epub")

        aggressive_level = "Off" if self.disable_join_var.get() else self.aggressive_var.get()

        try:
            self.log.insert("end", f"📄 Файл: {input_path.name}\n")
            self.log.insert("end", f"📌 Профиль: {self.profile_var.get()}\n")
            if self.profile_var.get() == "programming":
                self.log.insert("end", f"📌 Язык: {self.programming_lang_var.get()}\n")
            self.log.insert("end", f"📌 Склейка: {aggressive_level}\n")
            self.log.insert("end", f"🖼️ Изображения: {'вкл' if self.preserve_images_var.get() else 'выкл'}\n")
            self.log.insert("end", f"🔗 Ссылки на рисунки: {'сохраняются' if self.preserve_figure_references_var.get() else 'очищаются'}\n")
            self.log.see("end")

            result_path = convert_pdf_to_epub(
                input_pdf=input_path,
                output_epub=output_path,
                profile_name=self.profile_var.get(),
                aggressive_level=aggressive_level,
                preserve_images=self.preserve_images_var.get(),
                preserve_figure_references=self.preserve_figure_references_var.get(),
                programming_language=self.programming_lang_var.get() if self.profile_var.get() == "programming" else "General",
            )

            self.log.insert("end", "✅ Конвертация завершена успешно!\n")
            self.log.insert("end", f"📚 Результат: {result_path.name}\n\n")

        except Exception as e:
            self.log.insert("end", f"❌ Ошибка:\n{str(e)}\n\n")
        finally:
            self.convert_btn.configure(state="normal")
            self.log.see("end")


if __name__ == "__main__":
    app = Pdf2EpubGUI()
    app.mainloop()