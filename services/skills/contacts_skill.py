import re

from services.contacts_service import ContactsService
from services.skills.base_skill import BaseSkill, SkillResult


class ContactsSkill(BaseSkill):
    name = "contacts"
    priority = 35

    CONTACT_WORDS = (
        "contact",
        "contacts",
        "phone number",
        "phone",
        "telephone",
        "email",
        "e-mail",
        "address book",
        "контакт",
        "контакты",
        "телефон",
        "номер телефона",
        "почта",
        "email",
    )

    def can_handle(self, message, context):
        text = str(message or "").strip().lower()

        if not text:
            return 0.0

        if any(word in text for word in self.CONTACT_WORDS):
            return 0.98

        if re.search(
            r"\b(find|show|look up)\b.+\b(name|person)\b",
            text,
        ):
            return 0.78

        return 0.0

    @staticmethod
    def _extract_name(message):
        text = str(message or "").strip()

        patterns = (
            (
                r"(?i)^\s*(?:find|show|open|look\s+up)\s+"
                r"(?:me\s+)?(?:the\s+)?(?:contact\s+)?"
                r"(?:for\s+)?(.+?)\s*[?.!]?\s*$"
            ),
            (
                r"(?i)^\s*what(?:'s|\s+is)\s+"
                r"(.+?)(?:'s|\s+)\s+"
                r"(?:phone(?:\s+number)?|telephone|email|e-mail)"
                r"\s*[?.!]?\s*$"
            ),
            (
                r"(?i)^\s*(?:phone(?:\s+number)?|telephone|email|e-mail)"
                r"\s+(?:for|of)\s+(.+?)\s*[?.!]?\s*$"
            ),
            (
                r"(?i)^\s*(?:contact|contacts)\s+"
                r"(?:for\s+)?(.+?)\s*[?.!]?\s*$"
            ),
            (
                r"(?i)^\s*(?:найди|покажи)\s+"
                r"(?:контакт\s+)?(.+?)\s*[?.!]?\s*$"
            ),
            (
                r"(?i)^\s*(?:телефон|номер\s+телефона|почта|email)"
                r"\s+(?:для\s+|у\s+)?(.+?)\s*[?.!]?\s*$"
            ),
            (
                r"(?i)^\s*какой\s+(?:телефон|номер\s+телефона|email|почта)"
                r"\s+(?:у\s+)?(.+?)\s*[?.!]?\s*$"
            ),
        )

        for pattern in patterns:
            match = re.match(pattern, text)

            if match:
                value = match.group(1).strip(" ?.,!:'\"")

                if value:
                    return value

        cleaned = text

        replacements = (
            "look up",
            "phone number",
            "address book",
            "telephone",
            "contacts",
            "contact",
            "e-mail",
            "email",
            "phone",
            "what is",
            "what's",
            "find",
            "show",
            "open",
            "for",
            "of",
            "please",
            "my",
            "номер телефона",
            "контакты",
            "контакт",
            "телефон",
            "почта",
            "найди",
            "покажи",
            "какой",
            "для",
        )

        for word in replacements:
            cleaned = re.sub(
                rf"(?i)\b{re.escape(word)}\b",
                " ",
                cleaned,
            )

        cleaned = re.sub(
            r"\s+",
            " ",
            cleaned,
        ).strip(" ?.,!:'\"")

        return cleaned

    @staticmethod
    def _wants_email(message):
        text = str(message or "").lower()

        return (
            "email" in text
            or "e-mail" in text
            or "почт" in text
        )

    @staticmethod
    def _wants_phone(message):
        text = str(message or "").lower()

        return (
            "phone" in text
            or "telephone" in text
            or "телефон" in text
            or "номер" in text
        )

    @staticmethod
    def _format_contact(
        contact,
        want_phone=False,
        want_email=False,
    ):
        name = contact.get("name", "Unknown")
        phones = contact.get("phones", [])
        emails = contact.get("emails", [])

        parts = [name]

        if want_phone:
            if phones:
                parts.append(
                    "Phone: " + ", ".join(phones)
                )
            else:
                parts.append("No phone number saved.")

        elif want_email:
            if emails:
                parts.append(
                    "Email: " + ", ".join(emails)
                )
            else:
                parts.append("No email address saved.")

        else:
            if phones:
                parts.append(
                    "Phone: " + ", ".join(phones)
                )

            if emails:
                parts.append(
                    "Email: " + ", ".join(emails)
                )

            if not phones and not emails:
                parts.append(
                    "No phone number or email saved."
                )

        return "\n".join(parts)

    def handle(self, message, context):
        name = self._extract_name(message)

        if not name:
            return SkillResult(
                handled=True,
                answer=(
                    "Tell me the contact name "
                    "you want to find."
                ),
                confidence=1.0,
                action="contacts_search",
            )

        result = ContactsService.search(
            name,
            limit=8,
        )

        if result.get("permission_required"):
            return SkillResult(
                handled=True,
                answer=(
                    "M12 needs Contacts permission. "
                    "Allow Contacts in the Android permission popup, "
                    "then ask me for the contact again."
                ),
                confidence=1.0,
                action="contacts_permission",
            )

        if not result.get("ok"):
            return SkillResult(
                handled=True,
                answer=(
                    "I could not read the phone contacts. "
                    + str(result.get("error", ""))
                ).strip(),
                confidence=1.0,
                action="contacts_error",
                data=result,
            )

        contacts = result.get("contacts", [])

        if not contacts:
            return SkillResult(
                handled=True,
                answer=(
                    f"I couldn't find {name} "
                    "in your phone contacts."
                ),
                confidence=1.0,
                action="contacts_search",
                data={
                    "query": name,
                    "contacts": [],
                },
            )

        want_phone = self._wants_phone(message)
        want_email = self._wants_email(message)

        if len(contacts) == 1:
            answer = self._format_contact(
                contacts[0],
                want_phone=want_phone,
                want_email=want_email,
            )

        else:
            lines = [
                (
                    f"I found {len(contacts)} contacts "
                    f"matching {name}:"
                )
            ]

            for contact in contacts[:8]:
                lines.append(
                    self._format_contact(
                        contact,
                        want_phone=want_phone,
                        want_email=want_email,
                    )
                )

            answer = "\n\n".join(lines)

        return SkillResult(
            handled=True,
            answer=answer,
            confidence=1.0,
            action="contacts_search",
            data={
                "query": name,
                "contacts": contacts,
            },
        )