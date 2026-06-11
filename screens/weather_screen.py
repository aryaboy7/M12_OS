import json
import urllib.parse
import urllib.request
from datetime import datetime

from kivy.clock import Clock
from kivy.graphics import Color, Ellipse, Line, Rectangle
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget

from utils.config_manager import ConfigManager
from utils.ui_scale import font, height


WEATHER_CODES = {
    0: ("sun", "Clear"),
    1: ("sun_cloud", "Mostly Clear"),
    2: ("sun_cloud", "Partly Cloudy"),
    3: ("cloud", "Cloudy"),
    45: ("fog", "Fog"),
    48: ("fog", "Freezing Fog"),
    51: ("rain", "Light Drizzle"),
    53: ("rain", "Drizzle"),
    55: ("rain", "Heavy Drizzle"),
    61: ("rain", "Light Rain"),
    63: ("rain", "Rain"),
    65: ("rain", "Heavy Rain"),
    71: ("snow", "Light Snow"),
    73: ("snow", "Snow"),
    75: ("snow", "Heavy Snow"),
    80: ("rain", "Rain Showers"),
    81: ("rain", "Rain Showers"),
    82: ("storm", "Heavy Showers"),
    95: ("storm", "Thunderstorm"),
}

RAIN_CODES = [51, 53, 55, 61, 63, 65, 80, 81, 82]
SNOW_CODES = [71, 73, 75]


class WeatherIcon(Widget):
    def __init__(self, icon_type="sun", **kwargs):
        super().__init__(**kwargs)
        self.icon_type = icon_type
        self.bind(pos=self.draw_icon, size=self.draw_icon)

    def set_icon(self, icon_type):
        self.icon_type = icon_type
        self.draw_icon()

    def draw_icon(self, *args):
        self.canvas.clear()

        x, y = self.pos
        w, h = self.size
        cx = x + w / 2
        cy = y + h / 2
        s = min(w, h)

        with self.canvas:
            if self.icon_type in ("sun", "sun_cloud"):
                Color(1.0, 0.78, 0.10, 1)
                Ellipse(pos=(cx - s * 0.18, cy - s * 0.18), size=(s * 0.36, s * 0.36))

                import math
                for i in range(12):
                    a = i * math.pi / 6
                    x1 = cx + math.cos(a) * s * 0.25
                    y1 = cy + math.sin(a) * s * 0.25
                    x2 = cx + math.cos(a) * s * 0.39
                    y2 = cy + math.sin(a) * s * 0.39
                    Line(points=[x1, y1, x2, y2], width=max(1.5, s * 0.018))

            if self.icon_type in ("cloud", "sun_cloud", "rain", "snow", "storm", "fog"):
                Color(0.80, 0.84, 0.88, 1)
                cloud_y = cy - s * 0.14 if self.icon_type == "sun_cloud" else cy
                Ellipse(pos=(cx - s * 0.36, cloud_y - s * 0.10), size=(s * 0.32, s * 0.25))
                Ellipse(pos=(cx - s * 0.18, cloud_y + s * 0.00), size=(s * 0.38, s * 0.32))
                Ellipse(pos=(cx + s * 0.05, cloud_y - s * 0.10), size=(s * 0.36, s * 0.25))
                Rectangle(pos=(cx - s * 0.30, cloud_y - s * 0.10), size=(s * 0.62, s * 0.17))

            if self.icon_type == "rain":
                Color(0.18, 0.55, 1.0, 1)
                for dx in (-0.20, 0.0, 0.20):
                    Line(points=[cx + dx * s, cy - s * 0.20, cx + dx * s - s * 0.06, cy - s * 0.38], width=max(2, s * 0.025))

            if self.icon_type == "snow":
                Color(0.65, 0.90, 1.0, 1)
                for dx in (-0.20, 0.0, 0.20):
                    px = cx + dx * s
                    py = cy - s * 0.30
                    ww = max(1.5, s * 0.018)
                    Line(points=[px - s * 0.05, py, px + s * 0.05, py], width=ww)
                    Line(points=[px, py - s * 0.05, px, py + s * 0.05], width=ww)
                    Line(points=[px - s * 0.035, py - s * 0.035, px + s * 0.035, py + s * 0.035], width=ww)
                    Line(points=[px - s * 0.035, py + s * 0.035, px + s * 0.035, py - s * 0.035], width=ww)

            if self.icon_type == "storm":
                Color(1.0, 0.82, 0.10, 1)
                Line(points=[cx - s * 0.02, cy - s * 0.16, cx - s * 0.13, cy - s * 0.37, cx + s * 0.03, cy - s * 0.31, cx - s * 0.05, cy - s * 0.50], width=max(3, s * 0.035))

            if self.icon_type == "fog":
                Color(0.72, 0.76, 0.80, 1)
                for j in range(4):
                    yy = cy - s * 0.20 + j * s * 0.11
                    Line(points=[cx - s * 0.38, yy, cx + s * 0.38, yy], width=max(2, s * 0.025))


