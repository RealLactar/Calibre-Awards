"""Deutscher Buchpreis official HTML source.

Historical facts come from /archiv/jahr/YYYY/. Current-year facts prefer that
archive page when it exists; otherwise /nominiert/. Longlist is ignored.

Parsed facts are persisted as keyed cache entries: one archive-index payload
and one payload per award year. Historical years reuse stale disk without
claiming the shared refresh slot. Current year may optionally refresh.
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
SOURCE_KEY = 'german_book_prize'
AWARD_NAME = 'Deutscher Buchpreis'
CATEGORY = 'Fiction'
SOURCE_NAME = 'Deutscher Buchpreis'
SITE_ORIGIN = 'https://www.deutscher-buchpreis.de'
ARCHIVE_INDEX_URL = SITE_ORIGIN + '/archiv/'
YEAR_URL_TEMPLATE = SITE_ORIGIN + '/archiv/jahr/{year}/'
CURRENT_NOMINEES_URL = SITE_ORIGIN + '/nominiert/'
ARCHIVE_MIN_YEAR = 2005
CACHE_VERSION = 1
INDEX_ENTRY_KIND = 'index'
YEAR_ENTRY_KIND = 'years'
INDEX_CACHE_TTL_SECONDS = 630000
HISTORICAL_YEAR_CACHE_TTL_SECONDS = 180 * 24 * 60 * 60
CURRENT_YEAR_CACHE_BASE_TTL_SECONDS = 7 * 24 * 60 * 60
CURRENT_YEAR_CACHE_REFRESH_OFFSET_SECONDS = 7 * 60 * 60
CURRENT_YEAR_CACHE_TTL_SECONDS = (
    CURRENT_YEAR_CACHE_BASE_TTL_SECONDS + CURRENT_YEAR_CACHE_REFRESH_OFFSET_SECONDS
)
_SOURCE_KINDS = frozenset({'archive', 'nominiert'})
_CURRENT_RECOGNIZED_STATES = frozenset({
    'longlist_only',
    'shortlist',
    'winner',
})
_RECORD_CACHE_FIELDS = (
    'award_year',
    'category',
    'source_url',
    'status',
    'work_author',
    'work_title',
)
_INDEX_RECORD_FIELDS = ('award_year',)
_INDEX_COVERAGE_FIELDS = frozenset({
    'kind',
    'max_completed_year',
    'min_year',
})
_COMPLETED_YEAR_COVERAGE_FIELDS = frozenset({
    'award_year',
    'kind',
    'source_kind',
})
_CURRENT_YEAR_COVERAGE_FIELDS = frozenset({
    'award_year',
    'kind',
    'recognized_state',
    'source_kind',
})

_OFFICIAL_HTML_HOSTS = frozenset({
    'deutscher-buchpreis.de',
    'www.deutscher-buchpreis.de',
})
_IDENTITY_MARKERS = (
    'deutscher buchpreis',
    'deutschen buchpreis',
    'deutschen buchpreises',
)
_PARSED_STATUSES = frozenset({'Winner', 'Shortlisted'})
_STATUS_WEIGHT = {
    'Shortlisted': 1,
    'Winner': 2,
}
_COMPLETED_UNIQUE_MIN = 2
_COMPLETED_UNIQUE_MAX = 10
_CURRENT_UNIQUE_MAX = 10
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
_YEAR_PATH_RE = re.compile(
    r'^/archiv/jahr/(\d{4})/?$',
    re.IGNORECASE,
)
_BOOK_ID_RE = re.compile(r'^book-(\d+)$', re.IGNORECASE)
_BOOK_HREF_RE = re.compile(r'^#book-(\d+)$', re.IGNORECASE)
_ROMAN_HEADING_RE = re.compile(
    r'^Roman des Jahres\s+(\d{4})$',
    re.IGNORECASE,
)
_AUTHOR_LABEL_RE = re.compile(r'^(Autor|Autorin)$', re.IGNORECASE)
_YEAR_ONLY_RE = re.compile(r'^\d{4}$')
_INITIALS_SPACE_RE = re.compile(r'\b([A-Za-z])\.\s+')
_SHORTLIST_SECTION_IDS = frozenset({'shortlist', 'section_shortlist'})
_LONGLIST_SECTION_IDS = frozenset({'longlist', 'section_longlist'})
_JURY_SECTION_IDS = frozenset({'jury', 'section_jury'})

_BROWSER_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/122.0.0.0 Safari/537.36'
    ),
    'Accept': (
        'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
    ),
    'Accept-Language': 'de-DE,de;q=0.9,en;q=0.8',
    'Accept-Encoding': 'identity',
}


class DeutscherBuchpreisSourceError(RuntimeError):
    """Raised when official Deutscher Buchpreis HTML is blocked or unusable."""


@dataclass(frozen=True, slots=True)
class _ParsedRecord:
    award_year: int
    category: str
    status: str
    work_title: str
    work_author: str
    source_url: str


@dataclass(frozen=True, slots=True)
class _YearSnapshot:
    award_year: int
    records: tuple[_ParsedRecord, ...]
    source_kind: str
    recognized_state: str
    source_url: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _current_calendar_year() -> int:
    """UTC calendar year. Tests may patch _utc_now or this helper."""
    return _utc_now().year


def _year_is_completed(award_year: int) -> bool:
    return award_year < _current_calendar_year()


def _collapse_ws(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def _canonical_year_url(year: int) -> str:
    return YEAR_URL_TEMPLATE.format(year=year)


def _year_entry_key(year: int) -> str:
    """Stable logical year identity, independent of archive vs /nominiert/."""
    return str(year)


def _classes(attr: dict[str, str]) -> set[str]:
    return {part for part in attr.get('class', '').split() if part}


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _read_response_body(response) -> str:
    return response.read().decode('utf-8', errors='replace')


def _fetch_response(url: str) -> tuple[int, str]:
    """Return (status, body). HTTP 404 is returned; other failures raise."""
    request = urllib.request.Request(url, headers=dict(_BROWSER_HEADERS))
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            status = getattr(response, 'status', None) or response.getcode()
            body = _read_response_body(response)
    except urllib.error.HTTPError as exc:
        body = ''
        try:
            body = exc.read().decode('utf-8', errors='replace')
        except Exception:
            pass
        if exc.code == 404:
            return 404, body
        raise DeutscherBuchpreisSourceError(
            f'Deutscher Buchpreis request failed with HTTP {exc.code} for {url}'
        ) from exc
    except urllib.error.URLError as exc:
        raise DeutscherBuchpreisSourceError(
            f'Deutscher Buchpreis request failed for {url}: {exc.reason}'
        ) from exc
    if status != 200:
        raise DeutscherBuchpreisSourceError(
            f'Deutscher Buchpreis request failed with HTTP {status} for {url}'
        )
    return int(status), body


def _fetch_html(url: str) -> str:
    status, body = _fetch_response(url)
    if status != 200:
        raise DeutscherBuchpreisSourceError(
            f'Deutscher Buchpreis request failed with HTTP {status} for {url}'
        )
    return body


_archive_records_cache: tuple[_ParsedRecord, ...] | None = None
_index_years_cache: tuple[int, ...] | None = None
_year_records_cache: dict[int, tuple[_ParsedRecord, ...]] = {}
_cache_lock = threading.Lock()


def _reset_runtime_state() -> None:
    """Clear in-process caches. Used by tests. Does not delete disk cache."""
    global _archive_records_cache, _index_years_cache
    with _cache_lock:
        _archive_records_cache = None
        _index_years_cache = None
        _year_records_cache.clear()


# ---------------------------------------------------------------------------
# Official identity and URLs
# ---------------------------------------------------------------------------

def _require_official_identity(html: str, *, page_kind: str) -> None:
    folded = html.casefold()
    if not any(marker in folded for marker in _IDENTITY_MARKERS):
        raise DeutscherBuchpreisSourceError(
            f'Deutscher Buchpreis {page_kind} did not match official page identity'
        )
    if 'deutscher-buchpreis.de' not in folded and 'deutscher buchpreis' not in folded:
        raise DeutscherBuchpreisSourceError(
            f'Deutscher Buchpreis {page_kind} did not match official page identity'
        )


def _official_absolute_url(href: str | None) -> str | None:
    if not href or not href.strip():
        return None
    resolved = urljoin(f'{SITE_ORIGIN}/', href.strip())
    parsed = urlparse(resolved)
    if parsed.scheme not in {'http', 'https'}:
        return None
    host = (parsed.hostname or '').casefold().rstrip('.')
    if host not in _OFFICIAL_HTML_HOSTS:
        return None
    path = parsed.path if parsed.path.endswith('/') else parsed.path + '/'
    return f'{SITE_ORIGIN}{path}'


def _year_from_official_url(url: str) -> int | None:
    parsed = urlparse(url)
    path = parsed.path if parsed.path.endswith('/') else parsed.path + '/'
    match = _YEAR_PATH_RE.fullmatch(path)
    if match is None:
        return None
    return int(match.group(1))


def _source_url_is_year_page(source_url: str, year: int) -> bool:
    return source_url == _canonical_year_url(year)


def _source_url_is_nominiert(source_url: str) -> bool:
    return source_url == CURRENT_NOMINEES_URL


# ---------------------------------------------------------------------------
# Archive-index discovery
# ---------------------------------------------------------------------------

class _ArchiveIndexParser(HTMLParser):
    """Collect unique /archiv/jahr/YYYY/ links, ignoring fragments and chrome."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.years: set[int] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {name: (value or '') for name, value in attrs}
        candidates = []
        if tag in {'a', 'option'} and attr.get('href'):
            candidates.append(attr['href'])
        if tag == 'option' and attr.get('value'):
            candidates.append(attr['value'])
        if tag == 'a' and attr.get('value'):
            candidates.append(attr['value'])
        for raw in candidates:
            self._consider(raw)

    def _consider(self, raw: str) -> None:
        stripped = raw.strip().split('#', 1)[0]
        absolute = _official_absolute_url(stripped)
        if absolute is None:
            parsed = urlparse(stripped)
            path = parsed.path if parsed.path.endswith('/') else parsed.path + '/'
            match = _YEAR_PATH_RE.fullmatch(path)
            if match is None:
                return
            year = int(match.group(1))
        else:
            year = _year_from_official_url(absolute)
            if year is None:
                return
        if year >= ARCHIVE_MIN_YEAR:
            self.years.add(year)


