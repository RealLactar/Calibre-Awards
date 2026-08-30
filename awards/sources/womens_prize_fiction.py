"""Official Women's Prize for Fiction winner archive (Phase 1).

Two HTTP GETs: previous-prizes winner cards (1996 through the latest archived
year) plus the current prize page Winner. Shortlist and longlist are ignored.
JavaScript is not required. Historical Orange Prize years use the current
award name.
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
SOURCE_KEY = 'womens_prize_fiction'
AWARD_NAME = "Women's Prize for Fiction"
CATEGORY = 'Fiction'
SOURCE_NAME = "Women's Prize for Fiction"
SITE_ORIGIN = 'https://womensprize.com'
SOURCE_HOME_URL = SITE_ORIGIN + '/prizes/womens-prize-for-fiction/'
PREVIOUS_PRIZES_URL = (
    SITE_ORIGIN + '/prizes/womens-prize-for-fiction/previous-prizes/'
)
ARCHIVE_MIN_YEAR = 1996
CACHE_VERSION = 1
# 7-day base plus an explicit stagger. Do not derive from AWARD_SOURCES order.
CACHE_BASE_TTL_SECONDS = 7 * 24 * 60 * 60
CACHE_REFRESH_OFFSET_SECONDS = 10 * 60 * 60
CACHE_TTL_SECONDS = CACHE_BASE_TTL_SECONDS + CACHE_REFRESH_OFFSET_SECONDS

_OFFICIAL_HTML_HOSTS = frozenset({
    'womensprize.com',
    'www.womensprize.com',
})
_LIBRARY_SLUG_RE = re.compile(r'^[0-9A-Za-z][0-9A-Za-z_-]*$')
_INITIALS_SPACE_RE = re.compile(r'\b([A-Za-z])\.\s+')
_TITLE_BY_AUTHOR_RE = re.compile(
    r'^(?P<title>.+?)\s+by\s+(?P<author>.+)$',
    re.IGNORECASE,
)
_WON_YEAR_PHRASE_RE = re.compile(
    r'has won the\s+(?P<year>19\d{2}|20\d{2})\s+women',
    re.IGNORECASE,
)
_ARCHIVE_IDENTITY_MARKERS = (
    'previous-prizes',
    "previous winners of the women's prize for fiction",
    "women's prize for fiction",
)
_HOME_FICTION_H1_RE = re.compile(
    r'<h1[^>]*>\s*(?:the\s+)?women(?:[\'\u2019]|&#8217;)s prize for fiction\s*</h1>',
    re.IGNORECASE,
)
_HOME_NONFICTION_H1_RE = re.compile(
    r'<h1[^>]*>\s*(?:the\s+)?'
    r'women(?:[\'\u2019]|&#8217;)s prize for non-fiction\s*</h1>',
    re.IGNORECASE,
)
_OLDEST_TITLE = 'A Spell of Winter'
_OLDEST_AUTHOR = 'Helen Dunmore'
_CURRENT_YEAR_STATES = frozenset({'absent', 'winner'})
_IGNORE_TAGS = frozenset({
    'script',
    'style',
    'svg',
    'noscript',
    'iframe',
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


class WomensPrizeFictionSourceError(RuntimeError):
    """Raised when the official Women's Prize pages are blocked or unusable."""


@dataclass(frozen=True, slots=True)
class _ParsedRecord:
    award_year: int
    category: str
    status: str
    work_title: str
    work_author: str
    source_url: str


@dataclass(frozen=True, slots=True)
class _ArchiveCard:
    work_title: str
    work_author: str
    source_url: str


@dataclass(frozen=True, slots=True)
class _ParseSnapshot:
    records: tuple[_ParsedRecord, ...]
    archive_max_year: int
    current_year_state: str


_PARSED_STATUSES = frozenset({'Winner'})
_RECORD_CACHE_FIELDS = (
    'award_year',
    'category',
    'source_url',
    'status',
    'work_author',
    'work_title',
)
_COVERAGE_FIELDS = frozenset({
    'archive_max_year',
    'current_year',
    'current_year_state',
    'max_winner_year',
    'min_year',
    'record_count',
    'winner_count',
})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _current_calendar_year() -> int:
    """UTC calendar year. Tests may patch _utc_now or this helper."""
    return _utc_now().year


