"""Official PEN/Faulkner Award for Fiction source.

Historical Winners and Finalists come from the award landing page for
1981-2018. Modern years use verified Winner and Finalists announcement
HTML. Longlist is ignored. Other PEN/Faulkner Foundation honors are
excluded. REST is discovery-only for years after the verified map.
"""

from __future__ import annotations

import json
import re
import threading
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from urllib.parse import urlparse

from .. import cache
from ..matching import normalize_title_conjunctions
from ..model import AwardResult

TIMEOUT_SECONDS = 30
SOURCE_KEY = 'pen_faulkner'
AWARD_NAME = 'PEN/Faulkner Award for Fiction'
SOURCE_NAME = 'PEN/Faulkner Foundation'
CATEGORY = 'Fiction'
SITE_ORIGIN = 'https://www.penfaulkner.org'
SOURCE_HOME_URL = SITE_ORIGIN + '/our-awards/pen-faulkner-award/'
AWARD_NEWS_REST_URL = (
    SITE_ORIGIN + '/wp-json/wp/v2/posts?categories=238&per_page=100'
)
ARCHIVE_MIN_YEAR = 1981
HISTORICAL_ARCHIVE_MAX_YEAR = 2018
MAX_VERIFIED_YEAR = 2026
ARCHIVE_CACHE_VERSION = 1
YEAR_CACHE_VERSION = 1
ARCHIVE_ENTRY_KIND = 'archive'
ARCHIVE_ENTRY_KEY = 'landing'
YEAR_ENTRY_KIND = 'years'
HISTORICAL_CACHE_TTL_SECONDS = 180 * 24 * 60 * 60
CURRENT_CACHE_BASE_TTL_SECONDS = 7 * 24 * 60 * 60
CURRENT_CACHE_REFRESH_OFFSET_SECONDS = 13 * 60 * 60
CURRENT_CACHE_TTL_SECONDS = (
    CURRENT_CACHE_BASE_TTL_SECONDS + CURRENT_CACHE_REFRESH_OFFSET_SECONDS
)

# 2021 dedicated Finalists post canonicalizes to the 2022 Finalists page.
# The 2021 Winner announcement is the remaining first-party HTML that names
# both the Winner and the other Finalists.
VERIFIED_YEAR_URLS = {
    2019: {
        'winner': (
            SITE_ORIGIN
            + '/2019/04/29/announcing-the-2019-pen-faulkner-award-winner/'
        ),
        'finalists': (
            SITE_ORIGIN
            + '/2019/03/05/announcing-the-2019-pen-faulkner-award-finalists/'
        ),
    },
    2020: {
        'winner': (
            SITE_ORIGIN
            + '/2020/04/06/announcing-the-winner-of-the-2020-pen-faulkner'
            '-award-for-fiction-sea-monsters-by-chloe-aridjis/'
        ),
        'finalists': (
            SITE_ORIGIN
            + '/2020/03/03/announcing-the-2020-pen-faulkner-award-for'
            '-fiction-finalists/'
        ),
    },
    2021: {
        'winner': (
            SITE_ORIGIN
            + '/2021/04/06/announcing-the-winner-of-the-2021-pen-faulkner'
            '-award-for-fiction/'
        ),
        'finalists': (
            SITE_ORIGIN
            + '/2021/04/06/announcing-the-winner-of-the-2021-pen-faulkner'
            '-award-for-fiction/'
        ),
    },
    2022: {
        'winner': (
            SITE_ORIGIN
            + '/2022/04/05/announcing-the-winner-of-the-2022-pen-faulkner'
            '-award-for-fiction/'
        ),
        'finalists': (
            SITE_ORIGIN
            + '/2022/03/02/announcing-the-finalists-for-the-2022-pen-faulkner'
            '-award-for-fiction/'
        ),
    },
    2023: {
        'winner': (
            SITE_ORIGIN
            + '/2023/04/04/announcing-the-winner-of-the-2023-pen-faulkner'
            '-award-for-fiction/'
        ),
        'finalists': (
            SITE_ORIGIN
            + '/2023/03/07/announcing-the-finalists-for-the-2023-pen-faulkner'
            '-award-for-fiction/'
        ),
    },
    2024: {
        'winner': (
            SITE_ORIGIN
            + '/2024/04/02/announcing-the-winner-of-the-2024-pen-faulkner'
            '-award-for-fiction/'
        ),
        'finalists': (
            SITE_ORIGIN
            + '/2024/03/05/announcing-the-finalists-for-the-2024-pen-faulkner'
            '-award-for-fiction/'
        ),
    },
    2025: {
        'winner': (
            SITE_ORIGIN
            + '/2025/04/07/announcing-the-winner-of-the-2025-pen-faulkner'
            '-award-for-fiction/'
        ),
        'finalists': (
            SITE_ORIGIN
            + '/2025/03/03/announcing-the-finalists-for-the-2025-pen-faulkner'
            '-award-for-fiction/'
        ),
    },
    2026: {
        'winner': (
            SITE_ORIGIN
            + '/2026/04/06/announcing-the-winner-of-the-2026-pen-faulkner'
            '-award-for-fiction/'
        ),
        'finalists': (
            SITE_ORIGIN
            + '/2026/03/02/announcing-the-finalists-for-the-2026-pen-faulkner'
            '-award-for-fiction/'
        ),
    },
}

