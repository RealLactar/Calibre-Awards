"""Official International Booker Prize archive source.

One HTTP GET of the published International Booker winners/shortlist archive.
Longlist rows are ignored except to harvest same-document canonical book URLs.
JavaScript is not required.

Covers the modern work-level prize from 2016 through 2026 only.
2005-2015 was a biennial author/body-of-work prize and is not emitted.
2027 is the first Bukhman International Booker Prize cycle and is not
emitted until that naming and competitive-data question is solved separately.
This module does not cover the ordinary English-language Booker Prize.
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
SOURCE_KEY = 'international_booker'
AWARD_NAME = 'International Booker Prize'
SOURCE_NAME = 'The Booker Prizes'
SOURCEINFO_CATEGORIES = ('Fiction',)
SOURCE_HOME_URL = (
    'https://thebookerprizes.com/the-booker-library/features/'
    'full-list-of-international-booker-prize-winners-shortlisted-authors-and-their-books'
)
ARCHIVE_MIN_YEAR = 2016
ARCHIVE_MAX_YEAR = 2026
SUPPORTED_YEARS = frozenset(range(ARCHIVE_MIN_YEAR, ARCHIVE_MAX_YEAR + 1))
CACHE_VERSION = 1
# 7-day base plus an explicit stagger. Do not derive from AWARD_SOURCES order.
CACHE_BASE_TTL_SECONDS = 7 * 24 * 60 * 60
CACHE_REFRESH_OFFSET_SECONDS = 19 * 60 * 60
CACHE_TTL_SECONDS = CACHE_BASE_TTL_SECONDS + CACHE_REFRESH_OFFSET_SECONDS

_DETAIL_ORIGIN = 'https://thebookerprizes.com'
_OFFICIAL_HTML_HOSTS = frozenset({
    'thebookerprizes.com',
    'www.thebookerprizes.com',
})
_BOOK_PATH_PREFIX = ('the-booker-library', 'books')
_PRIZE_YEAR_PATH_PREFIX = (
    'the-booker-library',
    'prize-years',
    'international',
)
_BOOK_SLUG_RE = re.compile(r'^[0-9A-Za-z][0-9A-Za-z_-]*$')
_YEAR_HEADING_RE = re.compile(r'^\d{4}$')
_INITIALS_SPACE_RE = re.compile(r'\b([A-Za-z])\.\s+')
_SECTION_PUNCT_RE = re.compile(r'[^\w\s]+', re.UNICODE)
_TRAILING_PAREN_RE = re.compile(r'\s*\([^()]*\)\s*$')
_TRANSLATED_BY_RE = re.compile(
    r'(?is)\btranslated(?:\s+from\s+.+?)?\s+by\s+(.+)$'
)
_ARCHIVE_IDENTITY_MARKERS = (
    'full list of international booker prize winners',
)
_STATUS_WEIGHT = {
    'Shortlisted': 1,
    'Winner': 2,
}
_NOTES_PREFIX = 'Translated by '

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


class InternationalBookerSourceError(RuntimeError):
    """Raised when the official International Booker archive is blocked or unusable."""


@dataclass(frozen=True, slots=True)
class _ParsedRecord:
    award_year: int
    status: str
    work_title: str
    work_author: str
    source_url: str
    notes: str


_PARSED_STATUSES = frozenset({'Winner', 'Shortlisted'})
_RECORD_CACHE_FIELDS = (
    'award_year',
    'notes',
    'source_url',
    'status',
    'work_author',
    'work_title',
)
_QUALIFYING_SECTIONS = frozenset({'winner', 'shortlist'})
_URL_HARVEST_SECTIONS = frozenset({'winner', 'shortlist', 'longlist'})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _year_is_supported(award_year: int) -> bool:
    """2016-2026 only. Later years cannot opt in by archive growth."""
    return award_year in SUPPORTED_YEARS


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
        try:
            raise InternationalBookerSourceError(
                f'International Booker request failed with HTTP {exc.code} for {url}'
            ) from exc
        finally:
            exc.close()
    except urllib.error.URLError as exc:
        raise InternationalBookerSourceError(
            f'International Booker request failed for {url}: {exc.reason}'
        ) from exc
    if status != 200:
        raise InternationalBookerSourceError(
            f'International Booker request failed with HTTP {status} for {url}'
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
    """Return winner, shortlist, longlist, or ignore for an official label."""
    cleaned = _SECTION_PUNCT_RE.sub(' ', _collapse_ws(label))
    folded = _collapse_ws(cleaned).casefold()
    if folded in {'winner', 'winners'}:
        return 'winner'
    if folded == 'shortlist':
        return 'shortlist'
    if folded == 'longlist':
        return 'longlist'
    if not folded:
        return None
    return 'ignore'


def _official_book_url(href: str | None) -> str | None:
    """Return an official book-detail URL, or None.

    /node/N paths are not canonical book URLs and are never guessed into slugs.
    """
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


def _official_prize_year_url(year: int) -> str | None:
    """Return the official International Booker prize-year URL, or None."""
    if not _year_is_supported(year):
        return None
    if not isinstance(year, int) or isinstance(year, bool):
        return None
    return (
        f'{_DETAIL_ORIGIN}/the-booker-library/prize-years/international/{year}'
    )


def _translator_credit(paragraph: str) -> str | None:
    """Return the official translator credit, or None if it cannot be read."""
    match = _TRANSLATED_BY_RE.search(_collapse_ws(paragraph))
    if match is None:
        return None
    credit = _collapse_ws(match.group(1))
    credit = _TRAILING_PAREN_RE.sub('', credit).strip()
    credit = credit.strip(' ,;')
    if not credit:
        return None
    return credit


def _translator_notes(credit: str) -> str:
    return f'{_NOTES_PREFIX}{credit}'


class _InternationalBookerArchiveParser(HTMLParser):
    """Parse 2016-2026 Winner/Shortlist work rows from the official archive."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.records: list[_ParsedRecord] = []
        self.numeric_years: list[int] = []
        self.canonical_urls: dict[tuple[int, str, str], str | None] = {}
        self._year: int | None = None
        self._section: str | None = None
        self._capture: str | None = None
        self._buffer: list[str] = []
        self._in_p = False
        self._in_a = False
        self._in_em = False
        self._p_all_text: list[str] = []
        self._p_title: list[str] = []
        self._p_author: list[str] = []
        self._p_title_href: str | None = None
        self._p_book_urls: list[str] = []
        self._p_title_closed = False
        self._p_capturing_author = False
        self._p_author_done = False
        self._current_href: str | None = None

    def _reset_paragraph(self) -> None:
        self._in_p = False
        self._in_a = False
        self._in_em = False
        self._p_all_text = []
        self._p_title = []
        self._p_author = []
        self._p_title_href = None
        self._p_book_urls = []
        self._p_title_closed = False
        self._p_capturing_author = False
        self._p_author_done = False
        self._current_href = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {name: (value or '') for name, value in attrs}
        if tag == 'h2':
            self._finish_row()
            self._capture = 'h2'
            self._buffer = []
            return
        if tag == 'strong':
            self._finish_row()
            self._capture = 'strong'
            self._buffer = []
            return
        if tag == 'p':
            self._finish_row()
            self._in_p = True
            return
        if tag == 'a':
            href = attr.get('href', '')
            self._in_a = True
            self._current_href = href
            book_url = _official_book_url(href)
            if book_url is not None:
                self._p_book_urls.append(book_url)
            if (
                self._in_p
                and self._p_title_closed
                and not self._p_author_done
                and not self._p_capturing_author
            ):
                self._p_capturing_author = True
            return
        if tag == 'em':
            self._in_em = True

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
        if tag == 'em':
            if self._in_em and not self._p_title_closed:
                title = _collapse_ws(''.join(self._p_title))
                if title:
                    self._p_title_closed = True
                    if self._in_a:
                        self._p_title_href = self._current_href
            self._in_em = False
            return
        if tag == 'a':
            if self._p_capturing_author:
                self._p_capturing_author = False
                if _collapse_ws(''.join(self._p_author)):
                    self._p_author_done = True
            self._in_a = False
            self._current_href = None
            return
        if tag == 'p':
            self._finish_row()

    def handle_data(self, data: str) -> None:
        if self._capture in {'h2', 'strong'}:
            self._buffer.append(data)
            return
        if not self._in_p:
            return
        self._p_all_text.append(data)
        if self._in_em and not self._p_title_closed:
            self._p_title.append(data)
        if self._p_capturing_author and not self._p_author_done:
            self._p_author.append(data)

    def _remember_canonical(
        self,
        year: int,
        title: str,
        author: str,
        book_url: str,
    ) -> None:
        key = (year, _normalize_text(title), _normalize_text(author))
        existing = self.canonical_urls.get(key, _MISSING)
        if existing is _MISSING:
            self.canonical_urls[key] = book_url
            return
        if existing != book_url:
            self.canonical_urls[key] = None

    def _finish_row(self) -> None:
        if not self._in_p and not self._p_all_text and not self._p_title:
            self._reset_paragraph()
            return
        title = _collapse_ws(''.join(self._p_title))
        author = _collapse_ws(''.join(self._p_author))
        paragraph = _collapse_ws(''.join(self._p_all_text))
        title_href = self._p_title_href
        book_urls = list(self._p_book_urls)
        year = self._year
        section = self._section
        self._reset_paragraph()
        if not title or not author or year is None:
            return
        book_url = _official_book_url(title_href)
        if book_url is None and book_urls:
            unique = []
            for item in book_urls:
                if item not in unique:
                    unique.append(item)
            if len(unique) == 1:
                book_url = unique[0]
        if book_url is not None:
            self._remember_canonical(year, title, author, book_url)
        if section not in _URL_HARVEST_SECTIONS:
            return
        if section not in _QUALIFYING_SECTIONS:
            return
        if not _year_is_supported(year):
            return
        credit = _translator_credit(paragraph)
        if credit is None:
            return
        self.records.append(
            _ParsedRecord(
                award_year=year,
                status='Winner' if section == 'winner' else 'Shortlisted',
                work_title=title,
                work_author=author,
                source_url=book_url or '',
                notes=_translator_notes(credit),
            )
        )