def _collapse_ws(text: str) -> str:
    text = (
        text.replace('\xa0', ' ')
        .replace('\u2009', ' ')
        .replace('\u202f', ' ')
    )
    return re.sub(r'\s+', ' ', text).strip()


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
        raise WomensPrizeFictionSourceError(
            f"Women's Prize request failed with HTTP {exc.code} for {url}"
        ) from exc
    except urllib.error.URLError as exc:
        raise WomensPrizeFictionSourceError(
            f"Women's Prize request failed for {url}: {exc.reason}"
        ) from exc
    if status != 200:
        raise WomensPrizeFictionSourceError(
            f"Women's Prize request failed with HTTP {status} for {url}"
        )
    return html


_archive_records_cache: tuple[_ParsedRecord, ...] | None = None
_cache_lock = threading.Lock()


def _reset_runtime_state() -> None:
    """Clear in-process caches. Used by tests. Does not delete disk cache."""
    global _archive_records_cache
    with _cache_lock:
        _archive_records_cache = None


# ---------------------------------------------------------------------------
# URLs
# ---------------------------------------------------------------------------

def _official_library_url(href: str | None) -> str | None:
    if not href or not href.strip():
        return None
    resolved = urljoin(f'{SITE_ORIGIN}/', href.strip())
    parsed = urlparse(resolved)
    if parsed.scheme not in {'http', 'https'}:
        return None
    host = (parsed.hostname or '').casefold().rstrip('.')
    if host not in _OFFICIAL_HTML_HOSTS:
        return None
    parts = [piece for piece in parsed.path.split('/') if piece]
    if len(parts) != 2 or parts[0].casefold() != 'library':
        return None
    slug = parts[1]
    if not _LIBRARY_SLUG_RE.fullmatch(slug):
        return None
    return f'{SITE_ORIGIN}/library/{slug}/'


def _source_url_is_usable(source_url: str) -> bool:
    reconstructed = _official_library_url(source_url)
    return reconstructed is not None and reconstructed == source_url


def _class_tokens(value: str) -> frozenset[str]:
    return frozenset(value.split())


# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------

class _PreviousPrizesParser(HTMLParser):
    """Collect newest-first winner cards from the official book-grid."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cards: list[_ArchiveCard] = []
        self._ignore_depth = 0
        self._in_book_grid = 0
        self._in_card = 0
        self._in_content = False
        self._capture: str | None = None
        self._buffer: list[str] = []
        self._href: str | None = None
        self._title = ''
        self._author = ''

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {name: (value or '') for name, value in attrs}
        classes = _class_tokens(attr.get('class', ''))
        if tag in _IGNORE_TAGS:
            self._ignore_depth += 1
            return
        if self._ignore_depth:
            return
        if tag == 'section' and 'book-grid' in classes:
            self._in_book_grid += 1
            return
        if not self._in_book_grid:
            return
        if tag == 'div' and 'post-card--book' in classes:
            self._finish_card()
            self._in_card += 1
            return
        if not self._in_card:
            return
        if tag == 'span' and 'post-card__content' in classes:
            self._in_content = True
            return
        if tag == 'a':
            library = _official_library_url(attr.get('href'))
            if library is not None:
                self._href = library
            return
        if self._in_content and tag in {'h5', 'p'}:
            self._capture = tag
            self._buffer = []

    def handle_endtag(self, tag: str) -> None:
        if tag in _IGNORE_TAGS:
            if self._ignore_depth:
                self._ignore_depth -= 1
            return
        if self._ignore_depth:
            return
        if tag == 'section' and self._in_book_grid:
            self._finish_card()
            self._in_book_grid -= 1
            return
        if not self._in_book_grid:
            return
        if self._capture == tag:
            text = _collapse_ws(''.join(self._buffer))
            self._capture = None
            self._buffer = []
            if tag == 'h5':
                self._title = text
            elif tag == 'p' and not self._author:
                self._author = text
            return
        if tag == 'span' and self._in_content:
            self._in_content = False
            return
        if tag == 'div' and self._in_card:
            self._finish_card()
            self._in_card -= 1

    def handle_data(self, data: str) -> None:
        if self._ignore_depth or self._capture is None:
            return
        self._buffer.append(data)

    def _finish_card(self) -> None:
        title = _collapse_ws(self._title)
        author = _collapse_ws(self._author)
        href = self._href
        self._title = ''
        self._author = ''
        self._href = None
        self._capture = None
        self._buffer = []
        self._in_content = False
        if not title or not author or href is None:
            return
        self.cards.append(
            _ArchiveCard(
                work_title=title,
                work_author=author,
                source_url=href,
            )
        )


class _HomeWinnerParser(HTMLParser):
    """Collect the current-page Winner eyebrow block and overview text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.visible_parts: list[str] = []
        self.winner_line = ''
        self.winner_href: str | None = None
        self._ignore_depth = 0
        self._capture: str | None = None
        self._buffer: list[str] = []
        self._awaiting_winner_line = False
        self._in_winner_block = False
        self._skip_visible = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {name: (value or '') for name, value in attrs}
        classes = _class_tokens(attr.get('class', ''))
        if tag in _IGNORE_TAGS:
            self._ignore_depth += 1
            return
        if self._ignore_depth:
            return
        if tag == 'a' and 'book_card' in classes:
            self._skip_visible = True
        if tag == 'p' and 'eyebrow' in classes:
            self._capture = 'eyebrow'
            self._buffer = []
            return
        if tag == 'h3' and self._awaiting_winner_line:
            self._capture = 'h3'
            self._buffer = []
            return
        if tag == 'h1':
            self._capture = 'h1'
            self._buffer = []
            return
        if (
            tag == 'a'
            and self._in_winner_block
            and self.winner_href is None
            and 'book_card' not in classes
        ):
            library = _official_library_url(attr.get('href'))
            if library is not None:
                self.winner_href = library

    def handle_endtag(self, tag: str) -> None:
        if tag in _IGNORE_TAGS:
            if self._ignore_depth:
                self._ignore_depth -= 1
            return
        if self._ignore_depth:
            return
        if tag == 'a':
            self._skip_visible = False
        ended = tag
        if tag == 'p' and self._capture == 'eyebrow':
            ended = 'eyebrow'
        if self._capture == ended:
            text = _collapse_ws(''.join(self._buffer))
            self._capture = None
            self._buffer = []
            if ended == 'eyebrow' and text.casefold() == 'winner':
                self._awaiting_winner_line = True
                self._in_winner_block = True
            elif ended == 'h3' and self._awaiting_winner_line:
                self.winner_line = text
                self._awaiting_winner_line = False
            return

    def handle_data(self, data: str) -> None:
        if self._ignore_depth:
            return
        if self._capture is not None:
            self._buffer.append(data)
        if not self._skip_visible:
            self.visible_parts.append(data)