_YEAR_STATES = frozenset({'absent', 'finalist', 'winner'})
_PARSED_STATUSES = frozenset({'Winner', 'Finalist'})
_STATUS_WEIGHT = {
    'Finalist': 1,
    'Winner': 2,
}
_RECORD_CACHE_FIELDS = (
    'award_year',
    'category',
    'source_url',
    'status',
    'work_author',
    'work_title',
)
_ARCHIVE_COVERAGE_FIELDS = frozenset({
    'kind',
    'max_year',
    'min_year',
})
_YEAR_COVERAGE_FIELDS = frozenset({'award_year', 'state'})
_OFFICIAL_HTML_HOSTS = frozenset({
    'penfaulkner.org',
    'www.penfaulkner.org',
})
_IDENTITY_MARKER = 'pen/faulkner award for fiction'
_OTHER_PROGRAM_TITLE_MARKERS = (
    'hemingway',
    'malamud',
    'literary champion',
)
_LONG_LIST_MARKER = 'longlist'
_VOID_TAGS = frozenset({
    'area',
    'base',
    'br',
    'col',
    'embed',
    'hr',
    'img',
    'input',
    'link',
    'meta',
    'source',
    'track',
    'wbr',
})
_IGNORE_TAGS = frozenset({'script', 'style', 'svg', 'noscript', 'iframe'})
_YEAR_ONLY_RE = re.compile(r'^(19|20)\d{2}$')
_INITIALS_SPACE_RE = re.compile(r'\b([A-Za-z])\.\s+')
_AUTHOR_TITLE_RE = re.compile(
    r'^(?P<author>.+?),\s+(?P<title>.+)$',
    re.DOTALL,
)
_WINNER_SENTENCE_RE = re.compile(
    r'(?P<author>[A-Z\u00C0-\u024F][\w .\'\u2018\u2019\u00C0-\u024F-]*?)'
    r'(?:[\'\u2018\u2019]s|[\'\u2018\u2019])\s+'
    r'(?P<title>[A-Z0-9\u00C0-\u024F][^()]{0,160}?)\s*'
    r'(?:\([^)]*\))?\s+has been selected as the winner of the '
    r'(?P<year>19\d{2}|20\d{2})\s+PEN/Faulkner Award for Fiction',
    re.IGNORECASE,
)
_FIVE_FINALISTS_RE = re.compile(
    r'(?:the\s+)?(?:five\s+)?finalists for the (?P<year>19\d{2}|20\d{2})\s+'
    r'PEN/Faulkner Award for Fiction',
    re.IGNORECASE,
)
_TITLE_BY_AUTHOR_RE = re.compile(
    r'(?P<title>[A-Z0-9\u00C0-\u024F\'\u2018\u2019][^()]{0,140}?)\s+by\s+'
    r'(?P<author>[\'\u2018\u2019A-Z\u00C0-\u024F][^()]{0,90}?)\s*'
    r'\((?P<publisher>[^)]+)\)',
)
_AUTHOR_FOR_TITLE_RE = re.compile(
    r'(?P<author>[A-Z\u00C0-\u024F][^()]{1,90}?)\s+for\s+'
    r'(?P<title>[A-Z0-9\u00C0-\u024F\'\u2018\u2019][^()]{0,140}?)\s*'
    r'\((?P<publisher>[^)]+)\)',
)
_OTHER_FINALISTS_RE = re.compile(
    r'authors of each of the other finalists\s*[-\u2013\u2014:]\s*'
    r'(?P<body>.+?)\s*(?:will receive|each receive)',
    re.IGNORECASE | re.DOTALL,
)
_OTHER_FINALIST_ITEM_RE = re.compile(
    r'(?P<author>[A-Z\u00C0-\u024F][^,]{1,90}?),\s+for\s+'
    r'(?P<title>.+?)\s*$',
)
_AUTHOR_PREFIX_RE = re.compile(
    r'^(?:washington,\s*dc\s*[-\u2013\u2014]\s*|'
    r'we are excited to announce that\s+)+',
    re.IGNORECASE,
)
_BROWSER_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/122.0.0.0 Safari/537.36'
    ),
    'Accept': (
        'text/html,application/xhtml+xml,application/json,'
        'application/xml;q=0.9,*/*;q=0.8'
    ),
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'identity',
}


class PenFaulknerSourceError(RuntimeError):
    """Raised when official PEN/Faulkner pages are blocked or unusable."""


@dataclass(frozen=True, slots=True)
class _ParsedRecord:
    award_year: int
    category: str
    status: str
    work_title: str
    work_author: str
    source_url: str


@dataclass(frozen=True, slots=True)
class _ArchiveSnapshot:
    records: tuple[_ParsedRecord, ...]
    source_url: str


@dataclass(frozen=True, slots=True)
class _YearSnapshot:
    award_year: int
    state: str
    source_urls: tuple[str, ...]
    records: tuple[_ParsedRecord, ...]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _current_calendar_year() -> int:
    """UTC calendar year. Tests may patch _utc_now or this helper."""
    return _utc_now().year


def _collapse_ws(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def _year_entry_key(year: int) -> str:
    return str(year)


def _classes(attr: dict[str, str]) -> set[str]:
    return {part for part in attr.get('class', '').split() if part}


def _official_page_url(url: str) -> str | None:
    parsed = urlparse(url)
    host = (parsed.hostname or '').casefold()
    if host not in _OFFICIAL_HTML_HOSTS:
        return None
    if parsed.scheme != 'https':
        return None
    return url


def _path_year(url: str) -> int | None:
    parsed = urlparse(url)
    parts = [part for part in (parsed.path or '').split('/') if part]
    if not parts or not _YEAR_ONLY_RE.fullmatch(parts[0]):
        return None
    return int(parts[0])


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _build_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(CookieJar())
    )


def _read_response_body(response) -> str:
    return response.read().decode('utf-8', errors='replace')


def _fetch_response(url: str) -> tuple[int, str, str]:
    """Return (status, body, final_url). HTTP 404 is returned; others raise."""
    request = urllib.request.Request(url, headers=dict(_BROWSER_HEADERS))
    try:
        with _build_opener().open(request, timeout=TIMEOUT_SECONDS) as response:
            status = getattr(response, 'status', None) or response.getcode()
            body = _read_response_body(response)
            final_url = response.geturl() or url
    except urllib.error.HTTPError as exc:
        body = ''
        try:
            body = exc.read().decode('utf-8', errors='replace')
        except Exception:
            pass
        if exc.code == 404:
            return 404, body, url
        raise PenFaulknerSourceError(
            f'PEN/Faulkner request failed with HTTP {exc.code} for {url}'
        ) from exc
    except urllib.error.URLError as exc:
        raise PenFaulknerSourceError(
            f'PEN/Faulkner request failed for {url}: {exc.reason}'
        ) from exc
    if status == 404:
        return 404, body, final_url
    if status != 200:
        raise PenFaulknerSourceError(
            f'PEN/Faulkner request failed with HTTP {status} for {url}'
        )
    return int(status), body, final_url


def _fetch_html(url: str) -> tuple[str, str]:
    status, body, final_url = _fetch_response(url)
    if status != 200:
        raise PenFaulknerSourceError(
            f'PEN/Faulkner request failed with HTTP {status} for {url}'
        )
    return body, final_url


_landing_snapshot_cache: _ArchiveSnapshot | None = None
_year_snapshot_cache: dict[int, _YearSnapshot] = {}
_cache_lock = threading.Lock()


