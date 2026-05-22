"""
Модуль для кэширования результатов конвертации.
Поддерживает кэширование OCR, извлечения страниц и рендеринга.
"""
import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Callable

try:
    from typing import Union
except ImportError:
    from typing import Union as Any  # fallback


@dataclass
class CacheEntry:
    """Запись в кэше."""
    key: str
    data: bytes
    timestamp: float
    metadata: Optional[Dict[str, Any]] = None


class ConversionCache:
    """Кэш для ускорения повторной конвертации."""

    def __init__(self, cache_dir: Optional[Path] = None, enabled: bool = True):
        """
        Инициализация кэша.

        Args:
            cache_dir: Директория для кэша. Если None, используется временная.
            enabled: Включен ли кэш.
        """
        self.enabled = enabled
        self.cache_dir = cache_dir or Path.home() / ".cache" / "pdf2epubx"
        self.db_path: Optional[Path] = None

        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = self.cache_dir / "cache.db"
            self._init_db()

    def _init_db(self) -> None:
        """Инициализирует SQLite базу для кэша."""
        if not self.db_path:
            return

        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache_entries (
                    key TEXT PRIMARY KEY,
                    data BLOB NOT NULL,
                    timestamp REAL NOT NULL,
                    metadata TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp
                ON cache_entries(timestamp)
            """)
            conn.commit()

    @contextmanager
    def _get_connection(self):
        """Получает соединение с базой данных."""
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        try:
            yield conn
        finally:
            conn.close()

    def _compute_key(self, *args: Any, **kwargs: Any) -> str:
        """Вычисляет хэш-ключ для параметров."""
        serialized = json.dumps(
            {"args": args, "kwargs": kwargs},
            default=str,
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(serialized).hexdigest()

    def get(self, key: str) -> Optional[bytes]:
        """
        Получает данные из кэша по ключу.

        Args:
            key: Кэш-ключ.

        Returns:
            Данные или None если не найдено.
        """
        if not self.enabled or not self.db_path:
            return None

        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT data FROM cache_entries WHERE key = ?",
                (key,)
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def set(self, key: str, data: bytes, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Сохраняет данные в кэш.

        Args:
            key: Кэш-ключ.
            data: Данные для сохранения.
            metadata: Дополнительные метаданные.
        """
        if not self.enabled or not self.db_path:
            return

        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO cache_entries (key, data, timestamp, metadata)
                VALUES (?, ?, ?, ?)
            """, (
                key,
                data,
                time.time(),
                json.dumps(metadata) if metadata else None,
            ))
            conn.commit()

    def get_or_compute(
        self,
        key: str,
        compute_fn: Callable[[], bytes],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bytes:
        """
        Получает из кэша или вычисляет и сохраняет.

        Args:
            key: Кэш-ключ.
            compute_fn: Функция для вычисления если нет в кэше.
            metadata: Метаданные для сохранения.

        Returns:
            Данные.
        """
        cached = self.get(key)
        if cached is not None:
            return cached

        data = compute_fn()
        self.set(key, data, metadata)
        return data

    def invalidate(self, key: str) -> None:
        """Удаляет запись из кэша."""
        if not self.enabled or not self.db_path:
            return

        with self._get_connection() as conn:
            conn.execute("DELETE FROM cache_entries WHERE key = ?", (key,))
            conn.commit()

    def clear_old(self, max_age_days: int = 30) -> int:
        """
        Очищает старые записи из кэша.

        Args:
            max_age_days: Максимальный возраст записей в днях.

        Returns:
            Количество удаленных записей.
        """
        if not self.enabled or not self.db_path:
            return 0

        import time

        cutoff = time.time() - (max_age_days * 24 * 60 * 60)

        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM cache_entries WHERE timestamp < ?",
                (cutoff,)
            )
            count = cursor.fetchone()[0]

            conn.execute(
                "DELETE FROM cache_entries WHERE timestamp < ?",
                (cutoff,)
            )
            conn.commit()

        return count

    def get_stats(self) -> Dict[str, Any]:
        """Возвращает статистику кэша."""
        if not self.enabled or not self.db_path:
            return {"enabled": False}

        with self._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*), SUM(length(data)) FROM cache_entries")
            count, total_size = cursor.fetchone()

            return {
                "enabled": True,
                "entries": count or 0,
                "total_size_bytes": total_size or 0,
                "cache_dir": str(self.cache_dir),
            }


def compute_pdf_cache_key(pdf_path: Path, params: Dict[str, Any]) -> str:
    """
    Вычисляет ключ кэша для PDF файла.

    Args:
        pdf_path: Путь к PDF файлу.
        params: Параметры конвертации.

    Returns:
        Кэш-ключ.
    """
    stat = pdf_path.stat()
    key_data = {
        "path": str(pdf_path.resolve()),
        "size": stat.st_size,
        "mtime": stat.st_mtime,
        "params": params,
    }
    return hashlib.sha256(
        json.dumps(key_data, default=str, sort_keys=True).encode("utf-8")
    ).hexdigest()


def compute_page_cache_key(pdf_path: Path, page_index: int, params: Dict[str, Any]) -> str:
    """
    Вычисляет ключ кэша для страницы PDF.

    Args:
        pdf_path: Путь к PDF файлу.
        page_index: Индекс страницы.
        params: Параметры обработки.

    Returns:
        Кэш-ключ.
    """
    base_key = compute_pdf_cache_key(pdf_path, params)
    page_key = f"{base_key}:page:{page_index}"
    return hashlib.sha256(page_key.encode("utf-8")).hexdigest()


@contextmanager
def cache_context(cache: Optional[ConversionCache]):
    """Контекстный менеджер для работы с кэшем."""
    if cache is None:
        cache = ConversionCache(enabled=False)
    yield cache