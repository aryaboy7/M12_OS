import json
import re
import ssl
import urllib.parse
import urllib.request
import certifi
from datetime import datetime
from typing import Any

from services.skills.base_skill import BaseSkill, SkillResult
from utils.config_manager import ConfigManager


SSL_CONTEXT = ssl.create_default_context(
    cafile=certifi.where()
)


WEATHER_CODES = {
    0: "Clear",
    1: "Mostly clear",
    2: "Partly cloudy",
    3: "Cloudy",
    45: "Foggy",
    48: "Foggy",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    56: "Freezing drizzle",
    57: "Heavy freezing drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    66: "Freezing rain",
    67: "Heavy freezing rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Light rain showers",
    81: "Rain showers",
    82: "Heavy rain showers",
    85: "Light snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorms",
    96: "Thunderstorms with hail",
    99: "Severe thunderstorms with hail",
}


WEATHER_CODES_RU = {
    0: "ясно",
    1: "преимущественно ясно",
    2: "переменная облачность",
    3: "облачно",
    45: "туман",
    48: "туман",
    51: "небольшая морось",
    53: "морось",
    55: "сильная морось",
    56: "ледяная морось",
    57: "сильная ледяная морось",
    61: "небольшой дождь",
    63: "дождь",
    65: "сильный дождь",
    66: "ледяной дождь",
    67: "сильный ледяной дождь",
    71: "небольшой снег",
    73: "снег",
    75: "сильный снег",
    77: "снежная крупа",
    80: "небольшие ливни",
    81: "ливни",
    82: "сильные ливни",
    85: "небольшой снегопад",
    86: "сильный снегопад",
    95: "гроза",
    96: "гроза с градом",
    99: "сильная гроза с градом",
}


