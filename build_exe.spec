# build_exe.spec
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Собираем все подмодули pdf2epubx
pdf2epubx_hidden = collect_submodules('pdf2epubx')

a = Analysis(
    ['src/pdf2epubx/gui.py'],
    pathex=['.', 'src'],
    binaries=[],
    datas=[
        *collect_data_files('customtkinter'),
        *collect_data_files('tkinterdnd2'),
        # Добавляем файлы правил и шаблонов
        ('rules.*.json', '.'),
        ('src/pdf2epubx/*.json', 'pdf2epubx'),
    ],
    hiddenimports=[
        # Стандартные библиотеки
        'sqlite3',
        'sqlite3.dbapi2',
        'sqlite3.dump',
        '_sqlite3',
        'hashlib',
        'zlib',
        'gzip',
        'xml.etree.ElementTree',
        'xml.sax',
        'email.mime',
        'email.mime.text',
        'email.mime.multipart',
        'email.mime.image',
        'email.mime.application',

        # GUI библиотеки
        'tkinterdnd2',
        'customtkinter',
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        'PIL.ImageOps',
        'PIL.ImageDraw',
        'PIL.ImageFont',

        # PDF и EPUB библиотеки
        'fitz',  # PyMuPDF
        'ebooklib',
        'ebooklib.epub',

        # Все модули pdf2epubx
        *pdf2epubx_hidden,

        # Явно указываем новые модули
        'pdf2epubx.table_parser',
        'pdf2epubx.image_optimizer',
        'pdf2epubx.formula_detector',
        'pdf2epubx.cache',
        'pdf2epubx.epub_validator',
        'pdf2epubx.logger',
        'pdf2epubx.converter',
        'pdf2epubx.epub_writer',
        'pdf2epubx.renderer',
        'pdf2epubx.classifier',
        'pdf2epubx.cleanup',
        'pdf2epubx.code_repair',
        'pdf2epubx.chaptering',
        'pdf2epubx.extractor',
        'pdf2epubx.preflight',
        'pdf2epubx.profiles',
        'pdf2epubx.toc_parser',
        'pdf2epubx.ocr',
        'pdf2epubx.pdf_inspector',
        'pdf2epubx.edit_rules',
        'pdf2epubx.models',
        'pdf2epubx.utils',

        # Зависимости для OCR (если используется)
        'pytesseract',

        # Утилиты
        'typing_extensions',
        'json',
        're',
        'datetime',
        'pathlib',
        'tempfile',
        'shutil',
        'io',
        'base64',
        'html',
        'html.parser',
        'urllib',
        'urllib.parse',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'numpy',
        'scipy',
        'pandas',
        'jupyter',
        'notebook',
        'IPython',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='pdf2epubx',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # False = без окна консоли
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='icon.ico',      # закомментировали — иконка необязательна
)