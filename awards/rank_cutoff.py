"""Calibre-free normalization for the explicit ordinal rank cutoff preference.

This helper is for persisted/user-facing values. Qualification APIs validate
strictly and do not call it.
"""

DEFAULT_MAX_QUALIFYING_RANK = 5
MIN_MAX_QUALIFYING_RANK = 1
MAX_MAX_QUALIFYING_RANK = 100


def normalize_max_qualifying_rank(value) -> int:
    """Return a cutoff in 1..100, or DEFAULT_MAX_QUALIFYING_RANK.

    Accepted: int 1..100, and a clean integer string such as "10" in that
    range (JSONConfig may store numbers as strings). Bool is not an int.
    None, garbage, 0, 101, and other out-of-range values fall back to 5.
    Out-of-range values are not clamped to the nearest bound.
    """
    if isinstance(value, bool) or value is None:
        return DEFAULT_MAX_QUALIFYING_RANK
    if isinstance(value, int):
        if MIN_MAX_QUALIFYING_RANK <= value <= MAX_MAX_QUALIFYING_RANK:
            return value
        return DEFAULT_MAX_QUALIFYING_RANK
    if isinstance(value, str):
        text = value.strip()
        digits = text[1:] if text.startswith('-') else text
        if not text or not digits.isdigit():
            return DEFAULT_MAX_QUALIFYING_RANK
        parsed = int(text)
        if MIN_MAX_QUALIFYING_RANK <= parsed <= MAX_MAX_QUALIFYING_RANK:
            return parsed
        return DEFAULT_MAX_QUALIFYING_RANK
    return DEFAULT_MAX_QUALIFYING_RANK
