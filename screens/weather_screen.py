import json
import urllib.parse
import urllib.request

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label

from utils.config_manager import ConfigManager
from utils.ui_scale import font


WEATHER_CODES = {
    0: "Clear",
    1: "Mostly Clear",
    2: "Partly Cloudy",
    3: "Cloudy",
    45: "Fog",
    48: "Freezing Fog",
    51: "Light Drizzle",
    53: "Drizzle",
    55: "Heavy Drizzle",
    61: "Light Rain",
    63: "Rain",
    65: "Heavy Rain",
    71: "Light Snow",
    73: "Snow",
    75: "Heavy Snow",
    80: "Rain Showers",
    81: "Rain Showers",
    82: "Heavy Showers",
    95: "Thunderstorm",
}

RAIN_CODES = [51, 53, 55, 61, 63, 65, 80, 81, 82]
SNOW_CODES = [71, 73, 75]


class WeatherScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.config = ConfigManager()

        root = BoxLayout(
            orientation="vertical",
            padding=15,
            spacing=15
        )

        title = Label(
            text="Weather",
            font_size=font(34),
            size_hint=(1, 0.12)
        )
        root.add_widget(title)

        self.info = Label(
            text="Press Refresh Weather",
            font_size=font(22),
            halign="center",
            valign="middle",
            size_hint=(1, 0.50)
        )
        self.info.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        root.add_widget(self.info)

        refresh_btn = Button(
            text="Refresh Weather",
            font_size=font(24),
            size_hint=(1, 0.18)
        )
        refresh_btn.bind(on_release=self.refresh_weather)
        root.add_widget(refresh_btn)

        back_btn = Button(
            text="< Back",
            font_size=font(24),
            size_hint=(1, 0.18)
        )
        back_btn.bind(on_release=self.go_back)
        root.add_widget(back_btn)

        self.add_widget(root)

    def on_enter(self):
        self.config = ConfigManager()
        self.show_saved_weather()
        self.refresh_weather(None)

    def show_saved_weather(self):
        city = self.config.get("city", "Brooklyn, NY")
        temp = self.config.get("last_temperature", "--")
        unit = self.config.get("temperature_unit", "F")
        condition = self.config.get("last_condition", "")
        humidity = self.config.get("last_humidity", "--")
        wind = self.config.get("last_wind", "--")
        advice = self.config.get("last_advice", "")

        self.info.text = (
            f"{city}\n\n"
            f"{temp}°{unit}\n"
            f"{condition}\n\n"
            f"Humidity: {humidity}%\n"
            f"Wind: {wind} mph\n\n"
            f"{advice}"
        )

    def refresh_weather(self, instance):
        print("REFRESH BUTTON CLICKED")

        try:
            city = self.config.get("city", "Brooklyn, NY")
            unit = self.config.get("temperature_unit", "F")

            city_only = city.split(",")[0].strip()
            query = urllib.parse.quote(city_only)

            geo_url = (
                "https://geocoding-api.open-meteo.com/v1/search"
                f"?name={query}&count=1&language=en&format=json"
            )

            geo_data = json.loads(
                urllib.request.urlopen(geo_url, timeout=10).read().decode()
            )

            print("GEOCODE DATA =", geo_data)

            results = geo_data.get("results", [])

            if not results:
                self.info.text = f"City not found:\n{city}"
                return

            item = results[0]

            lat = item["latitude"]
            lon = item["longitude"]

            city_name = item.get("name", city_only)
            admin1 = item.get("admin1", "")
            if admin1:
                city_name = f"{city_name}, {admin1}"

            temp_unit = "fahrenheit" if unit == "F" else "celsius"

            weather_url = (
                "https://api.open-meteo.com/v1/forecast"
                f"?latitude={lat}"
                f"&longitude={lon}"
                "&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
                f"&temperature_unit={temp_unit}"
                "&wind_speed_unit=mph"
                "&timezone=auto"
            )

            weather_data = json.loads(
                urllib.request.urlopen(weather_url, timeout=10).read().decode()
            )

            print("WEATHER DATA =", weather_data)

            current = weather_data.get("current", {})

            temp = round(current.get("temperature_2m", 0))
            humidity = current.get("relative_humidity_2m", "--")
            wind = round(current.get("wind_speed_10m", 0))
            code = current.get("weather_code", -1)

            condition = WEATHER_CODES.get(code, "Weather")
            advice = self.make_advice(temp, code, unit)

            self.config.set("city", city_name)
            self.config.set("last_temperature", temp)
            self.config.set("last_condition", condition)
            self.config.set("last_humidity", humidity)
            self.config.set("last_wind", wind)
            self.config.set("last_advice", advice)

            self.info.text = (
                f"{city_name}\n\n"
                f"{temp}°{unit}\n"
                f"{condition}\n\n"
                f"Humidity: {humidity}%\n"
                f"Wind: {wind} mph\n\n"
                f"{advice}"
            )

        except Exception as e:
            print("WEATHER ERROR =", e)
            self.info.text = f"Weather error:\n{e}"

    def make_advice(self, temp, code, unit):
        advice = []

        if unit == "C":
            if temp <= 0:
                advice.append("Very cold today. Wear a heavy coat.")
            elif temp <= 5:
                advice.append("Cold today. Take a coat.")
            elif temp <= 16:
                advice.append("Cool weather. Light jacket recommended.")
            elif temp <= 27:
                advice.append("Nice weather. Shirt is fine.")
            else:
                advice.append("Hot today. Shorts and T-shirt recommended.")
        else:
            if temp <= 32:
                advice.append("Very cold today. Wear a heavy coat.")
            elif temp <= 40:
                advice.append("Cold today. Take a coat.")
            elif temp <= 60:
                advice.append("Cool weather. Light jacket recommended.")
            elif temp <= 70:
                advice.append("Nice weather. Shirt is fine.")
            else:
                advice.append("Hot today. Shorts and T-shirt recommended.")

        if code in RAIN_CODES:
            advice.append("Take an umbrella.")

        if code in SNOW_CODES:
            advice.append("Snow expected. Wear boots.")

        if code == 95:
            advice.append("Thunderstorm possible. Stay alert.")

        return "\n".join(advice)

    def go_back(self, instance):
        if self.manager and self.manager.has_screen("home"):
            home = self.manager.get_screen("home")
            if hasattr(home, "refresh_weather_card"):
                home.refresh_weather_card()

        self.manager.current = "home"