def _reset_runtime_state() -> None:
    """Clear in-process PEN/Faulkner caches. Does not delete disk cache."""
    global _landing_snapshot_cache
    with _cache_lock:
        _landing_snapshot_cache = None
        _year_snapshot_cache.clear()


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

def _extract_title(html: str) -> str:
    match = re.search(r'<title>([^<]+)</title>', html, re.IGNORECASE)
    if match is None:
        return ''
    return _collapse_ws(match.group(1))


def _html_has_award_identity(html: str) -> bool:
    return _IDENTITY_MARKER in html.casefold()


def _title_is_other_program(title: str) -> bool:
    folded = title.casefold()
    return any(marker in folded for marker in _OTHER_PROGRAM_TITLE_MARKERS)


def _page_declares_award_year(html: str, award_year: int) -> bool:
    token = f'{award_year} pen/faulkner award for fiction'
    return token in html.casefold()


def _require_official_html(html: str, url: str, *, award_year: int | None) -> str:
    official = _official_page_url(url)
    if official is None:
        raise PenFaulknerSourceError(f'PEN/Faulkner URL is not official: {url}')
    if not _html_has_award_identity(html):
        raise PenFaulknerSourceError(
            'PEN/Faulkner page did not identify the PEN/Faulkner Award for Fiction'
        )
    title = _extract_title(html)
    if _title_is_other_program(title):
        raise PenFaulknerSourceError(
            'PEN/Faulkner page identified a different Foundation award'
        )
    if award_year is not None:
        path_year = _path_year(url)
        if path_year is not None and path_year != award_year:
            raise PenFaulknerSourceError(
                f'PEN/Faulkner {award_year} URL redirected to year {path_year}'
            )
        if not _page_declares_award_year(html, award_year):
            raise PenFaulknerSourceError(
                f'PEN/Faulkner page did not declare award year {award_year}'
            )
    return official


def _require_landing_identity(html: str, url: str) -> str:
    official = _require_official_html(html, url, award_year=None)
    if 'pen/faulkner award' not in html.casefold():
        raise PenFaulknerSourceError(
            'PEN/Faulkner landing page did not identify the award'
        )
    return official


# ---------------------------------------------------------------------------
# Normalization / matching
# ---------------------------------------------------------------------------

def _normalize_text(value: str) -> str:
    text = unicodedata.normalize('NFKC', value)
    text = (
        text.replace('\u2018', "'")
        .replace('\u2019', "'")
        .replace('\u201c', '"')
        .replace('\u201d', '"')
        .replace('\u00b4', "'")
        .replace('`', "'")
    )
    text = _collapse_ws(text)
    text = text.casefold()
    text = _INITIALS_SPACE_RE.sub(r'\1.', text)
    return text


def _titles_match(query_title: str, record_title: str) -> bool:
    query_norm = normalize_title_conjunctions(_normalize_text(query_title))
    record_norm = normalize_title_conjunctions(_normalize_text(record_title))
    return query_norm == record_norm


def _authors_match(query_author: str, record_author: str) -> bool:
    return _normalize_text(query_author) == _normalize_text(record_author)


# Verified 2020 first-party inconsistencies only. Not general fuzzy matching.
_SEA_MONSTERS_TITLE_KEY = normalize_title_conjunctions(_normalize_text('Sea Monsters'))
_SEA_MONSTERS_AUTHOR_KEYS = frozenset({
    _normalize_text('Chloe Arijdis'),
    _normalize_text('Chloe Aridjis'),
})
_SEA_MONSTERS_CANONICAL_AUTHOR_KEY = _normalize_text('Chloe Aridjis')
_NIGHT_SWIMMERS_TITLE_KEYS = frozenset({
    normalize_title_conjunctions(_normalize_text('Night Swimmers')),
    normalize_title_conjunctions(_normalize_text('The Night Swimmers')),
})
_NIGHT_SWIMMERS_CANONICAL_TITLE_KEY = normalize_title_conjunctions(
    _normalize_text('Night Swimmers')
)
_PETER_ROCK_AUTHOR_KEY = _normalize_text('Peter Rock')


def _title_key(title: str) -> str:
    return normalize_title_conjunctions(_normalize_text(title))


def _identity_key(record: _ParsedRecord) -> tuple[int, str, str]:
    title_key = _title_key(record.work_title)
    author_key = _normalize_text(record.work_author)
    if record.award_year == 2020:
        if (
            title_key == _SEA_MONSTERS_TITLE_KEY
            and author_key in _SEA_MONSTERS_AUTHOR_KEYS
        ):
            author_key = _SEA_MONSTERS_CANONICAL_AUTHOR_KEY
        if (
            author_key == _PETER_ROCK_AUTHOR_KEY
            and title_key in _NIGHT_SWIMMERS_TITLE_KEYS
        ):
            title_key = _NIGHT_SWIMMERS_CANONICAL_TITLE_KEY
    return (record.award_year, title_key, author_key)


def _record_matches(record: _ParsedRecord, title: str, author: str) -> bool:
    if record.award_year == 2020:
        query_title = _title_key(title)
        record_title = _title_key(record.work_title)
        query_author = _normalize_text(author)
        record_author = _normalize_text(record.work_author)
        if (
            query_title == _SEA_MONSTERS_TITLE_KEY
            and record_title == _SEA_MONSTERS_TITLE_KEY
            and query_author in _SEA_MONSTERS_AUTHOR_KEYS
            and record_author in _SEA_MONSTERS_AUTHOR_KEYS
        ):
            return True
        if (
            query_author == _PETER_ROCK_AUTHOR_KEY
            and record_author == _PETER_ROCK_AUTHOR_KEY
            and query_title in _NIGHT_SWIMMERS_TITLE_KEYS
            and record_title in _NIGHT_SWIMMERS_TITLE_KEYS
        ):
            return True
    return _titles_match(title, record.work_title) and _authors_match(
        author, record.work_author
    )


# ---------------------------------------------------------------------------
# Merge / validation
# ---------------------------------------------------------------------------

def _dedupe_records(records: list[_ParsedRecord]) -> tuple[_ParsedRecord, ...]:
    best: dict[tuple[int, str, str], _ParsedRecord] = {}
    order: list[tuple[int, str, str]] = []
    for record in records:
        key = _identity_key(record)
        existing = best.get(key)
        if existing is None:
            best[key] = record
            order.append(key)
            continue
        if _STATUS_WEIGHT[record.status] > _STATUS_WEIGHT[existing.status]:
            best[key] = record
    return tuple(best[key] for key in order)


