"""
Модуль для валидации EPUB файлов.
Использует epubcheck через subprocess или альтернативные методы.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class ValidationResult:
    """Результат валидации EPUB."""
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)
    epubcheck_version: str | None = None

    def to_dict(self) -> dict:
        """Конвертирует в словарь."""
        return {
            "is_valid": self.is_valid,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "info_count": len(self.info),
            "epubcheck_version": self.epubcheck_version,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class EpubValidator:
    """Валидатор EPUB файлов."""

    def __init__(self, epubcheck_path: str | None = None):
        """
        Инициализация валидатора.

        Args:
            epubcheck_path: Путь к исполняемому файлу epubcheck.
                           Если None, пытается найти в PATH.
        """
        self.epubcheck_path = epubcheck_path or self._find_epubcheck()

    @staticmethod
    def _find_epubcheck() -> str | None:
        """Ищет epubcheck в PATH."""
        return shutil.which("epubcheck")

    def validate(self, epub_path: Path) -> ValidationResult:
        """
        Валидирует EPUB файл.

        Args:
            epub_path: Путь к EPUB файлу.

        Returns:
            ValidationResult с результатами валидации.
        """
        if not epub_path.exists():
            return ValidationResult(
                is_valid=False,
                errors=[f"Файл не найден: {epub_path}"],
            )

        # Пробуем epubcheck
        if self.epubcheck_path:
            return self._validate_with_epubcheck(epub_path)

        # Fallback: базовая проверка структуры
        return self._validate_basic(epub_path)

    def _validate_with_epubcheck(self, epub_path: Path) -> ValidationResult:
        """Валидация с помощью epubcheck."""
        result = ValidationResult(epubcheck_version=None)

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                output_json = Path(tmp_dir) / "result.json"

                cmd = [
                    self.epubcheck_path,
                    "-json", str(output_json),
                    str(epub_path),
                ]

                process = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )

                # Парсим вывод
                if process.stdout:
                    for line in process.stdout.splitlines():
                        if "FATAL" in line or "ERROR" in line:
                            result.errors.append(line.strip())
                        elif "WARNING" in line:
                            result.warnings.append(line.strip())
                        elif "INFO" in line:
                            result.info.append(line.strip())

                if process.returncode == 0:
                    result.is_valid = True
                else:
                    result.is_valid = False

                    # Если есть stderr, добавляем ошибки
                    if process.stderr:
                        for line in process.stderr.splitlines():
                            if line.strip() and line.strip() not in result.errors:
                                result.errors.append(line.strip())

                # Пытаемся получить версию
                version_cmd = [self.epubcheck_path, "--version"]
                try:
                    version_process = subprocess.run(
                        version_cmd,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if version_process.stdout:
                        result.epubcheck_version = version_process.stdout.strip()
                except Exception:
                    pass

        except subprocess.TimeoutExpired:
            result.is_valid = False
            result.errors.append("Превышено время ожидания валидации (120 сек)")

        except FileNotFoundError:
            result.is_valid = False
            result.errors.append(f"epubcheck не найден: {self.epubcheck_path}")

        except Exception as e:
            result.is_valid = False
            result.errors.append(f"Ошибка валидации: {str(e)}")

        return result

    def _validate_basic(self, epub_path: Path) -> ValidationResult:
        """
        Базовая валидация без epubcheck.
        Проверяет структуру ZIP и наличие обязательных файлов.
        """
        result = ValidationResult(is_valid=True)

        try:
            import zipfile

            with zipfile.ZipFile(epub_path, 'r') as zf:
                names = zf.namelist()

                # Проверяем mimetype
                if "mimetype" not in names:
                    result.errors.append("Отсутствует файл mimetype")
                    result.is_valid = False
                else:
                    # Проверяем что mimetype первый и не сжат
                    if names[0] != "mimetype":
                        result.warnings.append(
                            "Файл mimetype должен быть первым в архиве"
                        )

                    # Проверяем содержимое mimetype
                    mimetype_content = zf.read("mimetype").decode("utf-8").strip()
                    if mimetype_content != "application/epub+zip":
                        result.errors.append(
                            f"Неверный mimetype: {mimetype_content}"
                        )
                        result.is_valid = False

                # Проверяем META-INF/container.xml
                if "META-INF/container.xml" not in names:
                    result.errors.append("Отсутствует META-INF/container.xml")
                    result.is_valid = False

                # Проверяем наличие OPF файла
                opf_files = [n for n in names if n.endswith(".opf")]
                if not opf_files:
                    result.errors.append("Отсутствует OPF файл (.opf)")
                    result.is_valid = False
                else:
                    result.info.append(f"Найден OPF: {opf_files[0]}")

                # Проверяем наличие NCX или NAV
                ncx_files = [n for n in names if n.endswith(".ncx")]
                nav_files = [n for n in names if "nav" in n.lower() and n.endswith(".xhtml")]

                if not ncx_files and not nav_files:
                    result.warnings.append(
                        "Не найдено оглавление (NCX или NAV)"
                    )

                # Считаем количество XHTML файлов
                xhtml_files = [n for n in names if n.endswith((".xhtml", ".html"))]
                result.info.append(f"Найдено XHTML файлов: {len(xhtml_files)}")

                # Считаем изображения
                image_files = [
                    n for n in names
                    if n.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"))
                ]
                result.info.append(f"Найдено изображений: {len(image_files)}")

        except zipfile.BadZipFile:
            result.is_valid = False
            result.errors.append("Файл поврежден или не является ZIP архивом")

        except Exception as e:
            result.is_valid = False
            result.errors.append(f"Ошибка при проверке: {str(e)}")

        return result


def validate_epub(
    epub_path: Path,
    epubcheck_path: str | None = None,
    strict: bool = False,
) -> ValidationResult:
    """
    Удобная функция для валидации EPUB.

    Args:
        epub_path: Путь к EPUB файлу.
        epubcheck_path: Путь к epubcheck (опционально).
        strict: В строгом режиме предупреждения считаются ошибками.

    Returns:
        ValidationResult.
    """
    validator = EpubValidator(epubcheck_path=epubcheck_path)
    result = validator.validate(epub_path)

    if strict and result.warnings:
        result.is_valid = False
        result.errors.extend(result.warnings)

    return result


def check_epub_validity(epub_path: Path) -> tuple[bool, str]:
    """
    Быстрая проверка валидности EPUB.

    Args:
        epub_path: Путь к EPUB файлу.

    Returns:
        Кортеж (is_valid, message).
    """
    result = validate_epub(epub_path)

    if result.is_valid:
        msg = f"✓ EPUB валиден"
        if result.epubcheck_version:
            msg += f" (epubcheck {result.epubcheck_version})"
        if result.warnings:
            msg += f", предупреждений: {len(result.warnings)}"
        return True, msg
    else:
        msg = f"✗ EPUB невалиден"
        if result.errors:
            msg += f": {result.errors[0]}"
        return False, msg