def _discover_archive_years(html: str) -> tuple[int, ...]:
    parser = _ArchiveIndexParser()
    parser.feed(html)
    parser.close()
    return tuple(sorted(parser.years))


def _validate_discovered_years(
    years: tuple[int, ...],
    current_year: int,
) -> None:
    """Require contiguous completed years from 2005; current year may be absent."""
    if not years:
        raise DeutscherBuchpreisSourceError(
            'Deutscher Buchpreis archive index contained no year links'
        )
    discovered = set(years)
    required = set(range(ARCHIVE_MIN_YEAR, current_year))
    missing = sorted(required - discovered)
    if missing:
        raise DeutscherBuchpreisSourceError(
            'Deutscher Buchpreis archive index was missing required '
            f'completed year(s): {missing}'
        )
    extras = discovered - required - {current_year}
    if extras:
        raise DeutscherBuchpreisSourceError(
            'Deutscher Buchpreis archive index contained unexpected '
            f'year(s): {sorted(extras)}'
        )
    listed = sorted(year for year in discovered if year <= current_year)
    expected = list(range(ARCHIVE_MIN_YEAR, listed[-1] + 1))
    if listed != expected:
        raise DeutscherBuchpreisSourceError(
            'Deutscher Buchpreis archive index years were not contiguous '
            f'from {ARCHIVE_MIN_YEAR}'
        )