def _identity_text(html: str) -> str:
    return (
        html.replace('\u2019', "'")
        .replace('&#8217;', "'")
        .replace('&#x2019;', "'")
        .casefold()
    )


def _require_archive_identity(html: str) -> None:
    lowered = _identity_text(html)
    if all(marker in lowered for marker in _ARCHIVE_IDENTITY_MARKERS):
        return
    raise WomensPrizeFictionSourceError(
        "Women's Prize previous-prizes page did not match the official archive"
    )


def _require_home_identity(html: str) -> None:
    if _HOME_NONFICTION_H1_RE.search(html):
        raise WomensPrizeFictionSourceError(
            "Women's Prize home page is the Non-Fiction prize, not Fiction"
        )
    if _HOME_FICTION_H1_RE.search(html):
        return
    raise WomensPrizeFictionSourceError(
        "Women's Prize home page did not match the official fiction prize"
    )


def _parse_previous_prizes_html(html: str) -> tuple[_ArchiveCard, ...]:
    parser = _PreviousPrizesParser()
    parser.feed(html)
    parser.close()
    return tuple(parser.cards)


def _assign_archive_years(
    cards: tuple[_ArchiveCard, ...],
) -> tuple[tuple[_ParsedRecord, ...], int]:
    if not cards:
        raise WomensPrizeFictionSourceError(
            "Women's Prize previous-prizes page contained no winner cards"
        )
    archive_max_year = ARCHIVE_MIN_YEAR + len(cards) - 1
    current_year = _current_calendar_year()
    if archive_max_year > current_year:
        raise WomensPrizeFictionSourceError(
            "Women's Prize archive max year is in the future"
        )
    records = []
    for index, card in enumerate(cards):
        records.append(
            _ParsedRecord(
                award_year=archive_max_year - index,
                category=CATEGORY,
                status='Winner',
                work_title=card.work_title,
                work_author=card.work_author,
                source_url=card.source_url,
            )
        )
    return tuple(records), archive_max_year


