import html
import json
import re
import ssl
import urllib.parse
import urllib.request
from typing import Any

import certifi

from services.skills.base_skill import BaseSkill, SkillResult


SSL_CONTEXT = ssl.create_default_context(
    cafile=certifi.where()
)


class ImageSkill(BaseSkill):
    """
    Wikimedia Commons image search with short conversational memory.

    Supports:
        Show me a picture of Yuri Gagarin
        Yuri Gagarin pictures
        More pictures
        Another picture
        More detailed picture
        That is not Yuri Gagarin

        Покажи фото Гагарина
        Ещё фотографии
        Другая фотография
    """

    name = "image"
    priority = 14

    COMMONS_API = (
        "https://commons.wikimedia.org/w/api.php"
    )

    IMAGE_WORDS = {
        "picture",
        "pictures",
        "image",
        "images",
        "photo",
        "photos",
        "photograph",
        "photographs",
        "фото",
        "фотография",
        "фотографии",
        "фотографию",
        "картинка",
        "картинки",
        "картинку",
        "изображение",
        "изображения",
    }

    ACTION_WORDS = {
        "show",
        "find",
        "display",
        "get",
        "see",
        "покажи",
        "найди",
        "показать",
        "найти",
    }

    FOLLOW_UP_PHRASES = {
        "more pictures",
        "more images",
        "more photos",
        "show more pictures",
        "show more images",
        "show more photos",
        "another picture",
        "another image",
        "another photo",
        "next picture",
        "next image",
        "next photo",
        "more detailed picture",
        "more detailed image",
        "more detailed photo",
        "higher resolution picture",
        "higher resolution image",
        "higher resolution photo",
        "еще фото",
        "ещё фото",
        "еще фотографии",
        "ещё фотографии",
        "другая фотография",
        "другое фото",
        "следующее фото",
    }

    DETAIL_HINTS = {
        "detailed",
        "detail",
        "higher resolution",
        "high resolution",
        "high-res",
        "hi-res",
        "подробнее",
        "детальнее",
        "больше деталей",
    }

    def __init__(self):
        self.last_query = ""
        self.last_results = []
        self.next_index = 0

    def can_handle(
        self,
        message: str,
        context: Any,
    ) -> float:
        text = self._normalize(message)

        if not text:
            return 0.0

        if (
            self.last_query
            and self._is_follow_up(text)
        ):
            return 1.0

        words = set(text.split())

        if words.intersection(
            self.IMAGE_WORDS
        ):
            return 1.0

        # Examples: "Yuriy Gagarin pictures", "cats photos".
        if re.search(
            r"\b(?:pictures|images|photos|photographs)\s*$",
            text,
            re.IGNORECASE,
        ):
            return 1.0

        return 0.0

    def handle(
        self,
        message: str,
        context: Any,
    ) -> SkillResult:
        original = str(message).strip()
        normalized = self._normalize(
            original
        )
        russian = self._is_russian(
            original
        )

        follow_up = (
            bool(self.last_query)
            and self._is_follow_up(
                normalized
            )
        )

        detailed = self._is_detail_request(
            normalized
        )

        if follow_up:
            query = self.last_query
        else:
            query = self._extract_query(
                original
            )

        if not query:
            return SkillResult(
                handled=True,
                answer=(
                    "Какое изображение вы хотите увидеть?"
                    if russian
                    else "What picture would you like to see?"
                ),
                confidence=1.0,
            )

        try:
            if (
                not follow_up
                or query != self.last_query
                or not self.last_results
            ):
                self.last_results = (
                    self._search_commons(
                        query,
                        limit=20,
                    )
                )
                self.last_query = query
                self.next_index = 0

            if not self.last_results:
                return SkillResult(
                    handled=True,
                    answer=(
                        f"Я не нашёл подходящих изображений для: {query}."
                        if russian
                        else f"I could not find suitable images for: {query}."
                    ),
                    confidence=1.0,
                    data={
                        "type": "image_not_found",
                        "query": query,
                    },
                )

            # A "wrong picture" / "more pictures" follow-up advances
            # to the next group. First request starts at 0.
            if follow_up and self.next_index == 0:
                self.next_index = min(
                    4,
                    len(self.last_results),
                )

            batch = self._next_batch(
                count=4
            )

            if detailed:
                # Prefer original-resolution URLs for a detail request.
                detailed_batch = []
                for item in batch:
                    detailed_item = dict(item)
                    original_url = str(
                        detailed_item.get(
                            "original_url",
                            "",
                        )
                    ).strip()

                    if original_url:
                        detailed_item[
                            "image_url"
                        ] = original_url

                    detailed_batch.append(
                        detailed_item
                    )

                batch = detailed_batch

            if not batch:
                return SkillResult(
                    handled=True,
                    answer=(
                        f"Больше изображений для {query} не найдено."
                        if russian
                        else f"I do not have more images for {query}."
                    ),
                    confidence=1.0,
                )

            # Backward-compatible first image fields remain available.
            first = batch[0]

            answer = (
                f"Вот несколько изображений: {query}."
                if russian
                else f"Here are some images of {query}."
            )

            return SkillResult(
                handled=True,
                answer=answer,
                confidence=1.0,
                action="show_image_gallery",
                data={
                    "type": "image_gallery",
                    "query": query,
                    "images": batch,
                    "image_url": first.get(
                        "image_url",
                        "",
                    ),
                    "source_url": first.get(
                        "source_url",
                        "",
                    ),
                    "title": first.get(
                        "title",
                        query,
                    ),
                    "provider": (
                        "Wikimedia Commons"
                    ),
                },
            )

        except Exception as error:
            print(
                "ImageSkill search error: "
                f"{type(error).__name__}: {error}"
            )

            return SkillResult(
                handled=True,
                answer=(
                    "Не удалось загрузить изображения."
                    if russian
                    else "I could not load images."
                ),
                confidence=1.0,
                data={
                    "type": "image_error",
                    "query": query,
                    "error": (
                        f"{type(error).__name__}: "
                        f"{error}"
                    ),
                },
            )

    def _next_batch(
        self,
        count=4,
    ) -> list[dict]:
        if not self.last_results:
            return []

        if self.next_index >= len(
            self.last_results
        ):
            # Start again after reaching the end.
            self.next_index = 0

        start = self.next_index
        end = min(
            start + count,
            len(self.last_results),
        )

        batch = self.last_results[
            start:end
        ]

        self.next_index = end

        return list(batch)

    def _is_follow_up(
        self,
        text: str,
    ) -> bool:
        if text in self.FOLLOW_UP_PHRASES:
            return True

        if any(
            phrase in text
            for phrase in (
                "more picture",
                "more image",
                "more photo",
                "another picture",
                "another image",
                "another photo",
                "next picture",
                "next image",
                "next photo",
            )
        ):
            return True

        # "But it is not Yuri Gagarin" after an image result.
        if self.last_query:
            query_words = {
                word
                for word in self._normalize(
                    self.last_query
                ).split()
                if len(word) >= 3
            }

            if (
                any(
                    phrase in text
                    for phrase in (
                        "not ",
                        "wrong picture",
                        "wrong image",
                        "wrong photo",
                        "не ",
                        "не тот",
                        "не та",
                    )
                )
                and any(
                    word in text
                    for word in query_words
                )
            ):
                return True

        return False

    def _is_detail_request(
        self,
        text: str,
    ) -> bool:
        return any(
            hint in text
            for hint in self.DETAIL_HINTS
        )

    @staticmethod
    def _normalize(
        text: str,
    ) -> str:
        value = str(
            text
        ).strip().lower()

        value = re.sub(
            r"[^\w\sа-яё'-]+",
            " ",
            value,
            flags=re.IGNORECASE,
        )

        return " ".join(
            value.split()
        )

    @staticmethod
    def _is_russian(
        text: str,
    ) -> bool:
        return bool(
            re.search(
                r"[а-яё]",
                str(text),
                re.IGNORECASE,
            )
        )

    @staticmethod
    def _extract_query(
        message: str,
    ) -> str:
        text = str(
            message
        ).strip()

        patterns = (
            # English verb forms.
            r"^\s*(?:please\s+)?show\s+me\s+(?:a|an|the)?\s*"
            r"(?:picture|pictures|image|images|photo|photos|photograph|photographs)"
            r"\s+(?:of\s+)?(.+?)\s*$",

            r"^\s*(?:please\s+)?show\s+(?:a|an|the)?\s*"
            r"(?:picture|pictures|image|images|photo|photos|photograph|photographs)"
            r"\s+(?:of\s+)?(.+?)\s*$",

            r"^\s*(?:please\s+)?find\s+(?:me\s+)?(?:a|an|the)?\s*"
            r"(?:picture|pictures|image|images|photo|photos|photograph|photographs)"
            r"\s+(?:of\s+)?(.+?)\s*$",

            # "Yuriy Gagarin pictures"
            r"^\s*(.+?)\s+"
            r"(?:picture|pictures|image|images|photo|photos|photograph|photographs)"
            r"\s*$",

            # "picture of Yuri Gagarin"
            r"^\s*(?:picture|pictures|image|images|photo|photos|photograph|photographs)"
            r"\s+of\s+(.+?)\s*$",

            # Russian.
            r"^\s*(?:пожалуйста[,\s]+)?покажи\s+(?:мне\s+)?"
            r"(?:фото|фотографию|фотографии|картинку|картинки|изображение|изображения)"
            r"\s+(?:с\s+|с изображением\s+|где\s+)?(.+?)\s*$",

            r"^\s*(?:пожалуйста[,\s]+)?найди\s+(?:мне\s+)?"
            r"(?:фото|фотографию|фотографии|картинку|картинки|изображение|изображения)"
            r"\s+(?:с\s+|с изображением\s+)?(.+?)\s*$",
        )

        for pattern in patterns:
            match = re.match(
                pattern,
                text,
                re.IGNORECASE,
            )

            if match:
                query = match.group(1).strip(
                    " .?!,;:"
                )

                if query:
                    return query

        query = re.sub(
            (
                r"\b(?:show|find|display|get|see|me|please|of|"
                r"picture|pictures|image|images|photo|photos|"
                r"photograph|photographs|"
                r"покажи|найди|показать|найти|мне|пожалуйста|"
                r"фото|фотография|фотографии|фотографию|"
                r"картинка|картинки|картинку|"
                r"изображение|изображения)\b"
            ),
            " ",
            text,
            flags=re.IGNORECASE,
        )

        return " ".join(
            query.split()
        ).strip(
            " .?!,;:"
        )

    @classmethod
    def _search_commons(
        cls,
        query: str,
        limit=20,
    ) -> list[dict]:
        search_query = str(
            query
        ).strip()

        if not search_query:
            return []

        params = {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "generator": "search",
            "gsrsearch": search_query,
            "gsrnamespace": "6",
            "gsrlimit": str(
                max(
                    4,
                    min(
                        int(limit),
                        40,
                    ),
                )
            ),
            "gsrsort": "relevance",
            "prop": "imageinfo",
            "iiprop": (
                "url|mime|size|extmetadata"
            ),
            "iiurlwidth": "1200",
            "iiextmetadatalanguage": "en",
        }

        url = (
            cls.COMMONS_API
            + "?"
            + urllib.parse.urlencode(
                params
            )
        )

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "M12OS/0.5.3 "
                    "(image-skill; Wikimedia Commons client)"
                ),
                "Accept": "application/json",
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=15,
            context=SSL_CONTEXT,
        ) as response:
            payload = json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

        pages = (
            payload.get(
                "query",
                {},
            ).get(
                "pages",
                [],
            )
        )

        results = []
        seen_urls = set()

        for page in pages:
            imageinfo_list = page.get(
                "imageinfo",
                [],
            )

            if not imageinfo_list:
                continue

            info = imageinfo_list[0]

            mime = str(
                info.get(
                    "mime",
                    "",
                )
            ).strip().lower()

            if (
                mime
                and not mime.startswith(
                    "image/"
                )
            ):
                continue

            image_url = str(
                info.get(
                    "thumburl",
                    "",
                )
                or info.get(
                    "url",
                    "",
                )
            ).strip()

            original_url = str(
                info.get(
                    "url",
                    image_url,
                )
            ).strip()

            if not image_url.startswith(
                ("http://", "https://")
            ):
                continue

            if image_url in seen_urls:
                continue

            seen_urls.add(
                image_url
            )

            metadata = info.get(
                "extmetadata",
                {},
            )

            results.append(
                {
                    "title": str(
                        page.get(
                            "title",
                            "",
                        )
                    ).strip(),
                    "image_url": image_url,
                    "original_url": original_url,
                    "source_url": str(
                        info.get(
                            "descriptionurl",
                            "",
                        )
                    ).strip(),
                    "mime": mime,
                    "width": info.get(
                        "thumbwidth",
                        info.get(
                            "width",
                        ),
                    ),
                    "height": info.get(
                        "thumbheight",
                        info.get(
                            "height",
                        ),
                    ),
                    "license": cls._metadata_value(
                        metadata,
                        "LicenseShortName",
                    ),
                    "artist": cls._clean_metadata_html(
                        cls._metadata_value(
                            metadata,
                            "Artist",
                        )
                    ),
                    "credit": cls._clean_metadata_html(
                        cls._metadata_value(
                            metadata,
                            "Credit",
                        )
                    ),
                    "description": cls._clean_metadata_html(
                        cls._metadata_value(
                            metadata,
                            "ImageDescription",
                        )
                    ),
                    "provider": (
                        "Wikimedia Commons"
                    ),
                }
            )

        return results

    @staticmethod
    def _metadata_value(
        metadata: dict,
        key: str,
    ) -> str:
        item = metadata.get(
            key,
            {},
        )

        if isinstance(
            item,
            dict,
        ):
            return str(
                item.get(
                    "value",
                    "",
                )
            ).strip()

        return str(
            item or ""
        ).strip()

    @staticmethod
    def _clean_metadata_html(
        value: str,
    ) -> str:
        text = str(
            value or ""
        )

        text = re.sub(
            r"<[^>]+>",
            " ",
            text,
        )

        text = html.unescape(
            text
        )

        return " ".join(
            text.split()
        )