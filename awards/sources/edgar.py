"""Official Mystery Writers of America Edgar Awards database source.

Phase 1 covers bibliographic work categories from the server-rendered
Participants Database at edgarawards.com. Media, person/service, design,
and Special Edgars rows are ignored. Unknown future categories fail closed
without discarding the rest of the archive.
"""

from __future__ import annotations

import math
import re
import threading
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlparse

from .. import cache
from ..matching import normalize_title_conjunctions
from ..model import AwardResult

TIMEOUT_SECONDS = 30
SOURCE_KEY = 'edgar'
AWARD_NAME = 'Edgar Award'
SOURCE_NAME = 'Mystery Writers of America'
SOURCE_HOME_URL = 'https://edgarawards.com/'
SEARCH_DATABASE_URL = 'https://edgarawards.com/search-the-database/'
MIN_SUPPORTED_YEAR = 1946
CACHE_VERSION = 1
# 7-day base plus an explicit stagger. Do not derive from AWARD_SOURCES order.
CACHE_BASE_TTL_SECONDS = 7 * 24 * 60 * 60
CACHE_REFRESH_OFFSET_SECONDS = 17 * 60 * 60
CACHE_TTL_SECONDS = CACHE_BASE_TTL_SECONDS + CACHE_REFRESH_OFFSET_SECONDS
SOURCEINFO_CATEGORIES = (
    'Best Novel',
    'Best First Novel',
    'Best Paperback Original',
    'Best Fact Crime',
    'Best Critical/Biographical Work',
    'Best Short Story',
    'Best Juvenile',
    'Best Young Adult',
    'Robert L. Fish Memorial Award',
    'Mary Higgins Clark Award',
    'Sue Grafton Memorial Award',
    'Lilian Jackson Braun Memorial Award',
)

_OFFICIAL_HOSTS = frozenset({
    'edgarawards.com',
    'www.edgarawards.com',
})
_BROWSER_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/122.0.0.0 Safari/537.36'
    ),
    'Accept': (
        'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
    ),
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'identity',
}
_INITIALS_SPACE_RE = re.compile(r'\b([A-Za-z])\.\s+')
_BANNER_RE = re.compile(
    r'Total Records Found:\s*([0-9,]+),\s*showing\s+(\d+)\s+per page',
    re.IGNORECASE,
)
_LISTPAGE_RE = re.compile(r'listpage=(\d+)', re.IGNORECASE)
_YEAR_RE = re.compile(r'^\d{4}$')
_STORY_TITLE_RE = re.compile(
    r'^[\u201c\u201d\u2018\u2019"\'](.+?)[\u201c\u201d\u2018\u2019"\']'
    r'\s*[-–—]\s*(.+)$'
)
_IDENTITY_MARKERS = (
    'participants-list-1',
    'award year',
    'award category',
    "author's name",
    'publisher/producer',
)
_CHALLENGE_MARKERS = (
    'just a moment',
    'attention required',
    'cf-browser-verification',
    'enable javascript and cookies to continue',
    'checking your browser',
)
_ERROR_MARKERS = (
    'there has been a critical error on this website',
)
_EXPECTED_COLUMNS = (
    'Award Year',
    'Award Category',
    'Title',
    "Author's Name",
    'Publisher/Producer',
    'Notes',
)
_TABLE_FIELDS = frozenset({
    'award_year',
    'award_category',
    'title',
    'authors_name',
    'publisherproducer',
    'notes',
})
GRAFTON_SOURCE_CATEGORY = "G.P. Putnam's Sons Sue Grafton Memoriam Award"
GRAFTON_CANONICAL_CATEGORY = "G.P. Putnam's Sons Sue Grafton Memorial Award"
CATEGORY_BEST_NOVEL = 'Best Novel'
CATEGORY_BEST_FIRST_NOVEL = 'Best First Novel'
CATEGORY_BEST_PAPERBACK_ORIGINAL = 'Best Paperback Original'
CATEGORY_BEST_FACT_CRIME = 'Best Fact Crime'
CATEGORY_BEST_CRITICAL_BIOGRAPHICAL = 'Best Critical/Biographical Work'
CATEGORY_BEST_SHORT_STORY = 'Best Short Story'
CATEGORY_BEST_JUVENILE = 'Best Juvenile'
CATEGORY_BEST_YOUNG_ADULT = 'Best Young Adult'
CATEGORY_FISH = 'The Robert L. Fish Memorial Award'
CATEGORY_MARY_HIGGINS_CLARK = 'Mary Higgins Clark Award'
CATEGORY_BRAUN = 'The Lilian Jackson Braun Memorial Award'