# ---------------------------------------------------------------------------
# Year-page / nominees HTML parser
# ---------------------------------------------------------------------------

class _PrizePageParser(HTMLParser):
    """Parse Winner/Shortlist facts from an official year or nominees page.

    Shortlist book panels are siblings of the tab sections. Association is
    through #book-N hrefs inside the Shortlist tab, not visual order.
    Longlist panels and Jury chrome are ignored.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.winner_title: str | None = None
        self.winner_author: str | None = None
        self.winner_records: list[tuple[str, str]] = []
        self.shortlist_ids: list[str] = []
        self.panels: dict[str, tuple[str, str]] = {}
        self.page_year: int | None = None
        self.roman_year: int | None = None
        self.canonical_url: str | None = None
        self.saw_winner_figure = False
        self.saw_shortlist_section = False
        self.saw_longlist_section = False
        self.saw_longlist_heading = False
        self.saw_shortlist_heading = False
        self.h1_text: str | None = None
        self._stack: list[tuple[str, str | None]] = []
        self._tab: str | None = None
        self._panel_id: str | None = None
        self._capture: str | None = None
        self._buffer: list[str] = []
        self._awaiting_winner_title = False
        self._awaiting_author_in: str | None = None
        self._open_winners: list[dict[str, str | None]] = []

    def _current_section_id(self) -> str | None:
        for _tag, element_id in reversed(self._stack):
            if element_id:
                return element_id
        return None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {name: (value or '') for name, value in attrs}
        element_id = attr.get('id') or None
        if tag not in _VOID_TAGS:
            self._stack.append((tag, element_id))
        self._enter_section(element_id)
        if 'single-book--winner' in _classes(attr):
            self.saw_winner_figure = True
        if tag == 'link' and 'canonical' in attr.get('rel', '').casefold().split():
            absolute = _official_absolute_url(attr.get('href'))
            if absolute is not None:
                self.canonical_url = absolute
        href = attr.get('href', '').strip()
        if href and self._tab == 'shortlist':
            match = _BOOK_HREF_RE.fullmatch(href)
            if match is not None:
                book_id = f'book-{match.group(1)}'
                if book_id not in self.shortlist_ids:
                    self.shortlist_ids.append(book_id)
        if element_id and _BOOK_ID_RE.fullmatch(element_id):
            self._panel_id = element_id
            self._capture = None
            self._buffer = []
        if tag in {'h1', 'h2', 'h3', 'h4', 'title'}:
            self._capture = tag
            self._buffer = []
        if tag == 'p' and self._awaiting_author_in is not None:
            self._capture = 'author_p'
            self._buffer = []

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID_TAGS:
            return
        if self._capture in {'h1', 'h2', 'h3', 'h4', 'title', 'author_p'} and (
            (self._capture == 'author_p' and tag == 'p')
            or tag == self._capture
        ):
            text = _collapse_ws(''.join(self._buffer))
            capture = self._capture
            self._capture = None
            self._buffer = []
            self._finish_text(capture, text)
        self._pop_until(tag)

    def handle_data(self, data: str) -> None:
        if self._capture is not None:
            self._buffer.append(data)

    def _enter_section(self, element_id: str | None) -> None:
        if element_id is None:
            return
        folded = element_id.casefold()
        if folded in _SHORTLIST_SECTION_IDS:
            self._tab = 'shortlist'
            self.saw_shortlist_section = True
        elif folded in _LONGLIST_SECTION_IDS:
            self._tab = 'longlist'
            self.saw_longlist_section = True
        elif folded in _JURY_SECTION_IDS:
            self._tab = 'jury'

    def _finish_text(self, capture: str, text: str) -> None:
        if capture == 'author_p' and self._awaiting_author_in is not None and not text:
            self._awaiting_author_in = None
            return
        if not text:
            return
        if capture == 'h1':
            self.h1_text = text
            if _YEAR_ONLY_RE.fullmatch(text):
                self.page_year = int(text)
            folded = text.casefold()
            if folded == 'longlist':
                self.saw_longlist_heading = True
            elif folded == 'shortlist':
                self.saw_shortlist_heading = True
            return
        if capture == 'h3' and _YEAR_ONLY_RE.fullmatch(text) and self.page_year is None:
            self.page_year = int(text)
        if capture == 'h4':
            roman = _ROMAN_HEADING_RE.fullmatch(text)
            if roman is not None:
                self.roman_year = int(roman.group(1))
                self._awaiting_winner_title = True
                self._open_winners.append({'title': None, 'author': None})
                return
            if _AUTHOR_LABEL_RE.fullmatch(text):
                if self._panel_id is not None:
                    self._awaiting_author_in = 'panel'
                elif self._tab is None and self._open_winners:
                    self._awaiting_author_in = 'winner'
                return
        if capture == 'h2' and self._awaiting_winner_title and self._tab is None:
            if self._open_winners and self._open_winners[-1]['title'] is None:
                self._open_winners[-1]['title'] = text
            elif self.winner_title is None:
                self.winner_title = text
            self._awaiting_winner_title = False
            return
        if capture == 'h3' and self._panel_id is not None:
            if self._panel_id not in self.panels:
                self.panels[self._panel_id] = (text, '')
            else:
                title, author = self.panels[self._panel_id]
                if not title:
                    self.panels[self._panel_id] = (text, author)
            return
        if capture == 'author_p' and self._awaiting_author_in is not None:
            target = self._awaiting_author_in
            self._awaiting_author_in = None
            if not text:
                return
            if target == 'winner' and self._open_winners:
                self._open_winners[-1]['author'] = text
                title = self._open_winners[-1]['title']
                if title:
                    self.winner_records.append((title, text))
                    if self.winner_title is None:
                        self.winner_title = title
                    if self.winner_author is None:
                        self.winner_author = text
            elif target == 'panel' and self._panel_id is not None:
                title, _author = self.panels.get(self._panel_id, ('', ''))
                self.panels[self._panel_id] = (title, text)

    def _pop_until(self, tag: str) -> None:
        while self._stack:
            stacked_tag, stacked_id = self._stack.pop()
            if stacked_id:
                folded = stacked_id.casefold()
                if folded in _SHORTLIST_SECTION_IDS and self._tab == 'shortlist':
                    self._tab = None
                elif folded in _LONGLIST_SECTION_IDS and self._tab == 'longlist':
                    self._tab = None
                elif folded in _JURY_SECTION_IDS and self._tab == 'jury':
                    self._tab = None
                if stacked_id == self._panel_id:
                    self._panel_id = None
                    if self._awaiting_author_in == 'panel':
                        self._awaiting_author_in = None
            if stacked_tag == tag:
                break

    def close(self) -> None:
        super().close()
        if (
            not self.winner_records
            and self.winner_title
            and self.winner_author
        ):
            self.winner_records.append((self.winner_title, self.winner_author))


def _parse_prize_page(html: str) -> _PrizePageParser:
    parser = _PrizePageParser()
    parser.feed(html)
    parser.close()
    return parser


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


def _sort_records(records: list[_ParsedRecord]) -> tuple[_ParsedRecord, ...]:
    return tuple(
        sorted(
            records,
            key=lambda record: (
                record.award_year,
                0 if record.status == 'Winner' else 1,
                record.work_title,
                record.work_author,
            ),
        )
    )


def _records_from_parser(
    parser: _PrizePageParser,
    *,
    award_year: int,
    source_url: str,
) -> list[_ParsedRecord]:
    records: list[_ParsedRecord] = []
    for title, author in parser.winner_records:
        title = title.strip()
        author = author.strip()
        if not title or not author:
            continue
        records.append(
            _ParsedRecord(
                award_year=award_year,
                category=CATEGORY,
                status='Winner',
                work_title=title,
                work_author=author,
                source_url=source_url,
            )
        )
    for book_id in parser.shortlist_ids:
        title, author = parser.panels.get(book_id, ('', ''))
        title = title.strip()
        author = author.strip()
        if not title or not author:
            continue
        records.append(
            _ParsedRecord(
                award_year=award_year,
                category=CATEGORY,
                status='Shortlisted',
                work_title=title,
                work_author=author,
                source_url=source_url,
            )
        )
    return _apply_status_precedence(records)


def _validate_record(record: _ParsedRecord, *, allow_nominiert: bool) -> None:
    if record.category != CATEGORY:
        raise DeutscherBuchpreisSourceError(
            f'Deutscher Buchpreis produced an unsupported category: {record.category!r}'
        )
    if record.status not in _PARSED_STATUSES:
        raise DeutscherBuchpreisSourceError(
            f'Deutscher Buchpreis produced an unexpected status: {record.status!r}'
        )
    if not record.work_title or not record.work_title.strip():
        raise DeutscherBuchpreisSourceError(
            'Deutscher Buchpreis produced an empty title'
        )
    if not record.work_author or not record.work_author.strip():
        raise DeutscherBuchpreisSourceError(
            'Deutscher Buchpreis produced an empty author'
        )
    if record.work_title != record.work_title.strip():
        raise DeutscherBuchpreisSourceError(
            'Deutscher Buchpreis produced an unstripped title'
        )
    if record.work_author != record.work_author.strip():
        raise DeutscherBuchpreisSourceError(
            'Deutscher Buchpreis produced an unstripped author'
        )
    year_ok = _source_url_is_year_page(record.source_url, record.award_year)
    nominees_ok = allow_nominiert and _source_url_is_nominiert(record.source_url)
    if not year_ok and not nominees_ok:
        raise DeutscherBuchpreisSourceError(
            'Deutscher Buchpreis produced an unexpected source URL: '
            f'{record.source_url!r}'
        )
    if (
        not isinstance(record.award_year, int)
        or isinstance(record.award_year, bool)
        or record.award_year < ARCHIVE_MIN_YEAR
    ):
        raise DeutscherBuchpreisSourceError(
            f'Deutscher Buchpreis produced an unexpected year: {record.award_year!r}'
        )


def _unique_work_count(records: list[_ParsedRecord]) -> int:
    return len({_identity_key(record) for record in records})


def _winner_count(records: list[_ParsedRecord]) -> int:
    return sum(1 for record in records if record.status == 'Winner')


def _require_year_consistency(
    parser: _PrizePageParser,
    award_year: int,
    *,
    require_page_year: bool,
) -> None:
    if parser.page_year is not None and parser.page_year != award_year:
        raise DeutscherBuchpreisSourceError(
            f'Deutscher Buchpreis page year {parser.page_year} did not match {award_year}'
        )
    if parser.roman_year is not None and parser.roman_year != award_year:
        raise DeutscherBuchpreisSourceError(
            f'Deutscher Buchpreis Roman des Jahres year {parser.roman_year} '
            f'did not match {award_year}'
        )
    if parser.canonical_url is not None:
        canonical_year = _year_from_official_url(parser.canonical_url)
        if canonical_year is not None and canonical_year != award_year:
            raise DeutscherBuchpreisSourceError(
                'Deutscher Buchpreis canonical URL year did not match '
                f'{award_year}'
            )
    if require_page_year and parser.page_year is None and parser.roman_year is None:
        raise DeutscherBuchpreisSourceError(
            f'Deutscher Buchpreis year page {award_year} lacked a consistent year marker'
        )


def _validate_completed_year(
    parser: _PrizePageParser,
    records: list[_ParsedRecord],
    award_year: int,
) -> None:
    if award_year < ARCHIVE_MIN_YEAR:
        raise DeutscherBuchpreisSourceError(
            f'Deutscher Buchpreis year {award_year} is before {ARCHIVE_MIN_YEAR}'
        )
    _require_year_consistency(parser, award_year, require_page_year=True)
    if not parser.saw_shortlist_section:
        raise DeutscherBuchpreisSourceError(
            f'Deutscher Buchpreis year {award_year} lacked a Shortlist section'
        )
    if not parser.shortlist_ids:
        raise DeutscherBuchpreisSourceError(
            f'Deutscher Buchpreis year {award_year} Shortlist contained no works'
        )
    _require_shortlist_panels_complete(parser, award_year)
    winners = _winner_count(records)
    if winners != 1:
        raise DeutscherBuchpreisSourceError(
            f'Deutscher Buchpreis year {award_year} had {winners} Winner record(s); '
            'completed years must have exactly 1'
        )
    unique = _unique_work_count(records)
    if unique < _COMPLETED_UNIQUE_MIN or unique > _COMPLETED_UNIQUE_MAX:
        raise DeutscherBuchpreisSourceError(
            f'Deutscher Buchpreis year {award_year} had {unique} unique '
            'Winner/Shortlisted work(s); expected a plausible finalist set'
        )
    identities = [_identity_key(record) for record in records]
    if len(identities) != len(set(identities)):
        raise DeutscherBuchpreisSourceError(
            f'Deutscher Buchpreis year {award_year} had duplicate work identities'
        )
    for record in records:
        _validate_record(record, allow_nominiert=False)


def _require_shortlist_panels_complete(
    parser: _PrizePageParser,
    award_year: int,
) -> None:
    for book_id in parser.shortlist_ids:
        title, author = parser.panels.get(book_id, ('', ''))
        if not title.strip() or not author.strip():
            raise DeutscherBuchpreisSourceError(
                f'Deutscher Buchpreis year {award_year} Shortlist had a '
                'malformed title or author'
            )


def _validate_current_year_records(
    parser: _PrizePageParser,
    records: list[_ParsedRecord],
    award_year: int,
    *,
    allow_nominiert: bool,
) -> None:
    if parser.shortlist_ids:
        _require_shortlist_panels_complete(parser, award_year)
    winners = _winner_count(records)
    if winners > 1:
        raise DeutscherBuchpreisSourceError(
            f'Deutscher Buchpreis current year {award_year} had {winners} '
            'Winner record(s); more than one is invalid'
        )
    if records:
        unique = _unique_work_count(records)
        if unique < 1 or unique > _CURRENT_UNIQUE_MAX:
            raise DeutscherBuchpreisSourceError(
                f'Deutscher Buchpreis current year {award_year} had {unique} '
                'unique Winner/Shortlisted work(s)'
            )
    identities = [_identity_key(record) for record in records]
    if len(identities) != len(set(identities)):
        raise DeutscherBuchpreisSourceError(
            f'Deutscher Buchpreis current year {award_year} had duplicate identities'
        )
    for record in records:
        _validate_record(record, allow_nominiert=allow_nominiert)


def parse_year_page(
    html: str,
    award_year: int,
    *,
    completed: bool,
) -> tuple[_ParsedRecord, ...]:
    """Parse an official /archiv/jahr/YYYY/ page into factual records."""
    _require_official_identity(html, page_kind=f'year {award_year}')
    parser = _parse_prize_page(html)
    source_url = _canonical_year_url(award_year)
    records = _records_from_parser(
        parser,
        award_year=award_year,
        source_url=source_url,
    )
    if completed:
        _validate_completed_year(parser, records, award_year)
    else:
        _require_year_consistency(parser, award_year, require_page_year=False)
        _validate_current_year_records(
            parser,
            records,
            award_year,
            allow_nominiert=False,
        )
    return tuple(records)


def _nominiert_is_recognized_longlist_only(parser: _PrizePageParser) -> bool:
    if parser.saw_winner_figure or parser.roman_year is not None:
        return False
    if parser.winner_records or parser.shortlist_ids:
        return False
    if parser.saw_shortlist_section or parser.saw_shortlist_heading:
        return False
    return parser.saw_longlist_section or parser.saw_longlist_heading


def parse_nominiert_page(
    html: str,
    award_year: int,
) -> tuple[_ParsedRecord, ...]:
    """Parse /nominiert/ for current-year Winner/Shortlist facts only."""
    _require_official_identity(html, page_kind='nominees')
    parser = _parse_prize_page(html)
    if _nominiert_is_recognized_longlist_only(parser):
        return ()
    recognized = (
        parser.saw_winner_figure
        or parser.roman_year is not None
        or parser.saw_shortlist_section
        or parser.saw_shortlist_heading
        or bool(parser.shortlist_ids)
        or bool(parser.winner_records)
    )
    if not recognized:
        raise DeutscherBuchpreisSourceError(
            'Deutscher Buchpreis nominees page had an unrecognized structure'
        )
    _require_year_consistency(parser, award_year, require_page_year=False)
    records = _records_from_parser(
        parser,
        award_year=award_year,
        source_url=CURRENT_NOMINEES_URL,
    )
    _validate_current_year_records(
        parser,
        records,
        award_year,
        allow_nominiert=True,
    )
    return tuple(records)


# ---------------------------------------------------------------------------
# Acquisition
# ---------------------------------------------------------------------------

def _completed_years(current_year: int) -> tuple[int, ...]:
    return tuple(range(ARCHIVE_MIN_YEAR, current_year))


def _recognized_state_from_parser(
    parser: _PrizePageParser,
    records: tuple[_ParsedRecord, ...],
) -> str:
    if (
        _winner_count(list(records)) >= 1
        or parser.saw_winner_figure
        or parser.roman_year is not None
        or parser.winner_records
    ):
        return 'winner'
    if (
        any(record.status == 'Shortlisted' for record in records)
        or parser.shortlist_ids
        or parser.saw_shortlist_section
        or parser.saw_shortlist_heading
    ):
        return 'shortlist'
    return 'longlist_only'


def _acquire_current_year_snapshot(current_year: int) -> _YearSnapshot:
    archive_url = _canonical_year_url(current_year)
    status, body = _fetch_response(archive_url)
    if status == 200:
        records = parse_year_page(body, current_year, completed=False)
        parser = _parse_prize_page(body)
        return _YearSnapshot(
            award_year=current_year,
            records=records,
            source_kind='archive',
            recognized_state=_recognized_state_from_parser(parser, records),
            source_url=archive_url,
        )
    if status == 404:
        nominees_html = _fetch_html(CURRENT_NOMINEES_URL)
        records = parse_nominiert_page(nominees_html, current_year)
        parser = _parse_prize_page(nominees_html)
        return _YearSnapshot(
            award_year=current_year,
            records=records,
            source_kind='nominiert',
            recognized_state=_recognized_state_from_parser(parser, records),
            source_url=CURRENT_NOMINEES_URL,
        )
    raise DeutscherBuchpreisSourceError(
        f'Deutscher Buchpreis current-year request failed with HTTP {status} '
        f'for {archive_url}'
    )


def _acquire_current_year_records(current_year: int) -> tuple[_ParsedRecord, ...]:
    return _acquire_current_year_snapshot(current_year).records


def _acquire_completed_year_records(award_year: int) -> tuple[_ParsedRecord, ...]:
    html = _fetch_html(_canonical_year_url(award_year))
    return parse_year_page(html, award_year, completed=True)


def _acquire_live_index_years() -> tuple[int, ...]:
    current_year = _current_calendar_year()
    index_html = _fetch_html(ARCHIVE_INDEX_URL)
    _require_official_identity(index_html, page_kind='archive index')
    years = _discover_archive_years(index_html)
    _validate_discovered_years(years, current_year)
    return _completed_years(current_year)


def _acquire_complete_records() -> tuple[_ParsedRecord, ...]:
    """Live-only complete fetch. Tests and cold paths may still call this."""
    current_year = _current_calendar_year()
    years = _acquire_live_index_years()
    records: list[_ParsedRecord] = []
    for year in years:
        records.extend(_acquire_completed_year_records(year))
    records.extend(_acquire_current_year_records(current_year))
    return _sort_records(records)


# ---------------------------------------------------------------------------
# Persistent keyed cache
# ---------------------------------------------------------------------------

def _is_positive_year(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


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
    if not _is_positive_year(award_year) or award_year < ARCHIVE_MIN_YEAR:
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
    return _ParsedRecord(
        award_year=award_year,
        category=category,
        status=status,
        work_title=work_title,
        work_author=work_author,
        source_url=source_url,
    )


def _records_from_payload(payload: dict) -> tuple[_ParsedRecord, ...] | None:
    raw_records = payload.get('records')
    if not isinstance(raw_records, list):
        return None
    records: list[_ParsedRecord] = []
    for item in raw_records:
        record = _record_from_cache_dict(item)
        if record is None:
            return None
        records.append(record)
    return tuple(records)


def _validate_cached_completed_year(
    records: tuple[_ParsedRecord, ...],
    award_year: int,
) -> bool:
    if not records:
        return False
    identities = [_identity_key(record) for record in records]
    if len(identities) != len(set(identities)):
        return False
    unique = _unique_work_count(list(records))
    if unique < _COMPLETED_UNIQUE_MIN or unique > _COMPLETED_UNIQUE_MAX:
        return False
    if _winner_count(list(records)) != 1:
        return False
    for record in records:
        if record.award_year != award_year:
            return False
        try:
            _validate_record(record, allow_nominiert=False)
        except DeutscherBuchpreisSourceError:
            return False
    return True


def _validate_cached_current_year(
    records: tuple[_ParsedRecord, ...],
    award_year: int,
    *,
    source_kind: str,
    recognized_state: str,
) -> bool:
    if source_kind not in _SOURCE_KINDS:
        return False
    if recognized_state not in _CURRENT_RECOGNIZED_STATES:
        return False
    winners = _winner_count(list(records))
    if winners > 1:
        return False
    if recognized_state == 'longlist_only':
        if records:
            return False
    elif recognized_state == 'shortlist':
        if winners != 0:
            return False
        if not any(record.status == 'Shortlisted' for record in records):
            return False
    elif recognized_state == 'winner':
        if winners != 1:
            return False
    if records:
        unique = _unique_work_count(list(records))
        if unique < 1 or unique > _CURRENT_UNIQUE_MAX:
            return False
    identities = [_identity_key(record) for record in records]
    if len(identities) != len(set(identities)):
        return False
    allow_nominiert = source_kind == 'nominiert'
    expected_url = (
        CURRENT_NOMINEES_URL if source_kind == 'nominiert' else _canonical_year_url(award_year)
    )
    for record in records:
        if record.award_year != award_year:
            return False
        if record.source_url != expected_url:
            return False
        try:
            _validate_record(record, allow_nominiert=allow_nominiert)
        except DeutscherBuchpreisSourceError:
            return False
    return True


def _index_years_from_payload(payload: dict) -> tuple[int, ...] | None:
    if payload.get('source_urls') != [ARCHIVE_INDEX_URL]:
        return None
    coverage = payload.get('coverage')
    if not isinstance(coverage, dict) or set(coverage) != _INDEX_COVERAGE_FIELDS:
        return None
    if coverage.get('kind') != 'archive_index':
        return None
    if coverage.get('min_year') != ARCHIVE_MIN_YEAR:
        return None
    max_completed = coverage.get('max_completed_year')
    if not _is_positive_year(max_completed) or max_completed < ARCHIVE_MIN_YEAR:
        return None
    raw_records = payload.get('records')
    if not isinstance(raw_records, list):
        return None
    years: list[int] = []
    for item in raw_records:
        if not isinstance(item, dict) or set(item) != set(_INDEX_RECORD_FIELDS):
            return None
        year = item.get('award_year')
        if not _is_positive_year(year) or year < ARCHIVE_MIN_YEAR:
            return None
        years.append(year)
    if not years:
        return None
    if len(years) != len(set(years)):
        return None
    if years != sorted(years):
        return None
    if years[0] != ARCHIVE_MIN_YEAR:
        return None
    if years[-1] != max_completed:
        return None
    if years != list(range(ARCHIVE_MIN_YEAR, max_completed + 1)):
        return None
    current_year = _current_calendar_year()
    if max_completed >= current_year:
        return None
    if max_completed != current_year - 1:
        return None
    return tuple(years)


def _completed_year_from_payload(
    payload: dict,
    award_year: int,
) -> tuple[_ParsedRecord, ...] | None:
    coverage = payload.get('coverage')
    if not isinstance(coverage, dict) or set(coverage) != _COMPLETED_YEAR_COVERAGE_FIELDS:
        return None
    if coverage.get('kind') != 'completed_year':
        return None
    if coverage.get('award_year') != award_year:
        return None
    if coverage.get('source_kind') != 'archive':
        return None
    if payload.get('source_urls') != [_canonical_year_url(award_year)]:
        return None
    records = _records_from_payload(payload)
    if records is None:
        return None
    if not _validate_cached_completed_year(records, award_year):
        return None
    return records


def _current_year_from_payload(
    payload: dict,
    award_year: int,
) -> tuple[_ParsedRecord, ...] | None:
    coverage = payload.get('coverage')
    if not isinstance(coverage, dict) or set(coverage) != _CURRENT_YEAR_COVERAGE_FIELDS:
        return None
    if coverage.get('kind') != 'current_year':
        return None
    if coverage.get('award_year') != award_year:
        return None
    source_kind = coverage.get('source_kind')
    recognized_state = coverage.get('recognized_state')
    if source_kind not in _SOURCE_KINDS:
        return None
    if recognized_state not in _CURRENT_RECOGNIZED_STATES:
        return None
    expected_url = (
        CURRENT_NOMINEES_URL if source_kind == 'nominiert' else _canonical_year_url(award_year)
    )
    if payload.get('source_urls') != [expected_url]:
        return None
    records = _records_from_payload(payload)
    if records is None:
        return None
    if not _validate_cached_current_year(
        records,
        award_year,
        source_kind=source_kind,
        recognized_state=recognized_state,
    ):
        return None
    return records


def _index_coverage(years: tuple[int, ...]) -> dict:
    return {
        'kind': 'archive_index',
        'max_completed_year': years[-1],
        'min_year': ARCHIVE_MIN_YEAR,
    }


def _completed_year_coverage(award_year: int) -> dict:
    return {
        'award_year': award_year,
        'kind': 'completed_year',
        'source_kind': 'archive',
    }


def _current_year_coverage(snapshot: _YearSnapshot) -> dict:
    return {
        'award_year': snapshot.award_year,
        'kind': 'current_year',
        'recognized_state': snapshot.recognized_state,
        'source_kind': snapshot.source_kind,
    }


def _save_persistent_index(years: tuple[int, ...]) -> None:
    try:
        cache.save_cache_entry(
            SOURCE_KEY,
            INDEX_ENTRY_KIND,
            ARCHIVE_INDEX_URL,
            CACHE_VERSION,
            records=[{'award_year': year} for year in years],
            source_urls=[ARCHIVE_INDEX_URL],
            coverage=_index_coverage(years),
            ttl_seconds=INDEX_CACHE_TTL_SECONDS,
        )
    except OSError:
        pass


def _save_persistent_completed_year(
    award_year: int,
    records: tuple[_ParsedRecord, ...],
) -> None:
    try:
        cache.save_cache_entry(
            SOURCE_KEY,
            YEAR_ENTRY_KIND,
            _year_entry_key(award_year),
            CACHE_VERSION,
            records=[_record_to_cache_dict(record) for record in records],
            source_urls=[_canonical_year_url(award_year)],
            coverage=_completed_year_coverage(award_year),
            ttl_seconds=HISTORICAL_YEAR_CACHE_TTL_SECONDS,
        )
    except OSError:
        pass


def _save_persistent_current_year(snapshot: _YearSnapshot) -> None:
    try:
        cache.save_cache_entry(
            SOURCE_KEY,
            YEAR_ENTRY_KIND,
            _year_entry_key(snapshot.award_year),
            CACHE_VERSION,
            records=[_record_to_cache_dict(record) for record in snapshot.records],
            source_urls=[snapshot.source_url],
            coverage=_current_year_coverage(snapshot),
            ttl_seconds=CURRENT_YEAR_CACHE_TTL_SECONDS,
        )
    except OSError:
        pass


def _load_persistent_index() -> tuple[tuple[int, ...], dict] | None:
    payload = cache.load_cache_entry(
        SOURCE_KEY,
        INDEX_ENTRY_KIND,
        ARCHIVE_INDEX_URL,
        CACHE_VERSION,
    )
    if payload is None:
        return None
    years = _index_years_from_payload(payload)
    if years is None:
        return None
    return years, payload


def _load_persistent_completed_year(
    award_year: int,
) -> tuple[tuple[_ParsedRecord, ...], dict] | None:
    payload = cache.load_cache_entry(
        SOURCE_KEY,
        YEAR_ENTRY_KIND,
        _year_entry_key(award_year),
        CACHE_VERSION,
    )
    if payload is None:
        return None
    records = _completed_year_from_payload(payload, award_year)
    if records is None:
        return None
    return records, payload


def _load_persistent_current_year(
    award_year: int,
) -> tuple[tuple[_ParsedRecord, ...], dict] | None:
    payload = cache.load_cache_entry(
        SOURCE_KEY,
        YEAR_ENTRY_KIND,
        _year_entry_key(award_year),
        CACHE_VERSION,
    )
    if payload is None:
        return None
    records = _current_year_from_payload(payload, award_year)
    if records is None:
        return None
    return records, payload


def _store_year_records(award_year: int, records: tuple[_ParsedRecord, ...]) -> None:
    with _cache_lock:
        _year_records_cache[award_year] = records


def _get_index_years() -> tuple[int, ...]:
    """Return completed years from RAM, complete stale/fresh disk, or live."""
    global _index_years_cache
    with _cache_lock:
        if _index_years_cache is not None:
            return _index_years_cache
    loaded = _load_persistent_index()
    if loaded is not None:
        years, _payload = loaded
        with _cache_lock:
            _index_years_cache = years
        return years
    years = _acquire_live_index_years()
    _save_persistent_index(years)
    with _cache_lock:
        _index_years_cache = years
    return years


def _get_completed_year_records(award_year: int) -> tuple[_ParsedRecord, ...]:
    """Historical year: RAM, then stale/fresh disk, else required live fetch."""
    with _cache_lock:
        cached = _year_records_cache.get(award_year)
    if cached is not None:
        return cached
    loaded = _load_persistent_completed_year(award_year)
    if loaded is not None:
        records, _payload = loaded
        _store_year_records(award_year, records)
        return records
    records = _acquire_completed_year_records(award_year)
    _store_year_records(award_year, records)
    _save_persistent_completed_year(award_year, records)
    return records


def _get_current_year_records(current_year: int) -> tuple[_ParsedRecord, ...]:
    """Current year: fresh disk, optional stale refresh, or required live."""
    with _cache_lock:
        cached = _year_records_cache.get(current_year)
    if cached is not None:
        return cached
    loaded = _load_persistent_current_year(current_year)
    if loaded is not None:
        records, payload = loaded
        if cache.cache_is_fresh(payload) or not cache.try_claim_stale_refresh():
            _store_year_records(current_year, records)
            return records
        try:
            snapshot = _acquire_current_year_snapshot(current_year)
        except Exception:
            _store_year_records(current_year, records)
            return records
        _store_year_records(current_year, snapshot.records)
        _save_persistent_current_year(snapshot)
        return snapshot.records
    snapshot = _acquire_current_year_snapshot(current_year)
    _store_year_records(current_year, snapshot.records)
    _save_persistent_current_year(snapshot)
    return snapshot.records


def _get_archive_records() -> tuple[_ParsedRecord, ...]:
    """Assemble index + completed years + current year. Fail closed on history."""
    global _archive_records_cache
    with _cache_lock:
        if _archive_records_cache is not None:
            return _archive_records_cache
    current_year = _current_calendar_year()
    completed_years = _get_index_years()
    records: list[_ParsedRecord] = []
    for year in completed_years:
        records.extend(_get_completed_year_records(year))
    records.extend(_get_current_year_records(current_year))
    assembled = _sort_records(records)
    with _cache_lock:
        _archive_records_cache = assembled
    return assembled


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
    # lower() not casefold(): Python casefold maps ß -> ss, which this source
    # must not treat as a match without later official-vs-Calibre evidence.
    text = text.lower()
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
        identity_kind='work',
    )


def lookup(title: str, author: str, series: str | None = None) -> list[AwardResult]:
    """Look up Deutscher Buchpreis results for a title and author.

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
