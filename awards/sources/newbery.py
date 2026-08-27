"""Official ALA John Newbery Medal HTML archive source.

Listing pages cover 1930-2023. Author confirmation is lazy: only title
candidates fetch a /winner/... page. 1922-1929 and 2024+ are out of scope.
This module does not register an engine source.
"""

from __future__ import annotations

import re
import threading
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from urllib.parse import urljoin, urlparse

from ..matching import normalize_title_conjunctions
from ..model import AwardResult

TIMEOUT_SECONDS = 30
AWARD_NAME = 'Newbery Medal'
CATEGORY = "Children's Literature"
SOURCE_NAME = 'John Newbery Medal'
SOURCE_HOME_URL = 'https://www.ala.org/'
DETAIL_ORIGIN = 'https://www.ala.org'

ARCHIVE_URL_2004_2023 = (
    'https://www.ala.org/awards/books-media/john-newbery-medal-2'
)
ARCHIVE_URL_1992_2003 = (
    'https://www.ala.org/awards/books-media/john-newbery-medal'
)
ARCHIVE_URL_1930_1991 = (
    'https://www.ala.org/awards/books-media/john-newbery-medal-1'
)
ARCHIVE_URLS = (
    ARCHIVE_URL_2004_2023,
    ARCHIVE_URL_1992_2003,
    ARCHIVE_URL_1930_1991,
)
# Drupal listing pages currently cover these years. Earlier and later years
# are out of scope and are not a structural failure.
ARCHIVE_MIN_YEAR = 1930
ARCHIVE_MAX_YEAR = 2023
_ARCHIVE_PAGE_SPECS: tuple[tuple[str, int, int], ...] = (
    (ARCHIVE_URL_1930_1991, 1930, 1991),
    (ARCHIVE_URL_1992_2003, 1992, 2003),
    (ARCHIVE_URL_2004_2023, 2004, 2023),
)

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

_OFFICIAL_HTML_HOSTS = frozenset({'ala.org', 'www.ala.org'})
_DETAIL_SLUG_RE = re.compile(r'^[0-9A-Za-z][0-9A-Za-z_-]*$')
_HEADING_YEAR_RE = re.compile(r'^(\d{4})$')
_WINNER_HONOR_RANK_RE = re.compile(
    r'^(?P<year>\d{4})\s*-\s*(?P<label>Winner|Honor)\(s\)\s*$',
    re.IGNORECASE,
)
_RUNNER_UP_RANK_RE = re.compile(
    r'^(?P<year>\d{4})\s*-\s*Runner(?:-|\s+)up(?:s|\(s\))?\s*$',
    re.IGNORECASE,
)
_INITIALS_SPACE_RE = re.compile(r'\b([A-Za-z])\.\s+')
_QUOTED_TITLE_PREFIX_RE = re.compile(
    r'^(?:'
    r'"[^"]+"'
    r'|\u201c[^\u201d]+\u201d'
    r")\s*"
)
_BYLINE_LEAD_RE = re.compile(
    r'^(?:written\s+by|by)\s+(?P<author>.+)$',
    re.IGNORECASE | re.DOTALL,
)
_PUBLISHER_CUT_RE = re.compile(
    r'[.,]?\s*(?:,\s*)?(?:and\s+)?published\s+by\b.*$',
    re.IGNORECASE | re.DOTALL,
)
_MAX_AUTHOR_LENGTH = 80


class NewberySourceError(RuntimeError):
    """Raised when official Newbery HTML cannot be parsed safely."""


@dataclass(frozen=True, slots=True)
class _ListingRecord:
    """One ALA listing-table row. Author is not present on listing pages."""

    work_title: str
    award_year: int
    status: str
    detail_url: str
    source_url: str