_INCLUDED_SOURCE_CATEGORIES = frozenset({
    CATEGORY_BEST_NOVEL,
    CATEGORY_BEST_FIRST_NOVEL,
    CATEGORY_BEST_PAPERBACK_ORIGINAL,
    CATEGORY_BEST_FACT_CRIME,
    CATEGORY_BEST_CRITICAL_BIOGRAPHICAL,
    CATEGORY_BEST_SHORT_STORY,
    CATEGORY_BEST_JUVENILE,
    CATEGORY_BEST_YOUNG_ADULT,
    CATEGORY_FISH,
    CATEGORY_MARY_HIGGINS_CLARK,
    GRAFTON_SOURCE_CATEGORY,
    GRAFTON_CANONICAL_CATEGORY,
    CATEGORY_BRAUN,
})
_CANONICAL_INCLUDED_CATEGORIES = frozenset({
    CATEGORY_BEST_NOVEL,
    CATEGORY_BEST_FIRST_NOVEL,
    CATEGORY_BEST_PAPERBACK_ORIGINAL,
    CATEGORY_BEST_FACT_CRIME,
    CATEGORY_BEST_CRITICAL_BIOGRAPHICAL,
    CATEGORY_BEST_SHORT_STORY,
    CATEGORY_BEST_JUVENILE,
    CATEGORY_BEST_YOUNG_ADULT,
    CATEGORY_FISH,
    CATEGORY_MARY_HIGGINS_CLARK,
    GRAFTON_CANONICAL_CATEGORY,
    CATEGORY_BRAUN,
})
_EXCLUDED_CATEGORIES = frozenset({
    'Best Episode in a TV Series',
    'Best Episode in a TV Seriers',
    'Best Episode in a TV Seriess',
    'Best Motion Picture',
    'Best Play',
    'Best Radio Drama',
    'Best TV Feature or MiniSeries',
    'Best Foreign film',
    'The Grand Master',
    'The Raven Award',
    'The Ellery Queen Award',
    "The President's Award",
    'Outstanding Mystery Criticism',
    'Special Edgars',
    'Book Jacket Award',
})
_STORY_CATEGORIES = frozenset({
    CATEGORY_BEST_SHORT_STORY,
    CATEGORY_FISH,
})
_PARSED_STATUSES = frozenset({'Winner', 'Nominee'})
_STATUS_WEIGHT = {
    'Nominee': 1,
    'Winner': 2,
}
_LATEST_YEAR_STATES = frozenset({'absent', 'nominees', 'winner'})
_RECORD_CACHE_FIELDS = (
    'award_year',
    'category',
    'notes',
    'source_url',
    'status',
    'work_author',
    'work_title',
)


class EdgarSourceError(RuntimeError):
    """Raised when the official Edgar database is blocked or unusable."""


