"""
Модуль для продвинутой обработки таблиц в PDF.
Конвертирует таблицы в настоящие HTML <table> вместо <pre>.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from pdf2epubx.models import RawBlock
from pdf2epubx.utils import html_escape


@dataclass
class TableCell:
    """Ячейка таблицы."""
    content: str
    colspan: int = 1
    rowspan: int = 1
    is_header: bool = False


@dataclass
class TableRow:
    """Строка таблицы."""
    cells: list[TableCell]
    is_header: bool = False


@dataclass
class ParsedTable:
    """Распарсенная таблица."""
    rows: list[TableRow]
    has_header: bool = False
    confidence: float = 0.0


class TableParser:
    """Парсер таблиц из текстовых блоков."""

    def __init__(self, mode: Literal["text", "hybrid", "smart"] = "smart"):
        self.mode = mode

    def parse_block(self, block: RawBlock) -> ParsedTable | None:
        """
        Парсит текстовый блок как таблицу.
        Возвращает ParsedTable или None если не таблица.
        """
        lines = self._extract_lines(block)

        if len(lines) < 2:
            return None

        # Пробуем разные стратегии парсинга
        table = self._try_parse_delimited(lines)
        if table and table.confidence > 0.7:
            return table

        table = self._try_parse_fixed_width(lines)
        if table and table.confidence > 0.6:
            return table

        table = self._try_parse_pipe_table(lines)
        if table and table.confidence > 0.8:
            return table

        return None

    def _extract_lines(self, block: RawBlock) -> list[str]:
        """Извлекает строки текста из блока."""
        result = []
        for line in block.lines:
            text = "".join(span.text for span in line.spans)
            if text.strip():
                result.append(text)
        return result

    def _try_parse_delimited(self, lines: list[str]) -> ParsedTable | None:
        """Парсит таблицы с разделителями (табуляции, множественные пробелы)."""
        if not lines:
            return None

        # Определяем разделитель
        delimiter = self._detect_delimiter(lines)
        if not delimiter:
            return None

        rows: list[TableRow] = []
        column_counts = []

        for line in lines:
            cells = self._split_line(line, delimiter)
            if cells:
                rows.append(TableRow(cells=[TableCell(content=c) for c in cells]))
                column_counts.append(len(cells))

        if len(rows) < 2:
            return None

        # Проверяем согласованность количества колонок
        avg_columns = sum(column_counts) / len(column_counts)
        consistent = all(abs(c - avg_columns) <= 1 for c in column_counts)

        if not consistent:
            return None

        confidence = min(1.0, len(rows) / 10.0) * 0.8
        if delimiter == "\t":
            confidence += 0.1

        # Пытаемся определить заголовок
        has_header = self._detect_header(rows)
        if has_header:
            rows[0].is_header = True
            for cell in rows[0].cells:
                cell.is_header = True

        return ParsedTable(rows=rows, has_header=has_header, confidence=confidence)

    def _try_parse_fixed_width(self, lines: list[str]) -> ParsedTable | None:
        """Парсит таблицы с фиксированной шириной колонок."""
        if len(lines) < 2:
            return None

        # Находим позиции колонок
        column_positions = self._find_column_positions(lines)

        if len(column_positions) < 2:
            return None

        rows: list[TableRow] = []

        for line in lines:
            cells = self._extract_fixed_width_cells(line, column_positions)
            if cells and any(c.strip() for c in cells):
                rows.append(TableRow(cells=[TableCell(content=c) for c in cells]))

        if len(rows) < 2:
            return None

        confidence = min(1.0, len(rows) / 8.0) * 0.7

        has_header = self._detect_header(rows)
        if has_header:
            rows[0].is_header = True
            for cell in rows[0].cells:
                cell.is_header = True

        return ParsedTable(rows=rows, has_header=has_header, confidence=confidence)

    def _try_parse_pipe_table(self, lines: list[str]) -> ParsedTable | None:
        """Парсит Markdown-подобные таблицы с |."""
        if not any("|" in line for line in lines):
            return None

        rows: list[TableRow] = []

        for line in lines:
            if "|" not in line:
                continue

            # Удаляем начальные и конечные |
            cells_str = line.strip()
            if cells_str.startswith("|"):
                cells_str = cells_str[1:]
            if cells_str.endswith("|"):
                cells_str = cells_str[:-1]

            cells = [c.strip() for c in cells_str.split("|")]

            # Пропускаем строку-разделитель Markdown (---|---|---)
            if all(re.match(r"^-[\s:-]*$", c) for c in cells):
                continue

            if cells:
                is_separator = any(re.match(r"^-[\s:-]*$", c) for c in cells)
                if not is_separator:
                    rows.append(TableRow(cells=[TableCell(content=c) for c in cells]))

        if len(rows) < 1:
            return None

        has_header = len(rows) > 1
        confidence = 0.9

        if has_header:
            rows[0].is_header = True
            for cell in rows[0].cells:
                cell.is_header = True

        return ParsedTable(rows=rows, has_header=has_header, confidence=confidence)

    def _detect_delimiter(self, lines: list[str]) -> str | None:
        """Определяет разделитель в таблице."""
        # Проверяем табуляции
        tab_count = sum(1 for line in lines if "\t" in line)
        if tab_count >= len(lines) * 0.5:
            return "\t"

        # Проверяем множественные пробелы (2+)
        space_pattern = re.compile(r"\s{2,}")
        space_count = sum(1 for line in lines if space_pattern.search(line))
        if space_count >= len(lines) * 0.5:
            return "multi_space"

        return None

    def _split_line(self, line: str, delimiter: str) -> list[str]:
        """Разделяет строку на ячейки."""
        if delimiter == "multi_space":
            return [cell.strip() for cell in re.split(r"\s{2,}", line.strip())]
        else:
            return [cell.strip() for cell in line.split(delimiter)]

    def _find_column_positions(self, lines: list[str]) -> list[int]:
        """Находит позиции начала колонок в таблицах с фиксированной шириной."""
        positions = set()

        for line in lines:
            # Находим начала непустых последовательностей символов
            stripped = line.lstrip()
            offset = len(line) - len(stripped)

            i = 0
            while i < len(stripped):
                if stripped[i].strip():
                    positions.add(offset + i)
                    # Пропускаем всю ячейку
                    while i < len(stripped) and stripped[i].strip():
                        i += 1
                else:
                    i += 1

        sorted_positions = sorted(positions)

        # Объединяем близкие позиции (в пределах 3 символов)
        if len(sorted_positions) < 2:
            return sorted_positions

        merged = [sorted_positions[0]]
        for pos in sorted_positions[1:]:
            if pos - merged[-1] > 3:
                merged.append(pos)

        return merged

    def _extract_fixed_width_cells(self, line: str, positions: list[int]) -> list[str]:
        """Извлекает ячейки из строки с фиксированной шириной."""
        if not positions:
            return [line]

        cells = []
        for i, start in enumerate(positions):
            end = positions[i + 1] if i + 1 < len(positions) else len(line)
            cell = line[start:end].strip()
            cells.append(cell)

        return cells

    def _detect_header(self, rows: list[TableRow]) -> bool:
        """Пытается определить, есть ли заголовок."""
        if len(rows) < 2:
            return False

        first_row = rows[0]

        # Заголовок обычно короче и содержит меньше специальных символов
        first_cell_count = len(first_row.cells)
        other_avg = sum(len(r.cells) for r in rows[1:]) / len(rows[1:])

        if abs(first_cell_count - other_avg) > 1:
            return False

        # Проверяем, выглядит ли первая строка как заголовок
        first_text = " ".join(cell.content for cell in first_row.cells)

        # Заголовки часто не заканчиваются точкой
        if first_text.endswith(".") and len(first_text) > 20:
            return False

        # Заголовки часто короче
        if len(first_text) > 100:
            return False

        return True


def render_table_html(table: ParsedTable, block: RawBlock) -> str:
    """Рендерит таблицу в HTML."""
    if not table.rows:
        return ""

    parts = ['<table class="pdf-table">']

    for row_idx, row in enumerate(table.rows):
        if row.is_header or (row_idx == 0 and table.has_header):
            parts.append("<thead>")
            parts.append("<tr>")
            for cell in row.cells:
                content = html_escape(cell.content)
                parts.append(f'<th colspan="{cell.colspan}" rowspan="{cell.rowspan}">{content}</th>')
            parts.append("</tr>")
            parts.append("</thead>")
            parts.append("<tbody>")
        elif row_idx == 1 and table.has_header:
            # Первая строка тела таблицы
            parts.append("<tr>")
            for cell in row.cells:
                content = html_escape(cell.content)
                parts.append(f'<td colspan="{cell.colspan}" rowspan="{cell.rowspan}">{content}</td>')
            parts.append("</tr>")
        else:
            parts.append("<tr>")
            for cell in row.cells:
                content = html_escape(cell.content)
                parts.append(f'<td colspan="{cell.colspan}" rowspan="{cell.rowspan}">{content}</td>')
            parts.append("</tr>")

    parts.append("</tbody>")
    parts.append("</table>")

    return "\n".join(parts)


def render_table_fallback(block: RawBlock) -> str:
    """Рендерит таблицу как fallback в <pre>."""
    from pdf2epubx.code_repair import repair_code_text
    from pdf2epubx.utils import html_escape

    lines = []
    for line in block.lines:
        text = "".join(span.text for span in line.spans)
        if text.strip():
            lines.append(text)

    if not lines:
        return ""

    text = "\n".join(lines).rstrip()
    text = repair_code_text(text, repair_git_spacing=False)

    return f'<pre class="table-text"><code>{html_escape(text)}</code></pre>'