"""Official Booker Prize archive source (The Booker Prize only).

One HTTP GET of the published winners/shortlist/longlist archive. Longlist
rows are ignored. JavaScript is not required. This module does not cover
the International Booker Prize.
"""

from __future__ import annotations

import re
import threading
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from .. import cache
from ..matching import normalize_title_conjunctions
from ..model import AwardResult

TIMEOUT_SECONDS = 30
SOURCE_KEY = 'booker'
AWARD_NAME = 'Booker Prize'
CATEGORY = 'Fiction'
SOURCE_NAME = 'The Booker Prize'
SOURCE_HOME_URL = (
    'https://thebookerprizes.com/the-booker-library/features/'
    'full-list-of-booker-prize-winners-shortlisted-and-longlisted-authors'
)
ARCHIVE_MIN_YEAR = 1969
CACHE_VERSION = 1
# 7-day base plus an explicit stagger. Do not derive from AWARD_SOURCES order.
CACHE_BASE_TTL_SECONDS = 7 * 24 * 60 * 60
CACHE_REFRESH_OFFSET_SECONDS = 6 * 60 * 60
CACHE_TTL_SECONDS = CACHE_BASE_TTL_SECONDS + CACHE_REFRESH_OFFSET_SECONDS

_DETAIL_ORIGIN = 'https://thebookerprizes.com'
_OFFICIAL_HTML_HOSTS = frozenset({
    'thebookerprizes.com',
    'www.thebookerprizes.com',
})
_BOOK_PATH_PREFIX = ('the-booker-library', 'books')
_BOOK_SLUG_RE = re.compile(r'^[0-9A-Za-z][0-9A-Za-z_-]*$')
_YEAR_HEADING_RE = re.compile(r'^\d{4}$')
_INITIALS_SPACE_RE = re.compile(r'\b([A-Za-z])\.\s+')
_SECTION_PUNCT_RE = re.compile(r'[^\w\s]+', re.UNICODE)
_ARCHIVE_IDENTITY_MARKERS = (
    'full list of booker prize winners, shortlisted and longlisted authors',
)
_JOINT_WINNER_YEARS = frozenset({1974, 1992, 2019})
_STATUS_WEIGHT = {
    'Shortlisted': 1,
    'Winner': 2,
}

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


class BookerSourceError(RuntimeError):
    """Raised when the official Booker archive is blocked or unusable."""


@dataclass(frozen=True, slots=True)
class _ParsedRecord:
    award_year: int
    category: str
    status: str
    work_title: str
    work_author: str
    source_url: str


