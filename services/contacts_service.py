import re

from kivy.utils import platform as kivy_platform


class ContactsService:
    """
    Local Android contacts reader for M12 OS.

    Reads useful human-facing Android contact fields from ContactsContract.
    No address book data is uploaded or cached.
    """

    READ_CONTACTS = "android.permission.READ_CONTACTS"

    @staticmethod
    def is_android():
        return kivy_platform == "android"

    @classmethod
    def _android_objects(cls):
        if not cls.is_android():
            return None

        from jnius import autoclass

        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        PackageManager = autoclass("android.content.pm.PackageManager")
        Contacts = autoclass("android.provider.ContactsContract$Contacts")
        Phone = autoclass("android.provider.ContactsContract$CommonDataKinds$Phone")
        Email = autoclass("android.provider.ContactsContract$CommonDataKinds$Email")
        Data = autoclass("android.provider.ContactsContract$Data")

        return {
            "activity": PythonActivity.mActivity,
            "PackageManager": PackageManager,
            "Contacts": Contacts,
            "Phone": Phone,
            "Email": Email,
            "Data": Data,
        }

    @classmethod
    def has_permission(cls):
        if not cls.is_android():
            return False

        try:
            objects = cls._android_objects()
            return (
                objects["activity"].checkSelfPermission(cls.READ_CONTACTS)
                == objects["PackageManager"].PERMISSION_GRANTED
            )
        except Exception:
            return False

    @classmethod
    def request_permission(cls):
        if not cls.is_android():
            return False

        if cls.has_permission():
            return True

        try:
            from android.permissions import Permission, request_permissions

            permission = getattr(Permission, "READ_CONTACTS", cls.READ_CONTACTS)
            request_permissions([permission])
            return True
        except Exception:
            try:
                from android.permissions import request_permissions

                request_permissions([cls.READ_CONTACTS])
                return True
            except Exception:
                return False

    @staticmethod
    def _cursor_value(cursor, column_name):
        index = cursor.getColumnIndex(str(column_name))
        if index < 0:
            return ""

        try:
            value = cursor.getString(index)
        except Exception:
            return ""

        return str(value or "").strip()

    @classmethod
    def _query_rows(
        cls,
        uri,
        projection,
        selection=None,
        selection_args=None,
        sort_order=None,
        limit=500,
    ):
        objects = cls._android_objects()
        resolver = objects["activity"].getContentResolver()

        cursor = None
        rows = []

        try:
            cursor = resolver.query(
                uri,
                projection,
                selection,
                selection_args,
                sort_order,
            )

            if cursor is None:
                return rows

            count = 0

            while cursor.moveToNext() and count < int(limit):
                row = {}

                for column_name in projection:
                    row[str(column_name)] = cls._cursor_value(
                        cursor,
                        column_name,
                    )

                rows.append(row)
                count += 1

            return rows

        finally:
            try:
                if cursor is not None:
                    cursor.close()
            except Exception:
                pass

    @staticmethod
    def _add_unique(items, item):
        if item not in items:
            items.append(item)

    @staticmethod
    def _clean_dict(data):
        return {
            key: value
            for key, value in data.items()
            if value not in ("", None, [], {})
        }

    RUSSIAN_NAME_ALIASES = {
        # Explicit bilingual equivalents. Add more names here as needed.
        "галина": "galina",
        "galina": "галина",
    }

    @staticmethod
    def _normalize_name_token(value):
        return re.sub(
            r"[^0-9a-zа-яё]+",
            "",
            str(value or "").casefold(),
        )

    @classmethod
    def _query_name_forms(cls, query):
        """
        Return only explicit search forms. No fuzzy matching.

        Example:
            Galina -> {"galina", "галина"}
            Галина -> {"галина", "galina"}
        """
        token = cls._normalize_name_token(query)
        forms = {token} if token else set()

        alias = cls.RUSSIAN_NAME_ALIASES.get(token)
        if alias:
            forms.add(alias)

        return forms

    @classmethod
    def _name_matches_query(cls, display_name, query):
        """
        Match complete name tokens only.

        'Галина' matches a saved 'Galina Ryaboy'.
        'Galina' matches a saved 'Галина ...'.
        It does not fuzzy-match Halina, David, or unrelated contacts.
        """
        forms = cls._query_name_forms(query)
        if not forms:
            return False

        name_tokens = {
            cls._normalize_name_token(part)
            for part in re.findall(
                r"[0-9A-Za-zА-Яа-яЁё]+",
                str(display_name or ""),
            )
        }
        name_tokens.discard("")

        return bool(forms.intersection(name_tokens))

    @classmethod
    def search(cls, query, limit=20):
        """
        Search Android contacts by display name.

        Returns all useful human-facing fields:
        names, nickname, phones, emails, addresses, organization,
        birthday/dates, websites, notes, relationships and photo URI.
        """
        name_query = str(query or "").strip()

        if not cls.is_android():
            return {
                "ok": False,
                "permission_required": False,
                "contacts": [],
                "error": "Phone contacts are available only on Android.",
            }

        if not name_query:
            return {
                "ok": False,
                "permission_required": False,
                "contacts": [],
                "error": "Enter a contact name.",
            }

        if not cls.has_permission():
            cls.request_permission()

            return {
                "ok": False,
                "permission_required": True,
                "contacts": [],
                "error": "Contacts permission is required.",
            }

        try:
            objects = cls._android_objects()
            Contacts = objects["Contacts"]
            Phone = objects["Phone"]
            Email = objects["Email"]
            Data = objects["Data"]

            like_arg = f"%{name_query}%"

            contact_projection = [
                Contacts._ID,
                Contacts.DISPLAY_NAME,
                Contacts.PHOTO_URI,
                Contacts.PHOTO_THUMBNAIL_URI,
            ]

            # Read the Contacts table without a provider-side LIKE filter.
            # Some Android contact providers do not reliably support
            # DISPLAY_NAME LIKE ? even though the same contacts are visible
            # through Contacts.CONTENT_URI. Filter names locally instead.
            contact_rows = cls._query_rows(
                Contacts.CONTENT_URI,
                contact_projection,
                None,
                None,
                f"{Contacts.DISPLAY_NAME} COLLATE NOCASE ASC",
                limit=10000,
            )

            contacts = {}
            query_fold = name_query.casefold()

            for row in contact_rows:
                contact_id = row.get(str(Contacts._ID), "")
                display_name = (
                    row.get(str(Contacts.DISPLAY_NAME), "").strip()
                    or "Unknown"
                )

                if not contact_id:
                    continue

                if not cls._name_matches_query(
                    display_name,
                    name_query,
                ):
                    continue

                contacts[contact_id] = {
                    "id": contact_id,
                    "name": display_name,
                    "first_name": "",
                    "middle_name": "",
                    "last_name": "",
                    "prefix": "",
                    "suffix": "",
                    "nickname": "",
                    "phones": [],
                    "emails": [],
                    "addresses": [],
                    "organization": {},
                    "birthday": "",
                    "dates": [],
                    "websites": [],
                    "notes": [],
                    "relationships": [],
                    "photo_uri": row.get(str(Contacts.PHOTO_URI), ""),
                    "thumbnail_uri": row.get(
                        str(Contacts.PHOTO_THUMBNAIL_URI),
                        "",
                    ),
                }

            if not contacts:
                return {
                    "ok": True,
                    "permission_required": False,
                    "contacts": [],
                    "error": "",
                }

            # Phones
            phone_projection = [
                Phone.CONTACT_ID,
                Phone.NUMBER,
                Phone.TYPE,
                Phone.LABEL,
            ]

            phone_ids = list(contacts.keys())
            phone_placeholders = ",".join(["?"] * len(phone_ids))

            phone_rows = cls._query_rows(
                Phone.CONTENT_URI,
                phone_projection,
                f"{Phone.CONTACT_ID} IN ({phone_placeholders})",
                phone_ids,
                None,
                limit=max(100, int(limit) * 20),
            )

            for row in phone_rows:
                contact_id = row.get(str(Phone.CONTACT_ID), "")
                number = row.get(str(Phone.NUMBER), "").strip()
                if not number:
                    continue

                entry = contacts.get(contact_id)
                if not entry:
                    continue

                phone_item = cls._clean_dict({
                    "number": number,
                    "type": row.get(str(Phone.TYPE), ""),
                    "label": row.get(str(Phone.LABEL), ""),
                })
                cls._add_unique(entry["phones"], phone_item)

            # Emails
            email_projection = [
                Email.CONTACT_ID,
                Email.ADDRESS,
                Email.TYPE,
                Email.LABEL,
            ]

            email_ids = list(contacts.keys())
            email_placeholders = ",".join(["?"] * len(email_ids))

            email_rows = cls._query_rows(
                Email.CONTENT_URI,
                email_projection,
                f"{Email.CONTACT_ID} IN ({email_placeholders})",
                email_ids,
                None,
                limit=max(100, int(limit) * 20),
            )

            for row in email_rows:
                contact_id = row.get(str(Email.CONTACT_ID), "")
                address = row.get(str(Email.ADDRESS), "").strip()
                if not address:
                    continue

                entry = contacts.get(contact_id)
                if not entry:
                    continue

                email_item = cls._clean_dict({
                    "address": address,
                    "type": row.get(str(Email.TYPE), ""),
                    "label": row.get(str(Email.LABEL), ""),
                })
                cls._add_unique(entry["emails"], email_item)

            # Generic Data table for structured fields.
            # DATA1..DATA10 are interpreted according to MIMETYPE.
            data_projection = [
                "contact_id",
                "mimetype",
                "data1",
                "data2",
                "data3",
                "data4",
                "data5",
                "data6",
                "data7",
                "data8",
                "data9",
                "data10",
            ]

            id_args = list(contacts.keys())
            placeholders = ",".join(["?"] * len(id_args))

            data_rows = cls._query_rows(
                Data.CONTENT_URI,
                data_projection,
                f"contact_id IN ({placeholders})",
                id_args,
                None,
                limit=max(500, int(limit) * 100),
            )

            MIME_NAME = "vnd.android.cursor.item/name"
            MIME_NICKNAME = "vnd.android.cursor.item/nickname"
            MIME_POSTAL = "vnd.android.cursor.item/postal-address_v2"
            MIME_ORG = "vnd.android.cursor.item/organization"
            MIME_EVENT = "vnd.android.cursor.item/contact_event"
            MIME_WEBSITE = "vnd.android.cursor.item/website"
            MIME_NOTE = "vnd.android.cursor.item/note"
            MIME_RELATION = "vnd.android.cursor.item/relation"

            for row in data_rows:
                contact_id = row.get("contact_id", "")
                entry = contacts.get(contact_id)
                if not entry:
                    continue

                mime = row.get("mimetype", "")

                if mime == MIME_NAME:
                    entry["first_name"] = row.get("data2", "")
                    entry["last_name"] = row.get("data3", "")
                    entry["prefix"] = row.get("data4", "")
                    entry["middle_name"] = row.get("data5", "")
                    entry["suffix"] = row.get("data6", "")

                elif mime == MIME_NICKNAME:
                    if row.get("data1", ""):
                        entry["nickname"] = row.get("data1", "")

                elif mime == MIME_POSTAL:
                    address_item = cls._clean_dict({
                        "formatted": row.get("data1", ""),
                        "type": row.get("data2", ""),
                        "label": row.get("data3", ""),
                        "street": row.get("data4", ""),
                        "po_box": row.get("data5", ""),
                        "neighborhood": row.get("data6", ""),
                        "city": row.get("data7", ""),
                        "region": row.get("data8", ""),
                        "postcode": row.get("data9", ""),
                        "country": row.get("data10", ""),
                    })
                    if address_item:
                        cls._add_unique(entry["addresses"], address_item)

                elif mime == MIME_ORG:
                    org = cls._clean_dict({
                        "company": row.get("data1", ""),
                        "type": row.get("data2", ""),
                        "label": row.get("data3", ""),
                        "title": row.get("data4", ""),
                        "department": row.get("data5", ""),
                        "job_description": row.get("data6", ""),
                        "symbol": row.get("data7", ""),
                        "phonetic_name": row.get("data8", ""),
                        "office_location": row.get("data9", ""),
                    })
                    if org:
                        entry["organization"] = org

                elif mime == MIME_EVENT:
                    date_value = row.get("data1", "")
                    event_type = row.get("data2", "")
                    label = row.get("data3", "")
                    event_item = cls._clean_dict({
                        "date": date_value,
                        "type": event_type,
                        "label": label,
                    })
                    if event_item:
                        cls._add_unique(entry["dates"], event_item)

                    # Android Event.TYPE_BIRTHDAY is 3.
                    if str(event_type) == "3" and date_value:
                        entry["birthday"] = date_value

                elif mime == MIME_WEBSITE:
                    value = row.get("data1", "")
                    if value:
                        cls._add_unique(entry["websites"], value)

                elif mime == MIME_NOTE:
                    value = row.get("data1", "")
                    if value:
                        cls._add_unique(entry["notes"], value)

                elif mime == MIME_RELATION:
                    relation = cls._clean_dict({
                        "name": row.get("data1", ""),
                        "type": row.get("data2", ""),
                        "label": row.get("data3", ""),
                    })
                    if relation:
                        cls._add_unique(entry["relationships"], relation)

            result = []

            for item in contacts.values():
                cleaned = cls._clean_dict(item)
                result.append(cleaned)

            query_fold = name_query.casefold()

            result.sort(
                key=lambda item: (
                    0
                    if item.get("name", "").casefold() == query_fold
                    else (
                        1
                        if item.get("name", "").casefold().startswith(
                            query_fold
                        )
                        else 2
                    ),
                    item.get("name", "").casefold(),
                )
            )

            return {
                "ok": True,
                "permission_required": False,
                "contacts": result[: int(limit)],
                "error": "",
            }

        except Exception as error:
            return {
                "ok": False,
                "permission_required": False,
                "contacts": [],
                "error": f"{type(error).__name__}: {error}",
            }