_MISSING = object()


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


def _resolve_source_urls(
    records: list[_ParsedRecord],
    canonical_urls: dict[tuple[int, str, str], str | None],
) -> list[_ParsedRecord]:
    resolved: list[_ParsedRecord] = []
    for record in records:
        source_url = record.source_url
        if not _official_book_url(source_url):
            mapped = canonical_urls.get(_identity_key(record))
            if mapped:
                source_url = mapped
            else:
                year_url = _official_prize_year_url(record.award_year)
                if year_url is None:
                    continue
                source_url = year_url
        resolved.append(
            _ParsedRecord(
                award_year=record.award_year,
                status=record.status,
                work_title=record.work_title,
                work_author=record.work_author,
                source_url=source_url,
                notes=record.notes,
            )
        )
    return resolved


def _parse_archive_html(
    html: str,
) -> tuple[tuple[_ParsedRecord, ...], tuple[int, ...]]:
    parser = _InternationalBookerArchiveParser()
    parser.feed(html)
    parser.close()
    ranked = _apply_status_precedence(parser.records)
    records = tuple(_resolve_source_urls(ranked, parser.canonical_urls))
    years = tuple(parser.numeric_years)
    return records, years


def _require_archive_identity(html: str) -> None:
    lowered = html.casefold()
    if any(marker in lowered for marker in _ARCHIVE_IDENTITY_MARKERS):
        return
    raise InternationalBookerSourceError(
        'International Booker archive page did not match the official '
        'winners/shortlist listing'
    )