def _year_for_winner(visible: str, title: str, author: str) -> int | None:
    """Return the official year naming this Winner, or None if none is proven."""
    for found in _WON_YEAR_PHRASE_RE.finditer(visible):
        clause = visible[max(0, found.start() - 280):found.start()]
        by_line = _TITLE_BY_AUTHOR_RE.search(clause)
        if by_line is not None and _titles_match(
            by_line.group('title'), title
        ) and _authors_match(by_line.group('author'), author):
            return int(found.group('year'))
        if title.casefold() in clause.casefold() and author.casefold() in clause.casefold():
            return int(found.group('year'))
    return None


def _parse_current_winner(html: str) -> _ParsedRecord | None:
    parser = _HomeWinnerParser()
    parser.feed(html)
    parser.close()
    if not parser.winner_line:
        return None
    match = _TITLE_BY_AUTHOR_RE.fullmatch(parser.winner_line)
    if match is None:
        raise WomensPrizeFictionSourceError(
            "Women's Prize home page Winner line was not title-by-author"
        )
    title = _collapse_ws(match.group('title'))
    author = _collapse_ws(match.group('author'))
    if not title or not author:
        raise WomensPrizeFictionSourceError(
            "Women's Prize home page Winner was missing title or author"
        )
    visible = _collapse_ws(''.join(parser.visible_parts))
    year = _year_for_winner(visible, title, author)
    if year is None:
        raise WomensPrizeFictionSourceError(
            "Women's Prize home page Winner year could not be determined"
        )
    if year > _current_calendar_year():
        raise WomensPrizeFictionSourceError(
            "Women's Prize home page Winner year is in the future"
        )
    if parser.winner_href is None:
        raise WomensPrizeFictionSourceError(
            "Women's Prize home page Winner was missing a library URL"
        )
    return _ParsedRecord(
        award_year=year,
        category=CATEGORY,
        status='Winner',
        work_title=title,
        work_author=author,
        source_url=parser.winner_href,
    )


def _identity_key(record: _ParsedRecord) -> tuple[int, str, str]:
    return (
        record.award_year,
        _normalize_text(record.work_title),
        _normalize_text(record.work_author),
    )


def _merge_records(
    archive_records: tuple[_ParsedRecord, ...],
    current: _ParsedRecord | None,
) -> tuple[_ParsedRecord, ...]:
    by_year: dict[int, _ParsedRecord] = {}
    order: list[int] = []
    for record in archive_records:
        if record.award_year not in by_year:
            order.append(record.award_year)
        by_year[record.award_year] = record
    if current is not None:
        existing = by_year.get(current.award_year)
        if existing is None:
            by_year[current.award_year] = current
            order.append(current.award_year)
        elif _identity_key(existing) != _identity_key(current):
            # Same year already archived: keep archive spelling.
            pass
    return tuple(by_year[year] for year in sorted(order))


def _validate_archive_records(
    records: tuple[_ParsedRecord, ...],
    archive_max_year: int,
) -> None:
    if not records:
        raise WomensPrizeFictionSourceError(
            "Women's Prize previous-prizes page contained no winner cards"
        )
    years = [record.award_year for record in records]
    expected = list(range(ARCHIVE_MIN_YEAR, archive_max_year + 1))
    if sorted(years) != expected:
        raise WomensPrizeFictionSourceError(
            "Women's Prize archive years were not contiguous from "
            f'{ARCHIVE_MIN_YEAR} through {archive_max_year}'
        )
    if years[-1] != ARCHIVE_MIN_YEAR:
        raise WomensPrizeFictionSourceError(
            "Women's Prize archive oldest year was not "
            f'{ARCHIVE_MIN_YEAR}'
        )
    oldest = records[-1]
    if (
        not _titles_match(oldest.work_title, _OLDEST_TITLE)
        or not _authors_match(oldest.work_author, _OLDEST_AUTHOR)
        or oldest.award_year != ARCHIVE_MIN_YEAR
    ):
        raise WomensPrizeFictionSourceError(
            "Women's Prize archive oldest winner was not "
            f'{_OLDEST_TITLE} / {_OLDEST_AUTHOR}'
        )
    identities = [_identity_key(record) for record in records]
    if len(identities) != len(set(identities)):
        raise WomensPrizeFictionSourceError(
            "Women's Prize archive contained duplicate work/year identities"
        )
    years_set = set(years)
    if len(years_set) != len(years):
        raise WomensPrizeFictionSourceError(
            "Women's Prize archive contained more than one Winner for a year"
        )
    for record in records:
        _validate_record(record)


