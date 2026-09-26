"""Cleaning free text from bank sources.

Auction data is typed by branch staff into forms with no validation, so it
arrives SHOUTING, with mojibake from Windows-1252 round-trips, stray
newlines and doubled spaces.
"""

import re

_WHITESPACE = re.compile(r"\s+")
_PINCODE = re.compile(r"\b(\d{6})\b")

# Characters produced when UTF-8 is misread as Windows-1252 and back again.
# The replacement character appears in real BAANKNET addresses.
_MOJIBAKE = {
    "\ufffd": "-",
    "\u00a0": " ",
    "â€“": "-",
    "â€”": "-",
    "â€˜": "'",
    "â€™": "'",
    "â€œ": '"',
    "â€\x9d": '"',
}

_ALWAYS_UPPER = {
    "hno",
    "no",
    "rcc",
    "gf",
    "ff",
    "sf",
    "tf",
    "bhk",
    "mig",
    "hig",
    "lig",
    "nh",
    "sh",
    "rs",
    "sq",
    "ft",
    "llp",
    "pvt",
    "ltd",
    "hp",
    "vip",
    "id",
}


def clean_text(value: object, max_length: int | None = None) -> str | None:
    """Collapse whitespace, repair mojibake, return None for empties."""
    if value is None:
        return None

    text = str(value)
    for bad, good in _MOJIBAKE.items():
        text = text.replace(bad, good)

    text = _WHITESPACE.sub(" ", text).strip(" ,;:-\t\r\n")
    if not text or text.lower() in {"null", "none", "n/a", "na", "-", "nil"}:
        return None

    if max_length and len(text) > max_length:
        text = text[:max_length].rsplit(" ", 1)[0] + "..."
    return text


def title_case(value: object) -> str | None:
    """Convert SHOUTED names to readable title case, preserving acronyms."""
    text = clean_text(value)
    if text is None:
        return None
    if text != text.upper():
        return text  # already mixed case; leave it alone

    words = []
    for word in text.split():
        stripped = word.strip(".,()").lower()
        words.append(word if stripped in _ALWAYS_UPPER else word.capitalize())
    return " ".join(words)


def normalise_pincode(value: object) -> str | None:
    """Extract a 6-digit Indian PIN code.

    The most reliable geographic anchor available, so it is worth pulling
    out of free text when a dedicated field is missing.
    """
    text = clean_text(value)
    if text is None:
        return None
    match = _PINCODE.search(text.replace(" ", ""))
    if match:
        return match.group(1)
    match = _PINCODE.search(text)
    return match.group(1) if match else None


def normalise_phone(value: object) -> str | None:
    """Keep Indian mobile/landline digits, drop formatting and country code."""
    text = clean_text(value)
    if text is None:
        return None
    digits = re.sub(r"\D", "", text)
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    return digits if 6 <= len(digits) <= 15 else None
