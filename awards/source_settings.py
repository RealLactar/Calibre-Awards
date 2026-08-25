"""Pure helpers for opt-out award-source selection. Calibre-free and Qt-free.

Preferences persist disabled_source_keys, not enabled keys, so a source added
in a later release starts on for existing users. Stale disabled keys are kept
during normalize and ignored when computing the enabled set. Registry order
wins; the preference list does not reorder sources.
"""

from __future__ import annotations

from collections.abc import Mapping


def normalize_disabled_source_keys(value) -> tuple[str, ...]:
    """Return unique trimmed source keys from a persisted preference value.

    A raw non-empty string is recovered as a single key. Mappings are ignored.
    Unusable entries are skipped. Unknown or stale keys are preserved rather
    than discarded; compute_enabled_source_keys ignores keys that are not in
    the current registry. Registry order remains authoritative.
    """
    if value is None:
        return ()
    if isinstance(value, str):
        key = value.strip()
        return (key,) if key else ()
    if isinstance(value, Mapping):
        return ()
    try:
        items = tuple(value)
    except TypeError:
        return ()
    seen: set[str] = set()
    keys: list[str] = []
    for item in items:
        if not isinstance(item, str):
            continue
        key = item.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        keys.append(key)
    return tuple(keys)


def compute_enabled_source_keys(all_keys, disabled_keys) -> tuple[str, ...]:
    """Return all_keys order minus normalized disabled keys.

    Unknown disabled keys are ignored. Duplicate all_keys are collapsed.
    """
    disabled = set(normalize_disabled_source_keys(disabled_keys))
    seen: set[str] = set()
    enabled: list[str] = []
    for key in all_keys:
        if key in disabled or key in seen:
            continue
        seen.add(key)
        enabled.append(key)
    return tuple(enabled)
