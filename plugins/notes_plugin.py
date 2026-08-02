import re
import unicodedata

from services.ai_plugin import (
    AIPlugin,
    PLUGIN_NOT_HANDLED,
)


class NotesPlugin(AIPlugin):
    """
    Local AI commands for opening and filtering Notes.
    """

    name = "notes"
    description = "Open and filter M12 notes"
    priority = 5

    FILTER_ALIASES = {
        "all": "All",
        "personal": "Personal",
        "work": "Work",
        "working": "Work",
        "project": "Project",
        "projects": "Project",
        "shopping": "Shopping",
        "shop": "Shopping",
        "idea": "Idea",
        "ideas": "Idea",
    }

    def can_handle(
        self,
        message,
        context,
    ):
        text = self._normalize(
            message
        )

        if text in (
            "note",
            "notes",
            "open note",
            "open notes",
            "show note",
            "show notes",
        ):
            return True

        return self._extract_filter(
            text
        ) is not None

    def execute(
        self,
        message,
        context,
    ):
        text = self._normalize(
            message
        )

        if text in (
            "note",
            "notes",
            "open note",
            "open notes",
            "show note",
            "show notes",
        ):
            if context.open_screen(
                "notes"
            ):
                return "Opening Notes."

            return "I could not open Notes."

        note_filter = self._extract_filter(
            text
        )

        if note_filter is None:
            return PLUGIN_NOT_HANDLED

        if not context.open_notes_filter(
            note_filter
        ):
            return (
                "I could not filter Notes by "
                f"{note_filter}."
            )

        if note_filter == "All":
            return "Showing all notes."

        return (
            f"Showing {note_filter} notes."
        )

    def _extract_filter(
        self,
        text,
    ):
        """
        Recognized examples:

            Show work notes
            Show working notes
            Show personal note.
            Filter notes by work
            Open shopping notes
            Show all notes
            Notes personal
        """
        words = text.split()

        if (
            "note" not in words
            and "notes" not in words
        ):
            return None

        for alias, note_type in (
            self.FILTER_ALIASES.items()
        ):
            if alias in words:
                return note_type

        return None

    @staticmethod
    def _normalize(
        message,
    ):
        """
        Normalize typed and transcribed speech.

        Removes punctuation so phrases such as
        "Show personal note." still match.
        """
        text = str(message).strip().lower().replace(
            "’",
            "'",
        )

        text = unicodedata.normalize(
            "NFKD",
            text,
        )

        text = "".join(
            character
            for character in text
            if not unicodedata.combining(
                character
            )
        )

        text = re.sub(
            r"[^a-z0-9а-яё\s']+",
            " ",
            text,
        )

        return " ".join(
            text.split()
        )