_PARSED_STATUSES = frozenset({'Winner', 'Shortlisted'})
_RECORD_CACHE_FIELDS = (
    'award_year',
    'category',
    'source_url',
    'status',
    'work_author',
    'work_title',
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _current_calendar_year() -> int:
    """UTC calendar year. Tests may patch _utc_now or this helper."""
    return _utc_now().year


def _year_is_completed(award_year: int) -> bool:
    """Years before the current UTC calendar year are expected completed."""
    return award_year < _current_calendar_year()


def _completed_year_winner_count_is_valid(count: int) -> bool:
    """Historical completed years may have one Winner or two joint Winners."""
    return count in (1, 2)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _read_response_body(response) -> str:
    return response.read().decode('utf-8', errors='replace')


def _fetch_html(url: str) -> str:
    request = urllib.request.Request(url, headers=dict(_BROWSER_HEADERS))
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            status = getattr(response, 'status', None) or response.getcode()
            html = _read_response_body(response)
    except urllib.error.HTTPError as exc:
        raise BookerSourceError(
            f'Booker request failed with HTTP {exc.code} for {url}'
        ) from exc
    except urllib.error.URLError as exc:
        raise BookerSourceError(
            f'Booker request failed for {url}: {exc.reason}'
        ) from exc
    if status != 200:
        raise BookerSourceError(
            f'Booker request failed with HTTP {status} for {url}'
        )
    return html


_archive_records_cache: tuple[_ParsedRecord, ...] | None = None
_cache_lock = threading.Lock()


def _reset_runtime_state() -> None:
    """Clear in-process caches. Used by tests. Does not delete disk cache."""
    global _archive_records_cache
    with _cache_lock:
        _archive_records_cache = None


def _load_live_archive() -> tuple[_ParsedRecord, ...]:
    """Fetch the official archive, parse, and validate. HTML is not kept."""
    html = _fetch_html(SOURCE_HOME_URL)
    _require_archive_identity(html)
    records, numeric_years = _parse_archive_html(html)
    _validate_archive(records, numeric_years)
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
            live = _load_live_archive()
        except Exception:
            if records is not None:
                _archive_records_cache = records
                return records
            raise
        _save_persistent_archive(live)
        _archive_records_cache = live
        return live


# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------

def _collapse_ws(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def _classify_section_label(label: str) -> str | None:
    """Return winner, shortlist, or ignore for an official section label."""
    cleaned = _SECTION_PUNCT_RE.sub(' ', _collapse_ws(label))
    folded = _collapse_ws(cleaned).casefold()
    if folded in {'winner', 'winners'}:
        return 'winner'
    if folded == 'shortlist':
        return 'shortlist'
    if folded in {'longlist', 'judges'}:
        return 'ignore'
    if not folded:
        return None
    return 'ignore'


def _official_book_url(href: str | None) -> str | None:
    """Return an official Booker book-detail URL, or None."""
    if not href or not href.strip():
        return None
    resolved = urljoin(f'{_DETAIL_ORIGIN}/', href.strip())
    parsed = urlparse(resolved)
    if parsed.scheme not in {'http', 'https'}:
        return None
    host = (parsed.hostname or '').casefold().rstrip('.')
    if host not in _OFFICIAL_HTML_HOSTS:
        return None
    parts = [piece for piece in parsed.path.split('/') if piece]
    if len(parts) != 3:
        return None
    if tuple(parts[:2]) != _BOOK_PATH_PREFIX:
        return None
    slug = parts[2]
    if not _BOOK_SLUG_RE.fullmatch(slug):
        return None
    return f'{_DETAIL_ORIGIN}/the-booker-library/books/{slug}'


class _BookerArchiveParser(HTMLParser):
    """Parse numeric-year Winner/Shortlist rows from the official archive."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.records: list[_ParsedRecord] = []
        self.numeric_years: list[int] = []
        self._year: int | None = None
        self._section: str | None = None
        self._capture: str | None = None
        self._buffer: list[str] = []
        self._in_book_a = False
        self._in_author_a = False
        self._row_title: list[str] = []
        self._row_author: list[str] = []
        self._row_href: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {name: (value or '') for name, value in attrs}
        if tag == 'h2':
            self._finish_row()
            self._capture = 'h2'
            self._buffer = []
            return
        if tag == 'strong':
            # Winner rows are often closed by an in-paragraph Shortlist label.
            self._finish_row()
            self._capture = 'strong'
            self._buffer = []
            return
        if tag == 'p':
            self._finish_row()
            return
        if tag == 'a':
            href = attr.get('href', '')
            book_url = _official_book_url(href)
            if book_url is not None:
                if self._row_href is not None:
                    self._finish_row()
                self._row_href = book_url
                self._in_book_a = True
                return
            if '/the-booker-library/authors/' in href:
                self._in_author_a = True
                return

    def handle_endtag(self, tag: str) -> None:
        if tag == 'h2' and self._capture == 'h2':
            heading = _collapse_ws(''.join(self._buffer))
            self._capture = None
            self._buffer = []
            self._section = None
            if _YEAR_HEADING_RE.fullmatch(heading):
                year = int(heading)
                self._year = year
                self.numeric_years.append(year)
            else:
                self._year = None
            return
        if tag == 'strong' and self._capture == 'strong':
            label = ''.join(self._buffer)
            self._capture = None
            self._buffer = []
            classified = _classify_section_label(label)
            if classified is not None:
                self._section = classified
            return
        if tag == 'a':
            self._in_book_a = False
            self._in_author_a = False
            return
        if tag == 'p':
            self._finish_row()

    def handle_data(self, data: str) -> None:
        if self._capture in {'h2', 'strong'}:
            self._buffer.append(data)
            return
        if self._in_book_a:
            self._row_title.append(data)
        if self._in_author_a:
            self._row_author.append(data)

    def _finish_row(self) -> None:
        title = _collapse_ws(''.join(self._row_title))
        author = _collapse_ws(''.join(self._row_author))
        href = self._row_href
        year = self._year
        section = self._section
        self._row_title = []
        self._row_author = []
        self._row_href = None
        self._in_book_a = False
        self._in_author_a = False
        if year is None or section not in {'winner', 'shortlist'}:
            return
        if not title or not author or href is None:
            return
        status = 'Winner' if section == 'winner' else 'Shortlisted'
        self.records.append(
            _ParsedRecord(
                award_year=year,
                category=CATEGORY,
                status=status,
                work_title=title,
                work_author=author,
                source_url=href,
            )
        )


def _identity_key(record: _ParsedRecord) -> tuple[int, str, str]:
    return (
        record.award_year,
        _normalize_text(record.work_title),
        _normalize_text(record.work_author),
    )


def _apply_status_precedence(
    records: list[_ParsedRecord],
) -> list[_ParsedRecord]:
    """Keep Winner over Shortlisted for the same work/year identity."""
    order: list[tuple[int, str, str]] = []
    by_key: dict[tuple[int, str, str], _ParsedRecord] = {}
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


def _parse_archive_html(
    html: str,
) -> tuple[tuple[_ParsedRecord, ...], tuple[int, ...]]:
    parser = _BookerArchiveParser()
    parser.feed(html)
    parser.close()
    records = tuple(_apply_status_precedence(parser.records))
    years = tuple(parser.numeric_years)
    return records, years


def _require_archive_identity(html: str) -> None:
    lowered = html.casefold()
    if any(marker in lowered for marker in _ARCHIVE_IDENTITY_MARKERS):
        return
    raise BookerSourceError(
        'Booker archive page did not match the official winners/shortlist listing'
    )


def _source_url_is_usable(source_url: str) -> bool:
    reconstructed = _official_book_url(source_url)
    return reconstructed is not None and reconstructed == source_url


def _validate_record(record: _ParsedRecord) -> None:
    if record.category != CATEGORY:
        raise BookerSourceError(
            f'Booker archive produced an unsupported category: {record.category!r}'
        )
    if record.status not in _PARSED_STATUSES:
        raise BookerSourceError(
            f'Booker archive produced an unexpected status: {record.status!r}'
        )
    if not record.work_title or not record.work_title.strip():
        raise BookerSourceError('Booker archive produced an empty title')
    if not record.work_author or not record.work_author.strip():
        raise BookerSourceError('Booker archive produced an empty author')
    if not _source_url_is_usable(record.source_url):
        raise BookerSourceError(
            f'Booker archive produced an unexpected source URL: {record.source_url!r}'
        )
    if (
        not isinstance(record.award_year, int)
        or isinstance(record.award_year, bool)
        or record.award_year < ARCHIVE_MIN_YEAR
    ):
        raise BookerSourceError(
            f'Booker archive produced an unexpected year: {record.award_year!r}'
        )


def _validate_numeric_years(numeric_years: tuple[int, ...]) -> None:
    if not numeric_years:
        raise BookerSourceError('Booker archive did not contain numeric year headings')
    unique = set(numeric_years)
    minimum = min(unique)
    maximum = max(unique)
    if minimum != ARCHIVE_MIN_YEAR:
        raise BookerSourceError(
            f'Booker archive history did not begin at {ARCHIVE_MIN_YEAR}'
        )
    expected = set(range(ARCHIVE_MIN_YEAR, maximum + 1))
    if unique != expected:
        raise BookerSourceError(
            'Booker archive year headings were not contiguous from '
            f'{ARCHIVE_MIN_YEAR} through {maximum}'
        )


def _validate_archive(
    records: tuple[_ParsedRecord, ...],
    numeric_years: tuple[int, ...] | None = None,
) -> None:
    """Fail closed if parsed records are not a usable Booker archive.

    Does not require a current-year Winner or Shortlist. Does not require
    winners to be restated under Shortlist. Does not constrain Shortlist
    or Longlist cardinality. A completed year may have one Winner or two
    joint Winners; zero or more than two is invalid.
    """
    if numeric_years is not None:
        _validate_numeric_years(numeric_years)
    if not records:
        raise BookerSourceError('Booker archive contained no prize records')
    identities = [_identity_key(record) for record in records]
    if len(identities) != len(set(identities)):
        raise BookerSourceError(
            'Booker archive contained duplicate work/year identities'
        )
    winners_by_year: dict[int, int] = {}
    for record in records:
        _validate_record(record)
        if record.status == 'Winner':
            winners_by_year[record.award_year] = (
                winners_by_year.get(record.award_year, 0) + 1
            )
    current_year = _current_calendar_year()
    for year in range(ARCHIVE_MIN_YEAR, current_year):
        count = winners_by_year.get(year, 0)
        if not _completed_year_winner_count_is_valid(count):
            raise BookerSourceError(
                f'Booker archive year {year} had {count} Winner record(s); '
                'completed years must have 1 or 2'
            )
    for year, count in winners_by_year.items():
        if year >= current_year and count > 2:
            raise BookerSourceError(
                f'Booker archive year {year} had an unexpected Winner count'
            )


def _validate_cached_archive(records: tuple[_ParsedRecord, ...]) -> None:
    _validate_archive(records)


# ---------------------------------------------------------------------------
# Persistent parsed-archive cache
# ---------------------------------------------------------------------------

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
    if (
        not isinstance(source_url, str)
        or not source_url.strip()
        or source_url != source_url.strip()
    ):
        return None
    if not _source_url_is_usable(source_url):
        return None
    return _ParsedRecord(
        award_year=award_year,
        category=category,
        status=status,
        work_title=work_title,
        work_author=work_author,
        source_url=source_url,
    )


def _archive_source_urls() -> tuple[str, ...]:
    return (SOURCE_HOME_URL,)


def _coverage_from_records(records: tuple[_ParsedRecord, ...]) -> dict:
    years = [record.award_year for record in records]
    return {
        'max_year': max(years) if years else None,
        'min_year': min(years) if years else None,
        'record_count': len(records),
        'shortlisted_count': sum(
            1 for record in records if record.status == 'Shortlisted'
        ),
        'winner_count': sum(1 for record in records if record.status == 'Winner'),
    }


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
    except BookerSourceError:
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


def _save_persistent_archive(records: tuple[_ParsedRecord, ...]) -> None:
    try:
        cache.save_source_cache(
            SOURCE_KEY,
            CACHE_VERSION,
            records=[_record_to_cache_dict(record) for record in records],
            source_urls=_archive_source_urls(),
            coverage=_coverage_from_records(records),
            ttl_seconds=CACHE_TTL_SECONDS,
        )
    except OSError:
        pass


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
        category=CATEGORY,
        status=record.status,
        rank=None,
        source_name=SOURCE_NAME,
        source_url=record.source_url,
        notes=None,
    )


# ---------------------------------------------------------------------------
# Public lookup
# ---------------------------------------------------------------------------

def lookup(title: str, author: str, series: str | None = None) -> list[AwardResult]:
    """Look up Booker Prize results for a title and author."""
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
