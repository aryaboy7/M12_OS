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
        "telephone number",
        "email address",
        "e-mail address",
        "address book",
        "birthday",
        "company",
        "job title",
        "work address",
        "home address",
        "website",
        "nickname",
        "контакт",
        "контакты",
        "номер телефона",
        "телефон у",
        "почта",
        "день рождения",
        "адрес",
        "компания",
        "работает",
        "сайт",
        "email",
    )

    def can_handle(self, message, context):
        text = str(message or "").strip().lower()

        if not text:
            return 0.0

        if any(word in text for word in self.CONTACT_WORDS):
            return 0.98

        if re.search(
            r"\b(find|show|look up)\b.+\b(contact|contacts|person|контакт|контакты)\b",
            text,
        ):
            return 0.84

        if re.search(
            r"(?i)\b(найди|найти|покажи)\b.+\b(контакт|контакты|contact|contacts)\b",
            text,
        ):
            return 0.84

        return 0.0

    @staticmethod
    def _extract_name(message):
        text = str(message or "").strip()

        patterns = (
            # ---------------------------------------------------------
            # English commands
            #
            # Find contact Galina
            # Find контакт Галина
            # Show contact Alex Mazilo
            # Look up контакт Галина
            # ---------------------------------------------------------
            r"(?i)^\s*(?:find|show|open|look\s+up)\s+"
            r"(?:me\s+)?(?:the\s+)?"
            r"(?:(?:contact|contacts|контакт|контакты)\s+)?"
            r"(?:for\s+)?(.+?)\s*[?.!]?\s*$",

            # What's Galina's phone number?
            r"(?i)^\s*what(?:'s|\s+is)\s+(.+?)"
            r"(?:'s|\s+)\s+"
            r"(?:phone(?:\s+number)?|telephone(?:\s+number)?|"
            r"email(?:\s+address)?|e-mail(?:\s+address)?|birthday|"
            r"address|company|job\s+title|website|nickname)"
            r"\s*[?.!]?\s*$",

            # Phone number for Galina
            r"(?i)^\s*"
            r"(?:phone(?:\s+number)?|telephone(?:\s+number)?|"
            r"email(?:\s+address)?|e-mail(?:\s+address)?|birthday|"
            r"address|company|job\s+title|website|nickname)"
            r"\s+(?:for|of)\s+(.+?)\s*[?.!]?\s*$",

            # Contact Galina
            # Контакт Галина
            r"(?i)^\s*(?:contact|contacts|контакт|контакты)"
            r"\s+(?:for\s+)?(.+?)\s*[?.!]?\s*$",

            # ---------------------------------------------------------
            # Russian commands
            #
            # Найди контакт Галина
            # Найти контакт Галина
            # Найди contact Galina
            # Покажи контакт Галина
            # ---------------------------------------------------------
            r"(?i)^\s*(?:найди|найти|покажи)\s+"
            r"(?:(?:контакт|контакты|contact|contacts)\s+)?"
            r"(.+?)\s*[?.!]?\s*$",

            # Телефон Галина
            # Номер телефона у Галина
            # Почта Галина
            r"(?i)^\s*"
            r"(?:телефон|номер\s+телефона|почта|email|"
            r"адрес|день\s+рождения|компания|сайт)"
            r"\s+(?:для\s+|у\s+)?(.+?)\s*[?.!]?\s*$",

            # Какой телефон у Галина
            r"(?i)^\s*какой\s+"
            r"(?:телефон|номер\s+телефона|email|почта|адрес|сайт)"
            r"\s+(?:у\s+)?(.+?)\s*[?.!]?\s*$",

            # Когда день рождения у Галина
            r"(?i)^\s*когда\s+день\s+рождения\s+"
            r"(?:у\s+)?(.+?)\s*[?.!]?\s*$",
        )

        for pattern in patterns:
            match = re.match(pattern, text)

            if match:
                value = match.group(1).strip(" ?.,!:'\"")

                if value:
                    return value

        # -------------------------------------------------------------
        # Fallback cleanup
        #
        # If none of the patterns matched, remove known command words
        # and leave only the likely contact name.
        # -------------------------------------------------------------
        cleaned = text

        replacements = (
            "look up",
            "phone number",
            "telephone number",
            "email address",
            "e-mail address",
            "address book",
            "job title",
            "telephone",
            "contacts",
            "contact",
            "e-mail",
            "email",
            "birthday",
            "address",
            "company",
            "website",
            "nickname",
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
            "день рождения",
            "контакты",
            "контакт",
            "телефон",
            "почта",
            "адрес",
            "компания",
            "сайт",
            "найди",
            "найти",
            "покажи",
            "какой",
            "когда",
            "для",
        )

        for word in replacements:
            cleaned = re.sub(
                rf"(?i)\b{re.escape(word)}\b",
                " ",
                cleaned,
            )

        return re.sub(
            r"\s+",
            " ",
            cleaned,
        ).strip(" ?.,!:'\"")

    @staticmethod
    def _intent(message):
        text = str(message or "").lower()

        if (
            "phone" in text
            or "telephone" in text
            or "телефон" in text
            or "номер" in text
        ):
            return "phone"

        if (
            "email" in text
            or "e-mail" in text
            or "почт" in text
        ):
            return "email"

        if (
            "birthday" in text
            or "день рождения" in text
        ):
            return "birthday"

        if (
            "address" in text
            or "адрес" in text
        ):
            return "address"

        if (
            "company" in text
            or "компан" in text
            or "работает" in text
            or "job title" in text
        ):
            return "organization"

        if (
            "website" in text
            or "сайт" in text
        ):
            return "website"

        if "nickname" in text:
            return "nickname"

        return "all"

    @staticmethod
    def _phone_text(items):
        if not items:
            return "No phone number saved."

        values = []

        for item in items:
            if isinstance(item, dict):
                label = item.get("label") or item.get("type")
                number = item.get("number", "")

                values.append(
                    f"{label}: {number}"
                    if label
                    else number
                )
            else:
                values.append(str(item))

        return "Phone: " + ", ".join(values)

    @staticmethod
    def _email_text(items):
        if not items:
            return "No email address saved."

        values = []

        for item in items:
            if isinstance(item, dict):
                label = item.get("label") or item.get("type")
                address = item.get("address", "")

                values.append(
                    f"{label}: {address}"
                    if label
                    else address
                )
            else:
                values.append(str(item))

        return "Email: " + ", ".join(values)

    @classmethod
    def _format_contact(cls, contact, intent="all"):
        name = contact.get("name", "Unknown")
        parts = [name]

        if intent == "phone":
            parts.append(
                cls._phone_text(
                    contact.get("phones", [])
                )
            )
            return "\n".join(parts)

        if intent == "email":
            parts.append(
                cls._email_text(
                    contact.get("emails", [])
                )
            )
            return "\n".join(parts)

        if intent == "birthday":
            parts.append(
                "Birthday: "
                + contact.get(
                    "birthday",
                    "Not saved.",
                )
            )
            return "\n".join(parts)

        if intent == "address":
            addresses = contact.get(
                "addresses",
                [],
            )

            if addresses:
                for item in addresses:
                    if isinstance(item, dict):
                        value = (
                            item.get("formatted")
                            or ", ".join(
                                part
                                for part in (
                                    item.get("street"),
                                    item.get("city"),
                                    item.get("region"),
                                    item.get("postcode"),
                                    item.get("country"),
                                )
                                if part
                            )
                        )

                        if value:
                            parts.append(
                                "Address: " + value
                            )
            else:
                parts.append(
                    "No address saved."
                )

            return "\n".join(parts)

        if intent == "organization":
            org = contact.get(
                "organization",
                {},
            )

            if org:
                if org.get("company"):
                    parts.append(
                        "Company: "
                        + org["company"]
                    )

                if org.get("title"):
                    parts.append(
                        "Job title: "
                        + org["title"]
                    )

                if org.get("department"):
                    parts.append(
                        "Department: "
                        + org["department"]
                    )
            else:
                parts.append(
                    "No organization saved."
                )

            return "\n".join(parts)

        if intent == "website":
            websites = contact.get(
                "websites",
                [],
            )

            parts.append(
                "Website: "
                + ", ".join(websites)
                if websites
                else "No website saved."
            )

            return "\n".join(parts)

        if intent == "nickname":
            parts.append(
                "Nickname: "
                + contact.get(
                    "nickname",
                    "Not saved.",
                )
            )

            return "\n".join(parts)

        # -------------------------------------------------------------
        # Full contact summary
        # -------------------------------------------------------------
        if (
            contact.get("first_name")
            or contact.get("last_name")
        ):
            full_parts = [
                contact.get("prefix", ""),
                contact.get("first_name", ""),
                contact.get("middle_name", ""),
                contact.get("last_name", ""),
                contact.get("suffix", ""),
            ]

            structured = " ".join(
                x for x in full_parts if x
            )

            if (
                structured
                and structured != name
            ):
                parts.append(
                    "Name: " + structured
                )

        if contact.get("nickname"):
            parts.append(
                "Nickname: "
                + contact["nickname"]
            )

        if contact.get("phones"):
            parts.append(
                cls._phone_text(
                    contact["phones"]
                )
            )

        if contact.get("emails"):
            parts.append(
                cls._email_text(
                    contact["emails"]
                )
            )

        if contact.get("organization"):
            org = contact["organization"]
            org_bits = []

            if org.get("company"):
                org_bits.append(
                    org["company"]
                )

            if org.get("title"):
                org_bits.append(
                    org["title"]
                )

            if org.get("department"):
                org_bits.append(
                    org["department"]
                )

            if org_bits:
                parts.append(
                    "Work: "
                    + " — ".join(org_bits)
                )

        if contact.get("addresses"):
            for item in contact["addresses"][:3]:
                if isinstance(item, dict):
                    value = (
                        item.get("formatted")
                        or ", ".join(
                            part
                            for part in (
                                item.get("street"),
                                item.get("city"),
                                item.get("region"),
                                item.get("postcode"),
                                item.get("country"),
                            )
                            if part
                        )
                    )

                    if value:
                        parts.append(
                            "Address: " + value
                        )

        if contact.get("birthday"):
            parts.append(
                "Birthday: "
                + contact["birthday"]
            )

        if contact.get("websites"):
            parts.append(
                "Website: "
                + ", ".join(
                    contact["websites"]
                )
            )

        if contact.get("notes"):
            parts.append(
                "Notes: "
                + " | ".join(
                    contact["notes"][:3]
                )
            )

        if contact.get("relationships"):
            relationship_text = []

            for item in contact[
                "relationships"
            ][:5]:
                if isinstance(item, dict):
                    label = (
                        item.get("label")
                        or item.get("type")
                    )

                    value = item.get(
                        "name",
                        "",
                    )

                    relationship_text.append(
                        f"{label}: {value}"
                        if label
                        else value
                    )

            if relationship_text:
                parts.append(
                    "Relationships: "
                    + ", ".join(
                        relationship_text
                    )
                )

        if len(parts) == 1:
            parts.append(
                "No additional contact details saved."
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
                    "Allow Contacts in the Android "
                    "permission popup, then ask me "
                    "for the contact again."
                ),
                confidence=1.0,
                action="contacts_permission",
            )

        if not result.get("ok"):
            return SkillResult(
                handled=True,
                answer=(
                    "I could not read the phone contacts. "
                    + str(
                        result.get(
                            "error",
                            "",
                        )
                    )
                ).strip(),
                confidence=1.0,
                action="contacts_error",
                data=result,
            )

        contacts = result.get(
            "contacts",
            [],
        )

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

        intent = self._intent(message)

        if len(contacts) == 1:
            answer = self._format_contact(
                contacts[0],
                intent=intent,
            )

        else:
            lines = [
                (
                    f"I found {len(contacts)} "
                    f"contacts matching {name}:"
                )
            ]

            for contact in contacts[:8]:
                lines.append(
                    self._format_contact(
                        contact,
                        intent=intent,
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