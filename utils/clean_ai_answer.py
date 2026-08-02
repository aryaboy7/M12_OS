import re


def clean_ai_answer(text):
    """
    Clean AI output before displaying it or speaking it.
    """

    text = str(text).strip()

    # --------------------------------------------------
    # Convert Markdown links:
    # [OpenAI](https://openai.com)
    # becomes:
    # OpenAI
    # --------------------------------------------------
    text = re.sub(
        r"\[([^\]]+)\]\(https?://[^)]+\)",
        r"\1",
        text,
    )

    # --------------------------------------------------
    # Remove bare URLs
    # --------------------------------------------------
    text = re.sub(
        r"https?://\S+",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # --------------------------------------------------
    # Remove domains inside parentheses
    # Example:
    # (diplomatie.gouv.fr)
    # (bbc.com)
    # --------------------------------------------------
    text = re.sub(
        r"\(\s*[A-Za-z0-9.-]+\.[A-Za-z]{2,}\s*\)",
        "",
        text,
    )

    # --------------------------------------------------
    # Remove standalone domains
    # Example:
    # diplomatie.gouv.fr
    # cnn.com
    # wikipedia.org
    # --------------------------------------------------
    text = re.sub(
        r"\b[A-Za-z0-9.-]+\.(?:com|org|net|gov|edu|mil|io|ai|co|us|uk|ca|au|fr|de|it|es|jp|cn|ru|info|biz)\b",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # --------------------------------------------------
    # Remove source labels
    # Example:
    # Source: CNN
    # Sources:
    # According to...
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