def _validate_historical_records(records: tuple[_ParsedRecord, ...]) -> None:
    by_year: dict[int, list[_ParsedRecord]] = {}
    seen: set[tuple[int, str, str]] = set()
    for record in records:
        if record.award_year < ARCHIVE_MIN_YEAR:
            raise PenFaulknerSourceError(
                'PEN/Faulkner historical archive contained a pre-1981 year'
            )
        if record.award_year > HISTORICAL_ARCHIVE_MAX_YEAR:
            raise PenFaulknerSourceError(
                'PEN/Faulkner historical archive contained a post-2018 year'
            )
        if record.category != CATEGORY:
            raise PenFaulknerSourceError(
                'PEN/Faulkner historical archive contained a non-Fiction record'
            )
        if record.status not in _PARSED_STATUSES:
            raise PenFaulknerSourceError(
                'PEN/Faulkner historical archive contained an unsupported status'
            )
        if not record.work_title or not record.work_author:
            raise PenFaulknerSourceError(
                'PEN/Faulkner historical archive contained an incomplete work'
            )
        key = _identity_key(record)
        if key in seen:
            raise PenFaulknerSourceError(
                'PEN/Faulkner historical archive contained duplicate works'
            )
        seen.add(key)
        by_year.setdefault(record.award_year, []).append(record)
    expected = set(range(ARCHIVE_MIN_YEAR, HISTORICAL_ARCHIVE_MAX_YEAR + 1))
    present = set(by_year)
    if present != expected:
        missing = sorted(expected - present)
        extra = sorted(present - expected)
        raise PenFaulknerSourceError(
            'PEN/Faulkner historical archive years were incomplete: '
            f'missing={missing!r} extra={extra!r}'
        )
    for year, year_records in by_year.items():
        winners = [item for item in year_records if item.status == 'Winner']
        finalists = [item for item in year_records if item.status == 'Finalist']
        if len(winners) != 1:
            raise PenFaulknerSourceError(
                f'PEN/Faulkner {year} did not contain exactly one Winner'
            )
        if not finalists:
            raise PenFaulknerSourceError(
                f'PEN/Faulkner {year} did not contain named Finalists'
            )


def _validate_modern_records(
    records: tuple[_ParsedRecord, ...],
    award_year: int,
    state: str,
) -> None:
    seen: set[tuple[int, str, str]] = set()
    winners = 0
    finalists = 0
    for record in records:
        if record.award_year != award_year:
            raise PenFaulknerSourceError(
                f'PEN/Faulkner {award_year} contained a mismatched year'
            )
        if record.category != CATEGORY:
            raise PenFaulknerSourceError(
                f'PEN/Faulkner {award_year} contained a non-Fiction record'
            )
        if record.status not in _PARSED_STATUSES:
            raise PenFaulknerSourceError(
                f'PEN/Faulkner {award_year} contained an unsupported status'
            )
        if not record.work_title or not record.work_author:
            raise PenFaulknerSourceError(
                f'PEN/Faulkner {award_year} contained an incomplete work'
            )
        key = _identity_key(record)
        if key in seen:
            raise PenFaulknerSourceError(
                f'PEN/Faulkner {award_year} contained duplicate works'
            )
        seen.add(key)
        if record.status == 'Winner':
            winners += 1
        else:
            finalists += 1
    if state == 'absent':
        if records:
            raise PenFaulknerSourceError(
                f'PEN/Faulkner {award_year} absent state contained records'
            )
        return
    if state == 'finalist':
        if winners:
            raise PenFaulknerSourceError(
                f'PEN/Faulkner {award_year} finalist state contained a Winner'
            )
        if ARCHIVE_MIN_YEAR <= award_year <= MAX_VERIFIED_YEAR:
            if winners + finalists != 5:
                raise PenFaulknerSourceError(
                    f'PEN/Faulkner {award_year} Finalists were not five works'
                )
        elif not finalists:
            raise PenFaulknerSourceError(
                f'PEN/Faulkner {award_year} did not contain Finalists'
            )
        return
    if state == 'winner':
        if winners != 1:
            raise PenFaulknerSourceError(
                f'PEN/Faulkner {award_year} did not contain exactly one Winner'
            )
        if ARCHIVE_MIN_YEAR <= award_year <= MAX_VERIFIED_YEAR:
            if winners + finalists != 5:
                raise PenFaulknerSourceError(
                    f'PEN/Faulkner {award_year} did not contain five honors'
                )
        return
    raise PenFaulknerSourceError(
        f'PEN/Faulkner {award_year} had an unsupported state'
    )


def _classify_year_state(records: tuple[_ParsedRecord, ...]) -> str:
    if any(record.status == 'Winner' for record in records):
        return 'winner'
    if any(record.status == 'Finalist' for record in records):
        return 'finalist'
    return 'absent'


# ---------------------------------------------------------------------------
# Historical landing parser
# ---------------------------------------------------------------------------

