"""
Модуль для поддержки математических формул.
Распознавание и конвертация формул в MathML.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


@dataclass
class Formula:
    """Представление математической формулы."""
    latex: str
    position: tuple[int, int]  # (строка, колонка)
    confidence: float = 1.0
    formula_type: Literal["inline", "display", "unknown"] = "unknown"


class FormulaDetector:
    """Детектор математических формул в тексте."""

    # Паттерны для распознавания LaTeX формул
    LATEX_PATTERNS = [
        r'\$\$([^$]+)\$\$',  # Display math $$...$$
        r'\$([^$]+)\$',     # Inline math $...$
        r'\\\[([\s\S]*?)\\\]',  # Display math \[...\]
        r'\\\( ([\s\S]*?)\\\)',  # Inline math \(...\)
        r'\\begin\{equation\}([\s\S]*?)\\end\{equation\}',
        r'\\begin\{align\}([\s\S]*?)\\end\{align\}',
        r'\\begin\{gather\}([\s\S]*?)\\end\{gather\}',
    ]

    # Паттерны для распознавания Unicode математики
    UNICODE_MATH_RANGES = [
        (0x2200, 0x22FF),  # Mathematical Operators
        (0x2150, 0x217F),  # Number Forms
        (0x2070, 0x209F),  # Superscripts and Subscripts
        (0x1D400, 0x1D7FF),  # Mathematical Alphanumeric Symbols
    ]

    def __init__(self, enabled: bool = True):
        """
        Инициализация детектора.

        Args:
            enabled: Включено ли распознавание формул.
        """
        self.enabled = enabled
        self.compiled_patterns = [
            re.compile(pattern) for pattern in self.LATEX_PATTERNS
        ]

    def detect_formulas(self, text: str) -> list[Formula]:
        """
        Detects mathematical formulas in text.

        Args:
            text: Input text to search for formulas.

        Returns:
            List of detected Formula objects.
        """
        if not self.enabled:
            return []

        formulas = []

        # Поиск LaTeX формул
        for pattern in self.compiled_patterns:
            for match in pattern.finditer(text):
                formula_type = self._determine_formula_type(match.group(0))
                formulas.append(
                    Formula(
                        latex=match.group(1).strip(),
                        position=(match.start(), match.end()),
                        confidence=0.95,
                        formula_type=formula_type,
                    )
                )

        # Поиск Unicode математики
        unicode_formulas = self._detect_unicode_math(text)
        formulas.extend(unicode_formulas)

        return formulas

    def _determine_formula_type(self, match_text: str) -> Literal["inline", "display"]:
        """Определяет тип формулы по синтаксису."""
        if match_text.startswith('$$') or match_text.startswith('\\['):
            return "display"
        return "inline"

    def _detect_unicode_math(self, text: str) -> list[Formula]:
        """Detects formulas with Unicode math symbols."""
        formulas = []
        current_formula = []
        start_pos = None

        for i, char in enumerate(text):
            code_point = ord(char)
            is_math = any(
                start <= code_point <= end
                for start, end in self.UNICODE_MATH_RANGES
            )

            # Также считаем математикой греческие буквы
            if 0x0370 <= code_point <= 0x03FF:
                is_math = True

            if is_math:
                if start_pos is None:
                    start_pos = i
                current_formula.append(char)
            else:
                if current_formula and len(current_formula) >= 3:
                    formulas.append(
                        Formula(
                            latex=self._unicode_to_latex("".join(current_formula)),
                            position=(start_pos, i),
                            confidence=0.7,
                            formula_type="inline",
                        )
                    )
                current_formula = []
                start_pos = None

        # Обработка конца строки
        if current_formula and len(current_formula) >= 3:
            formulas.append(
                Formula(
                    latex=self._unicode_to_latex("".join(current_formula)),
                    position=(start_pos, len(text)),
                    confidence=0.7,
                    formula_type="inline",
                )
            )

        return formulas

    def _unicode_to_latex(self, text: str) -> str:
        """Конвертирует Unicode математику в LaTeX."""
        replacements = {
            '∑': '\\sum',
            '∏': '\\prod',
            '∫': '\\int',
            '∂': '\\partial',
            '√': '\\sqrt',
            '∞': '\\infty',
            '≠': '\\neq',
            '≤': '\\leq',
            '≥': '\\geq',
            '≈': '\\approx',
            '∈': '\\in',
            '∉': '\\notin',
            '⊂': '\\subset',
            '⊃': '\\supset',
            '∪': '\\cup',
            '∩': '\\cap',
            '∧': '\\wedge',
            '∨': '\\vee',
            '¬': '\\neg',
            '→': '\\rightarrow',
            '←': '\\leftarrow',
            '↔': '\\leftrightarrow',
            '⇒': '\\Rightarrow',
            '⇐': '\\Leftarrow',
            '⇔': '\\Leftrightarrow',
            'α': '\\alpha',
            'β': '\\beta',
            'γ': '\\gamma',
            'δ': '\\delta',
            'ε': '\\epsilon',
            'ζ': '\\zeta',
            'η': '\\eta',
            'θ': '\\theta',
            'ι': '\\iota',
            'κ': '\\kappa',
            'λ': '\\lambda',
            'μ': '\\mu',
            'ν': '\\nu',
            'ξ': '\\xi',
            'π': '\\pi',
            'ρ': '\\rho',
            'σ': '\\sigma',
            'τ': '\\tau',
            'υ': '\\upsilon',
            'φ': '\\phi',
            'χ': '\\chi',
            'ψ': '\\psi',
            'ω': '\\omega',
            '×': '\\times',
            '÷': '\\div',
            '±': '\\pm',
            '°': '^\\circ',
            '²': '^2',
            '³': '^3',
        }

        result = text
        for unicode_char, latex in replacements.items():
            result = result.replace(unicode_char, latex)

        return result


def latex_to_mathml(latex: str) -> str:
    """
    Конвертирует LaTeX в MathML.

    Это упрощенная реализация. Для продакшена рекомендуется
    использовать библиотеки типа latex2mathml или серверные решения.

    Args:
        latex: LaTeX выражение.

    Returns:
        MathML строка.
    """
    # Базовые замены для простых формул
    mathml = latex

    # Фракции
    mathml = re.sub(
        r'\\frac\{([^}]+)\}\{([^}]+)\}',
        r'<mfrac><mi>\1</mi><mi>\2</mi></mfrac>',
        mathml
    )

    # Степени
    mathml = re.sub(
        r'\^(\w+)',
        r'<msup><mi></mi><mi>\1</mi></msup>',
        mathml
    )

    # Индексы
    mathml = re.sub(
        r'_\{?(\w+)\}?',
        r'<msub><mi></mi><mi>\1</mi></msub>',
        mathml
    )

    # Греческие буквы
    greek_letters = {
        'alpha': 'α', 'beta': 'β', 'gamma': 'γ', 'delta': 'δ',
        'epsilon': 'ε', 'zeta': 'ζ', 'eta': 'η', 'theta': 'θ',
        'iota': 'ι', 'kappa': 'κ', 'lambda': 'λ', 'mu': 'μ',
        'nu': 'ν', 'xi': 'ξ', 'pi': 'π', 'rho': 'ρ',
        'sigma': 'σ', 'tau': 'τ', 'upsilon': 'υ', 'phi': 'φ',
        'chi': 'χ', 'psi': 'ψ', 'omega': 'ω',
    }

    for latex_name, unicode_char in greek_letters.items():
        mathml = re.sub(
            rf'\\{latex_name}\b',
            f'<mi>{unicode_char}</mi>',
            mathml
        )

    # Операторы
    operators = {
        '\\sum': '∑', '\\prod': '∏', '\\int': '∫',
        '\\sqrt': '√', '\\infty': '∞',
    }

    for latex_op, unicode_char in operators.items():
        mathml = mathml.replace(latex_op, f'<mo>{unicode_char}</mo>')

    # Оборачиваем в MathML
    return f'<math xmlns="http://www.w3.org/1998/Math/MathML">{mathml}</math>'


def render_formula_html(formula: Formula) -> str:
    """
    Рендерит формулу в HTML.

    Args:
        formula: Объект Formula.

    Returns:
        HTML строка с формулой.
    """
    mathml = latex_to_mathml(formula.latex)

    if formula.formula_type == "display":
        return f'<div class="math-display">{mathml}</div>'
    else:
        return f'<span class="math-inline">{mathml}</span>'


def extract_and_replace_formulas(text: str, detector: FormulaDetector) -> tuple[str, list[Formula]]:
    """
    Извлекает формулы из текста и заменяет их на плейсхолдеры.

    Args:
        text: Исходный текст.
        detector: Детектор формул.

    Returns:
        Кортеж (текст с плейсхолдерами, список формул).
    """
    formulas = detector.detect_formulas(text)

    if not formulas:
        return text, []

    # Сортируем по позиции (от конца к началу для замены)
    formulas.sort(key=lambda f: f.position[0], reverse=True)

    result_text = text
    for i, formula in enumerate(formulas):
        start, end = formula.position
        placeholder = f"<!-- FORMULA_{i} -->"
        result_text = result_text[:start] + placeholder + result_text[end:]

    return result_text, formulas