@dataclass(frozen=True, slots=True)
class _ParsedRecord:
    award_year: int
    category: str
    status: str
    work_title: str
    work_author: str
    source_url: str
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class _PageParse:
    records: tuple[_ParsedRecord, ...]
    unknown_categories: frozenset[str]
    blank_row_count: int
    excluded_row_count: int


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _collapse_ws(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def _classify_category(category: str) -> str:
    """Return included, excluded, or unknown for an official category string."""
    if category in _EXCLUDED_CATEGORIES:
        return 'excluded'
    if category in _INCLUDED_SOURCE_CATEGORIES:
        return 'included'
    return 'unknown'


def _canonical_category(category: str) -> str:
    if category == GRAFTON_SOURCE_CATEGORY:
        return GRAFTON_CANONICAL_CATEGORY
    return category


def _split_presented_title(title: str) -> tuple[str, str | None]:
    """Split a quoted short-story title and venue when the pattern is strong.

    Unquoted titles, including those containing dashes, are left intact.
    """
    cleaned = _collapse_ws(title)
    match = _STORY_TITLE_RE.fullmatch(cleaned)
    if match is None:
        return cleaned, None
    story = _collapse_ws(match.group(1))
    venue = _collapse_ws(match.group(2))
    if not story:
        return cleaned, None
    return story, venue or None


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _read_response_body(response) -> str:
    return response.read().decode('utf-8', errors='replace')


def _host_is_official(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {'http', 'https'}:
        return False
    host = (parsed.hostname or '').casefold().rstrip('.')
    return host in _OFFICIAL_HOSTS


def _page_url(page: int) -> str:
    if page <= 1:
        return SEARCH_DATABASE_URL
    return f'{SEARCH_DATABASE_URL}?listpage={page}&instance=1'


def _fetch_html(url: str) -> str:
    if not _host_is_official(url):
        raise EdgarSourceError(f'Edgar request used a non-official URL: {url}')
    request = urllib.request.Request(url, headers=dict(_BROWSER_HEADERS))
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            status = getattr(response, 'status', None) or response.getcode()
            final_url = getattr(response, 'geturl', lambda: url)()
            html = _read_response_body(response)
    except urllib.error.HTTPError as exc:
        raise EdgarSourceError(
            f'Edgar request failed with HTTP {exc.code} for {url}'
        ) from exc
    except urllib.error.URLError as exc:
        raise EdgarSourceError(
            f'Edgar request failed for {url}: {exc.reason}'
        ) from exc
    if status != 200:
        raise EdgarSourceError(
            f'Edgar request failed with HTTP {status} for {url}'
        )
    if not _host_is_official(final_url):
        raise EdgarSourceError(
            f'Edgar request redirected off the official host: {final_url}'
        )
    return html


_archive_records_cache: tuple[_ParsedRecord, ...] | None = None
_live_page_count_holder: list[int | None] = [None]
_cache_lock = threading.Lock()


def _reset_runtime_state() -> None:
    """Clear in-process caches. Used by tests. Does not delete disk cache."""
    global _archive_records_cache
    with _cache_lock:
        _archive_records_cache = None
        _live_page_count_holder[0] = None


# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------

def _is_challenge_or_error_html(html: str) -> bool:
    lowered = html.casefold()
    if any(marker in lowered for marker in _CHALLENGE_MARKERS):
        return True
    if any(marker in lowered for marker in _ERROR_MARKERS):
        return True
    return False


def _require_database_identity(html: str) -> None:
    if not html or not html.strip():
        raise EdgarSourceError('Edgar database page was empty')
    if _is_challenge_or_error_html(html):
        raise EdgarSourceError(
            'Edgar database page looked like a challenge or error page'
        )
    lowered = html.casefold()
    missing = [marker for marker in _IDENTITY_MARKERS if marker not in lowered]
    if missing:
        raise EdgarSourceError(
            'Edgar page did not match the official Participants Database listing'
        )


def _discover_page_count(html: str) -> int:
    """Return how many list pages the live banner/pagination require."""
    banner = _BANNER_RE.search(html)
    linked = [int(value) for value in _LISTPAGE_RE.findall(html)]
    pages_from_links = max(linked) if linked else 1
    if banner is None:
        return max(1, pages_from_links)
    total = int(banner.group(1).replace(',', ''))
    per_page = int(banner.group(2))
    if per_page < 1:
        raise EdgarSourceError('Edgar database banner had an invalid page size')
    if total < 1:
        raise EdgarSourceError('Edgar database banner reported no records')
    pages_from_banner = max(1, math.ceil(total / per_page))
    return max(pages_from_banner, pages_from_links)


def _field_from_td_class(class_attr: str) -> tuple[str | None, bool]:
    tokens = class_attr.split()
    winner = 'edgar-winner' in tokens
    field = None
    for token in tokens:
        if token.endswith('-field'):
            field = token[: -len('-field')]
            break
    return field, winner


class _EdgarTableParser(HTMLParser):
    """Parse bibliographic rows from the Edgar Participants Database table."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.records: list[_ParsedRecord] = []
        self.unknown_categories: set[str] = set()
        self.blank_row_count = 0
        self.excluded_row_count = 0
        self.column_headers: list[str] = []
        self.saw_participants_list = False
        self._in_th = False
        self._in_td = False
        self._td_field: str | None = None
        self._td_winner = False
        self._buffer: list[str] = []
        self._row_fields: dict[str, str] = {}
        self._row_winner = False
        self._in_row = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {name: (value or '') for name, value in attrs}
        if tag == 'div' and attr.get('id') == 'participants-list-1':
            self.saw_participants_list = True
            return
        if tag == 'th':
            self._in_th = True
            self._buffer = []
            return
        if tag == 'tr':
            self._finish_row()
            self._in_row = True
            self._row_fields = {}
            self._row_winner = False
            return
        if tag == 'td':
            field, winner = _field_from_td_class(attr.get('class', ''))
            self._in_td = True
            self._td_field = field
            self._td_winner = winner
            self._buffer = []
            if winner:
                self._row_winner = True

    def handle_endtag(self, tag: str) -> None:
        if tag == 'th' and self._in_th:
            self.column_headers.append(_collapse_ws(''.join(self._buffer)))
            self._in_th = False
            self._buffer = []
            return
        if tag == 'td' and self._in_td:
            text = _collapse_ws(''.join(self._buffer))
            if self._td_field in _TABLE_FIELDS:
                self._row_fields[self._td_field] = text
            self._in_td = False
            self._td_field = None
            self._td_winner = False
            self._buffer = []
            return
        if tag == 'tr':
            self._finish_row()

    def handle_data(self, data: str) -> None:
        if self._in_th or self._in_td:
            self._buffer.append(data)

    def _finish_row(self) -> None:
        fields = self._row_fields
        winner = self._row_winner
        self._in_row = False
        self._row_fields = {}
        self._row_winner = False
        self._in_td = False
        self._td_field = None
        if not fields:
            return
        year_text = fields.get('award_year', '')
        category = fields.get('award_category', '')
        title = fields.get('title', '')
        author = fields.get('authors_name', '')
        publisher = fields.get('publisherproducer', '')
        notes = fields.get('notes', '')
        if not any((year_text, category, title, author, publisher, notes)):
            self.blank_row_count += 1
            return
        if not _YEAR_RE.fullmatch(year_text):
            return
        award_year = int(year_text)
        if award_year < MIN_SUPPORTED_YEAR:
            return
        kind = _classify_category(category)
        if kind == 'unknown':
            if category:
                self.unknown_categories.add(category)
            return
        if kind == 'excluded':
            self.excluded_row_count += 1
            return
        if not title or not author:
            return
        canonical = _canonical_category(category)
        work_title = title
        venue = None
        if canonical in _STORY_CATEGORIES:
            work_title, venue = _split_presented_title(title)
        elif _STORY_TITLE_RE.fullmatch(title):
            work_title, venue = _split_presented_title(title)
        result_notes = venue
        if result_notes is None and notes:
            result_notes = notes
        self.records.append(
            _ParsedRecord(
                award_year=award_year,
                category=canonical,
                status='Winner' if winner else 'Nominee',
                work_title=work_title,
                work_author=author,
                source_url=SEARCH_DATABASE_URL,
                notes=result_notes,
            )
        )


def _require_expected_columns(headers: list[str]) -> None:
    present = {_collapse_ws(header) for header in headers}
    missing = [name for name in _EXPECTED_COLUMNS if name not in present]
    if missing:
        raise EdgarSourceError(
            'Edgar database table did not contain the expected award columns'
        )


def _parse_database_html(html: str) -> _PageParse:
    _require_database_identity(html)
    parser = _EdgarTableParser()
    parser.feed(html)
    parser.close()
    if not parser.saw_participants_list:
        raise EdgarSourceError(
            'Edgar page did not contain the Participants Database list'
        )
    _require_expected_columns(parser.column_headers)
    records = tuple(_apply_status_precedence(parser.records))
    return _PageParse(
        records=records,
        unknown_categories=frozenset(parser.unknown_categories),
        blank_row_count=parser.blank_row_count,
        excluded_row_count=parser.excluded_row_count,
    )


def _identity_key(record: _ParsedRecord) -> tuple[int, str, str, str]:
    return (
        record.award_year,
        record.category,
        _normalize_text(record.work_title),
        _normalize_text(record.work_author),
    )


def _apply_status_precedence(
    records: list[_ParsedRecord] | tuple[_ParsedRecord, ...],
) -> list[_ParsedRecord]:
    """Keep Winner over Nominee for the same year/category/title/author."""
    order: list[tuple[int, str, str, str]] = []
    by_key: dict[tuple[int, str, str, str], _ParsedRecord] = {}
    for record in records:
        key = _identity_key(record)
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = record
            order.append(key)
            continue
        if _STATUS_WEIGHT[record.status] > _STATUS_WEIGHT[existing.status]:
            by_key[key] = record
    return [by_key[key] for key in order]


def _validate_record(record: _ParsedRecord) -> None:
    if record.category not in _CANONICAL_INCLUDED_CATEGORIES:
        raise EdgarSourceError(
            f'Edgar archive produced an unsupported category: {record.category!r}'
        )
    if record.status not in _PARSED_STATUSES:
        raise EdgarSourceError(
            f'Edgar archive produced an unexpected status: {record.status!r}'
        )
    if not record.work_title or not record.work_title.strip():
        raise EdgarSourceError('Edgar archive produced an empty title')
    if not record.work_author or not record.work_author.strip():
        raise EdgarSourceError('Edgar archive produced an empty author')
    if record.source_url != SEARCH_DATABASE_URL:
        raise EdgarSourceError(
            f'Edgar archive produced an unexpected source URL: {record.source_url!r}'
        )
    if (
        not isinstance(record.award_year, int)
        or isinstance(record.award_year, bool)
        or record.award_year < MIN_SUPPORTED_YEAR
    ):
        raise EdgarSourceError(
            f'Edgar archive produced an unexpected year: {record.award_year!r}'
        )
    if record.notes is not None and (
        not isinstance(record.notes, str) or not record.notes.strip()
    ):
        raise EdgarSourceError('Edgar archive produced an empty notes value')


def _validate_archive(records: tuple[_ParsedRecord, ...]) -> None:
    if not records:
        raise EdgarSourceError('Edgar archive contained no supported award records')
    identities = [_identity_key(record) for record in records]
    if len(identities) != len(set(identities)):
        raise EdgarSourceError(
            'Edgar archive contained duplicate year/category/title/author identities'
        )
    years = [record.award_year for record in records]
    if min(years) != MIN_SUPPORTED_YEAR:
        raise EdgarSourceError(
            f'Edgar archive history did not begin at {MIN_SUPPORTED_YEAR}'
        )
    if not any(record.status == 'Winner' for record in records):
        raise EdgarSourceError('Edgar archive contained no Winner records')
    if not any(record.category == CATEGORY_BEST_NOVEL for record in records):
        raise EdgarSourceError('Edgar archive contained no Best Novel records')
    for record in records:
        _validate_record(record)


def _validate_cached_archive(records: tuple[_ParsedRecord, ...]) -> None:
    _validate_archive(records)


def _latest_year_state(records: tuple[_ParsedRecord, ...]) -> str:
    if not records:
        return 'absent'
    max_year = max(record.award_year for record in records)
    year_records = [
        record for record in records if record.award_year == max_year
    ]
    if any(record.status == 'Winner' for record in year_records):
        return 'winner'
    if any(record.status == 'Nominee' for record in year_records):
        return 'nominees'
    return 'absent'


# ---------------------------------------------------------------------------
# Persistent parsed-archive cache
# ---------------------------------------------------------------------------

def _record_to_cache_dict(record: _ParsedRecord) -> dict:
    return {
        'award_year': record.award_year,
        'category': record.category,
        'notes': record.notes,
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
    notes = data.get('notes')
    if category not in _CANONICAL_INCLUDED_CATEGORIES:
        return None
    if status not in _PARSED_STATUSES:
        return None
    if not isinstance(work_title, str) or not work_title.strip() or work_title != work_title.strip():
        return None
    if not isinstance(work_author, str) or not work_author.strip() or work_author != work_author.strip():
        return None
    if source_url != SEARCH_DATABASE_URL:
        return None
    if notes is not None:
        if not isinstance(notes, str) or not notes.strip() or notes != notes.strip():
            return None
    return _ParsedRecord(
        award_year=award_year,
        category=category,
        status=status,
        work_title=work_title,
        work_author=work_author,
        source_url=source_url,
        notes=notes,
    )


def _archive_source_urls() -> tuple[str, ...]:
    return (SEARCH_DATABASE_URL,)


def _coverage_from_records(
    records: tuple[_ParsedRecord, ...],
    *,
    page_count: int | None = None,
) -> dict:
    years = [record.award_year for record in records]
    coverage = {
        'latest_year_state': _latest_year_state(records),
        'max_year': max(years) if years else None,
        'min_year': min(years) if years else None,
        'nominee_count': sum(
            1 for record in records if record.status == 'Nominee'
        ),
        'record_count': len(records),
        'winner_count': sum(
            1 for record in records if record.status == 'Winner'
        ),
    }
    if page_count is not None:
        coverage['page_count'] = page_count
    return coverage


def _records_from_cache_payload(
    payload: dict,
) -> tuple[_ParsedRecord, ...] | None:
    if payload.get('source_urls') != list(_archive_source_urls()):
        return None
    raw_records = payload.get('records')
    if not isinstance(raw_records, list):
        return None
    records: list[_ParsedRecord] = []
    for item in raw_records:
        record = _record_from_cache_dict(item)
        if record is None:
            return None
        records.append(record)
    restored = tuple(records)
    try:
        _validate_cached_archive(restored)
    except EdgarSourceError:
        return None
    return restored


def _load_persistent_archive() -> (
    tuple[tuple[_ParsedRecord, ...], dict] | None
):
    payload = cache.load_source_cache(SOURCE_KEY, CACHE_VERSION)
    if payload is None:
        return None
    records = _records_from_cache_payload(payload)
    if records is None:
        return None
    return records, payload


def _save_persistent_archive(
    records: tuple[_ParsedRecord, ...],
    *,
    page_count: int | None = None,
) -> None:
    try:
        cache.save_source_cache(
            SOURCE_KEY,
            CACHE_VERSION,
            records=[_record_to_cache_dict(record) for record in records],
            source_urls=_archive_source_urls(),
            coverage=_coverage_from_records(records, page_count=page_count),
            ttl_seconds=CACHE_TTL_SECONDS,
        )
    except OSError:
        pass


def _fetch_and_parse_live_archive() -> tuple[tuple[_ParsedRecord, ...], int]:
    first_html = _fetch_html(_page_url(1))
    first_page = _parse_database_html(first_html)
    page_count = _discover_page_count(first_html)
    combined: list[_ParsedRecord] = list(first_page.records)
    for page in range(2, page_count + 1):
        html = _fetch_html(_page_url(page))
        parsed = _parse_database_html(html)
        combined.extend(parsed.records)
    records = tuple(_apply_status_precedence(combined))
    _validate_archive(records)
    return records, page_count


def _load_live_archive() -> tuple[_ParsedRecord, ...]:
    """Fetch every required database page, parse, and validate. HTML is not kept."""
    records, page_count = _fetch_and_parse_live_archive()
    _live_page_count_holder[0] = page_count
    return records


def _get_archive_records() -> tuple[_ParsedRecord, ...]:
    """Return records: RAM, then disk, then live fetch/parse/validate.

    A fresh disk cache is used immediately. A stale-but-valid disk cache
    live-refreshes only if this lookup still has a stale-refresh slot;
    otherwise the stale archive is used with no network. A missing or
    invalid cache still live-fetches. A failed optional refresh leaves a
    good snapshot in place and does not rewrite its timestamp.
    """
    global _archive_records_cache
    with _cache_lock:
        if _archive_records_cache is not None:
            return _archive_records_cache
        disk = _load_persistent_archive()
        if disk is not None:
            records, payload = disk
            if cache.cache_is_fresh(payload):
                _archive_records_cache = records
                return records
            if not cache.try_claim_stale_refresh():
                _archive_records_cache = records
                return records
        else:
            records = None
        try:
            _live_page_count_holder[0] = None
            live = _load_live_archive()
            page_count = _live_page_count_holder[0]
        except Exception:
            if records is not None:
                _archive_records_cache = records
                return records
            raise
        _save_persistent_archive(live, page_count=page_count)
        _archive_records_cache = live
        return live


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


def _record_matches(record: _ParsedRecord, title: str, author: str) -> bool:
    return _titles_match(title, record.work_title) and _authors_match(
        author, record.work_author
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
        notes=record.notes,
        identity_kind='work',
    )


def lookup(title: str, author: str, series: str | None = None) -> list[AwardResult]:
    """Look up Edgar Award results for a title and author."""
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