def _collapse_ws(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def _class_set(attrs: list[tuple[str, str | None]]) -> set[str]:
    attr = {name: (value or '') for name, value in attrs}
    return set(attr.get('class', '').split())


def _attr_map(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
    return {name: (value or '') for name, value in attrs}


def _safe_detail_url(href: str | None) -> str | None:
    """Return an official https://www.ala.org/winner/{slug} URL, or None."""
    if not href or not href.strip():
        return None
    resolved = urljoin(f'{DETAIL_ORIGIN}/', href.strip())
    parsed = urlparse(resolved)
    if parsed.scheme != 'https':
        return None
    host = (parsed.hostname or '').casefold().rstrip('.')
    if host not in _OFFICIAL_HTML_HOSTS:
        return None
    parts = [piece for piece in parsed.path.split('/') if piece]
    if len(parts) != 2:
        return None
    kind, slug = parts
    if kind.casefold() != 'winner' or not _DETAIL_SLUG_RE.fullmatch(slug):
        return None
    return f'{DETAIL_ORIGIN}/winner/{slug}'


def _normalize_status(label: str) -> str:
    key = _collapse_ws(label).casefold()
    if key == 'winner':
        return 'Winner'
    if key in {'honor', 'runner-up', 'runner up'}:
        return 'Honor'
    raise NewberySourceError(
        f'Newbery listing row has an unrecognized status {label!r}'
    )


def _parse_rank_text(text: str) -> tuple[int, str]:
    cleaned = _collapse_ws(text)
    match = _WINNER_HONOR_RANK_RE.fullmatch(cleaned)
    if match is not None:
        return int(match.group('year')), _normalize_status(match.group('label'))
    match = _RUNNER_UP_RANK_RE.fullmatch(cleaned)
    if match is not None:
        return int(match.group('year')), 'Honor'
    raise NewberySourceError(
        'Newbery listing row has a malformed award status '
        f'{cleaned!r}; expected "YYYY - Winner(s)" or "YYYY - Honor(s)"'
    )


class _NewberyListingParser(HTMLParser):
    """Parse one ALA Newbery Drupal winners-table page into listing records."""

    def __init__(self, source_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.source_url = source_url
        self.records: list[_ListingRecord] = []
        self._section_year: int | None = None
        self._in_year_heading = False
        self._heading_buffer: list[str] = []
        self._listing_table_depth = 0
        self._in_thead = False
        self._in_row = False
        self._td_kind: str | None = None
        self._in_title_p = False
        self._title_buffer: list[str] = []
        self._title_href: str | None = None
        self._rank_buffer: list[str] = []
        self._seen: set[tuple[int, str, str, str]] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = _class_set(attrs)
        attr = _attr_map(attrs)

        if tag == 'h3' and 'accordion-item__heading' in classes:
            self._in_year_heading = True
            self._heading_buffer = []
            return

        if tag == 'table' and 'views-table' in classes:
            self._listing_table_depth = 1
            return
        if tag == 'table' and self._listing_table_depth:
            self._listing_table_depth += 1
            return

        if not self._listing_table_depth:
            return

        if tag == 'thead':
            self._in_thead = True
            return
        if self._in_thead:
            return

        if tag == 'tr':
            self._in_row = True
            self._td_kind = None
            self._in_title_p = False
            self._title_buffer = []
            self._title_href = None
            self._rank_buffer = []
            return

        if not self._in_row:
            return

        if tag == 'td':
            if 'views-field-title-1' in classes:
                self._td_kind = 'title'
            elif 'views-field-field-winner-rank' in classes:
                self._td_kind = 'rank'
            else:
                self._td_kind = 'other'
            return

        if tag == 'p' and self._td_kind == 'title':
            self._in_title_p = True
            return

        if tag == 'a' and self._td_kind == 'title' and self._title_href is None:
            self._title_href = attr.get('href') or None

    def handle_endtag(self, tag: str) -> None:
        if tag == 'h3' and self._in_year_heading:
            heading = _collapse_ws(''.join(self._heading_buffer))
            year_match = _HEADING_YEAR_RE.fullmatch(heading)
            self._section_year = int(year_match.group(1)) if year_match else None
            self._in_year_heading = False
            self._heading_buffer = []
            return

        if tag == 'thead' and self._listing_table_depth:
            self._in_thead = False
            return

        if tag == 'p' and self._in_title_p:
            self._in_title_p = False
            return

        if tag == 'td' and self._in_row:
            self._td_kind = None
            self._in_title_p = False
            return

        if tag == 'tr' and self._in_row:
            self._finish_row()
            self._in_row = False
            return

        if tag == 'table' and self._listing_table_depth:
            self._listing_table_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_year_heading:
            self._heading_buffer.append(data)
            return
        if self._td_kind == 'title' and not self._in_title_p:
            self._title_buffer.append(data)
            return
        if self._td_kind == 'rank':
            self._rank_buffer.append(data)

    def _finish_row(self) -> None:
        title = _collapse_ws(''.join(self._title_buffer))
        rank_text = _collapse_ws(''.join(self._rank_buffer))
        href = self._title_href
        if not title and not rank_text and not href:
            return
        if not title:
            raise NewberySourceError(
                'Newbery listing row is missing a title for '
                f'{self.source_url}'
            )
        if not rank_text:
            raise NewberySourceError(
                'Newbery listing row is missing an award status for '
                f'{title!r} on {self.source_url}'
            )
        award_year, status = _parse_rank_text(rank_text)
        if (
            self._section_year is not None
            and award_year != self._section_year
        ):
            raise NewberySourceError(
                'Newbery listing row year does not match its accordion '
                f'section: row={award_year}, section={self._section_year} '
                f'for {title!r} on {self.source_url}'
            )
        detail_url = _safe_detail_url(href)
        if detail_url is None:
            raise NewberySourceError(
                'Newbery listing row is missing an official winner URL for '
                f'{title!r} on {self.source_url}'
            )
        key = (
            award_year,
            status.casefold(),
            title.casefold(),
            detail_url.casefold(),
        )
        if key in self._seen:
            return
        self._seen.add(key)
        self.records.append(
            _ListingRecord(
                work_title=title,
                award_year=award_year,
                status=status,
                detail_url=detail_url,
                source_url=self.source_url,
            )
        )


def _parse_listing_html(html: str, source_url: str) -> list[_ListingRecord]:
    """Parse one official Newbery listing page. Malformed rows raise."""
    parser = _NewberyListingParser(source_url)
    parser.feed(html)
    parser.close()
    return parser.records


def _author_from_byline(text: str) -> str | None:
    """Extract a work author from an ALA winner-page byline, or None.

    Stops before publisher information. Does not guess from blurbs.
    """
    cleaned = _collapse_ws(text)
    if not cleaned:
        return None
    remainder = _QUOTED_TITLE_PREFIX_RE.sub('', cleaned, count=1).strip()
    match = _BYLINE_LEAD_RE.fullmatch(remainder)
    if match is None:
        return None
    author = _PUBLISHER_CUT_RE.sub('', match.group('author')).strip()
    author = author.strip(' ,.;')
    if not author:
        return None
    if 'published by' in author.casefold():
        return None
    if len(author) > _MAX_AUTHOR_LENGTH:
        return None
    return author


class _NewberyDetailParser(HTMLParser):
    """Capture the first paragraph after h1; ignore About/body blurbs."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.byline: str | None = None
        self._in_h1 = False
        self._seen_h1 = False
        self._in_byline_p = False
        self._byline_buffer: list[str] = []
        self._byline_done = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == 'h1':
            self._in_h1 = True
            return
        if self._byline_done or self._in_h1:
            return
        if tag == 'h2' and self._seen_h1:
            self._byline_done = True
            return
        if tag == 'p' and self._seen_h1 and not self._in_byline_p:
            self._in_byline_p = True
            self._byline_buffer = []

    def handle_endtag(self, tag: str) -> None:
        if tag == 'h1' and self._in_h1:
            self._in_h1 = False
            self._seen_h1 = True
            return
        if tag == 'p' and self._in_byline_p:
            self.byline = _collapse_ws(''.join(self._byline_buffer))
            self._in_byline_p = False
            self._byline_done = True

    def handle_data(self, data: str) -> None:
        if self._in_byline_p:
            self._byline_buffer.append(data)


def _parse_detail_author(html: str) -> str | None:
    """Return the winner-page byline author, or None if none is usable."""
    parser = _NewberyDetailParser()
    parser.feed(html)
    parser.close()
    if not parser.byline:
        return None
    return _author_from_byline(parser.byline)


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
    if query_norm == record_norm:
        return True

    query_has_subtitle = ':' in query_norm
    record_has_subtitle = ':' in record_norm
    if query_has_subtitle == record_has_subtitle:
        return False

    query_base = (
        query_norm.split(':', 1)[0].strip() if query_has_subtitle else query_norm
    )
    record_base = (
        record_norm.split(':', 1)[0].strip() if record_has_subtitle else record_norm
    )
    return bool(query_base) and query_base == record_base


# Comparison-only. AwardResult.work_author keeps the official ALA spelling.
# The 1972 Tombs of Atuan winner page writes "LeGuin" without a space.
# Keys are _normalize_text results (initials compacted: "K. Le" -> "k.le").
_LE_GUIN_MATCH_FORMS = frozenset({
    'ursula k.leguin',
    'ursula k.le guin',
})
_LE_GUIN_MATCH_KEY = 'ursula k.le guin'


def _author_match_key(author: str) -> str:
    """Return the Newbery author comparison key.

    Exact normalized spelling except for the explicit Le Guin/LeGuin alias.
    """
    normalized = _normalize_text(author)
    if normalized in _LE_GUIN_MATCH_FORMS:
        return _LE_GUIN_MATCH_KEY
    return normalized


def _authors_match(query_author: str, record_author: str) -> bool:
    # Exact normalized strings, plus the explicit Le Guin alias above.
    return _author_match_key(query_author) == _author_match_key(record_author)


# ---------------------------------------------------------------------------
# HTTP retrieval
# ---------------------------------------------------------------------------

def _build_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(CookieJar())
    )


def _read_response_body(response) -> str:
    return response.read().decode('utf-8', errors='replace')


def _fetch_html(opener: urllib.request.OpenerDirector, url: str) -> str:
    request = urllib.request.Request(url, headers=dict(_BROWSER_HEADERS))
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            status = getattr(response, 'status', None) or response.getcode()
            html = _read_response_body(response)
    except urllib.error.HTTPError as exc:
        body = _read_response_body(exc)
        raise NewberySourceError(
            f'Newbery request failed with HTTP {exc.code} for {url}'
            + (f': {body[:200].strip()}' if body.strip() else '')
        ) from exc
    except urllib.error.URLError as exc:
        raise NewberySourceError(
            f'Newbery request failed for {url}: {exc.reason}'
        ) from exc
    except TimeoutError as exc:
        raise NewberySourceError(
            f'Newbery request timed out for {url}'
        ) from exc

    if status != 200:
        raise NewberySourceError(
            f'Newbery request failed with HTTP {status} for {url}'
        )
    return html


# ---------------------------------------------------------------------------
# Archive validation and listing cache
# ---------------------------------------------------------------------------

_listing_records_cache: tuple[_ListingRecord, ...] | None = None
_detail_author_cache: dict[str, str] = {}
_cache_lock = threading.Lock()


def _reset_runtime_state() -> None:
    """Clear in-process caches. Used by tests."""
    global _listing_records_cache
    with _cache_lock:
        _listing_records_cache = None
        _detail_author_cache.clear()


def _in_phase_range(year: int) -> bool:
    return ARCHIVE_MIN_YEAR <= year <= ARCHIVE_MAX_YEAR


def _validate_page_records(
    records: list[_ListingRecord],
    url: str,
    start_year: int,
    end_year: int,
) -> None:
    """Require this page's year range; ignore years outside 1930-2023."""
    by_year: dict[int, list[_ListingRecord]] = {}
    for record in records:
        year = record.award_year
        if not _in_phase_range(year):
            continue
        if year < start_year or year > end_year:
            raise NewberySourceError(
                f'Newbery archive page {url} contained year {year}, '
                f'which belongs on another listing page'
            )
        by_year.setdefault(year, []).append(record)

    missing = [
        year
        for year in range(start_year, end_year + 1)
        if year not in by_year
    ]
    if missing:
        raise NewberySourceError(
            f'Newbery archive page {url} is missing required years: '
            + ', '.join(str(year) for year in missing)
        )

    for year in range(start_year, end_year + 1):
        winners = [
            record for record in by_year[year] if record.status == 'Winner'
        ]
        if not winners:
            raise NewberySourceError(
                f'Newbery archive page {url} has no Winner for {year}'
            )
        if len(winners) > 1:
            raise NewberySourceError(
                f'Newbery archive page {url} has {len(winners)} Winners '
                f'for {year}'
            )


def _usable_listing_records(
    records: list[_ListingRecord],
) -> tuple[_ListingRecord, ...]:
    return tuple(
        record for record in records if _in_phase_range(record.award_year)
    )


def _validate_combined_archive(records: tuple[_ListingRecord, ...]) -> None:
    if not records:
        raise NewberySourceError(
            'Newbery archive pages were retrieved but no 1930-2023 records '
            'could be parsed'
        )
    by_year: dict[int, list[_ListingRecord]] = {}
    for record in records:
        by_year.setdefault(record.award_year, []).append(record)
    missing = [
        year
        for year in range(ARCHIVE_MIN_YEAR, ARCHIVE_MAX_YEAR + 1)
        if year not in by_year
    ]
    if missing:
        raise NewberySourceError(
            'Newbery combined archive is missing required years: '
            + ', '.join(str(year) for year in missing)
        )
    for year in range(ARCHIVE_MIN_YEAR, ARCHIVE_MAX_YEAR + 1):
        winners = [
            record for record in by_year[year] if record.status == 'Winner'
        ]
        if len(winners) != 1:
            raise NewberySourceError(
                'Newbery combined archive does not have exactly one Winner '
                f'for {year}'
            )


def _load_listing_records() -> tuple[_ListingRecord, ...]:
    """Fetch all three archive pages, validate, and keep 1930-2023 rows."""
    opener = _build_opener()
    combined: list[_ListingRecord] = []
    for url, start_year, end_year in _ARCHIVE_PAGE_SPECS:
        html = _fetch_html(opener, url)
        records = _parse_listing_html(html, url)
        _validate_page_records(records, url, start_year, end_year)
        combined.extend(records)
    usable = _usable_listing_records(combined)
    _validate_combined_archive(usable)
    return usable


def _get_listing_records() -> tuple[_ListingRecord, ...]:
    """Return cached 1930-2023 listing records after a successful load."""
    global _listing_records_cache
    with _cache_lock:
        if _listing_records_cache is not None:
            return _listing_records_cache
        records = _load_listing_records()
        _listing_records_cache = records
        return records


def _get_detail_author(
    opener: urllib.request.OpenerDirector,
    url: str,
) -> str:
    """Return a cached official author, fetching the winner page once."""
    with _cache_lock:
        cached = _detail_author_cache.get(url)
        if cached is not None:
            return cached
        html = _fetch_html(opener, url)
        author = _parse_detail_author(html)
        if author is None:
            raise NewberySourceError(
                'Newbery winner page did not contain a usable author byline '
                f'for {url}'
            )
        _detail_author_cache[url] = author
        return author


def _to_award_result(record: _ListingRecord, work_author: str) -> AwardResult:
    return AwardResult(
        work_title=record.work_title,
        work_author=work_author,
        award_name=AWARD_NAME,
        award_year=record.award_year,
        category=CATEGORY,
        status=record.status,
        rank=None,
        source_name=SOURCE_NAME,
        source_url=record.detail_url,
        notes=None,
        identity_kind='work',
    )


def lookup(
    title: str,
    author: str,
    series: str | None = None,
) -> list[AwardResult]:
    """Look up Newbery Medal results for a title and author (1930-2023)."""
    cleaned_title = title.strip()
    cleaned_author = author.strip()
    if not cleaned_title:
        raise ValueError('title must be a non-empty string')
    if not cleaned_author:
        raise ValueError('author must be a non-empty string')

    candidates = [
        record
        for record in _get_listing_records()
        if _titles_match(cleaned_title, record.work_title)
    ]
    if not candidates:
        return []

    opener = _build_opener()
    matches: list[AwardResult] = []
    seen: set[tuple[int, str, str, str, str]] = set()
    for record in candidates:
        official_author = _get_detail_author(opener, record.detail_url)
        if not _authors_match(cleaned_author, official_author):
            continue
        key = (
            record.award_year,
            record.status,
            record.work_title.casefold(),
            official_author.casefold(),
            record.detail_url,
        )
        if key in seen:
            continue
        seen.add(key)
        matches.append(_to_award_result(record, official_author))
    return matches