def _validate_record(record: _ParsedRecord) -> None:
    if record.category != CATEGORY:
        raise WomensPrizeFictionSourceError(
            f"Women's Prize produced an unsupported category: {record.category!r}"
        )
    if record.status not in _PARSED_STATUSES:
        raise WomensPrizeFictionSourceError(
            f"Women's Prize produced an unexpected status: {record.status!r}"
        )
    if not record.work_title or not record.work_title.strip():
        raise WomensPrizeFictionSourceError("Women's Prize produced an empty title")
    if not record.work_author or not record.work_author.strip():
        raise WomensPrizeFictionSourceError("Women's Prize produced an empty author")
    if not _source_url_is_usable(record.source_url):
        raise WomensPrizeFictionSourceError(
            f"Women's Prize produced an unexpected source URL: {record.source_url!r}"
        )
    if (
        not isinstance(record.award_year, int)
        or isinstance(record.award_year, bool)
        or record.award_year < ARCHIVE_MIN_YEAR
    ):
        raise WomensPrizeFictionSourceError(
            f"Women's Prize produced an unexpected year: {record.award_year!r}"
        )


def _validate_merged_records(
    records: tuple[_ParsedRecord, ...],
    archive_max_year: int,
) -> None:
    if not records:
        raise WomensPrizeFictionSourceError(
            "Women's Prize produced no Winner records"
        )
    current_year = _current_calendar_year()
    if archive_max_year > current_year:
        raise WomensPrizeFictionSourceError(
            "Women's Prize archive max year is in the future"
        )
    identities = [_identity_key(record) for record in records]
    if len(identities) != len(set(identities)):
        raise WomensPrizeFictionSourceError(
            "Women's Prize produced duplicate work/year identities"
        )
    winners_by_year: dict[int, int] = {}
    for record in records:
        _validate_record(record)
        winners_by_year[record.award_year] = (
            winners_by_year.get(record.award_year, 0) + 1
        )
    for year in range(ARCHIVE_MIN_YEAR, current_year):
        count = winners_by_year.get(year, 0)
        if count != 1:
            raise WomensPrizeFictionSourceError(
                f"Women's Prize year {year} had {count} Winner record(s); "
                'completed years must have exactly 1'
            )
    if winners_by_year.get(current_year, 0) > 1:
        raise WomensPrizeFictionSourceError(
            f"Women's Prize year {current_year} had an unexpected Winner count"
        )
    extra_years = [year for year in winners_by_year if year > current_year]
    if extra_years:
        raise WomensPrizeFictionSourceError(
            "Women's Prize produced a Winner after the current calendar year"
        )
    oldest = min(records, key=lambda item: item.award_year)
    if (
        oldest.award_year != ARCHIVE_MIN_YEAR
        or not _titles_match(oldest.work_title, _OLDEST_TITLE)
        or not _authors_match(oldest.work_author, _OLDEST_AUTHOR)
    ):
        raise WomensPrizeFictionSourceError(
            "Women's Prize oldest winner was not "
            f'{_OLDEST_TITLE} / {_OLDEST_AUTHOR}'
        )


def _validate_cached_archive(
    records: tuple[_ParsedRecord, ...],
    coverage: dict | None = None,
) -> None:
    if coverage is None:
        archive_max = max(record.award_year for record in records)
        _validate_merged_records(records, archive_max)
        return
    _validate_cached_coverage(records, coverage)


def _validate_cached_coverage(
    records: tuple[_ParsedRecord, ...],
    coverage: dict,
) -> None:
    if not isinstance(coverage, dict) or set(coverage) != _COVERAGE_FIELDS:
        raise WomensPrizeFictionSourceError(
            "Women's Prize coverage metadata is incomplete"
        )
    archive_max = coverage.get('archive_max_year')
    if (
        isinstance(archive_max, bool)
        or not isinstance(archive_max, int)
        or archive_max < ARCHIVE_MIN_YEAR
    ):
        raise WomensPrizeFictionSourceError(
            "Women's Prize coverage archive_max_year is invalid"
        )
    _validate_merged_records(records, archive_max)
    current_year = _current_calendar_year()
    stored_year = coverage.get('current_year')
    state = coverage.get('current_year_state')
    if (
        isinstance(stored_year, bool)
        or not isinstance(stored_year, int)
        or stored_year < ARCHIVE_MIN_YEAR
        or stored_year > current_year
    ):
        raise WomensPrizeFictionSourceError(
            "Women's Prize coverage current year is stale or invalid"
        )
    if state not in _CURRENT_YEAR_STATES:
        raise WomensPrizeFictionSourceError(
            "Women's Prize coverage has an unknown current-year state"
        )
    if coverage.get('min_year') != ARCHIVE_MIN_YEAR:
        raise WomensPrizeFictionSourceError(
            "Women's Prize coverage does not begin at 1996"
        )
    derived_state = 'winner' if any(
        record.award_year == current_year for record in records
    ) else 'absent'
    if stored_year == current_year and state != derived_state:
        raise WomensPrizeFictionSourceError(
            "Women's Prize coverage current-year state does not match records"
        )


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
    return (PREVIOUS_PRIZES_URL, SOURCE_HOME_URL)


