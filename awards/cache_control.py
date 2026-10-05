"""Queue source updates without network access or deleting validated fallback.

Disk requests survive restarts; explicit refresh bypasses the ordinary stale
refresh budget. Bundled sources reset RAM and reload their shipped archive.
Refresh is immediate maintenance, not a saved preference.
"""

from __future__ import annotations

from . import cache
from .source_info import SOURCE_INFOS
from .sources import (
    akutagawa,
    naoki,
    mao_dun,
    medicis,
    dublin,
    diagram,
    bad_sex_fiction,
    balrog,
    booker,
    bram_stoker,
    edgar,
    international_booker,
    german_book_prize,
    hugo,
    ipaf,
    locus,
    miles_franklin,
    national_book_critics_circle,
    nebula,
    newbery,
    nobel,
    pen_faulkner,
    pen_hemingway,
    prix_goncourt,
    pulitzer,
    romantic_novel_awards,
    womens_prize_fiction,
    world_fantasy,
    wolfson_history,
)

CACHE_REFRESH_BUTTON_LABEL = 'Refresh'
SOURCES_GROUP_HINT = (
    'Select the award sources used by Check Awards. '
    'Refresh requests a download while retaining saved fallback data. '
    'Bundled sources reload their archive; new coverage requires a plugin update. '
    'If no executable award sources are selected, Check Awards is hidden '
    'in Edit Metadata.'
)

# One reset callable per registered source key. Adding a source to
# AWARD_SOURCES without a mapping here is caught by tests.
_SOURCE_RUNTIME_RESETS = {
    'akutagawa': akutagawa._reset_runtime_state,
    'naoki': naoki._reset_runtime_state,
    'mao_dun': mao_dun._reset_runtime_state,
    'medicis': medicis._reset_runtime_state,
    'dublin': dublin._reset_runtime_state,
    'diagram': diagram._reset_runtime_state,
    'bad_sex_fiction': bad_sex_fiction._reset_runtime_state,
    'balrog': balrog._reset_runtime_state,
    'booker': booker._reset_runtime_state,
    'bram_stoker': bram_stoker._reset_runtime_state,
    'edgar': edgar._reset_runtime_state,
    'german_book_prize': german_book_prize._reset_runtime_state,
    'hugo': hugo._reset_runtime_state,
    'international_booker': international_booker._reset_runtime_state,
    'ipaf': ipaf._reset_runtime_state,
    'locus': locus._reset_runtime_state,
    'miles_franklin': miles_franklin._reset_runtime_state,
    'national_book_critics_circle': (
        national_book_critics_circle._reset_runtime_state
    ),
    'nebula': nebula._reset_runtime_state,
    'newbery': newbery._reset_runtime_state,
    'nobel': nobel._reset_runtime_state,
    'pen_faulkner': pen_faulkner._reset_runtime_state,
    'pen_hemingway': pen_hemingway._reset_runtime_state,
    'prix_goncourt': prix_goncourt._reset_runtime_state,
    'pulitzer': pulitzer._reset_runtime_state,
    'romantic_novel_awards': romantic_novel_awards._reset_runtime_state,
    'womens_prize_fiction': womens_prize_fiction._reset_runtime_state,
    'world_fantasy': world_fantasy._reset_runtime_state,
    'wolfson_history': wolfson_history._reset_runtime_state,
}


def runtime_reset_source_keys() -> frozenset[str]:
    """Return the source keys that have in-process cache reset coverage."""
    return frozenset(_SOURCE_RUNTIME_RESETS)


def cache_refresh_source_rows() -> tuple[tuple[str, str], ...]:
    """Return (source_key, display_name) rows in established UI order."""
    return tuple((info.key, info.display_name) for info in SOURCE_INFOS)


def source_cache_refresh_confirm_title(display_name: str) -> str:
    return f'Refresh cached {display_name} data?'


BUNDLED_SOURCE_KEYS = frozenset({'bad_sex_fiction', 'diagram'})


def source_refresh_description(source_key):
    if source_key in BUNDLED_SOURCE_KEYS:
        return 'The next lookup reloads the bundled archive. New coverage requires a plugin update.'
    return ('A download is requested for the next lookup. Validated saved data and any bundled fallback are retained '
            'until a replacement succeeds. Pending disk requests survive restarts and '
            'bypass the ordinary stale-refresh budget.')


def bulk_refresh_description(source_keys):
    keys = set(source_keys)
    parts = []
    if keys - BUNDLED_SOURCE_KEYS:
        parts.append('Downloads are requested on the next lookup; validated saved fallback data is retained.')
    if keys & BUNDLED_SOURCE_KEYS:
        parts.append('Bundled sources reload their archive; new coverage requires a plugin update.')
    return ' '.join(parts)


def source_cache_refresh_confirm_body(source_key, display_name):
    return (f'Request a refresh for {display_name}?\n\n' + source_refresh_description(source_key)
            + '\n\nNo book metadata will change. This happens immediately and is not undone '
              'by Canceling Preferences.')


def source_cache_refresh_status_text(source_key, display_name):
    action = 'Bundled archive reload queued' if source_key in BUNDLED_SOURCE_KEYS else 'Download request queued'
    return f'{display_name}: {action}.\n' + source_refresh_description(source_key)


def source_cache_refresh_failure_text(display_name):
    return (f'{display_name}: the refresh request could not be saved. '
            'Saved fallback data was retained. Try Refresh again.')


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

    Returns None if cancelled, True if the request was queued, or False if
    the request could not be persisted. Saved fallback is retained in all
    cases. Cancel leaves disk, RAM, and preferences unchanged. Confirm queues
    the request immediately and does not wait for Apply/OK.
    """
    if not confirmed:
        return None
    return refresh_award_source_cache(source_key)


def refresh_award_source_cache(source_key: str) -> bool:
    """Queue a lazy refresh; keep persistent records and clear source RAM."""
    if not isinstance(source_key, str) or not source_key.strip():
        raise ValueError('unknown award source cache key')
    key = source_key.strip()
    reset = _SOURCE_RUNTIME_RESETS.get(key)
    if reset is None:
        raise ValueError(f'unknown award source cache key: {key!r}')
    if key in BUNDLED_SOURCE_KEYS:
        reset()
        return True
    try:
        return cache.request_source_refresh(key)
    finally:
        if key == 'pulitzer':
            pulitzer.mark_official_refresh_requested()
        else:
            reset()


def prepare_source_lookup(source_key):
    """Retry pending entries in the background even if RAM contains fallback."""
    if cache.source_refresh_pending(source_key):
        reset = _SOURCE_RUNTIME_RESETS.get(source_key)
        if reset is not None:
            reset()
