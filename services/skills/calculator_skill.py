import ast
import math
import operator
import re
from typing import Any

from services.skills.base_skill import BaseSkill, SkillResult


class CalculatorSkill(BaseSkill):
    """
    Local arithmetic and unit-conversion skill.

    Examples:
        What is 25 plus 17?
        Calculate 18 percent of 240.
        Convert 10 miles to kilometers.
        Convert 100 Fahrenheit to Celsius.
        Open calculator.

        Сколько будет 25 плюс 17?
        Вычисли 18 процентов от 240.
        Переведи 10 миль в километры.
        Открой калькулятор.
    """

    name = "calculator"
    priority = 1

    CALCULATOR_OPEN_PHRASES = {
        "open calculator",
        "show calculator",
        "calculator app",
        "go to calculator",
        "calculator",
        "kalkulator",
        "calc",
        "open kalkulator",
        "show kalkulator",
        "открой калькулятор",
        "покажи калькулятор",
        "перейди в калькулятор",
        "калькулятор",
    }

    CONVERTER_OPEN_PHRASES = {
        "open calculator converter",
        "open calculator-converter",
        "show calculator converter",
        "show converter",
        "open converter",
        "calculator converter",
        "calculator-converter",
        "открой калькулятор конвертер",
        "открой калькулятор-конвертер",
        "покажи калькулятор конвертер",
        "открой конвертер",
        "покажи конвертер",
    }

    OPEN_PHRASES = (
        CALCULATOR_OPEN_PHRASES
        | CONVERTER_OPEN_PHRASES
    )

    CALCULATOR_HINTS = {
        "calculate",
        "calculator",
        "compute",
        "convert",
        "conversion",
        "percent",
        "percentage",
        "plus",
        "minus",
        "times",
        "multiplied",
        "divided",
        "square root",
        "сколько",
        "вычисли",
        "посчитай",
        "калькулятор",
        "переведи",
        "конвертируй",
        "процент",
        "процентов",
        "плюс",
        "минус",
        "умножить",
        "разделить",
        "корень",
    }

    UNIT_ALIASES = {
        "mm": "millimeter",
        "millimeter": "millimeter",
        "millimeters": "millimeter",
        "мм": "millimeter",

        "cm": "centimeter",
        "centimeter": "centimeter",
        "centimeters": "centimeter",
        "см": "centimeter",

        "m": "meter",
        "meter": "meter",
        "meters": "meter",
        "metre": "meter",
        "metres": "meter",
        "метр": "meter",
        "метра": "meter",
        "метров": "meter",

        "km": "kilometer",
        "kilometer": "kilometer",
        "kilometers": "kilometer",
        "kilometre": "kilometer",
        "kilometres": "kilometer",
        "км": "kilometer",
        "километр": "kilometer",
        "километра": "kilometer",
        "километров": "kilometer",

        "in": "inch",
        "inch": "inch",
        "inches": "inch",
        "дюйм": "inch",
        "дюйма": "inch",
        "дюймов": "inch",

        "ft": "foot",
        "foot": "foot",
        "feet": "foot",
        "фут": "foot",
        "фута": "foot",
        "футов": "foot",

        "yd": "yard",
        "yard": "yard",
        "yards": "yard",
        "ярд": "yard",
        "ярда": "yard",
        "ярдов": "yard",

        "mi": "mile",
        "mile": "mile",
        "miles": "mile",
        "миля": "mile",
        "мили": "mile",
        "миль": "mile",

        "g": "gram",
        "gram": "gram",
        "grams": "gram",
        "г": "gram",
        "грамм": "gram",
        "грамма": "gram",
        "граммов": "gram",

        "kg": "kilogram",
        "kilogram": "kilogram",
        "kilograms": "kilogram",
        "кг": "kilogram",
        "килограмм": "kilogram",
        "килограмма": "kilogram",
        "килограммов": "kilogram",

        "oz": "ounce",
        "ounce": "ounce",
        "ounces": "ounce",
        "унция": "ounce",
        "унции": "ounce",
        "унций": "ounce",

        "lb": "pound",
        "lbs": "pound",
        "pound": "pound",
        "pounds": "pound",
        "фунт": "pound",
        "фунта": "pound",
        "фунтов": "pound",

        "ml": "milliliter",
        "milliliter": "milliliter",
        "milliliters": "milliliter",
        "мл": "milliliter",

        "l": "liter",
        "liter": "liter",
        "liters": "liter",
        "litre": "liter",
        "litres": "liter",
        "литр": "liter",
        "литра": "liter",
        "литров": "liter",

        "floz": "fluid_ounce",
        "fluid ounce": "fluid_ounce",
        "fluid ounces": "fluid_ounce",

        "cup": "cup",
        "cups": "cup",
        "чашка": "cup",
        "чашки": "cup",
        "чашек": "cup",

        "pint": "pint",
        "pints": "pint",

        "quart": "quart",
        "quarts": "quart",

        "gallon": "gallon",
        "gallons": "gallon",
        "галлон": "gallon",
        "галлона": "gallon",
        "галлонов": "gallon",

        "sq ft": "square_foot",
        "square foot": "square_foot",
        "square feet": "square_foot",
        "ft2": "square_foot",
        "ft²": "square_foot",
        "кв фут": "square_foot",

        "sq m": "square_meter",
        "square meter": "square_meter",
        "square meters": "square_meter",
        "m2": "square_meter",
        "m²": "square_meter",
        "кв м": "square_meter",

        "acre": "acre",
        "acres": "acre",
        "акр": "acre",
        "акра": "acre",
        "акров": "acre",

        "hectare": "hectare",
        "hectares": "hectare",
        "гектар": "hectare",
        "гектара": "hectare",
        "гектаров": "hectare",

        "c": "celsius",
        "°c": "celsius",
        "celsius": "celsius",
        "цельсий": "celsius",

        "f": "fahrenheit",
        "°f": "fahrenheit",
        "fahrenheit": "fahrenheit",
        "фаренгейт": "fahrenheit",
    }

    UNIT_FACTORS = {
        "millimeter": ("length", 0.001),
        "centimeter": ("length", 0.01),
        "meter": ("length", 1.0),
        "kilometer": ("length", 1000.0),
        "inch": ("length", 0.0254),
        "foot": ("length", 0.3048),
        "yard": ("length", 0.9144),
        "mile": ("length", 1609.344),

        "gram": ("mass", 0.001),
        "kilogram": ("mass", 1.0),
        "ounce": ("mass", 0.028349523125),
        "pound": ("mass", 0.45359237),

        "milliliter": ("volume", 0.001),
        "liter": ("volume", 1.0),
        "fluid_ounce": ("volume", 0.0295735295625),
        "cup": ("volume", 0.2365882365),
        "pint": ("volume", 0.473176473),
        "quart": ("volume", 0.946352946),
        "gallon": ("volume", 3.785411784),

        "square_foot": ("area", 0.09290304),
        "square_meter": ("area", 1.0),
        "acre": ("area", 4046.8564224),
        "hectare": ("area", 10000.0),
    }

    BINARY_OPERATORS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
    }

    UNARY_OPERATORS = {
        ast.UAdd: operator.pos,
        ast.USub: operator.neg,
    }

    def can_handle(
        self,
        message: str,
        context: Any,
    ) -> float:
        text = self._normalize(message)

        if not text:
            return 0.0

        if text in self.OPEN_PHRASES:
            return 1.0

        if any(
            re.search(
                rf"(?<!\w){re.escape(hint)}(?!\w)",
                text,
                re.IGNORECASE,
            )
            for hint in self.CALCULATOR_HINTS
        ):
            return 0.99

        if self._looks_like_expression(text):
            return 0.97

        if self._looks_like_conversion(text):
            return 0.99

        return 0.0

    def handle(
        self,
        message: str,
        context: Any,
    ) -> SkillResult:
        text = self._normalize(message)
        russian = self._is_russian(text)

        if text in self.CONVERTER_OPEN_PHRASES:
            opened = self._open_converter(context)

            return SkillResult(
                handled=True,
                answer=(
                    "Конвертер открыт."
                    if russian and opened
                    else "Не удалось открыть конвертер."
                    if russian
                    else "Converter opened."
                    if opened
                    else "I couldn't open the converter."
                ),
                confidence=1.0,
                action="open_converter",
                data={"opened": opened},
            )

        if text in self.CALCULATOR_OPEN_PHRASES:
            opened = self._open_calculator_tab(
                context
            )

            return SkillResult(
                handled=True,
                answer=(
                    "Калькулятор открыт."
                    if russian and opened
                    else "Не удалось открыть калькулятор."
                    if russian
                    else "Calculator opened."
                    if opened
                    else "I couldn't open the calculator."
                ),
                confidence=1.0,
                action="open_calculator",
                data={"opened": opened},
            )

        conversion = self._parse_conversion(text)

        if conversion is not None:
            value, from_unit, to_unit = conversion

            try:
                result = self._convert(
                    value=value,
                    from_unit=from_unit,
                    to_unit=to_unit,
                )
            except ValueError as error:
                return SkillResult(
                    handled=True,
                    answer=str(error),
                    confidence=0.99,
                    action="conversion_error",
                )

            answer = self._format_conversion_answer(
                value=value,
                from_unit=from_unit,
                result=result,
                to_unit=to_unit,
                russian=russian,
            )

            return SkillResult(
                handled=True,
                answer=answer,
                confidence=0.99,
                action="unit_conversion",
                data={
                    "value": value,
                    "from_unit": from_unit,
                    "to_unit": to_unit,
                    "result": result,
                },
            )

        percent = self._parse_percentage(text)

        if percent is not None:
            percent_value, base_value = percent
            result = (
                percent_value / 100.0
            ) * base_value

            answer = (
                f"{self._format_number(percent_value)} процентов "
                f"от {self._format_number(base_value)} равно "
                f"{self._format_number(result)}."
                if russian
                else
                f"{self._format_number(percent_value)} percent "
                f"of {self._format_number(base_value)} is "
                f"{self._format_number(result)}."
            )

            return SkillResult(
                handled=True,
                answer=answer,
                confidence=0.99,
                action="percentage",
                data={
                    "percent": percent_value,
                    "base": base_value,
                    "result": result,
                },
            )

        expression = self._extract_expression(text)

        if expression is None:
            return SkillResult(
                handled=True,
                answer=(
                    "Я не смог распознать вычисление."
                    if russian
                    else "I couldn't recognize the calculation."
                ),
                confidence=0.97,
                action="calculation_error",
            )

        try:
            result = self._safe_evaluate(
                expression
            )
        except (
            ValueError,
            ZeroDivisionError,
            OverflowError,
        ) as error:
            return SkillResult(
                handled=True,
                answer=(
                    f"Ошибка вычисления: {error}."
                    if russian
                    else f"Calculation error: {error}."
                ),
                confidence=0.97,
                action="calculation_error",
            )

        answer = (
            f"Ответ: {self._format_number(result)}."
            if russian
            else f"The answer is {self._format_number(result)}."
        )

        return SkillResult(
            handled=True,
            answer=answer,
            confidence=0.97,
            action="calculation",
            data={
                "expression": expression,
                "result": result,
            },
        )

    @staticmethod
    def _normalize(message: str) -> str:
        text = str(message).strip().lower()
        text = text.replace("×", "*")
        text = text.replace("÷", "/")
        text = text.replace("−", "-")
        text = text.replace("’", "'")

        # Voice transcripts commonly end with punctuation.
        # Remove only sentence punctuation while preserving
        # arithmetic symbols, decimal points, and unit notation.
        text = re.sub(
            r"[!?;,]+",
            " ",
            text,
        )
        text = re.sub(
            r"\.(?=\s*$)",
            "",
            text,
        )

        return " ".join(text.split())

    @staticmethod
    def _is_russian(text: str) -> bool:
        return bool(
            re.search(
                r"[а-яё]",
                text,
                re.IGNORECASE,
            )
        )

    @staticmethod
    def _open_calculator(context: Any) -> bool:
        method = getattr(
            context,
            "open_screen",
            None,
        )

        if not callable(method):
            return False

        for screen_name in (
            "calculator",
            "calculator_converter",
            "calculator-converter",
            "converter",
        ):
            try:
                if method(screen_name):
                    return True
            except Exception:
                continue

        return False

    @staticmethod
    def _open_calculator_tab(
        context: Any,
    ) -> bool:
        """
        Open Calculator-Converter and switch to the Calculator tab.
        """
        if context is None:
            return False

        open_screen = getattr(
            context,
            "open_screen",
            None,
        )
        get_screen = getattr(
            context,
            "get_screen",
            None,
        )

        if not callable(open_screen):
            return False

        screen_name = None

        for candidate in (
            "calculator",
            "calculator_converter",
            "calculator-converter",
        ):
            try:
                if open_screen(candidate):
                    screen_name = candidate
                    break
            except Exception:
                continue

        if screen_name is None:
            return False

        if not callable(get_screen):
            return False

        try:
            screen = get_screen(screen_name)
        except Exception as error:
            print(
                "CalculatorSkill calculator screen error: "
                f"{type(error).__name__}: {error}"
            )
            return False

        if screen is None:
            return False

        show_calculator = getattr(
            screen,
            "show_calculator",
            None,
        )

        if not callable(show_calculator):
            print(
                "CalculatorSkill: calculator screen "
                "does not have show_calculator()."
            )
            return False

        try:
            show_calculator(None)
            return True
        except TypeError:
            try:
                show_calculator()
                return True
            except Exception as error:
                print(
                    "CalculatorSkill show_calculator error: "
                    f"{type(error).__name__}: {error}"
                )
                return False
        except Exception as error:
            print(
                "CalculatorSkill show_calculator error: "
                f"{type(error).__name__}: {error}"
            )
            return False

    @staticmethod
    def _open_converter(context: Any) -> bool:
        """
        Open Calculator-Converter and switch to its Converter tab.
        """
        if context is None:
            return False

        open_screen = getattr(
            context,
            "open_screen",
            None,
        )
        get_screen = getattr(
            context,
            "get_screen",
            None,
        )

        if not callable(open_screen):
            return False

        screen_name = None

        for candidate in (
            "calculator",
            "calculator_converter",
            "calculator-converter",
        ):
            try:
                if open_screen(candidate):
                    screen_name = candidate
                    break
            except Exception:
                continue

        if screen_name is None:
            return False

        if not callable(get_screen):
            return False

        try:
            screen = get_screen(screen_name)
        except Exception as error:
            print(
                "CalculatorSkill converter screen error: "
                f"{type(error).__name__}: {error}"
            )
            return False

        if screen is None:
            return False

        show_converter = getattr(
            screen,
            "show_converter",
            None,
        )

        if not callable(show_converter):
            print(
                "CalculatorSkill: calculator screen "
                "does not have show_converter()."
            )
            return False

        try:
            show_converter(None)
            return True
        except TypeError:
            try:
                show_converter()
                return True
            except Exception as error:
                print(
                    "CalculatorSkill show_converter error: "
                    f"{type(error).__name__}: {error}"
                )
                return False
        except Exception as error:
            print(
                "CalculatorSkill show_converter error: "
                f"{type(error).__name__}: {error}"
            )
            return False

    @classmethod
    def _looks_like_expression(
        cls,
        text: str,
    ) -> bool:
        if re.fullmatch(
            r"[\d\s()+\-*/%.^]+",
            text,
        ):
            return True

        return bool(
            re.search(
                r"\d",
                text,
            )
            and re.search(
                r"(?:\+|-|\*|/|\^|plus|minus|times|divided|плюс|минус|умнож|раздел)",
                text,
                re.IGNORECASE,
            )
        )

    @classmethod
    def _looks_like_conversion(
        cls,
        text: str,
    ) -> bool:
        if not re.search(r"\d", text):
            return False

        return bool(
            re.search(
                r"\b(?:to|into|in|в|на)\b",
                text,
                re.IGNORECASE,
            )
            and any(
                alias in text
                for alias in cls.UNIT_ALIASES
            )
        )

    @classmethod
    def _parse_conversion(
        cls,
        text: str,
    ) -> tuple[float, str, str] | None:
        cleaned = text

        prefixes = (
            "convert ",
            "conversion ",
            "how many ",
            "what is ",
            "переведи ",
            "конвертируй ",
            "сколько ",
        )

        for prefix in prefixes:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):]
                break

        aliases = sorted(
            cls.UNIT_ALIASES.keys(),
            key=len,
            reverse=True,
        )

        alias_pattern = "|".join(
            re.escape(alias)
            for alias in aliases
        )

        pattern = (
            rf"(-?\d+(?:\.\d+)?)\s*"
            rf"({alias_pattern})\s*"
            rf"(?:to|into|in|в|на)\s*"
            rf"({alias_pattern})"
        )

        match = re.search(
            pattern,
            cleaned,
            re.IGNORECASE,
        )

        if not match:
            return None

        value = float(match.group(1))
        from_unit = cls.UNIT_ALIASES[
            match.group(2).lower()
        ]
        to_unit = cls.UNIT_ALIASES[
            match.group(3).lower()
        ]

        return value, from_unit, to_unit

    @staticmethod
    def _parse_percentage(
        text: str,
    ) -> tuple[float, float] | None:
        patterns = (
            r"(-?\d+(?:\.\d+)?)\s*%"
            r"\s*(?:of|от)\s*"
            r"(-?\d+(?:\.\d+)?)",
            r"(-?\d+(?:\.\d+)?)\s*"
            r"(?:percent|percentage|процент|процентов)"
            r"\s*(?:of|от)\s*"
            r"(-?\d+(?:\.\d+)?)",
        )

        for pattern in patterns:
            match = re.search(
                pattern,
                text,
                re.IGNORECASE,
            )

            if match:
                return (
                    float(match.group(1)),
                    float(match.group(2)),
                )

        return None

    @classmethod
    def _extract_expression(
        cls,
        text: str,
    ) -> str | None:
        expression = text

        replacements = (
            (r"\bwhat is\b", ""),
            (r"\bcalculate\b", ""),
            (r"\bcompute\b", ""),
            (r"\bhow much is\b", ""),
            (r"\bсколько будет\b", ""),
            (r"\bвычисли\b", ""),
            (r"\bпосчитай\b", ""),
            (r"\bplus\b", "+"),
            (r"\badded to\b", "+"),
            (r"\bminus\b", "-"),
            (r"\btimes\b", "*"),
            (r"\bmultiplied by\b", "*"),
            (r"\bdivided by\b", "/"),
            (r"\bover\b", "/"),
            (r"\bto the power of\b", "**"),
            (r"\bплюс\b", "+"),
            (r"\bминус\b", "-"),
            (r"\bумножить на\b", "*"),
            (r"\bумножь на\b", "*"),
            (r"\bразделить на\b", "/"),
            (r"\bподелить на\b", "/"),
            (r"\bв степени\b", "**"),
        )

        for pattern, replacement in replacements:
            expression = re.sub(
                pattern,
                replacement,
                expression,
                flags=re.IGNORECASE,
            )

        square_root_match = re.search(
            r"(?:square root of|sqrt|корень из)\s*"
            r"(-?\d+(?:\.\d+)?)",
            expression,
            re.IGNORECASE,
        )

        if square_root_match:
            return (
                f"sqrt({square_root_match.group(1)})"
            )

        expression = expression.replace(
            "^",
            "**",
        )

        expression = re.sub(
            r"[^0-9+\-*/().%\s]",
            "",
            expression,
        )

        expression = " ".join(
            expression.split()
        )

        return expression or None

    @classmethod
    def _safe_evaluate(
        cls,
        expression: str,
    ) -> float:
        if len(expression) > 200:
            raise ValueError(
                "expression is too long"
            )

        parsed = ast.parse(
            expression,
            mode="eval",
        )

        result = cls._evaluate_node(
            parsed.body
        )

        if isinstance(result, complex):
            raise ValueError(
                "complex numbers are not supported"
            )

        if not math.isfinite(
            float(result)
        ):
            raise ValueError(
                "result is not finite"
            )

        return float(result)

    @classmethod
    def _evaluate_node(
        cls,
        node: ast.AST,
    ) -> float:
        if isinstance(
            node,
            ast.Constant,
        ):
            if isinstance(
                node.value,
                (int, float),
            ):
                return float(node.value)

            raise ValueError(
                "invalid value"
            )

        if isinstance(
            node,
            ast.BinOp,
        ):
            operator_type = type(
                node.op
            )

            function = cls.BINARY_OPERATORS.get(
                operator_type
            )

            if function is None:
                raise ValueError(
                    "operator is not supported"
                )

            left = cls._evaluate_node(
                node.left
            )
            right = cls._evaluate_node(
                node.right
            )

            if (
                operator_type is ast.Pow
                and abs(right) > 100
            ):
                raise ValueError(
                    "exponent is too large"
                )

            return function(
                left,
                right,
            )

        if isinstance(
            node,
            ast.UnaryOp,
        ):
            function = cls.UNARY_OPERATORS.get(
                type(node.op)
            )

            if function is None:
                raise ValueError(
                    "unary operator is not supported"
                )

            return function(
                cls._evaluate_node(
                    node.operand
                )
            )

        if isinstance(
            node,
            ast.Call,
        ):
            if (
                isinstance(node.func, ast.Name)
                and node.func.id == "sqrt"
                and len(node.args) == 1
            ):
                value = cls._evaluate_node(
                    node.args[0]
                )

                if value < 0:
                    raise ValueError(
                        "square root of a negative number"
                    )

                return math.sqrt(value)

            raise ValueError(
                "function is not supported"
            )

        raise ValueError(
            "expression is not supported"
        )

    @classmethod
    def _convert(
        cls,
        value: float,
        from_unit: str,
        to_unit: str,
    ) -> float:
        if (
            from_unit == "celsius"
            and to_unit == "fahrenheit"
        ):
            return (
                value * 9.0 / 5.0
            ) + 32.0

        if (
            from_unit == "fahrenheit"
            and to_unit == "celsius"
        ):
            return (
                value - 32.0
            ) * 5.0 / 9.0

        if (
            from_unit in {
                "celsius",
                "fahrenheit",
            }
            or to_unit in {
                "celsius",
                "fahrenheit",
            }
        ):
            raise ValueError(
                "Temperature can only be converted "
                "between Celsius and Fahrenheit."
            )

        source = cls.UNIT_FACTORS.get(
            from_unit
        )
        target = cls.UNIT_FACTORS.get(
            to_unit
        )

        if source is None or target is None:
            raise ValueError(
                "That conversion is not supported."
            )

        source_category, source_factor = source
        target_category, target_factor = target

        if source_category != target_category:
            raise ValueError(
                "Those units are not compatible."
            )

        base_value = value * source_factor
        return base_value / target_factor

    @staticmethod
    def _format_number(
        value: float,
    ) -> str:
        if abs(
            value - round(value)
        ) < 1e-10:
            return str(int(round(value)))

        return (
            f"{value:.6f}"
            .rstrip("0")
            .rstrip(".")
        )

    @classmethod
    def _format_conversion_answer(
        cls,
        value: float,
        from_unit: str,
        result: float,
        to_unit: str,
        russian: bool,
    ) -> str:
        left = cls._format_number(value)
        right = cls._format_number(result)

        if russian:
            return (
                f"{left} {from_unit} равно "
                f"{right} {to_unit}."
            )

        return (
            f"{left} {from_unit} equals "
            f"{right} {to_unit}."
        )