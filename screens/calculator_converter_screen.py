from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.graphics import Color, Rectangle

from utils.ui_scale import font, height


BG = (0.04, 0.07, 0.12, 1)
TAB_OFF = (0.10, 0.14, 0.22, 1)
TAB_ON = (0.16, 0.36, 0.62, 1)
BTN_NUM = (0.10, 0.16, 0.26, 1)
BTN_OP = (0.85, 0.42, 0.10, 1)
BTN_OK = (0.10, 0.55, 0.32, 1)
BTN_BAD = (0.65, 0.15, 0.15, 1)
INPUT_BG = (0.08, 0.11, 0.18, 1)


class CalculatorConverterScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.expression = ""
        self.converter_value = ""

        root = BoxLayout(orientation="vertical", padding=height(10), spacing=height(8))

        with root.canvas.before:
            Color(*BG)
            self.bg_rect = Rectangle(pos=root.pos, size=root.size)

        root.bind(pos=self.update_bg, size=self.update_bg)

        top = BoxLayout(size_hint=(1, 0.10), spacing=height(10))

        back = Button(
            text="< Back",
            font_size=font(22),
            background_normal="",
            background_color=(0.25, 0.25, 0.30, 1),
            color=(1, 1, 1, 1)
        )
        back.bind(on_press=self.go_back)

        title = Label(
            text="Calculator - Converter",
            font_size=font(24),
            bold=True,
            color=(0.85, 0.95, 1, 1)
        )

        top.add_widget(back)
        top.add_widget(title)
        root.add_widget(top)

        tabs = BoxLayout(size_hint=(1, 0.10), spacing=height(8))

        self.calc_tab = Button(
            text="Calculator",
            font_size=font(22),
            background_normal="",
            background_color=TAB_ON,
            color=(1, 1, 1, 1)
        )

        self.conv_tab = Button(
            text="Converter",
            font_size=font(22),
            background_normal="",
            background_color=TAB_OFF,
            color=(1, 1, 1, 1)
        )

        self.calc_tab.bind(on_press=self.show_calculator)
        self.conv_tab.bind(on_press=self.show_converter)

        tabs.add_widget(self.calc_tab)
        tabs.add_widget(self.conv_tab)
        root.add_widget(tabs)

        self.body = BoxLayout(orientation="vertical", spacing=height(7))
        root.add_widget(self.body)

        self.add_widget(root)
        self.show_calculator(None)

    def update_bg(self, instance, value):
        self.bg_rect.pos = instance.pos
        self.bg_rect.size = instance.size

    def go_back(self, instance):
        if self.manager:
            self.manager.current = "home"

    def clear_body(self):
        self.body.clear_widgets()

    def make_label(self, text, size=18):
        return Label(
            text=text,
            font_size=font(size),
            color=(0.65, 0.85, 1, 1),
            size_hint=(1, 0.055)
        )

    def make_spinner(self, text, values):
        return Spinner(
            text=text,
            values=values,
            font_size=font(20),
            size_hint=(1, 0.09),
            background_normal="",
            background_color=(0.12, 0.22, 0.36, 1),
            color=(1, 1, 1, 1)
        )

    # =========================
    # Calculator
    # =========================

    def show_calculator(self, instance):
        self.clear_body()

        self.calc_tab.background_color = TAB_ON
        self.conv_tab.background_color = TAB_OFF

        self.display = TextInput(
            text=self.expression,
            readonly=True,
            multiline=False,
            font_size=font(38),
            size_hint=(1, 0.18),
            halign="right",
            background_color=INPUT_BG,
            foreground_color=(1, 1, 1, 1),
            cursor_color=(1, 1, 1, 1)
        )
        self.body.add_widget(self.display)

        grid = GridLayout(cols=4, spacing=height(8), size_hint=(1, 0.82))

        buttons = [
            "7", "8", "9", "/",
            "4", "5", "6", "*",
            "1", "2", "3", "-",
            "0", ".", "=", "+",
            "C", "DEL", "(", ")"
        ]

        for text in buttons:
            color = BTN_NUM

            if text in ("+", "-", "*", "/", "(", ")"):
                color = BTN_OP
            elif text == "=":
                color = BTN_OK
            elif text in ("C", "DEL"):
                color = BTN_BAD

            btn = Button(
                text=text,
                font_size=font(28),
                background_normal="",
                background_color=color,
                color=(1, 1, 1, 1)
            )

            if text == "=":
                btn.bind(on_press=self.calculate)
            elif text == "C":
                btn.bind(on_press=self.clear_calc)
            elif text == "DEL":
                btn.bind(on_press=self.backspace)
            else:
                btn.bind(on_press=self.add_char)

            grid.add_widget(btn)

        self.body.add_widget(grid)

    def add_char(self, instance):
        self.expression += instance.text
        self.display.text = self.expression

    def clear_calc(self, instance):
        self.expression = ""
        self.display.text = ""

    def backspace(self, instance):
        self.expression = self.expression[:-1]
        self.display.text = self.expression

    def calculate(self, instance):
        try:
            allowed = "0123456789+-*/(). "
            if not all(c in allowed for c in self.expression):
                raise ValueError

            result = eval(self.expression)
            self.expression = str(result)
            self.display.text = self.expression

        except Exception:
            self.display.text = "Error"
            self.expression = ""

    # =========================
    # Converter
    # =========================

    def show_converter(self, instance):
        self.clear_body()

        self.calc_tab.background_color = TAB_OFF
        self.conv_tab.background_color = TAB_ON

        self.body.add_widget(self.make_label("Conversion Type"))

        self.conv_type = self.make_spinner(
            "Length",
            ("Length", "Area", "Weight", "Temperature", "Volume")
        )
        self.conv_type.bind(text=self.update_units)
        self.body.add_widget(self.conv_type)

        row = BoxLayout(size_hint=(1, 0.20), spacing=height(8))

        left = BoxLayout(orientation="vertical", spacing=height(5))

        left.add_widget(self.make_label("From"))
        self.from_unit = self.make_spinner("Meters", ())
        left.add_widget(self.from_unit)

        left.add_widget(self.make_label("To"))
        self.to_unit = self.make_spinner("Feet", ())
        left.add_widget(self.to_unit)

        right = BoxLayout(orientation="vertical", spacing=height(5))

        right.add_widget(self.make_label("Value"))
        self.value_display = TextInput(
            text=self.converter_value,
            readonly=True,
            multiline=False,
            font_size=font(28),
            size_hint=(1, 0.42),
            halign="right",
            background_color=INPUT_BG,
            foreground_color=(1, 1, 1, 1),
            cursor_color=(1, 1, 1, 1)
        )
        right.add_widget(self.value_display)

        self.result_label = Label(
            text="Result: --",
            font_size=font(24),
            bold=True,
            size_hint=(1, 0.42),
            color=(0.90, 1, 1, 1)
        )
        right.add_widget(self.result_label)

        row.add_widget(left)
        row.add_widget(right)

        self.body.add_widget(row)

        keypad = GridLayout(cols=3, spacing=height(7), size_hint=(1, 0.58))

        keys = [
            "7", "8", "9",
            "4", "5", "6",
            "1", "2", "3",
            "0", ".", "DEL",
            "C", "-", "Convert"
        ]

        for text in keys:
            color = BTN_NUM

            if text == "Convert":
                color = BTN_OK
            elif text in ("C", "DEL"):
                color = BTN_BAD
            elif text == "-":
                color = BTN_OP

            btn = Button(
                text=text,
                font_size=font(24),
                background_normal="",
                background_color=color,
                color=(1, 1, 1, 1),
                bold=True if text == "Convert" else False
            )

            if text == "Convert":
                btn.bind(on_press=self.convert)
            elif text == "C":
                btn.bind(on_press=self.clear_converter_value)
            elif text == "DEL":
                btn.bind(on_press=self.converter_backspace)
            else:
                btn.bind(on_press=self.converter_add_char)

            keypad.add_widget(btn)

        self.body.add_widget(keypad)

        self.update_units(None, "Length")

    def converter_add_char(self, instance):
        char = instance.text

        if char == "." and "." in self.converter_value:
            return

        if char == "-":
            if self.converter_value.startswith("-"):
                self.converter_value = self.converter_value[1:]
            else:
                self.converter_value = "-" + self.converter_value
        else:
            self.converter_value += char

        self.value_display.text = self.converter_value

    def clear_converter_value(self, instance):
        self.converter_value = ""
        self.value_display.text = ""
        self.result_label.text = "Result: --"

    def converter_backspace(self, instance):
        self.converter_value = self.converter_value[:-1]
        self.value_display.text = self.converter_value

    def update_units(self, instance, value):
        if value == "Length":
            units = (
                "Millimeters",
                "Centimeters",
                "Meters",
                "Kilometers",
                "Inches",
                "Feet",
                "Yards",
                "Miles"
            )
            self.from_unit.text = "Meters"
            self.to_unit.text = "Feet"

        elif value == "Area":
            units = (
                "Square Meters",
                "Square Feet",
                "Square Inches",
                "Square Yards",
                "Acres",
                "Hectares"
            )
            self.from_unit.text = "Square Feet"
            self.to_unit.text = "Square Meters"

        elif value == "Weight":
            units = (
                "Kilograms",
                "Pounds",
                "Ounces",
                "Grams"
            )
            self.from_unit.text = "Kilograms"
            self.to_unit.text = "Pounds"

        elif value == "Temperature":
            units = (
                "Celsius",
                "Fahrenheit",
                "Kelvin"
            )
            self.from_unit.text = "Celsius"
            self.to_unit.text = "Fahrenheit"

        else:
            units = (
                "Liters",
                "Gallons",
                "Milliliters"
            )
            self.from_unit.text = "Liters"
            self.to_unit.text = "Gallons"

        self.from_unit.values = units
        self.to_unit.values = units

    def convert(self, instance):
        try:
            if self.converter_value in ("", "-", "."):
                raise ValueError

            value = float(self.converter_value)

            result = self.convert_value(
                value,
                self.conv_type.text,
                self.from_unit.text,
                self.to_unit.text
            )

            self.result_label.text = f"Result: {result:.4f}"

        except Exception:
            self.result_label.text = "Result: Error"

    def convert_value(self, value, ctype, from_u, to_u):
        if from_u == to_u:
            return value

        if ctype == "Length":
            meters = {
                "Millimeters": 0.001,
                "Centimeters": 0.01,
                "Meters": 1,
                "Kilometers": 1000,
                "Inches": 0.0254,
                "Feet": 0.3048,
                "Yards": 0.9144,
                "Miles": 1609.344
            }
            return value * meters[from_u] / meters[to_u]

        if ctype == "Area":
            sqm = {
                "Square Meters": 1,
                "Square Feet": 0.09290304,
                "Square Inches": 0.00064516,
                "Square Yards": 0.83612736,
                "Acres": 4046.8564224,
                "Hectares": 10000
            }
            return value * sqm[from_u] / sqm[to_u]

        if ctype == "Weight":
            grams = {
                "Kilograms": 1000,
                "Pounds": 453.59237,
                "Ounces": 28.3495,
                "Grams": 1
            }
            return value * grams[from_u] / grams[to_u]

        if ctype == "Volume":
            liters = {
                "Liters": 1,
                "Gallons": 3.78541,
                "Milliliters": 0.001
            }
            return value * liters[from_u] / liters[to_u]

        if ctype == "Temperature":
            return self.convert_temperature(value, from_u, to_u)

        return value

    def convert_temperature(self, value, from_u, to_u):
        if from_u == "Celsius":
            c = value
        elif from_u == "Fahrenheit":
            c = (value - 32) * 5 / 9
        else:
            c = value - 273.15

        if to_u == "Celsius":
            return c
        elif to_u == "Fahrenheit":
            return c * 9 / 5 + 32
        else:
            return c + 273.15