def _coverage_from_snapshot(snapshot: _ParseSnapshot) -> dict:
    records = snapshot.records
    years = [record.award_year for record in records]
    current_year = _current_calendar_year()
    return {
        'archive_max_year': snapshot.archive_max_year,
        'current_year': current_year,
        'current_year_state': snapshot.current_year_state,
        'max_winner_year': max(years) if years else None,
        'min_year': min(years) if years else ARCHIVE_MIN_YEAR,
        'record_count': len(records),
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
        _validate_cached_archive(restored, payload.get('coverage'))
    except WomensPrizeFictionSourceError:
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


def _save_persistent_archive(snapshot: _ParseSnapshot) -> None:
    try:
        cache.save_source_cache(
            SOURCE_KEY,
            CACHE_VERSION,
            records=[_record_to_cache_dict(record) for record in snapshot.records],
            source_urls=_archive_source_urls(),
            coverage=_coverage_from_snapshot(snapshot),
            ttl_seconds=CACHE_TTL_SECONDS,
        )
    except OSError:
        pass


def _fetch_parse_validate() -> _ParseSnapshot:
    archive_html = _fetch_html(PREVIOUS_PRIZES_URL)
    _require_archive_identity(archive_html)
    cards = _parse_previous_prizes_html(archive_html)
    archive_records, archive_max_year = _assign_archive_years(cards)
    _validate_archive_records(archive_records, archive_max_year)

    current: _ParsedRecord | None = None
    try:
        home_html = _fetch_html(SOURCE_HOME_URL)
        _require_home_identity(home_html)
        current = _parse_current_winner(home_html)
    except WomensPrizeFictionSourceError:
        current = None

    merged = _merge_records(archive_records, current)
    _validate_merged_records(merged, archive_max_year)
    current_year = _current_calendar_year()
    state = 'winner' if any(
        record.award_year == current_year for record in merged
    ) else 'absent'
    return _ParseSnapshot(
        records=merged,
        archive_max_year=archive_max_year,
        current_year_state=state,
    )


def _load_live_archive() -> tuple[_ParsedRecord, ...]:
    """Fetch both official pages, parse, and validate. HTML is not kept."""
    snapshot = _fetch_parse_validate()
    _load_live_archive.last_snapshot = snapshot  # type: ignore[attr-defined]
    return snapshot.records


def _get_archive_records() -> tuple[_ParsedRecord, ...]:
    """Return records: RAM, then disk, then live fetch/parse/validate."""
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
            _load_live_archive.last_snapshot = None  # type: ignore[attr-defined]
            live = _load_live_archive()
            snapshot = getattr(_load_live_archive, 'last_snapshot', None)
        except Exception:
            if records is not None:
                _archive_records_cache = records
                return records
            raise
        if snapshot is None:
            snapshot = _ParseSnapshot(
                records=live,
                archive_max_year=max(record.award_year for record in live),
                current_year_state=(
                    'winner'
                    if any(
                        record.award_year == _current_calendar_year()
                        for record in live
                    )
                    else 'absent'
                ),
            )
        _save_persistent_archive(snapshot)
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
        category=CATEGORY,
        status=record.status,
        rank=None,
        source_name=SOURCE_NAME,
        source_url=record.source_url,
        notes=None,
        identity_kind='work',
    )


# ---------------------------------------------------------------------------
# Public lookup
# ---------------------------------------------------------------------------

def lookup(title: str, author: str, series: str | None = None) -> list[AwardResult]:
    """Look up Women's Prize for Fiction winners for a title and author."""
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
