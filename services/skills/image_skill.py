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

    CONTEXT_REFERENCE_PHRASES = {
        "them",
        "their pictures",
        "their images",
        "their photos",
        "these people",
        "those people",
        "these persons",
        "those persons",
        "these presidents",
        "those presidents",
        "this presidents",
        "these men",
        "those men",
        "these women",
        "those women",
        "их фото",
        "их фотографии",
        "эти люди",
        "эти президенты",
        "этих президентов",
    }

    def __init__(self):
        self.last_query = ""
        self.last_results = []
        self.next_index = 0

        self.last_context_subjects = []

    def _is_context_reference_request(
        self,
        text: str,
    ) -> bool:
        if any(
            phrase in text
            for phrase in self.CONTEXT_REFERENCE_PHRASES
        ):
            return True

        return bool(
            re.search(
                r"\b(?:pictures|images|photos|photographs)\s+of\s+"
                r"(?:them|these|those|their|this)\b",
                text,
                re.IGNORECASE,
            )
        )

    @staticmethod
    def _extract_context_text(
        context: Any,
    ) -> str:
        """
        Return only the immediately previous assistant answer.

        Do not scan broad conversation/history data here: doing so can
        introduce unrelated names into contextual image requests.
        """
        if context is None:
            return ""

        router = getattr(
            context,
            "router",
            None,
        )

        if router is None and isinstance(context, dict):
            router = context.get("router")

        if router is None:
            return ""

        value = getattr(
            router,
            "last_assistant_answer",
            None,
        )

        if isinstance(value, str):
            return value.strip()

        return ""

    @classmethod
    def _extract_subjects_from_context(
        cls,
        context: Any,
    ) -> list[str]:
        text = cls._extract_context_text(
            context
        )

        if not text:
            return []

        cleaned = re.sub(
            r"\s+",
            " ",
            text,
        ).strip()

        candidates = []

        numeric = re.findall(
            (
                r"(?:^|[.;]\s*|,\s*)"
                r"\d{1,2}[.)]\s*"
                r"(.+?)"
                r"(?=(?:[.;]\s*|,\s*)\d{1,2}[.)]\s*|$)"
            ),
            cleaned,
            flags=re.IGNORECASE,
        )

        if len(numeric) >= 2:
            candidates = numeric

        if len(candidates) < 2:
            ordinal_words = (
                r"first|second|third|fourth|fifth|sixth|seventh|"
                r"eighth|ninth|tenth"
            )

            ordinal = re.findall(
                (
                    rf"(?:^|[.;]\s*)"
                    rf"(?:{ordinal_words})"
                    r"\s*[,.:)-]\s*"
                    r"(.+?)"
                    rf"(?=(?:[.;]\s*)(?:{ordinal_words})"
                    r"\s*[,.:)-]\s*|$)"
                ),
                cleaned,
                flags=re.IGNORECASE,
            )

            if len(ordinal) >= 2:
                candidates = ordinal

        if len(candidates) < 2:
            number_words = (
                r"one|two|three|four|five|six|seven|eight|nine|ten"
            )

            word_numbered = re.findall(
                (
                    rf"(?:^|[.;]\s*)"
                    rf"(?:{number_words})"
                    r"\s*[,.:)-]\s*"
                    r"(.+?)"
                    rf"(?=(?:[.;]\s*)(?:{number_words})"
                    r"\s*[,.:)-]\s*|$)"
                ),
                cleaned,
                flags=re.IGNORECASE,
            )

            if len(word_numbered) >= 2:
                candidates = word_numbered

        if len(candidates) < 2 and ";" in cleaned:
            candidates = cleaned.split(";")

        if len(candidates) < 2:
            comma_parts = [
                part.strip()
                for part in cleaned.split(",")
            ]

            if (
                2 <= len(comma_parts) <= 10
                and all(
                    1 <= len(part.split()) <= 5
                    for part in comma_parts
                )
            ):
                candidates = comma_parts

        subjects = []

        ordinal_prefix = re.compile(
            r"^\s*(?:"
            r"\d{1,2}[.)]|"
            r"first|second|third|fourth|fifth|sixth|seventh|"
            r"eighth|ninth|tenth|"
            r"one|two|three|four|five|six|seven|eight|nine|ten"
            r")\s*[,.:)-]?\s*",
            flags=re.IGNORECASE,
        )

        for item in candidates:
            item = ordinal_prefix.sub(
                "",
                str(item),
            ).strip(" .,:;-")

            item = re.sub(
                r"^(?:and\s+)?(?:then\s+)?",
                "",
                item,
                flags=re.IGNORECASE,
            ).strip()

            if ":" in item:
                left, right = item.split(
                    ":",
                    1,
                )
                if len(left.split()) > 3:
                    item = right.strip()

            words = item.split()

            if not (
                1 <= len(words) <= 5
            ):
                continue

            lowered = item.lower()

            if any(
                token in lowered
                for token in (
                    "http://",
                    "https://",
                    "here are",
                    "images of",
                    "pictures of",
                    "i can",
                    "let me",
                )
            ):
                continue

            subjects.append(
                item
            )

        unique = []
        seen = set()

        for item in subjects:
            key = item.casefold()

            if key not in seen:
                seen.add(key)
                unique.append(item)

        return unique[:8]

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

        if self._is_context_reference_request(text):
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

        context_reference = self._is_context_reference_request(
            normalized
        )

        if context_reference:
            subjects = self._extract_subjects_from_context(
                context
            )
        else:
            subjects = []

        if context_reference and subjects:
            self.last_context_subjects = subjects
            return self._handle_subject_gallery(
                subjects=subjects,
                russian=russian,
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
        russian: bool,
    ) -> SkillResult:
        images = []

        for subject in subjects:
            try:
                # Ask Wikimedia for a broader set, then select the best
                # subject-specific portrait locally instead of trusting
                # the first search result.
                results = self._search_commons(
                    subject,
                    limit=20,
                )
            except Exception:
                results = []

            if not results:
                continue

            best = self._pick_best_subject_image(
                subject,
                results,
            )

            if best is None:
                continue

            item = dict(best)
            item["subject"] = subject
            images.append(item)

        if not images:
            return SkillResult(
                handled=True,
                answer=(
                    "Не удалось найти подходящие изображения."
                    if russian
                    else "I could not find suitable images for those people."
                ),
                confidence=1.0,
            )

        first = images[0]
        query_label = ", ".join(subjects)

        self.last_query = query_label
        self.last_results = images
        self.next_index = len(images)

        return SkillResult(
            handled=True,
            answer=(
                "Вот изображения этих людей."
                if russian
                else "Here are images of those people."
            ),
            confidence=1.0,
            action="show_image_gallery",
            data={
                "type": "image_gallery",
                "query": query_label,
                "subjects": subjects,
                "images": images[:4],
                "image_url": first.get("image_url", ""),
                "source_url": first.get("source_url", ""),
                "title": first.get("title", query_label),
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
        Choose a portrait-like Commons result that actually matches
        the requested person/entity.

        This prevents broad search results such as group photos,
        presidential gatherings, or another president from being used
        just because Commons ranked them first.
        """
        subject_clean = cls._normalize(
            subject
        )

        subject_words = [
            word
            for word in subject_clean.split()
            if len(word) >= 3
        ]

        if not subject_words:
            return (
                results[0]
                if results
                else None
            )

        surname = subject_words[-1]

        reject_terms = {
            "group",
            "presidents",
            "presidential",
            "meeting",
            "conference",
            "summit",
            "inauguration",
            "family",
            "wives",
            "wife",
            "cabinet",
            "administration",
            "white house",
            "with president",
            "with presidents",
            "trump invited",
            "all presidents",
            "former presidents",
        }

        scored = []

        for index, item in enumerate(results):
            title = str(
                item.get(
                    "title",
                    "",
                )
            )
            description = str(
                item.get(
                    "description",
                    "",
                )
            )
            artist = str(
                item.get(
                    "artist",
                    "",
                )
            )

            searchable = cls._normalize(
                " ".join(
                    (
                        title,
                        description,
                        artist,
                    )
                )
            )

            if not searchable:
                continue

            # Require at least the surname. For common surnames this is
            # strengthened below by matching the full name tokens too.
            if surname not in searchable:
                continue

            score = 0

            # Exact full-name phrase is strongest.
            if subject_clean in searchable:
                score += 120

            matched_words = sum(
                1
                for word in subject_words
                if word in searchable
            )

            score += matched_words * 30

            # Prefer files whose title itself identifies the person.
            title_norm = cls._normalize(
                title
            )

            if subject_clean in title_norm:
                score += 100

            if surname in title_norm:
                score += 35

            # Portrait/headshot/profile clues.
            portrait_hints = (
                "portrait",
                "official portrait",
                "painting",
                "headshot",
                "photograph",
                "photo",
                "profile",
            )

            if any(
                hint in searchable
                for hint in portrait_hints
            ):
                score += 20

            # Reject or heavily penalize obvious group/event imagery.
            rejected = False
            for term in reject_terms:
                if term in searchable:
                    score -= 140
                    rejected = True

            width = item.get("width")
            height = item.get("height")

            try:
                width_value = float(width or 0)
                height_value = float(height or 0)

                # Vertical/square images are more likely to be portraits.
                if (
                    width_value > 0
                    and height_value > 0
                ):
                    ratio = (
                        height_value
                        / width_value
                    )

                    if ratio >= 1.0:
                        score += 20
                    elif ratio < 0.72:
                        score -= 25
            except Exception:
                pass

            # Commons relevance order is still useful as a small tie-breaker.
            score += max(
                0,
                20 - index,
            )

            scored.append(
                (
                    score,
                    rejected,
                    item,
                )
            )

        if not scored:
            return None

        scored.sort(
            key=lambda row: row[0],
            reverse=True,
        )

        best_score, rejected, best_item = (
            scored[0]
        )

        # Do not knowingly return a weak/unrelated result.
        if best_score < 55:
            return None

        return best_item

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