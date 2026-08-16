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
        original = str(message).strip()

        # Internal semantic-router protocol. This is not a user-language
        # phrase; it carries already-resolved image subjects from the AI.
        if original.startswith(
            "__M12_IMAGE_SUBJECTS__:"
        ):
            return 1.0

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

        # AI semantic routing resolves conversational references before the
        # request reaches ImageSkill. Multiple explicit subjects are carried
        # as JSON so this skill only performs image search/display work.
        if original.startswith(
            "__M12_IMAGE_SUBJECTS__:"
        ):
            raw_subjects = original.split(
                ":",
                1,
            )[1].strip()

            try:
                subjects = json.loads(
                    raw_subjects
                )
            except Exception:
                subjects = []

            if not isinstance(
                subjects,
                list,
            ):
                subjects = []

            subjects = [
                str(item).strip()
                for item in subjects
                if str(item).strip()
            ][:8]

            if not subjects:
                return SkillResult(
                    handled=True,
                    answer="I could not determine what images to show.",
                    confidence=1.0,
                )

            if len(subjects) > 1:
                return self._handle_subject_gallery(
                    subjects
                )

            # A single resolved subject keeps the original behavior: show a
            # gallery of several images for that one subject.
            original = (
                "show images of "
                + subjects[0]
            )

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

    def _handle_subject_gallery(
        self,
        subjects: list[str],
    ) -> SkillResult:
        """
        Return one strong image per explicit subject.

        Language understanding does not happen here. The subjects were already
        resolved by the AI semantic router from conversation context.
        """
        images = []

        for subject in subjects:
            try:
                results = self._search_commons(
                    subject + " portrait",
                    limit=30,
                )

                # Commons may rank a generic portrait search poorly for some
                # historical figures. Fall back to the exact full name.
                if not results:
                    results = self._search_commons(
                        subject,
                        limit=30,
                    )
            except Exception:
                results = []

            best = self._pick_best_subject_image(
                subject,
                results,
            )

            if best is None:
                continue

            item = dict(best)
            item["subject"] = subject
            images.append(item)

            if len(images) >= 4:
                break

        if not images:
            return SkillResult(
                handled=True,
                answer="I could not find suitable images for those subjects.",
                confidence=1.0,
            )

        first = images[0]
        query_label = ", ".join(
            subjects[:4]
        )

        self.last_query = query_label
        self.last_results = images
        self.next_index = len(images)

        return SkillResult(
            handled=True,
            answer="Here are the requested images.",
            confidence=1.0,
            action="show_image_gallery",
            data={
                "type": "image_gallery",
                "query": query_label,
                "subjects": subjects[:4],
                "images": images,
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
                    query_label,
                ),
                "provider": "Wikimedia Commons",
            },
        )

    @classmethod
    def _pick_best_subject_image(
        cls,
        subject: str,
        results: list[dict],
    ):
        """
        Choose one image that identifies the exact requested subject.

        For people, a metadata-only match is not strong enough because
        Commons descriptions/credits can mention several public figures.
        Prefer an exact full-name match in the Commons file title.

        Android/Kivy also behaves most reliably with JPEG and PNG thumbnails,
        so unsupported/less reliable formats are not selected for galleries.
        """
        subject_clean = cls._normalize(
            subject
        )

        subject_words = [
            word
            for word in subject_clean.split()
            if len(word) >= 2
        ]

        if not subject_words:
            return None

        safe_mimes = {
            "image/jpeg",
            "image/jpg",
            "image/png",
        }

        reject_terms = {
            "group",
            "meeting",
            "conference",
            "summit",
            "family",
            "cabinet",
            "administration",
            "presidents together",
            "former presidents",
            "all presidents",
        }

        exact_title_matches = []
        exact_metadata_matches = []

        for index, item in enumerate(results):
            mime = str(
                item.get(
                    "mime",
                    "",
                )
                or ""
            ).strip().lower()

            if mime and mime not in safe_mimes:
                continue

            image_url = str(
                item.get(
                    "image_url",
                    "",
                )
                or ""
            ).strip()

            if not image_url.startswith(
                ("http://", "https://")
            ):
                continue

            title_clean = cls._normalize(
                item.get(
                    "title",
                    "",
                )
            )

            searchable = cls._normalize(
                " ".join(
                    str(
                        item.get(key, "")
                        or ""
                    )
                    for key in (
                        "title",
                        "description",
                        "artist",
                        "credit",
                    )
                )
            )

            if not searchable:
                continue

            if any(
                term in searchable
                for term in reject_terms
            ):
                continue

            full_name_in_title = (
                subject_clean in title_clean
            )

            all_name_words_in_title = all(
                word in title_clean
                for word in subject_words
            )

            full_name_in_metadata = (
                subject_clean in searchable
            )

            if full_name_in_title:
                score = 300
            elif all_name_words_in_title:
                score = 240
            elif full_name_in_metadata:
                score = 120
            else:
                continue

            try:
                width = int(
                    item.get("width")
                    or 0
                )
                height = int(
                    item.get("height")
                    or 0
                )
            except Exception:
                width = 0
                height = 0

            if width > 0 and height > 0:
                ratio = (
                    float(height)
                    / float(width)
                )

                # Portrait or near-square images are more useful for people.
                if 0.85 <= ratio <= 2.2:
                    score += 30

                # Very small thumbnails are less desirable.
                if min(width, height) >= 500:
                    score += 15

            score += max(
                0,
                20 - index,
            )

            candidate = (
                score,
                item,
            )

            if (
                full_name_in_title
                or all_name_words_in_title
            ):
                exact_title_matches.append(
                    candidate
                )
            else:
                exact_metadata_matches.append(
                    candidate
                )

        pool = (
            exact_title_matches
            or exact_metadata_matches
        )

        if not pool:
            return None

        pool.sort(
            key=lambda row: row[0],
            reverse=True,
        )

        return pool[0][1]

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