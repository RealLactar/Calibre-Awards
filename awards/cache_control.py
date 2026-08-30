"""Per-source award-cache maintenance. Qt-free and Calibre-free.

refresh_award_source_cache() invalidates that source's persistent disk cache
and in-process RAM. It does not look up awards or open the network. The next
Check Awards search lazily rebuilds the selected source.

Locus refresh clears both author and annual keyed caches. The action is
immediate maintenance, not a saved preference.
"""

from __future__ import annotations

from . import cache
from .source_info import SOURCE_INFOS
from .sources import (
    booker,
    german_book_prize,
    hugo,
    locus,
    miles_franklin,
    nebula,
    newbery,
    nobel,
    prix_goncourt,
    pulitzer,
    womens_prize_fiction,
    world_fantasy,
)

CACHE_REFRESH_BUTTON_LABEL = 'Refresh'
SOURCES_GROUP_HINT = (
    'Select the award sources used by Check Awards. '
    'Refresh clears cached data for an enabled source; fresh data will be '
    'retrieved the next time that source is checked.'
)

# One reset callable per registered source key. Adding a source to
# AWARD_SOURCES without a mapping here is caught by tests.
_SOURCE_RUNTIME_RESETS = {
    'booker': booker._reset_runtime_state,
    'german_book_prize': german_book_prize._reset_runtime_state,
    'hugo': hugo._reset_runtime_state,
    'locus': locus._reset_runtime_state,
    'miles_franklin': miles_franklin._reset_runtime_state,
    'nebula': nebula._reset_runtime_state,
    'newbery': newbery._reset_runtime_state,
    'nobel': nobel._reset_runtime_state,
    'prix_goncourt': prix_goncourt._reset_runtime_state,
    'pulitzer': pulitzer._reset_runtime_state,
    'womens_prize_fiction': womens_prize_fiction._reset_runtime_state,
    'world_fantasy': world_fantasy._reset_runtime_state,
}


def runtime_reset_source_keys() -> frozenset[str]:
    """Return the source keys that have in-process cache reset coverage."""
    return frozenset(_SOURCE_RUNTIME_RESETS)


def cache_refresh_source_rows() -> tuple[tuple[str, str], ...]:
    """Return (source_key, display_name) rows in established UI order."""
    return tuple((info.key, info.display_name) for info in SOURCE_INFOS)


def source_cache_refresh_confirm_title(display_name: str) -> str:
    return f'Refresh cached {display_name} data?'


def source_cache_refresh_confirm_body(display_name: str) -> str:
    return (
        f'This will remove saved {display_name} lookup data and clear its '
        'current in-memory cache.\n\n'
        'No award information already stored in your books will be changed.\n\n'
        f'The next Check Awards search may take longer while fresh '
        f'{display_name} data is retrieved.\n\n'
        'This action happens immediately and is not undone by Canceling '
        'Preferences.'
    )


def source_cache_refresh_status_text(display_name: str) -> str:
    return (
        f'{display_name} cached data cleared.\n'
        'Fresh data will be retrieved by the next Check Awards search.'
    )


def source_cache_refresh_failure_text(display_name: str) -> str:
    return (
        f'{display_name} in-memory cache was cleared, but some saved cache '
        'data could not be removed.\n\n'
        'The next Check Awards search may still use the existing saved data.\n\n'
        'Close Calibre and try Refresh again.'
    )


def bind_source_refresh_callback(handler, source_key: str, display_name: str):
    """Return a Qt clicked() handler bound to this source key.

    Default-argument binding avoids the loop late-binding pitfall.
    """

    def _clicked(checked=False, key=source_key, name=display_name):
        handler(key, name)

    return _clicked


def bind_refresh_enabled_to_checkbox(refresh_button):
    """Return a toggled(checked) handler that enables Refresh with the checkbox."""

    def _toggled(checked=False, button=refresh_button):
        button.setEnabled(bool(checked))

    return _toggled


def run_source_cache_refresh_if_confirmed(
    source_key: str,
    display_name: str,
    *,
    confirmed: bool,
) -> bool | None:
    """Refresh one source only after confirmation.

    Returns None if cancelled. Returns True when persistent cache data for
    that source is gone. Returns False when RAM was reset but some saved
    files could not be removed. Cancel leaves disk, RAM, and preferences
    unchanged. Confirm invalidates that source immediately and does not
    wait for Apply/OK.
    """
    if not confirmed:
        return None
    return refresh_award_source_cache(source_key)


def refresh_award_source_cache(source_key: str) -> bool:
    """Invalidate one source's disk cache and reset only that source's RAM.

    Disk is cleared first so a later RAM reset cannot be refilled from the
    old file. RAM is still reset if persistent deletion fails. Returns True
    when managed persistent data for that source is absent afterwards.
    Unknown keys raise ValueError and do not touch any cache. No network
    request is made.
    """
    if not isinstance(source_key, str) or not source_key.strip():
        raise ValueError('unknown award source cache key')
    key = source_key.strip()
    reset = _SOURCE_RUNTIME_RESETS.get(key)
    if reset is None:
        raise ValueError(f'unknown award source cache key: {key!r}')
    persistent_ok = False
    try:
        persistent_ok = cache.invalidate_source_cache(key)
    finally:
        reset()
    return bool(persistent_ok)
