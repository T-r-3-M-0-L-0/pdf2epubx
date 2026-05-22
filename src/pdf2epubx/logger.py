"""
Модуль для логирования и отображения прогресса конвертации.
"""
from __future__ import annotations

import logging
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class LogLevel(Enum):
    """Уровни логирования."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class ProgressStats:
    """Статистика прогресса."""
    total_pages: int = 0
    processed_pages: int = 0
    current_chapter: int = 0
    total_chapters: int = 0
    start_time: float = field(default_factory=time.time)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def page_progress(self) -> float:
        """Прогресс обработки страниц (0.0-1.0)."""
        if self.total_pages == 0:
            return 0.0
        return self.processed_pages / self.total_pages

    @property
    def elapsed_time(self) -> float:
        """Прошедшее время в секундах."""
        return time.time() - self.start_time

    @property
    def eta_seconds(self) -> float:
        """Ожидаемое время до завершения (секунды)."""
        if self.page_progress == 0:
            return 0.0
        remaining = (1.0 - self.page_progress) * self.elapsed_time / max(self.page_progress, 0.001)
        return max(0.0, remaining)

    @property
    def pages_per_second(self) -> float:
        """Страниц обрабатывается в секунду."""
        if self.elapsed_time == 0:
            return 0.0
        return self.processed_pages / self.elapsed_time

    def to_dict(self) -> dict[str, Any]:
        """Конвертирует в словарь."""
        return {
            "total_pages": self.total_pages,
            "processed_pages": self.processed_pages,
            "page_progress_percent": round(self.page_progress * 100, 1),
            "current_chapter": self.current_chapter,
            "total_chapters": self.total_chapters,
            "elapsed_seconds": round(self.elapsed_time, 2),
            "eta_seconds": round(self.eta_seconds, 2),
            "pages_per_second": round(self.pages_per_second, 2),
            "errors_count": len(self.errors),
            "warnings_count": len(self.warnings),
        }


class ConversionLogger:
    """Логгер для процесса конвертации."""

    def __init__(
        self,
        log_level: LogLevel = LogLevel.INFO,
        log_file: Path | None = None,
        verbose: bool = False,
    ):
        """
        Инициализация логгера.

        Args:
            log_level: Уровень логирования.
            log_file: Путь к файлу лога (опционально).
            verbose: Режим подробного вывода.
        """
        self.log_level = log_level
        self.verbose = verbose
        self.stats = ProgressStats()

        # Настройка logging
        self.logger = logging.getLogger("pdf2epubx")
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers.clear()

        # Консольный обработчик
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(self._get_logging_level(log_level))
        console_formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%H:%M:%S",
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)

        # Файловый обработчик (если указан)
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_formatter = logging.Formatter(
                "%(asctime)s | %(name)s | %(levelname)-8s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)

    def _get_logging_level(self, level: LogLevel) -> int:
        """Конвертирует LogLevel в logging уровень."""
        mapping = {
            LogLevel.DEBUG: logging.DEBUG,
            LogLevel.INFO: logging.INFO,
            LogLevel.WARNING: logging.WARNING,
            LogLevel.ERROR: logging.ERROR,
        }
        return mapping.get(level, logging.INFO)

    def set_total_pages(self, total: int) -> None:
        """Устанавливает общее количество страниц."""
        self.stats.total_pages = total
        self.logger.info(f"Всего страниц: {total}")

    def set_total_chapters(self, total: int) -> None:
        """Устанавливает общее количество глав."""
        self.stats.total_chapters = total
        self.logger.info(f"Всего глав: {total}")

    def page_processed(self, page_number: int, chapter: int = 0) -> None:
        """Отмечает страницу как обработанную."""
        self.stats.processed_pages = page_number
        self.stats.current_chapter = chapter

        if self.verbose or page_number % 10 == 0 or page_number == self.stats.total_pages:
            self._log_progress()

    def chapter_completed(self, chapter_number: int, title: str) -> None:
        """Отмечает главу как завершенную."""
        self.stats.current_chapter = chapter_number
        self.logger.info(f"✓ Глава {chapter_number}: {title}")

    def error(self, message: str) -> None:
        """Логирует ошибку."""
        self.stats.errors.append(message)
        self.logger.error(message)

    def warning(self, message: str) -> None:
        """Логирует предупреждение."""
        self.stats.warnings.append(message)
        self.logger.warning(message)

    def info(self, message: str) -> None:
        """Логирует информацию."""
        self.logger.info(message)

    def debug(self, message: str) -> None:
        """Логирует отладочную информацию."""
        self.logger.debug(message)

    def _log_progress(self) -> None:
        """Выводит текущий прогресс."""
        stats = self.stats.to_dict()
        progress_bar = self._render_progress_bar(stats["page_progress_percent"])

        eta_min = stats["eta_seconds"] / 60
        msg = (
            f"{progress_bar} | "
            f"Страница {stats['processed_pages']}/{stats['total_pages']} | "
            f"Глава {stats['current_chapter']}/{stats['total_chapters']} | "
            f"{stats['pages_per_second']:.1f} стр/сек | "
            f"ETA: {eta_min:.1f} мин"
        )

        self.logger.info(msg)

    @staticmethod
    def _render_progress_bar(percent: float, width: int = 30) -> str:
        """Рендерит текстовый прогресс-бар."""
        filled = int(width * percent / 100)
        bar = "█" * filled + "░" * (width - filled)
        return f"[{bar}] {percent:5.1f}%"

    def finalize(self) -> ProgressStats:
        """Завершает логирование и возвращает статистику."""
        stats = self.stats.to_dict()

        self.logger.info("=" * 60)
        self.logger.info("Конвертация завершена!")
        self.logger.info(f"Всего страниц: {stats['total_pages']}")
        self.logger.info(f"Всего глав: {stats['total_chapters']}")
        self.logger.info(f"Время выполнения: {stats['elapsed_seconds']:.2f} сек")
        self.logger.info(f"Средняя скорость: {stats['pages_per_second']:.2f} стр/сек")

        if stats["warnings_count"] > 0:
            self.logger.warning(f"Предупреждений: {stats['warnings_count']}")

        if stats["errors_count"] > 0:
            self.logger.error(f"Ошибок: {stats['errors_count']}")
            for err in self.stats.errors[:5]:  # Показываем первые 5 ошибок
                self.logger.error(f"  - {err}")

        return self.stats


def create_logger(
    verbose: bool = False,
    quiet: bool = False,
    log_file: Path | None = None,
) -> ConversionLogger:
    """
    Создает логгер с заданными параметрами.

    Args:
        verbose: Подробный режим.
        quiet: Тихий режим (только ошибки).
        log_file: Путь к файлу лога.

    Returns:
        ConversionLogger instance.
    """
    if quiet:
        level = LogLevel.ERROR
    elif verbose:
        level = LogLevel.DEBUG
    else:
        level = LogLevel.INFO

    return ConversionLogger(
        log_level=level,
        log_file=log_file,
        verbose=verbose,
    )