from kivy.utils import platform as kivy_platform


class ContactsService:
    """
    Local Android contacts reader for M12 OS.

    The service reads contacts through Android's Contacts Provider.
    It does not upload the address book or cache the complete contacts list.
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

        PythonActivity = autoclass(
            "org.kivy.android.PythonActivity"
        )
        PackageManager = autoclass(
            "android.content.pm.PackageManager"
        )
        ContactsContractContacts = autoclass(
            "android.provider.ContactsContract$Contacts"
        )
        ContactsContractPhone = autoclass(
            "android.provider.ContactsContract$CommonDataKinds$Phone"
        )
        ContactsContractEmail = autoclass(
            "android.provider.ContactsContract$CommonDataKinds$Email"
        )

        activity = PythonActivity.mActivity

        return {
            "activity": activity,
            "PackageManager": PackageManager,
            "Contacts": ContactsContractContacts,
            "Phone": ContactsContractPhone,
            "Email": ContactsContractEmail,
        }

    @classmethod
    def has_permission(cls):
        if not cls.is_android():
            return False

        try:
            objects = cls._android_objects()
            activity = objects["activity"]
            PackageManager = objects["PackageManager"]

            return (
                activity.checkSelfPermission(
                    cls.READ_CONTACTS
                )
                == PackageManager.PERMISSION_GRANTED
            )

        except Exception:
            return False

    @classmethod
    def request_permission(cls):
        """
        Ask Android for READ_CONTACTS.

        Permission callbacks are asynchronous, so callers should tell the
        user to approve the Android prompt and then retry the contacts query.
        """
        if not cls.is_android():
            return False

        if cls.has_permission():
            return True

        try:
            from android.permissions import (
                Permission,
                request_permissions,
            )

            permission = getattr(
                Permission,
                "READ_CONTACTS",
                cls.READ_CONTACTS,
            )

            request_permissions(
                [permission]
            )
            return True

        except Exception:
            try:
                from android.permissions import (
                    request_permissions,
                )

                request_permissions(
                    [cls.READ_CONTACTS]
                )
                return True

            except Exception:
                return False

    @staticmethod
    def _cursor_value(cursor, column_name):
        index = cursor.getColumnIndex(
            column_name
        )

        if index < 0:
            return ""

        value = cursor.getString(index)

        return str(value or "").strip()

    @classmethod
    def _query_rows(
        cls,
        uri,
        projection,
        selection,
        selection_args,
        sort_order=None,
        limit=50,
    ):
        objects = cls._android_objects()
        activity = objects["activity"]
        resolver = activity.getContentResolver()

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

            while (
                cursor.moveToNext()
                and count < int(limit)
            ):
                row = {}

                for column_name in projection:
                    row[str(column_name)] = (
                        cls._cursor_value(
                            cursor,
                            column_name,
                        )
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

    @classmethod
    def search(cls, query, limit=20):
        """
        Search the Android address book by display name.

        Returns:
            {
                "ok": bool,
                "permission_required": bool,
                "contacts": [
                    {
                        "name": "...",
                        "phones": ["..."],
                        "emails": ["..."],
                    }
                ],
                "error": "...",
            }
        """
        name_query = str(
            query or ""
        ).strip()

        if not cls.is_android():
            return {
                "ok": False,
                "permission_required": False,
                "contacts": [],
                "error": (
                    "Phone contacts are available "
                    "only on Android."
                ),
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
                "error": (
                    "Contacts permission is required."
                ),
            }

        try:
            objects = cls._android_objects()
            Phone = objects["Phone"]
            Email = objects["Email"]

            like_arg = f"%{name_query}%"

            phone_projection = [
                Phone.DISPLAY_NAME,
                Phone.NUMBER,
            ]

            phone_rows = cls._query_rows(
                Phone.CONTENT_URI,
                phone_projection,
                f"{Phone.DISPLAY_NAME} LIKE ?",
                [like_arg],
                f"{Phone.DISPLAY_NAME} COLLATE NOCASE ASC",
                limit=max(50, int(limit) * 8),
            )

            email_projection = [
                Email.DISPLAY_NAME,
                Email.ADDRESS,
            ]

            email_rows = cls._query_rows(
                Email.CONTENT_URI,
                email_projection,
                f"{Email.DISPLAY_NAME} LIKE ?",
                [like_arg],
                f"{Email.DISPLAY_NAME} COLLATE NOCASE ASC",
                limit=max(50, int(limit) * 8),
            )

            contacts = {}

            def get_entry(name):
                clean_name = str(
                    name or ""
                ).strip() or "Unknown"

                key = clean_name.casefold()

                if key not in contacts:
                    contacts[key] = {
                        "name": clean_name,
                        "phones": [],
                        "emails": [],
                    }

                return contacts[key]

            for row in phone_rows:
                name = row.get(
                    str(Phone.DISPLAY_NAME),
                    "",
                )
                number = row.get(
                    str(Phone.NUMBER),
                    "",
                )

                if not number:
                    continue

                entry = get_entry(name)

                if number not in entry["phones"]:
                    entry["phones"].append(
                        number
                    )

            for row in email_rows:
                name = row.get(
                    str(Email.DISPLAY_NAME),
                    "",
                )
                address = row.get(
                    str(Email.ADDRESS),
                    "",
                )

                if not address:
                    continue

                entry = get_entry(name)

                if address not in entry["emails"]:
                    entry["emails"].append(
                        address
                    )

            result = list(
                contacts.values()
            )

            query_fold = name_query.casefold()

            result.sort(
                key=lambda item: (
                    0
                    if item["name"].casefold()
                    == query_fold
                    else (
                        1
                        if item["name"].casefold().startswith(
                            query_fold
                        )
                        else 2
                    ),
                    item["name"].casefold(),
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
                "error": (
                    f"{type(error).__name__}: "
                    f"{error}"
                ),
            }