def _source_url_is_usable(source_url: str, award_year: int) -> bool:
    reconstructed = _official_book_url(source_url)
    if reconstructed is not None and reconstructed == source_url:
        return True
    year_url = _official_prize_year_url(award_year)
    return year_url is not None and source_url == year_url


def _notes_are_usable(notes: str) -> bool:
    if not isinstance(notes, str) or notes != notes.strip():
        return False
    if not notes.startswith(_NOTES_PREFIX):
        return False
    return len(notes) > len(_NOTES_PREFIX)


def _validate_record(record: _ParsedRecord) -> None:
    if record.status not in _PARSED_STATUSES:
        raise InternationalBookerSourceError(
            'International Booker archive produced an unexpected status: '
            f'{record.status!r}'
        )
    if not record.work_title or not record.work_title.strip():
        raise InternationalBookerSourceError(
            'International Booker archive produced an empty title'
        )
    if not record.work_author or not record.work_author.strip():
        raise InternationalBookerSourceError(
            'International Booker archive produced an empty author'
        )
    if not _notes_are_usable(record.notes):
        raise InternationalBookerSourceError(
            'International Booker archive produced an unexpected translator note'
        )
    if not _year_is_supported(record.award_year):
        raise InternationalBookerSourceError(
            'International Booker archive produced an unsupported year: '
            f'{record.award_year!r}'
        )
    if not _source_url_is_usable(record.source_url, record.award_year):
        raise InternationalBookerSourceError(
            'International Booker archive produced an unexpected source URL: '
            f'{record.source_url!r}'
        )


