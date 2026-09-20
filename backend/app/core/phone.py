"""Phone number normalization utilities supporting international numbers."""
import re


def normalize_phone_number(raw_phone: str) -> str:
    """Normalize a verified phone number into a canonical E.164-like representation.

    Rules:
    - Strip surrounding whitespace and formatting characters (spaces, dashes, parentheses).
    - Must start with a '+' followed by country code and subscriber number.
    - Reject obviously malformed values (letters, missing country code, invalid digit counts).
    - Preserves international country codes without hardcoding any specific country (e.g., India/+91).
    - Does NOT convert local numbers arbitrarily into international numbers.
    """
    if not raw_phone or not isinstance(raw_phone, str):
        raise ValueError("Phone number must be a non-empty string.")

    cleaned = raw_phone.strip()

    # Must start with a single '+'
    if not cleaned.startswith("+"):
        raise ValueError("Phone number must include an international country code starting with '+'.")

    # Remove formatting characters like spaces, dashes, dots, and parentheses
    digits_part = re.sub(r"[\s\-\(\)\.]", "", cleaned[1:])

    # The remainder must be purely digits
    if not digits_part.isdigit():
        raise ValueError("Phone number contains invalid non-numeric characters.")

    # E.164 standard: country code + subscriber number has between 7 and 15 digits
    if len(digits_part) < 7 or len(digits_part) > 15:
        raise ValueError(f"Phone number digit length ({len(digits_part)}) is outside valid range (7-15 digits).")

    return f"+{digits_part}"
