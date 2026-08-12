import re


def clean_ai_answer(text):
    """
    Clean AI output before displaying it or speaking it.

    URLs are preserved so the AI Conversation screen can
    display them as clickable links.
    """

    text = str(text).strip()

    # --------------------------------------------------
    # Convert Markdown links.
    #
    # [Yahoo](https://www.yahoo.com)
    # becomes:
    # Yahoo - https://www.yahoo.com
    #
    # [https://www.yahoo.com](https://www.yahoo.com)
    # becomes:
    # https://www.yahoo.com
    # --------------------------------------------------
    def replace_markdown_link(match):
        label = match.group(1).strip()
        url = match.group(2).strip()

        if label == url:
            return url

        return f"{label} - {url}"

    text = re.sub(
        r"\[([^\]]+)\]\((https?://[^)]+)\)",
        replace_markdown_link,
        text,
        flags=re.IGNORECASE,
    )

    # --------------------------------------------------
    # IMPORTANT:
    # Do NOT remove bare http:// or https:// URLs.
    #
    # ai_screen.py detects these URLs and turns them into
    # clickable links.
    # --------------------------------------------------

    # --------------------------------------------------
    # Do NOT remove standalone domains either.
    #
    # They may be useful information in an AI response.
    # Only complete http:// and https:// URLs become
    # clickable in the AI Conversation screen.
    # --------------------------------------------------

    # --------------------------------------------------
    # Remove source labels
    # Example:
    # Source: CNN
    # Sources:
    # --------------------------------------------------
    text = re.sub(
        r"(?im)^(source|sources)\s*:.*$",
        "",
        text,
    )

    # --------------------------------------------------
    # Remove empty parentheses
    # --------------------------------------------------
    text = re.sub(
        r"\(\s*\)",
        "",
        text,
    )

    # --------------------------------------------------
    # Remove empty brackets
    # --------------------------------------------------
    text = re.sub(
        r"\[\s*\]",
        "",
        text,
    )

    # --------------------------------------------------
    # Remove repeated spaces
    # --------------------------------------------------
    text = re.sub(
        r"[ \t]+",
        " ",
        text,
    )

    # --------------------------------------------------
    # Remove excessive blank lines
    # --------------------------------------------------
    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text,
    )

    # --------------------------------------------------
    # Clean spaces before punctuation
    # --------------------------------------------------
    text = re.sub(
        r"\s+([.,!?;:])",
        r"\1",
        text,
    )

    return text.strip()