class WeatherRow(BoxLayout):
    def __init__(self, left_text, icon_type, right_text, height_value=92, **kwargs):
        super().__init__(orientation="horizontal", spacing=8, size_hint_y=None, height=height(height_value), **kwargs)

        left = Label(text=left_text, font_size=font(22), bold=True, halign="center", valign="middle", size_hint=(0.22, 1))
        left.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        self.add_widget(left)

        self.add_widget(WeatherIcon(icon_type=icon_type, size_hint=(0.16, 1)))

        right = Label(text=right_text, font_size=font(20), halign="left", valign="middle", size_hint=(0.62, 1))
        right.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        self.add_widget(right)


class WeatherScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.config = ConfigManager()
        self.weather_data = None
        self.air_data = None
        self.city_name = self.config.get("city", "Brooklyn, NY")
        self.active_tab = "current"

        root = BoxLayout(orientation="vertical", padding=15, spacing=10)
        root.add_widget(Label(text="Weather", font_size=font(40), bold=True, size_hint=(1, 0.09)))

        tabs = BoxLayout(orientation="horizontal", spacing=8, size_hint=(1, 0.09))
        self.current_btn = self.make_tab_button("Current")
        self.forecast_btn = self.make_tab_button("Forecast")
        self.hourly_btn = self.make_tab_button("Hourly")
        self.current_btn.bind(on_release=lambda instance: self.show_current())
        self.forecast_btn.bind(on_release=lambda instance: self.show_forecast())
        self.hourly_btn.bind(on_release=lambda instance: self.show_hourly())
        tabs.add_widget(self.current_btn)
        tabs.add_widget(self.forecast_btn)
        tabs.add_widget(self.hourly_btn)
        root.add_widget(tabs)

        self.content = BoxLayout(orientation="vertical", spacing=8, size_hint=(1, 0.64))
        root.add_widget(self.content)

        bottom = BoxLayout(orientation="horizontal", spacing=8, size_hint=(1, 0.12))
        refresh_btn = Button(text="Refresh", font_size=font(28), background_normal="", background_color=(0.12, 0.20, 0.35, 1))
        refresh_btn.bind(on_release=self.refresh_weather)
        bottom.add_widget(refresh_btn)
        back_btn = Button(text="< Back", font_size=font(28), background_normal="", background_color=(0.10, 0.15, 0.25, 1))
        back_btn.bind(on_release=self.go_back)
        bottom.add_widget(back_btn)
        root.add_widget(bottom)
        self.add_widget(root)

    def make_tab_button(self, text):
        return Button(text=text, font_size=font(26), background_normal="", background_color=(0.10, 0.15, 0.25, 1))

    def on_enter(self):
        self.config = ConfigManager()
        self.city_name = self.config.get("city", "Brooklyn, NY")
        self.show_saved_current()
        Clock.schedule_once(lambda dt: self.refresh_weather(None), 0.2)

    def clear_content(self):
        self.content.clear_widgets()

    def set_active_button(self, tab_name):
        self.active_tab = tab_name
        normal = (0.10, 0.15, 0.25, 1)
        active = (0.12, 0.20, 0.35, 1)
        self.current_btn.background_color = active if tab_name == "current" else normal
        self.forecast_btn.background_color = active if tab_name == "forecast" else normal
        self.hourly_btn.background_color = active if tab_name == "hourly" else normal

    def show_loading(self, text="Loading weather..."):
        self.clear_content()
        self.content.add_widget(Label(text=text, font_size=font(32), halign="center", valign="middle"))

    def add_scroll_text(self, text, font_size_value=None):
        scroll = ScrollView(do_scroll_x=False, do_scroll_y=True)
        label = Label(text=text, font_size=font_size_value or font(18), halign="center", valign="top", size_hint_y=None, padding=(10, 10))
        label.bind(width=lambda inst, val: setattr(inst, "text_size", (val - 20, None)))
        label.bind(texture_size=lambda inst, val: setattr(inst, "height", val[1] + height(60)))
        scroll.add_widget(label)
        self.content.add_widget(scroll)

    def show_saved_current(self):
        self.set_active_button("current")
        self.clear_content()
        city = self.config.get("city", "Brooklyn, NY")
        unit = self.config.get("temperature_unit", "F")
        temp = self.config.get("last_temperature", "--")
        feels_like = self.config.get("last_feels_like", "--")
        condition = self.config.get("last_condition", "Weather")
        humidity = self.config.get("last_humidity", "--")
        wind = self.config.get("last_wind", "--")
        advice = self.config.get("last_advice", "")
        icon_type = self.config.get("last_icon_type", "cloud")
        uv = self.config.get("last_uv", "--")
        aqi = self.config.get("last_aqi", "--")
        sunrise = self.config.get("last_sunrise", "--")
        sunset = self.config.get("last_sunset", "--")
        self.build_current_view(icon_type, city, temp, unit, condition, feels_like, advice, humidity, wind, uv, aqi, sunrise, sunset, "Refreshing...")

    def refresh_weather(self, instance):
        self.show_loading()
        try:
            unit = self.config.get("temperature_unit", "F")
            city = self.config.get("city", "Brooklyn, NY")
            geo = self.geocode_city(city)
            if not geo:
                self.show_loading(f"City not found:\n{city}")
                return
            self.city_name = geo["name"]
            self.weather_data = self.get_weather_data(geo["latitude"], geo["longitude"], unit)
            self.air_data = self.get_air_quality_data(geo["latitude"], geo["longitude"])
            self.save_current_weather(unit)
            if self.active_tab == "forecast":
                self.show_forecast()
            elif self.active_tab == "hourly":
                self.show_hourly()
            else:
                self.show_current()
        except Exception as e:
            print("WEATHER ERROR =", e)
            self.show_loading(f"Weather error:\n{e}")

    def geocode_city(self, city):
        city_only = city.split(",")[0].strip()
        query = urllib.parse.quote(city_only)
        url = f"https://geocoding-api.open-meteo.com/v1/search?name={query}&count=1&language=en&format=json"
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
        results = data.get("results", [])
        if not results:
            return None
        item = results[0]
        name = item.get("name", city_only)
        admin1 = item.get("admin1", "")
        if admin1:
            name = f"{name}, {admin1}"
        return {"name": name, "latitude": item["latitude"], "longitude": item["longitude"]}

    def get_weather_data(self, latitude, longitude, unit):
        temp_unit = "fahrenheit" if unit == "F" else "celsius"
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={latitude}"
            f"&longitude={longitude}"
            "&current=temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m"
            "&hourly=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
            "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,uv_index_max,sunrise,sunset"
            f"&temperature_unit={temp_unit}"
            "&wind_speed_unit=mph"
            "&forecast_days=10"
            "&timezone=auto"
        )
        print("WEATHER URL =", url)
        with urllib.request.urlopen(url, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))

    def get_air_quality_data(self, latitude, longitude):
        url = f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={latitude}&longitude={longitude}&current=us_aqi&timezone=auto"
        print("AIR QUALITY URL =", url)
        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as e:
            print("AIR QUALITY ERROR =", e)
            return {}

    def save_current_weather(self, unit):
        if not self.weather_data:
            return
        current = self.weather_data.get("current", {})
        daily = self.weather_data.get("daily", {})
        temp = round(current.get("temperature_2m", 0))
        feels_like = round(current.get("apparent_temperature", temp))
        humidity = current.get("relative_humidity_2m", "--")
        wind = round(current.get("wind_speed_10m", 0))
        code = current.get("weather_code", -1)
        icon_type, condition = self.code_to_icon_condition(code)
        advice = self.make_advice(temp, code, unit)
        uv = self.first_value(daily.get("uv_index_max", []), "--")
        sunrise = self.format_api_time(self.first_value(daily.get("sunrise", []), "--"))
        sunset = self.format_api_time(self.first_value(daily.get("sunset", []), "--"))
        aqi = "--"
        if self.air_data:
            aqi = self.air_data.get("current", {}).get("us_aqi", "--")
        self.config.set("city", self.city_name)
        self.config.set("last_temperature", temp)
        self.config.set("last_feels_like", feels_like)
        self.config.set("last_condition", condition)
        self.config.set("last_humidity", humidity)
        self.config.set("last_wind", wind)
        self.config.set("last_advice", advice)
        self.config.set("last_icon_type", icon_type)
        self.config.set("last_uv", uv)
        self.config.set("last_aqi", aqi)
        self.config.set("last_sunrise", sunrise)
        self.config.set("last_sunset", sunset)

    def show_current(self):
        self.set_active_button("current")
        if not self.weather_data:
            self.show_saved_current()
            return
        unit = self.config.get("temperature_unit", "F")
        current = self.weather_data.get("current", {})
        daily = self.weather_data.get("daily", {})
        temp = round(current.get("temperature_2m", 0))
        feels_like = round(current.get("apparent_temperature", temp))
        humidity = current.get("relative_humidity_2m", "--")
        wind = round(current.get("wind_speed_10m", 0))
        code = current.get("weather_code", -1)
        icon_type, condition = self.code_to_icon_condition(code)
        advice = self.make_advice(temp, code, unit)
        uv = self.first_value(daily.get("uv_index_max", []), "--")
        sunrise = self.format_api_time(self.first_value(daily.get("sunrise", []), "--"))
        sunset = self.format_api_time(self.first_value(daily.get("sunset", []), "--"))
        aqi = "--"
        if self.air_data:
            aqi = self.air_data.get("current", {}).get("us_aqi", "--")
        updated = datetime.now().strftime("%I:%M %p")
        self.build_current_view(icon_type, self.city_name, temp, unit, condition, feels_like, advice, humidity, wind, uv, aqi, sunrise, sunset, f"Updated: {updated}")

    def build_current_view(self, icon_type, city, temp, unit, condition, feels_like, advice, humidity, wind, uv, aqi, sunrise, sunset, updated_text):
        self.clear_content()
        self.content.add_widget(WeatherIcon(icon_type=icon_type, size_hint=(1, 0.24)))
        self.content.add_widget(Label(text=f"{city}\n{temp}°{unit}  {condition}", font_size=font(42), bold=True, size_hint=(1, 0.22), halign="center", valign="middle"))
        uv_label = self.uv_text(uv)
        aqi_label = self.aqi_text(aqi)
        details = (
            f"Feels Like: {feels_like}°{unit}\n\n"
            f"{advice}\n\n"
            f"Humidity: {humidity}%\n"
            f"Wind: {wind} mph\n\n"
            f"UV Index: {uv} ({uv_label})\n\n"
            f"Air Quality: {aqi} ({aqi_label})\n\n"
            f"Sunrise: {sunrise}\n"
            f"Sunset: {sunset}\n\n"
            f"{updated_text}"
        )
        self.add_scroll_text(details, font_size_value=font(24))

    def show_forecast(self):
        self.set_active_button("forecast")
        if not self.weather_data:
            self.show_loading("No forecast yet.\nPress Refresh.")
            return
        unit = self.config.get("temperature_unit", "F")
        daily = self.weather_data.get("daily", {})
        dates = daily.get("time", [])
        max_t = daily.get("temperature_2m_max", [])
        min_t = daily.get("temperature_2m_min", [])
        codes = daily.get("weather_code", [])
        precip = daily.get("precipitation_probability_max", [])
        if len(dates) < 2:
            self.show_loading("No forecast data.")
            return
        self.clear_content()
        scroll = ScrollView(do_scroll_x=False, do_scroll_y=True)
        list_box = BoxLayout(orientation="vertical", spacing=6, size_hint_y=None)
        list_box.bind(minimum_height=list_box.setter("height"))
        header = Label(text=f"{self.city_name}\n\nTOMORROW FORECAST", font_size=font(32), bold=True, size_hint_y=None, height=height(100), halign="center", valign="middle")
        header.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        list_box.add_widget(header)
        i = 1
        icon_type, cond = self.code_to_icon_condition(codes[i])
        rain = precip[i] if i < len(precip) else "--"
        list_box.add_widget(Label(text="Tomorrow", font_size=font(34), bold=True, size_hint_y=None, height=height(60)))
        list_box.add_widget(WeatherRow("Tomorrow", icon_type, f"{round(max_t[i])}/{round(min_t[i])}°{unit}\n{cond}  Rain {rain}%", height_value=110))
        list_box.add_widget(Label(text="\nNext 10 Days", font_size=font(32), bold=True, size_hint_y=None, height=height(85), halign="center", valign="middle"))
        for i in range(1, min(10, len(dates))):
            icon_type, cond = self.code_to_icon_condition(codes[i])
            rain = precip[i] if i < len(precip) else "--"
            day_name = self.short_day(dates[i])
            right_text = f"{round(max_t[i])}/{round(min_t[i])}°{unit}\n{cond}  Rain {rain}%"
            list_box.add_widget(WeatherRow(day_name, icon_type, right_text, height_value=92))
        list_box.add_widget(Label(text=f"Updated: {datetime.now().strftime('%I:%M %p')}", font_size=font(24), size_hint_y=None, height=height(60), halign="center", valign="middle"))
        scroll.add_widget(list_box)
        self.content.add_widget(scroll)

    def show_hourly(self):
        self.set_active_button("hourly")
        if not self.weather_data:
            self.show_loading("No hourly forecast yet.\nPress Refresh.")
            return
        unit = self.config.get("temperature_unit", "F")
        daily = self.weather_data.get("daily", {})
        hourly = self.weather_data.get("hourly", {})
        dates = daily.get("time", [])
        today = dates[0] if dates else datetime.now().strftime("%Y-%m-%d")
        h_times = hourly.get("time", [])
        h_temps = hourly.get("temperature_2m", [])
        h_codes = hourly.get("weather_code", [])
        h_winds = hourly.get("wind_speed_10m", [])
        h_hums = hourly.get("relative_humidity_2m", [])
        self.clear_content()
        scroll = ScrollView(do_scroll_x=False, do_scroll_y=True)
        list_box = BoxLayout(orientation="vertical", spacing=6, size_hint_y=None)
        list_box.bind(minimum_height=list_box.setter("height"))
        header = Label(text=f"{self.city_name}\n\nHourly Today", font_size=font(32), bold=True, size_hint_y=None, height=height(100), halign="center", valign="middle")
        header.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        list_box.add_widget(header)
        count = 0
        for i, h_time in enumerate(h_times):
            if not h_time.startswith(today):
                continue
            hour = h_time.split("T")[-1][:5]
            icon_type, cond = self.code_to_icon_condition(h_codes[i])
            right_text = f"{round(h_temps[i])}°{unit}\n{cond}  H:{h_hums[i]}%  W:{round(h_winds[i])}"
            list_box.add_widget(WeatherRow(hour, icon_type, right_text, height_value=92))
            count += 1
            if count >= 24:
                break
        if count == 0:
            list_box.add_widget(Label(text="No hourly data.", font_size=font(28), size_hint_y=None, height=height(75)))
        list_box.add_widget(Label(text=f"Updated: {datetime.now().strftime('%I:%M %p')}", font_size=font(24), size_hint_y=None, height=height(60), halign="center", valign="middle"))
        scroll.add_widget(list_box)
        self.content.add_widget(scroll)

    def code_to_icon_condition(self, code):
        return WEATHER_CODES.get(code, ("cloud", "Weather"))

    def short_day(self, date_text):
        try:
            dt = datetime.strptime(date_text, "%Y-%m-%d")
            return dt.strftime("%a %m/%d")
        except Exception:
            return date_text

    def first_value(self, values, default="--"):
        if not values:
            return default
        value = values[0]
        if value is None or value == "":
            return default
        return value

    def format_api_time(self, value):
        if not value or value == "--":
            return "--"
        try:
            dt = datetime.fromisoformat(value)
            return dt.strftime("%I:%M %p")
        except Exception:
            return str(value).split("T")[-1]

    def uv_text(self, uv):
        try:
            uv = float(uv)
        except Exception:
            return "Unknown"
        if uv < 3:
            return "Low"
        if uv < 6:
            return "Moderate"
        if uv < 8:
            return "High"
        if uv < 11:
            return "Very High"
        return "Extreme"

    def aqi_text(self, aqi):
        try:
            aqi = int(aqi)
        except Exception:
            return "Unknown"
        if aqi <= 50:
            return "Good"
        if aqi <= 100:
            return "Moderate"
        if aqi <= 150:
            return "Unhealthy for Sensitive Groups"
        if aqi <= 200:
            return "Unhealthy"
        if aqi <= 300:
            return "Very Unhealthy"
        return "Hazardous"

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