class WeatherSkill(BaseSkill):
    """
    Handles current weather and short forecast requests.

    Examples:
        What is the weather?
        What is the weather in Boston?
        What is the temperature outside?
        Will it rain today?
        What is the weather tomorrow?
        Open weather.

        Какая погода?
        Какая погода в Москве?
        Какая температура?
        Будет ли дождь сегодня?
        Какая погода завтра?
        Открой погоду.
    """

    name = "weather"
    priority = 15

    OPEN_PHRASES = {
        "open weather",
        "show weather app",
        "go to weather",
        "weather app",
        "открой погоду",
        "покажи приложение погоды",
        "перейди к погоде",
    }

    WEATHER_WORDS = {
        "weather",
        "temperature",
        "forecast",
        "rain",
        "snow",
        "wind",
        "humidity",
        "outside",
        "погода",
        "температура",
        "прогноз",
        "дождь",
        "снег",
        "ветер",
        "влажность",
    }

    TOMORROW_HINTS = (
        "tomorrow",
        "завтра",
    )

    DIRECT_FORECAST_PHRASES = {
        "show forecast",
        "show me the forecast",
        "weather forecast",
        "forecast",
        "покажи прогноз",
        "покажи прогноз погоды",
        "прогноз погоды",
        "прогноз",
    }

    FORECAST_HINTS = (
        "forecast",
        "next days",
        "next few days",
        "week weather",
        "прогноз",
        "на несколько дней",
        "на неделю",
    )

    def __init__(self):
        self.config = ConfigManager()

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

        if text in self.DIRECT_FORECAST_PHRASES:
            return 1.0

        words = set(text.split())

        if words.intersection(self.WEATHER_WORDS):
            return 1.0

        common_phrases = (
            "how hot is it",
            "how cold is it",
            "is it raining",
            "will it rain",
            "do i need an umbrella",
            "what is it like outside",
            "сколько градусов",
            "на улице холодно",
            "на улице жарко",
            "нужен ли зонт",
            "идет ли дождь",
            "идёт ли дождь",
        )

        if any(
            phrase in text
            for phrase in common_phrases
        ):
            return 0.98

        return 0.0

    def handle(
        self,
        message: str,
        context: Any,
    ) -> SkillResult:
        text = self._normalize(message)
        russian = self._is_russian(text)

        if text in self.OPEN_PHRASES:
            opened = self._open_weather(context)

            answer = (
                "Погода открыта."
                if russian and opened
                else "Не удалось открыть погоду."
                if russian
                else "Weather opened."
                if opened
                else "I couldn't open Weather."
            )

            return SkillResult(
                handled=True,
                answer=answer,
                confidence=1.0,
                action="open_weather",
                data={"opened": opened},
            )

        self.config = ConfigManager()

        saved_city = str(
            self.config.get(
                "city",
                "Brooklyn, NY",
            )
        ).strip() or "Brooklyn, NY"

        unit = str(
            self.config.get(
                "temperature_unit",
                "F",
            )
        ).strip().upper()

        if unit not in {"F", "C"}:
            unit = "F"

        requested_city = self._extract_city(
            text
        )

        city = requested_city or saved_city

        try:
            geo = self._geocode_city(city)

            if geo is None:
                return SkillResult(
                    handled=True,
                    answer=(
                        f"Город не найден: {city}."
                        if russian
                        else f"City not found: {city}."
                    ),
                    confidence=0.99,
                    action="weather_not_found",
                    data={"city": city},
                )

            weather = self._get_weather_data(
                latitude=geo["latitude"],
                longitude=geo["longitude"],
                unit=unit,
            )

            if any(
                hint in text
                for hint in self.TOMORROW_HINTS
            ):
                answer, data = self._tomorrow_answer(
                    city=geo["name"],
                    weather=weather,
                    unit=unit,
                    russian=russian,
                )
                action = "weather_tomorrow"

            elif (
                text in self.DIRECT_FORECAST_PHRASES
                or any(
                    hint in text
                    for hint in self.FORECAST_HINTS
                )
            ):
                answer, data = self._forecast_answer(
                    city=geo["name"],
                    weather=weather,
                    unit=unit,
                    russian=russian,
                )
                action = "weather_forecast"

            else:
                answer, data = self._current_answer(
                    city=geo["name"],
                    weather=weather,
                    unit=unit,
                    russian=russian,
                    original_text=text,
                )
                action = "weather_current"

            self._save_current(
                city=geo["name"],
                weather=weather,
                unit=unit,
            )

            data["requested_city"] = city
            data["saved_city_used"] = (
                requested_city is None
            )

            return SkillResult(
                handled=True,
                answer=answer,
                confidence=0.99,
                action=action,
                data=data,
            )

        except Exception as error:
            print(
                "WeatherSkill error: "
                f"{type(error).__name__}: {error}"
            )

            return SkillResult(
                handled=True,
                answer=(
                    "Не удалось получить погоду. "
                    "Проверьте подключение к интернету."
                    if russian
                    else
                    "I couldn't get the weather. "
                    "Please check the internet connection."
                ),
                confidence=0.99,
                action="weather_error",
                data={
                    "city": city,
                    "error": str(error),
                },
            )

    @staticmethod
    def _normalize(
        message: str,
    ) -> str:
        text = str(message).strip().lower()
        text = text.replace("’", "'")
        text = re.sub(
            r"[^a-z0-9а-яё,'\s.-]+",
            " ",
            text,
        )
        return " ".join(text.split())

    @staticmethod
    def _is_russian(
        text: str,
    ) -> bool:
        return bool(
            re.search(
                r"[а-яё]",
                text,
                re.IGNORECASE,
            )
        )

    @staticmethod
    def _open_weather(
        context: Any,
    ) -> bool:
        if context is None:
            return False

        method = getattr(
            context,
            "open_screen",
            None,
        )

        if callable(method):
            try:
                return bool(
                    method("weather")
                )
            except Exception as error:
                print(
                    "WeatherSkill open error: "
                    f"{type(error).__name__}: {error}"
                )

        return False

    @staticmethod
    def _normalize_city_name(
        city: str,
    ) -> str:
        """
        Remove conversational filler without maintaining
        a database of city names.
        """
        value = str(city).strip(" .?!,")

        value = re.sub(
            r"^(?:the\s+)?city\s+of\s+",
            "",
            value,
            flags=re.IGNORECASE,
        )

        value = re.sub(
            r"^(?:в\s+)?(?:город|городе|города|городу|г\.?)\s+",
            "",
            value,
            flags=re.IGNORECASE,
        )

        value = re.sub(
            r"^(?:in|near|around)\s+",
            "",
            value,
            flags=re.IGNORECASE,
        )

        value = re.sub(
            r"\s+",
            " ",
            value,
        ).strip(" .?!,")

        return value

    @staticmethod
    def _russian_base_candidates(
        city: str,
    ) -> list[str]:
        """
        Generate likely nominative city forms from common
        Russian locative/accusative endings.

        This is intentionally generic. It does not contain
        a city-name database.
        """
        value = str(city).strip()
        lowered = value.lower()

        candidates = [value]

        transformations = (
            ("ске", "ск"),
            ("цке", "цк"),
            ("оке", "ок"),
            ("еке", "ек"),
            ("ике", "ик"),
            ("ыке", "ык"),
            ("аке", "ак"),
            ("уке", "ук"),
            ("жске", "жск"),
            ("чске", "чск"),
            ("нске", "нск"),
            ("рске", "рск"),
            ("льске", "льск"),
            ("бурге", "бург"),
            ("граде", "град"),
            ("поле", "поль"),
            ("ове", "ов"),
            ("еве", "ев"),
            ("ёве", "ёв"),
            ("ине", "ин"),
            ("ыне", "ын"),
            ("оне", "он"),
            ("ене", "ен"),
            ("ане", "ан"),
            ("уне", "ун"),
            ("аре", "ар"),
            ("оре", "ор"),
            ("ире", "ир"),
            ("уре", "ур"),
            ("аже", "аж"),
            ("иже", "иж"),
            ("еже", "еж"),
            ("оже", "ож"),
            ("яже", "яж"),
            ("че", "ч"),
            ("ше", "ш"),
            ("ще", "щ"),
            ("же", "ж"),
            ("це", "ц"),
            ("ке", "ка"),
            ("ге", "га"),
            ("хе", "ха"),
            ("ве", "ва"),
            ("зе", "за"),
            ("те", "т"),
            ("де", "д"),
            ("ле", "л"),
            ("ме", "м"),
            ("не", "н"),
            ("пе", "п"),
            ("ре", "р"),
            ("се", "с"),
            ("фе", "ф"),
            ("бе", "б"),
            ("е", ""),
            ("у", "а"),
            ("ой", "а"),
            ("ом", ""),
        )

        for suffix, replacement in transformations:
            if not lowered.endswith(suffix):
                continue

            stem = value[:-len(suffix)]
            candidate = stem + replacement

            if len(candidate) >= 3:
                candidates.append(candidate)

        # Special grammar pattern used by feminine names ending in -ва:
        # Москве -> Москва, Литве -> Литва.
        if lowered.endswith("ве") and len(value) > 3:
            candidates.append(
                value[:-2] + "ва"
            )

        unique = []

        for candidate in candidates:
            cleaned = candidate.strip(" .?!,")

            if (
                cleaned
                and cleaned.lower()
                not in {
                    item.lower()
                    for item in unique
                }
            ):
                unique.append(cleaned)

        return unique

    @staticmethod
    def _city_candidates(
        city: str,
    ) -> list[str]:
        normalized = WeatherSkill._normalize_city_name(
            city
        )

        if not normalized:
            return []

        if "," in normalized:
            city_part, country_part = normalized.split(
                ",",
                1,
            )
            country_part = country_part.strip()

            base_candidates = (
                WeatherSkill._russian_base_candidates(
                    city_part.strip()
                )
            )

            combined = []

            for candidate in base_candidates:
                combined.append(candidate)

                if country_part:
                    combined.append(
                        f"{candidate}, {country_part}"
                    )

            return combined

        return WeatherSkill._russian_base_candidates(
            normalized
        )

    @staticmethod
    def _extract_city(
        text: str,
    ) -> str | None:
        patterns = (
            r"\bweather\s+in\s+(.+)$",
            r"\bforecast\s+for\s+(.+)$",
            r"\btemperature\s+in\s+(.+)$",
            r"\bweather\s+for\s+(.+)$",
            r"\bпогода\s+в\s+(?:городе\s+|город\s+)?(.+)$",
            r"\bпогода\s+(?:в\s+)?(?:городе\s+|город\s+)?([а-яё][а-яё\s,-]+)$",
            r"\bпрогноз\s+для\s+(.+)$",
            r"\bтемпература\s+в\s+(?:городе\s+|город\s+)?(.+)$",
        )

        for pattern in patterns:
            match = re.search(
                pattern,
                text,
                re.IGNORECASE,
            )

            if not match:
                continue

            city = match.group(1).strip(
                " .?!,"
            )

            city = re.sub(
                r"\b(today|tomorrow|сегодня|завтра)$",
                "",
                city,
                flags=re.IGNORECASE,
            ).strip(" .?!,")

            if city:
                return WeatherSkill._normalize_city_name(
                    city
                )

        return None

    @staticmethod
    def _geocode_city(
        city: str,
    ) -> dict | None:
        """
        Geocode a requested city while respecting optional state/country hints.

        Examples:
            Newport
            Newport, RI
            Newport, RI, USA
            Moscow, Russia

        Open-Meteo can return several cities with the same name. We search by
        the city name and then rank results against the supplied region/country
        hints instead of blindly accepting results[0].
        """
        requested = WeatherSkill._normalize_city_name(city)

        if not requested:
            return None

        parts = [
            part.strip()
            for part in requested.split(",")
            if part.strip()
        ]

        city_name = parts[0]
        region_hint = parts[1] if len(parts) >= 2 else ""
        country_hint = parts[2] if len(parts) >= 3 else ""

        US_STATES = {
            "AL": "ALABAMA", "AK": "ALASKA", "AZ": "ARIZONA",
            "AR": "ARKANSAS", "CA": "CALIFORNIA", "CO": "COLORADO",
            "CT": "CONNECTICUT", "DE": "DELAWARE", "FL": "FLORIDA",
            "GA": "GEORGIA", "HI": "HAWAII", "ID": "IDAHO",
            "IL": "ILLINOIS", "IN": "INDIANA", "IA": "IOWA",
            "KS": "KANSAS", "KY": "KENTUCKY", "LA": "LOUISIANA",
            "ME": "MAINE", "MD": "MARYLAND", "MA": "MASSACHUSETTS",
            "MI": "MICHIGAN", "MN": "MINNESOTA", "MS": "MISSISSIPPI",
            "MO": "MISSOURI", "MT": "MONTANA", "NE": "NEBRASKA",
            "NV": "NEVADA", "NH": "NEW HAMPSHIRE", "NJ": "NEW JERSEY",
            "NM": "NEW MEXICO", "NY": "NEW YORK",
            "NC": "NORTH CAROLINA", "ND": "NORTH DAKOTA",
            "OH": "OHIO", "OK": "OKLAHOMA", "OR": "OREGON",
            "PA": "PENNSYLVANIA", "RI": "RHODE ISLAND",
            "SC": "SOUTH CAROLINA", "SD": "SOUTH DAKOTA",
            "TN": "TENNESSEE", "TX": "TEXAS", "UT": "UTAH",
            "VT": "VERMONT", "VA": "VIRGINIA", "WA": "WASHINGTON",
            "WV": "WEST VIRGINIA", "WI": "WISCONSIN", "WY": "WYOMING",
        }

        COUNTRY_ALIASES = {
            "US": "US",
            "USA": "US",
            "UNITED STATES": "US",
            "UNITED STATES OF AMERICA": "US",
            "UK": "GB",
            "UNITED KINGDOM": "GB",
            "GREAT BRITAIN": "GB",
        }

        region_upper = region_hint.upper()
        country_upper = country_hint.upper()

        # A US state abbreviation itself implies United States.
        expected_state = US_STATES.get(
            region_upper,
            region_upper,
        )

        expected_country_code = COUNTRY_ALIASES.get(
            country_upper,
            "",
        )

        if region_upper in US_STATES and not expected_country_code:
            expected_country_code = "US"

        # For "City, Country" requests where the second component is not a
        # US state, treat it as a country hint as well as a possible region.
        second_part_country_code = COUNTRY_ALIASES.get(
            region_upper,
            "",
        )

        if second_part_country_code and not expected_country_code:
            expected_country_code = second_part_country_code
            expected_state = ""

        query = urllib.parse.quote(city_name)

        url = (
            "https://geocoding-api.open-meteo.com/v1/search"
            f"?name={query}"
            "&count=30"
            "&language=en"
            "&format=json"
        )

        try:
            with urllib.request.urlopen(
                url,
                timeout=10,
                context=SSL_CONTEXT,
            ) as response:
                data = json.loads(
                    response.read().decode("utf-8")
                )
        except Exception as error:
            print(
                "WeatherSkill geocoding error: "
                f"{type(error).__name__}: {error}"
            )
            return None

        results = data.get("results", [])

        if not results:
            return None

        def score(item):
            value = 0

            item_name = str(
                item.get("name", "")
            ).strip().upper()

            admin1 = str(
                item.get("admin1", "")
            ).strip().upper()

            country = str(
                item.get("country", "")
            ).strip().upper()

            country_code = str(
                item.get("country_code", "")
            ).strip().upper()

            if item_name == city_name.upper():
                value += 20

            if expected_state:
                if admin1 == expected_state:
                    value += 100
                elif expected_state in admin1:
                    value += 60

            if region_hint and not expected_state:
                hint = region_hint.upper()
                if admin1 == hint:
                    value += 70
                if country == hint:
                    value += 80
                if country_code == hint:
                    value += 80

            if expected_country_code:
                if country_code == expected_country_code:
                    value += 100
                else:
                    value -= 100

            # Prefer more populated exact matches when geographic hints tie.
            try:
                population = int(item.get("population", 0) or 0)
                value += min(population // 100000, 10)
            except Exception:
                pass

            return value

        selected = max(
            results,
            key=score,
        )

        # If explicit geographic hints were supplied, do not silently use a
        # conflicting city just because its name matches.
        selected_admin1 = str(
            selected.get("admin1", "")
        ).strip().upper()

        selected_country_code = str(
            selected.get("country_code", "")
        ).strip().upper()

        if expected_state and selected_admin1 != expected_state:
            return None

        if (
            expected_country_code
            and selected_country_code != expected_country_code
        ):
            return None

        name_parts = [
            str(
                selected.get(
                    "name",
                    city_name,
                )
            ).strip(),
            str(
                selected.get(
                    "admin1",
                    "",
                )
            ).strip(),
        ]

        if selected_country_code and selected_country_code != "US":
            name_parts.append(selected_country_code)

        name = ", ".join(
            part
            for part in name_parts
            if part
        )

        return {
            "name": name,
            "latitude": selected["latitude"],
            "longitude": selected["longitude"],
            "matched_query": requested,
            "country_code": selected_country_code,
        }

    @staticmethod
    def _get_weather_data(
        latitude: float,
        longitude: float,
        unit: str,
    ) -> dict:
        temperature_unit = (
            "fahrenheit"
            if unit == "F"
            else "celsius"
        )

        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={latitude}"
            f"&longitude={longitude}"
            "&current="
            "temperature_2m,"
            "apparent_temperature,"
            "relative_humidity_2m,"
            "weather_code,"
            "wind_speed_10m"
            "&daily="
            "weather_code,"
            "temperature_2m_max,"
            "temperature_2m_min,"
            "precipitation_probability_max"
            f"&temperature_unit={temperature_unit}"
            "&wind_speed_unit=mph"
            "&forecast_days=7"
            "&timezone=auto"
        )

        with urllib.request.urlopen(
            url,
            timeout=15,
            context=SSL_CONTEXT,
        ) as response:
            return json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

    def _current_answer(
        self,
        city: str,
        weather: dict,
        unit: str,
        russian: bool,
        original_text: str,
    ) -> tuple[str, dict]:
        current = weather.get(
            "current",
            {},
        )

        temperature = round(
            current.get(
                "temperature_2m",
                0,
            )
        )

        feels_like = round(
            current.get(
                "apparent_temperature",
                temperature,
            )
        )

        humidity = current.get(
            "relative_humidity_2m",
            "--",
        )

        wind = round(
            current.get(
                "wind_speed_10m",
                0,
            )
        )

        code = int(
            current.get(
                "weather_code",
                -1,
            )
        )

        condition = (
            WEATHER_CODES_RU.get(
                code,
                "неизвестные погодные условия",
            )
            if russian
            else WEATHER_CODES.get(
                code,
                "Unknown conditions",
            )
        )

        daily = weather.get(
            "daily",
            {},
        )

        rain_values = daily.get(
            "precipitation_probability_max",
            [],
        )

        rain_chance = (
            rain_values[0]
            if rain_values
            else "--"
        )

        if (
            "rain" in original_text
            or "umbrella" in original_text
            or "дожд" in original_text
            or "зонт" in original_text
        ):
            if russian:
                answer = (
                    f"Вероятность осадков сегодня в {city}: "
                    f"{rain_chance} процентов. "
                    f"Сейчас {condition.lower()}, "
                    f"{temperature} градусов {unit}."
                )
            else:
                answer = (
                    f"The chance of precipitation today in {city} "
                    f"is {rain_chance} percent. "
                    f"It is currently {condition.lower()}, "
                    f"{temperature} degrees {unit}."
                )
        elif russian:
            answer = (
                f"Сейчас в {city}: {condition.lower()}, "
                f"{temperature} градусов {unit}. "
                f"Ощущается как {feels_like}. "
                f"Влажность {humidity} процентов, "
                f"ветер {wind} миль в час."
            )
        else:
            answer = (
                f"Current weather in {city}: "
                f"{condition.lower()}, "
                f"{temperature} degrees {unit}. "
                f"It feels like {feels_like}. "
                f"Humidity is {humidity} percent "
                f"and wind is {wind} miles per hour."
            )

        return answer, {
            "city": city,
            "temperature": temperature,
            "feels_like": feels_like,
            "unit": unit,
            "condition": condition,
            "humidity": humidity,
            "wind_mph": wind,
            "precipitation_probability": (
                rain_chance
            ),
        }

    def _tomorrow_answer(
        self,
        city: str,
        weather: dict,
        unit: str,
        russian: bool,
    ) -> tuple[str, dict]:
        daily = weather.get(
            "daily",
            {},
        )

        dates = daily.get(
            "time",
            [],
        )
        maximums = daily.get(
            "temperature_2m_max",
            [],
        )
        minimums = daily.get(
            "temperature_2m_min",
            [],
        )
        codes = daily.get(
            "weather_code",
            [],
        )
        rain = daily.get(
            "precipitation_probability_max",
            [],
        )

        index = 1

        if (
            len(dates) <= index
            or len(maximums) <= index
            or len(minimums) <= index
            or len(codes) <= index
        ):
            raise RuntimeError(
                "Tomorrow forecast is unavailable."
            )

        forecast_date_text = str(
            dates[index]
        ).strip()

        try:
            forecast_date = datetime.strptime(
                forecast_date_text,
                "%Y-%m-%d",
            )

            english_date = (
                f"{forecast_date.strftime('%A, %B')} "
                f"{forecast_date.day}, "
                f"{forecast_date.year}"
            )

            russian_date = (
                f"{forecast_date.day:02d}."
                f"{forecast_date.month:02d}."
                f"{forecast_date.year}"
            )

        except ValueError:
            english_date = forecast_date_text
            russian_date = forecast_date_text

        high = round(maximums[index])
        low = round(minimums[index])
        condition_code = int(codes[index])

        condition = (
            WEATHER_CODES_RU.get(
                condition_code,
                "неизвестные погодные условия",
            )
            if russian
            else WEATHER_CODES.get(
                condition_code,
                "Unknown conditions",
            )
        )

        rain_chance = (
            rain[index]
            if len(rain) > index
            else "--"
        )

        if russian:
            answer = (
                f"Завтра, {russian_date}, в {city}: "
                f"{condition.lower()}. "
                f"Максимум {high} градусов {unit}, "
                f"минимум {low}. "
                f"Вероятность осадков "
                f"{rain_chance} процентов."
            )
        else:
            answer = (
                f"Tomorrow, {english_date}, in {city}: "
                f"{condition.lower()}. "
                f"The high will be {high} degrees {unit}, "
                f"the low {low}, "
                f"with a {rain_chance} percent chance "
                f"of precipitation."
            )

        return answer, {
            "city": city,
            "date": forecast_date_text,
            "high": high,
            "low": low,
            "unit": unit,
            "condition": condition,
            "precipitation_probability": (
                rain_chance
            ),
        }

    def _forecast_answer(
        self,
        city: str,
        weather: dict,
        unit: str,
        russian: bool,
    ) -> tuple[str, dict]:
        daily = weather.get(
            "daily",
            {},
        )

        dates = daily.get("time", [])
        maximums = daily.get(
            "temperature_2m_max",
            [],
        )
        minimums = daily.get(
            "temperature_2m_min",
            [],
        )
        codes = daily.get(
            "weather_code",
            [],
        )
        rain = daily.get(
            "precipitation_probability_max",
            [],
        )

        count = min(
            5,
            len(dates),
            len(maximums),
            len(minimums),
            len(codes),
        )

        if count == 0:
            raise RuntimeError(
                "Forecast is unavailable."
            )

        lines = []
        items = []

        for index in range(count):
            condition_code = int(codes[index])
            condition = (
                WEATHER_CODES_RU.get(
                    condition_code,
                    "неизвестные погодные условия",
                )
                if russian
                else WEATHER_CODES.get(
                    condition_code,
                    "Unknown conditions",
                )
            )
            high = round(maximums[index])
            low = round(minimums[index])
            rain_chance = (
                rain[index]
                if len(rain) > index
                else "--"
            )

            if russian:
                label = (
                    "Сегодня"
                    if index == 0
                    else "Завтра"
                    if index == 1
                    else dates[index]
                )

                lines.append(
                    f"{label}: {condition}, "
                    f"максимум {high}, минимум {low}, "
                    f"осадки {rain_chance}%."
                )
            else:
                label = (
                    "Today"
                    if index == 0
                    else "Tomorrow"
                    if index == 1
                    else dates[index]
                )

                lines.append(
                    f"{label}: {condition}, "
                    f"high {high}, low {low}, "
                    f"precipitation {rain_chance}%."
                )

            items.append(
                {
                    "date": dates[index],
                    "condition": condition,
                    "high": high,
                    "low": low,
                    "unit": unit,
                    "precipitation_probability": (
                        rain_chance
                    ),
                }
            )

        if russian:
            answer = (
                f"Прогноз для {city} на пять дней:\n"
                + "\n".join(
                    f"{index}. {line}"
                    for index, line in enumerate(
                        lines,
                        start=1,
                    )
                )
            )
        else:
            answer = (
                f"Five-day forecast for {city}:\n"
                + "\n".join(
                    f"{index}. {line}"
                    for index, line in enumerate(
                        lines,
                        start=1,
                    )
                )
            )

        return answer, {
            "city": city,
            "unit": unit,
            "days": items,
        }

    def _save_current(
        self,
        city: str,
        weather: dict,
        unit: str,
    ) -> None:
        current = weather.get(
            "current",
            {},
        )

        temperature = round(
            current.get(
                "temperature_2m",
                0,
            )
        )

        humidity = current.get(
            "relative_humidity_2m",
            "--",
        )

        wind = round(
            current.get(
                "wind_speed_10m",
                0,
            )
        )

        code = int(
            current.get(
                "weather_code",
                -1,
            )
        )

        condition = WEATHER_CODES.get(
            code,
            "Unknown conditions",
        )

        try:
            self.config.set(
                "city",
                city,
            )
            self.config.set(
                "temperature_unit",
                unit,
            )
            self.config.set(
                "last_temperature",
                temperature,
            )
            self.config.set(
                "last_condition",
                condition,
            )
            self.config.set(
                "last_humidity",
                humidity,
            )
            self.config.set(
                "last_wind",
                wind,
            )
        except Exception as error:
            print(
                "WeatherSkill config save error: "
                f"{type(error).__name__}: {error}"
            )