class _LandingParser(HTMLParser):
    """Collect 1981-2018 h2 year blocks with WINNER:/FINALISTS: lines."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignore_depth = 0
        self._in_entry = False
        self._entry_depth = 0
        self._heading = False
        self._heading_parts: list[str] = []
        self._in_em = False
        self._year: int | None = None
        self._mode: str | None = None
        self._line_parts: list[tuple[str, bool]] = []
        self.years: dict[int, dict[str, list[tuple[str, str]]]] = {}

    def handle_starttag(self, tag, attrs):
        if self._ignore_depth:
            if tag not in _VOID_TAGS:
                self._ignore_depth += 1
            return
        if tag in _IGNORE_TAGS:
            self._ignore_depth = 1
            return
        attr = {key: value or '' for key, value in attrs}
        if (
            tag in {'div', 'article'}
            and 'entry-content' in _classes(attr)
            and not self._in_entry
        ):
            self._in_entry = True
            self._entry_depth = 1
            return
        if not self._in_entry:
            return
        if tag not in _VOID_TAGS:
            self._entry_depth += 1
        if tag in {'h1', 'h2', 'h3', 'h4'}:
            self._flush_line()
            self._heading = True
            self._heading_parts = []
            return
        if tag == 'em':
            self._in_em = True
            return
        if tag in {'br', 'p', 'li'}:
            self._flush_line()

    def handle_endtag(self, tag):
        if self._ignore_depth:
            if tag not in _VOID_TAGS:
                self._ignore_depth -= 1
            return
        if tag == 'em':
            self._in_em = False
        if tag in {'h1', 'h2', 'h3', 'h4'} and self._heading:
            self._finish_heading(tag)
            self._heading = False
            self._heading_parts = []
        if tag in {'p', 'li'} and self._in_entry:
            self._flush_line()
        if self._in_entry and tag not in _VOID_TAGS:
            self._entry_depth -= 1
            if self._entry_depth <= 0:
                self._flush_line()
                self._in_entry = False

    def handle_data(self, data):
        if self._ignore_depth or not self._in_entry:
            return
        if self._heading:
            self._heading_parts.append(data)
            return
        if self._year is None:
            return
        text = data
        if not text:
            return
        self._line_parts.append((text, self._in_em))

    def _finish_heading(self, tag: str) -> None:
        heading = _collapse_ws(''.join(self._heading_parts))
        if tag == 'h2' and _YEAR_ONLY_RE.fullmatch(heading):
            year = int(heading)
            if ARCHIVE_MIN_YEAR <= year <= HISTORICAL_ARCHIVE_MAX_YEAR:
                self._year = year
                self._mode = None
                self.years.setdefault(year, {'Winner': [], 'Finalist': []})
                return
            self._year = None
            self._mode = None
            return
        if tag in {'h2', 'h3'} and self._year is not None:
            # Later chrome headings end the historical year block.
            if not _YEAR_ONLY_RE.fullmatch(heading):
                self._year = None
                self._mode = None

    def _flush_line(self) -> None:
        if self._year is None or not self._line_parts:
            self._line_parts = []
            return
        raw = _collapse_ws(''.join(part for part, _em in self._line_parts))
        em_text = _collapse_ws(
            ''.join(part for part, in_em in self._line_parts if in_em)
        )
        self._line_parts = []
        if not raw:
            return
        label = raw.replace(' ', '').casefold()
        if label.startswith('winner:'):
            self._mode = 'Winner'
            remainder = raw.split(':', 1)[1].strip()
            if remainder:
                self._add_work(remainder, em_text)
            return
        if label.startswith('finalists:'):
            self._mode = 'Finalist'
            remainder = raw.split(':', 1)[1].strip()
            if remainder:
                self._add_work(remainder, em_text)
            return
        if self._mode is None:
            return
        self._add_work(raw, em_text)

    def _add_work(self, raw: str, em_text: str) -> None:
        if self._year is None or self._mode is None:
            return
        parsed = _parse_author_title_line(raw, em_text)
        if parsed is None:
            return
        author, title = parsed
        bucket = self.years[self._year][self._mode]
        bucket.append((title, author))

    def close(self) -> None:
        self._flush_line()
        super().close()


def _parse_author_title_line(
    raw: str,
    em_text: str,
) -> tuple[str, str] | None:
    text = _collapse_ws(raw)
    if not text or text.endswith(':'):
        return None
    match = _AUTHOR_TITLE_RE.fullmatch(text)
    if match is None:
        return None
    author = _collapse_ws(match.group('author'))
    title = _collapse_ws(em_text) if em_text else _collapse_ws(match.group('title'))
    if not author or not title:
        return None
    return author, title


def _parse_landing_html(html: str, source_url: str) -> tuple[_ParsedRecord, ...]:
    parser = _LandingParser()
    parser.feed(html)
    parser.close()
    records: list[_ParsedRecord] = []
    for year in range(ARCHIVE_MIN_YEAR, HISTORICAL_ARCHIVE_MAX_YEAR + 1):
        payload = parser.years.get(year)
        if payload is None:
            continue
        for title, author in payload.get('Winner', ()):
            records.append(
                _ParsedRecord(
                    award_year=year,
                    category=CATEGORY,
                    status='Winner',
                    work_title=title,
                    work_author=author,
                    source_url=source_url,
                )
            )
        for title, author in payload.get('Finalist', ()):
            records.append(
                _ParsedRecord(
                    award_year=year,
                    category=CATEGORY,
                    status='Finalist',
                    work_title=title,
                    work_author=author,
                    source_url=source_url,
                )
            )
    return _dedupe_records(records)


# ---------------------------------------------------------------------------
# Article body extraction and modern parsers
# ---------------------------------------------------------------------------

class _ArticleBodyParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignore_depth = 0
        self._in_entry = False
        self._entry_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if self._ignore_depth:
            if tag not in _VOID_TAGS:
                self._ignore_depth += 1
            return
        if tag in _IGNORE_TAGS:
            self._ignore_depth = 1
            return
        attr = {key: value or '' for key, value in attrs}
        if (
            tag in {'div', 'article'}
            and 'entry-content' in _classes(attr)
            and not self._in_entry
        ):
            self._in_entry = True
            self._entry_depth = 1
            return
        if not self._in_entry:
            return
        if tag not in _VOID_TAGS:
            self._entry_depth += 1
        if tag in {'p', 'h1', 'h2', 'h3', 'li', 'br', 'div'}:
            self._parts.append('\n')

    def handle_endtag(self, tag):
        if self._ignore_depth:
            if tag not in _VOID_TAGS:
                self._ignore_depth -= 1
            return
        if self._in_entry and tag not in _VOID_TAGS:
            self._entry_depth -= 1
            if self._entry_depth <= 0:
                self._in_entry = False

    def handle_data(self, data):
        if self._ignore_depth or not self._in_entry:
            return
        self._parts.append(data)

    def text(self) -> str:
        return ''.join(self._parts)


def _article_body(html: str) -> str:
    parser = _ArticleBodyParser()
    parser.feed(html)
    parser.close()
    return parser.text()


def _finalists_list_chunk(body: str, award_year: int) -> str | None:
    match = _FIVE_FINALISTS_RE.search(body)
    if match is None or int(match.group('year')) != award_year:
        return None
    start = match.end()
    remainder = body[start:]
    are_match = re.search(r'\bfinalists are:?\s*', remainder, re.IGNORECASE)
    if are_match is not None:
        remainder = remainder[are_match.end():]
    end_markers = (
        'this year’s judges',
        "this year's judges",
        'about the authors',
        'about the finalists',
        'the “first among equals”',
        'the "first among equals"',
        'the winner, who will receive',
        'the winner who will receive',
    )
    folded = remainder.casefold()
    ends = [len(remainder)]
    for marker in end_markers:
        index = folded.find(marker)
        if index >= 0:
            ends.append(index)
    return remainder[: min(ends)]


def _pairs_from_chunk(chunk: str) -> list[tuple[str, str]]:
    by_author = [
        (_collapse_ws(match.group('title')), _collapse_ws(match.group('author')))
        for match in _TITLE_BY_AUTHOR_RE.finditer(chunk)
    ]
    if len(by_author) >= 5:
        return by_author[:5]
    for_title = [
        (_collapse_ws(match.group('title')), _collapse_ws(match.group('author')))
        for match in _AUTHOR_FOR_TITLE_RE.finditer(chunk)
    ]
    if len(for_title) >= 5:
        return for_title[:5]
    if len(by_author) > len(for_title):
        return by_author
    return for_title


def _parse_finalists_html(
    html: str,
    award_year: int,
    source_url: str,
) -> tuple[_ParsedRecord, ...]:
    body = _article_body(html)
    chunk = _finalists_list_chunk(body, award_year)
    if chunk is None:
        return ()
    pairs = _pairs_from_chunk(chunk)
    records = [
        _ParsedRecord(
            award_year=award_year,
            category=CATEGORY,
            status='Finalist',
            work_title=title,
            work_author=author,
            source_url=source_url,
        )
        for title, author in pairs
    ]
    return tuple(records)


def _parse_winner_html(
    html: str,
    award_year: int,
    source_url: str,
) -> _ParsedRecord | None:
    body = _article_body(html)
    for match in _WINNER_SENTENCE_RE.finditer(body):
        year = int(match.group('year'))
        if year != award_year:
            continue
        author = _collapse_ws(_AUTHOR_PREFIX_RE.sub('', match.group('author')))
        title = _collapse_ws(match.group('title'))
        if not author or not title:
            continue
        if 'announce' in author.casefold():
            continue
        return _ParsedRecord(
            award_year=award_year,
            category=CATEGORY,
            status='Winner',
            work_title=title,
            work_author=author,
            source_url=source_url,
        )
    return None


def _parse_other_finalists_from_winner_body(
    html: str,
    award_year: int,
    source_url: str,
) -> tuple[_ParsedRecord, ...]:
    body = _article_body(html)
    match = _OTHER_FINALISTS_RE.search(body)
    if match is None:
        return ()
    raw_items = [part.strip() for part in match.group('body').split(';')]
    records: list[_ParsedRecord] = []
    for item in raw_items:
        cleaned = _collapse_ws(item).strip(' .')
        cleaned = re.sub(r'^and\s+', '', cleaned, flags=re.IGNORECASE)
        item_match = _OTHER_FINALIST_ITEM_RE.fullmatch(cleaned)
        if item_match is None:
            continue
        records.append(
            _ParsedRecord(
                award_year=award_year,
                category=CATEGORY,
                status='Finalist',
                work_title=_collapse_ws(item_match.group('title')).rstrip(' \t-–—'),
                work_author=_collapse_ws(item_match.group('author')),
                source_url=source_url,
            )
        )
    return tuple(records)


# ---------------------------------------------------------------------------
# REST discovery (years after MAX_VERIFIED_YEAR)
# ---------------------------------------------------------------------------

def _rest_text(value) -> str:
    if isinstance(value, dict):
        rendered = value.get('rendered')
        if isinstance(rendered, str):
            return rendered
        return ''
    if isinstance(value, str):
        return value
    return ''


def _rest_candidate_role(title: str, slug: str, link: str) -> str | None:
    blob = f'{title} {slug} {link}'.casefold()
    if _LONG_LIST_MARKER in blob:
        return None
    if any(marker in blob for marker in _OTHER_PROGRAM_TITLE_MARKERS):
        return None
    if 'pen/faulkner award for fiction' not in blob and 'pen-faulkner-award' not in blob:
        if 'pen/faulkner award' not in blob and 'penfaulkner-award' not in blob:
            return None
        if 'fiction' not in blob and 'pen-faulkner-award-for-fiction' not in blob:
            if 'penfaulkner-award-for-fiction' not in blob:
                return None
    if 'winner' in blob:
        return 'winner'
    if 'finalist' in blob:
        return 'finalist'
    return None


def _discover_year_urls(award_year: int, payload) -> dict[str, str]:
    if not isinstance(payload, list):
        raise PenFaulknerSourceError(
            'PEN/Faulkner Award News index was not a JSON list'
        )
    found: dict[str, list[str]] = {'winner': [], 'finalists': []}
    for item in payload:
        if not isinstance(item, dict):
            continue
        title = _collapse_ws(_rest_text(item.get('title')))
        slug = item.get('slug') if isinstance(item.get('slug'), str) else ''
        link = item.get('link') if isinstance(item.get('link'), str) else ''
        official = _official_page_url(link)
        if official is None:
            continue
        role = _rest_candidate_role(title, slug, official)
        if role is None:
            continue
        path_year = _path_year(official)
        if path_year is not None and path_year != award_year:
            continue
        key = 'finalists' if role == 'finalist' else 'winner'
        if official not in found[key]:
            found[key].append(official)
    selected: dict[str, str] = {}
    for key, urls in found.items():
        if len(urls) > 1:
            raise PenFaulknerSourceError(
                f'PEN/Faulkner {award_year} discovery found ambiguous {key} URLs'
            )
        if len(urls) == 1:
            selected[key] = urls[0]
    return selected


def _acquire_discovery_urls(award_year: int) -> dict[str, str]:
    body, _final_url = _fetch_html(AWARD_NEWS_REST_URL)
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise PenFaulknerSourceError(
            'PEN/Faulkner Award News index was unreadable'
        ) from exc
    return _discover_year_urls(award_year, payload)


# ---------------------------------------------------------------------------
# Acquire live snapshots
# ---------------------------------------------------------------------------

def _year_urls(award_year: int) -> dict[str, str]:
    mapped = VERIFIED_YEAR_URLS.get(award_year)
    if mapped is not None:
        return dict(mapped)
    return _acquire_discovery_urls(award_year)


def _acquire_live_landing() -> _ArchiveSnapshot:
    html, final_url = _fetch_html(SOURCE_HOME_URL)
    official = _require_landing_identity(html, final_url)
    records = _parse_landing_html(html, SOURCE_HOME_URL)
    _validate_historical_records(records)
    return _ArchiveSnapshot(records=records, source_url=official or SOURCE_HOME_URL)


def _acquire_live_year(award_year: int) -> _YearSnapshot:
    urls = _year_urls(award_year)
    winner_url = urls.get('winner')
    finalists_url = urls.get('finalists')
    if not winner_url and not finalists_url:
        return _YearSnapshot(
            award_year=award_year,
            state='absent',
            source_urls=(),
            records=(),
        )
    fetched: dict[str, tuple[str, str]] = {}
    unique_urls = []
    for url in (winner_url, finalists_url):
        if url and url not in unique_urls:
            unique_urls.append(url)
    last_error: PenFaulknerSourceError | None = None
    for url in unique_urls:
        try:
            html, final_url = _fetch_html(url)
            official = _require_official_html(
                html, final_url, award_year=award_year
            )
            fetched[url] = (html, official)
        except PenFaulknerSourceError as exc:
            last_error = exc
    if not fetched:
        if last_error is not None:
            raise last_error
        raise PenFaulknerSourceError(
            f'PEN/Faulkner {award_year} announcements were unavailable'
        )
    records: list[_ParsedRecord] = []
    source_urls: list[str] = []
    if finalists_url and finalists_url in fetched:
        html, official = fetched[finalists_url]
        finalist_records = _parse_finalists_html(html, award_year, official)
        records.extend(finalist_records)
        if official not in source_urls:
            source_urls.append(official)
    if not any(item.status == 'Finalist' for item in records):
        fallback_url = winner_url if winner_url in fetched else finalists_url
        if fallback_url and fallback_url in fetched:
            html, official = fetched[fallback_url]
            records.extend(
                _parse_other_finalists_from_winner_body(
                    html, award_year, official
                )
            )
            if official not in source_urls:
                source_urls.append(official)
    if winner_url and winner_url in fetched:
        html, official = fetched[winner_url]
        winner = _parse_winner_html(html, award_year, official)
        if winner is not None:
            records.append(winner)
        if official not in source_urls:
            source_urls.append(official)
    merged = _dedupe_records(records)
    state = _classify_year_state(merged)
    if state == 'absent':
        if award_year <= MAX_VERIFIED_YEAR:
            raise PenFaulknerSourceError(
                f'PEN/Faulkner {award_year} announcements did not parse'
            )
        return _YearSnapshot(
            award_year=award_year,
            state='absent',
            source_urls=(),
            records=(),
        )
    _validate_modern_records(merged, award_year, state)
    return _YearSnapshot(
        award_year=award_year,
        state=state,
        source_urls=tuple(source_urls),
        records=merged,
    )


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def _archive_coverage() -> dict:
    return {
        'kind': 'landing',
        'max_year': HISTORICAL_ARCHIVE_MAX_YEAR,
        'min_year': ARCHIVE_MIN_YEAR,
    }


def _year_coverage(award_year: int, state: str) -> dict:
    return {'award_year': award_year, 'state': state}


def _year_ttl_seconds(state: str) -> int:
    if state == 'winner':
        return HISTORICAL_CACHE_TTL_SECONDS
    return CURRENT_CACHE_TTL_SECONDS


def _record_to_cache_dict(record: _ParsedRecord) -> dict:
    return {
        'award_year': record.award_year,
        'category': record.category,
        'source_url': record.source_url,
        'status': record.status,
        'work_author': record.work_author,
        'work_title': record.work_title,
    }


def _record_from_cache_dict(data) -> _ParsedRecord | None:
    if not isinstance(data, dict) or set(data) != set(_RECORD_CACHE_FIELDS):
        return None
    award_year = data.get('award_year')
    if isinstance(award_year, bool) or not isinstance(award_year, int) or award_year <= 0:
        return None
    category = data.get('category')
    status = data.get('status')
    work_title = data.get('work_title')
    work_author = data.get('work_author')
    source_url = data.get('source_url')
    if category != CATEGORY:
        return None
    if status not in _PARSED_STATUSES:
        return None
    if not isinstance(work_title, str) or not work_title.strip() or work_title != work_title.strip():
        return None
    if not isinstance(work_author, str) or not work_author.strip() or work_author != work_author.strip():
        return None
    if not isinstance(source_url, str) or not source_url.strip() or source_url != source_url.strip():
        return None
    if _official_page_url(source_url) is None:
        return None
    return _ParsedRecord(
        award_year=award_year,
        category=category,
        status=status,
        work_title=work_title,
        work_author=work_author,
        source_url=source_url,
    )


def _archive_from_payload(payload: dict) -> _ArchiveSnapshot | None:
    coverage = payload.get('coverage')
    if not isinstance(coverage, dict) or set(coverage) != _ARCHIVE_COVERAGE_FIELDS:
        return None
    if coverage.get('kind') != 'landing':
        return None
    if coverage.get('min_year') != ARCHIVE_MIN_YEAR:
        return None
    if coverage.get('max_year') != HISTORICAL_ARCHIVE_MAX_YEAR:
        return None
    source_urls = payload.get('source_urls')
    if not isinstance(source_urls, list) or len(source_urls) != 1:
        return None
    if source_urls[0] != SOURCE_HOME_URL:
        return None
    raw_records = payload.get('records')
    if not isinstance(raw_records, list) or not raw_records:
        return None
    records: list[_ParsedRecord] = []
    for item in raw_records:
        record = _record_from_cache_dict(item)
        if record is None:
            return None
        records.append(record)
    restored = _dedupe_records(records)
    try:
        _validate_historical_records(restored)
    except PenFaulknerSourceError:
        return None
    return _ArchiveSnapshot(records=restored, source_url=SOURCE_HOME_URL)


def _year_from_payload(payload: dict, award_year: int) -> _YearSnapshot | None:
    coverage = payload.get('coverage')
    if not isinstance(coverage, dict) or set(coverage) != _YEAR_COVERAGE_FIELDS:
        return None
    if coverage.get('award_year') != award_year:
        return None
    state = coverage.get('state')
    if state not in _YEAR_STATES:
        return None
    raw_records = payload.get('records')
    if not isinstance(raw_records, list):
        return None
    source_urls = payload.get('source_urls')
    if not isinstance(source_urls, list):
        return None
    if state == 'absent':
        if raw_records or source_urls:
            return None
        return _YearSnapshot(
            award_year=award_year,
            state='absent',
            source_urls=(),
            records=(),
        )
    urls: list[str] = []
    for item in source_urls:
        if not isinstance(item, str) or _official_page_url(item) is None:
            return None
        urls.append(item)
    if not urls:
        return None
    records: list[_ParsedRecord] = []
    for item in raw_records:
        record = _record_from_cache_dict(item)
        if record is None or record.award_year != award_year:
            return None
        records.append(record)
    restored = _dedupe_records(records)
    try:
        _validate_modern_records(restored, award_year, state)
    except PenFaulknerSourceError:
        return None
    return _YearSnapshot(
        award_year=award_year,
        state=state,
        source_urls=tuple(urls),
        records=restored,
    )


def _save_persistent_landing(snapshot: _ArchiveSnapshot) -> None:
    try:
        cache.save_cache_entry(
            SOURCE_KEY,
            ARCHIVE_ENTRY_KIND,
            ARCHIVE_ENTRY_KEY,
            ARCHIVE_CACHE_VERSION,
            records=[_record_to_cache_dict(record) for record in snapshot.records],
            source_urls=[SOURCE_HOME_URL],
            coverage=_archive_coverage(),
            ttl_seconds=HISTORICAL_CACHE_TTL_SECONDS,
        )
    except OSError:
        pass


def _load_persistent_landing() -> tuple[_ArchiveSnapshot, dict] | None:
    payload = cache.load_cache_entry(
        SOURCE_KEY,
        ARCHIVE_ENTRY_KIND,
        ARCHIVE_ENTRY_KEY,
        ARCHIVE_CACHE_VERSION,
    )
    if payload is None:
        return None
    snapshot = _archive_from_payload(payload)
    if snapshot is None:
        return None
    return snapshot, payload


def _save_persistent_year(snapshot: _YearSnapshot) -> None:
    try:
        cache.save_cache_entry(
            SOURCE_KEY,
            YEAR_ENTRY_KIND,
            _year_entry_key(snapshot.award_year),
            YEAR_CACHE_VERSION,
            records=[_record_to_cache_dict(record) for record in snapshot.records],
            source_urls=list(snapshot.source_urls),
            coverage=_year_coverage(snapshot.award_year, snapshot.state),
            ttl_seconds=_year_ttl_seconds(snapshot.state),
        )
    except OSError:
        pass


def _load_persistent_year(award_year: int) -> tuple[_YearSnapshot, dict] | None:
    payload = cache.load_cache_entry(
        SOURCE_KEY,
        YEAR_ENTRY_KIND,
        _year_entry_key(award_year),
        YEAR_CACHE_VERSION,
    )
    if payload is None:
        return None
    snapshot = _year_from_payload(payload, award_year)
    if snapshot is None:
        return None
    return snapshot, payload


def _store_landing_snapshot(snapshot: _ArchiveSnapshot) -> None:
    global _landing_snapshot_cache
    with _cache_lock:
        _landing_snapshot_cache = snapshot


def _store_year_snapshot(snapshot: _YearSnapshot) -> None:
    with _cache_lock:
        _year_snapshot_cache[snapshot.award_year] = snapshot


def _ram_landing() -> _ArchiveSnapshot | None:
    with _cache_lock:
        return _landing_snapshot_cache


def _ram_year(award_year: int) -> _YearSnapshot | None:
    with _cache_lock:
        return _year_snapshot_cache.get(award_year)


def _get_landing() -> _ArchiveSnapshot:
    ram = _ram_landing()
    if ram is not None:
        return ram
    loaded = _load_persistent_landing()
    if loaded is not None:
        snapshot, payload = loaded
        if cache.cache_is_fresh(payload) or not cache.try_claim_stale_refresh():
            _store_landing_snapshot(snapshot)
            return snapshot
        try:
            live = _acquire_live_landing()
        except Exception:
            _store_landing_snapshot(snapshot)
            return snapshot
        _save_persistent_landing(live)
        _store_landing_snapshot(live)
        return live
    live = _acquire_live_landing()
    _save_persistent_landing(live)
    _store_landing_snapshot(live)
    return live


def _get_one_year(award_year: int) -> _YearSnapshot:
    ram = _ram_year(award_year)
    if ram is not None:
        return ram
    loaded = _load_persistent_year(award_year)
    if loaded is not None:
        snapshot, payload = loaded
        if cache.cache_is_fresh(payload) or not cache.try_claim_stale_refresh():
            _store_year_snapshot(snapshot)
            return snapshot
        try:
            live = _acquire_live_year(award_year)
        except Exception:
            _store_year_snapshot(snapshot)
            return snapshot
        _save_persistent_year(live)
        _store_year_snapshot(live)
        return live
    live = _acquire_live_year(award_year)
    _save_persistent_year(live)
    _store_year_snapshot(live)
    return live


def _modern_years() -> tuple[int, ...]:
    end = max(MAX_VERIFIED_YEAR, _current_calendar_year())
    return tuple(range(HISTORICAL_ARCHIVE_MAX_YEAR + 1, end + 1))


def _get_archive_records() -> tuple[_ParsedRecord, ...]:
    collected: list[_ParsedRecord] = list(_get_landing().records)
    for year in _modern_years():
        try:
            snapshot = _get_one_year(year)
        except PenFaulknerSourceError:
            continue
        collected.extend(snapshot.records)
    return tuple(
        sorted(
            collected,
            key=lambda record: (
                record.award_year,
                0 if record.status == 'Winner' else 1,
                record.work_title.casefold(),
            ),
        )
    )


def _to_award_result(record: _ParsedRecord) -> AwardResult:
    return AwardResult(
        work_title=record.work_title,
        work_author=record.work_author,
        award_name=AWARD_NAME,
        award_year=record.award_year,
        category=record.category,
        status=record.status,
        rank=None,
        source_name=SOURCE_NAME,
        source_url=record.source_url,
        notes=None,
        identity_kind='work',
    )


def lookup(title: str, author: str, series: str | None = None) -> list[AwardResult]:
    """Look up PEN/Faulkner Award for Fiction results for a title and author.

    series is accepted for AwardSource compatibility and ignored.
    """
    cleaned_title = title.strip()
    cleaned_author = author.strip()
    if not cleaned_title:
        raise ValueError('title must be a non-empty string')
    if not cleaned_author:
        raise ValueError('author must be a non-empty string')

    matches: list[AwardResult] = []
    for record in _get_archive_records():
        if _record_matches(record, cleaned_title, cleaned_author):
            matches.append(_to_award_result(record))
    return matches