def _validate_numeric_years(numeric_years: tuple[int, ...]) -> None:
    if not numeric_years:
        raise InternationalBookerSourceError(
            'International Booker archive did not contain numeric year headings'
        )
    unique = set(numeric_years)
    missing = sorted(SUPPORTED_YEARS - unique)
    if missing:
        raise InternationalBookerSourceError(
            'International Booker archive did not include supported year '
            f'headings {missing}'
        )


def _validate_archive(
    records: tuple[_ParsedRecord, ...],
    numeric_years: tuple[int, ...] | None = None,
) -> None:
    """Fail closed if parsed records are not a usable 2016-2026 archive.

    Every supported year must have exactly one Winner and five Shortlisted
    results after Winner-over-Shortlisted precedence. Extra year headings
    (legacy 2005-2015 or a future 2027 block) are allowed; those years must
    not appear in emitted records.
    """
    if numeric_years is not None:
        _validate_numeric_years(numeric_years)
    if not records:
        raise InternationalBookerSourceError(
            'International Booker archive contained no prize records'
        )
    identities = [_identity_key(record) for record in records]
    if len(identities) != len(set(identities)):
        raise InternationalBookerSourceError(
            'International Booker archive contained duplicate work/year identities'
        )
    winners_by_year: dict[int, int] = {}
    shortlisted_by_year: dict[int, int] = {}
    years_seen: set[int] = set()
    for record in records:
        _validate_record(record)
        years_seen.add(record.award_year)
        if record.status == 'Winner':
            winners_by_year[record.award_year] = (
                winners_by_year.get(record.award_year, 0) + 1
            )
        elif record.status == 'Shortlisted':
            shortlisted_by_year[record.award_year] = (
                shortlisted_by_year.get(record.award_year, 0) + 1
            )
    missing_years = sorted(SUPPORTED_YEARS - years_seen)
    if missing_years:
        raise InternationalBookerSourceError(
            'International Booker archive omitted supported years '
            f'{missing_years}'
        )
    unexpected_years = sorted(years_seen - SUPPORTED_YEARS)
    if unexpected_years:
        raise InternationalBookerSourceError(
            'International Booker archive emitted unsupported years '
            f'{unexpected_years}'
        )
    for year in sorted(SUPPORTED_YEARS):
        winner_count = winners_by_year.get(year, 0)
        shortlisted_count = shortlisted_by_year.get(year, 0)
        if winner_count != 1:
            raise InternationalBookerSourceError(
                f'International Booker archive year {year} had '
                f'{winner_count} Winner record(s); supported years must have 1'
            )
        if shortlisted_count != 5:
            raise InternationalBookerSourceError(
                f'International Booker archive year {year} had '
                f'{shortlisted_count} Shortlisted record(s); supported years '
                'must have 5 after Winner precedence'
            )


def _validate_cached_archive(records: tuple[_ParsedRecord, ...]) -> None:
    _validate_archive(records)


# ---------------------------------------------------------------------------
# Persistent parsed-archive cache
# ---------------------------------------------------------------------------

def _record_to_cache_dict(record: _ParsedRecord) -> dict:
    return {
        'award_year': record.award_year,
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
    if (
        isinstance(award_year, bool)
        or not isinstance(award_year, int)
        or not _year_is_supported(award_year)
    ):
        return None
    status = data.get('status')
    work_title = data.get('work_title')
    work_author = data.get('work_author')
    source_url = data.get('source_url')
    notes = data.get('notes')
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
    if not _notes_are_usable(notes):
        return None
    if not _source_url_is_usable(source_url, award_year):
        return None
    return _ParsedRecord(
        award_year=award_year,
        status=status,
        work_title=work_title,
        work_author=work_author,
        source_url=source_url,
        notes=notes,
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
    except InternationalBookerSourceError:
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
        category=None,
        status=record.status,
        rank=None,
        source_name=SOURCE_NAME,
        source_url=record.source_url,
        notes=record.notes,
        identity_kind='work',
        is_specifically_cited_work=False,
    )


# ---------------------------------------------------------------------------
# Public lookup
# ---------------------------------------------------------------------------

def lookup(title: str, author: str, series: str | None = None) -> list[AwardResult]:
    """Look up International Booker Prize results for a title and author."""
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
