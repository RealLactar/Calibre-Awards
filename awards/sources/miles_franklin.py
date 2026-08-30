"""Official Miles Franklin Literary Award history-page source.

One HTTP GET of Perpetual's judges-and-history-of-recipients archive.
Coverage begins in 2007. Longlist-only and unlabeled mixed-list works are
ignored. JavaScript is not required. Insights/PDF pages are not used.
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
from urllib.parse import urlparse

from .. import cache
from ..matching import normalize_title_conjunctions
from ..model import AwardResult

TIMEOUT_SECONDS = 30
SOURCE_KEY = 'miles_franklin'
AWARD_NAME = 'Miles Franklin Literary Award'
CATEGORY = 'Fiction'
SOURCE_NAME = 'Miles Franklin Literary Award'
SITE_ORIGIN = 'https://www.perpetual.com.au'
SOURCE_HOME_URL = SITE_ORIGIN + '/wealth-management/milesfranklin/'
HISTORY_URL = (
    SITE_ORIGIN
    + '/wealth-management/milesfranklin/judges-and-history-of-recipients/'
)
ARCHIVE_MIN_YEAR = 2007
CACHE_VERSION = 1
# 7-day base plus an explicit stagger. Do not derive from AWARD_SOURCES order.
CACHE_BASE_TTL_SECONDS = 7 * 24 * 60 * 60
CACHE_REFRESH_OFFSET_SECONDS = 9 * 60 * 60
CACHE_TTL_SECONDS = CACHE_BASE_TTL_SECONDS + CACHE_REFRESH_OFFSET_SECONDS

_OFFICIAL_HTML_HOSTS = frozenset({
    'perpetual.com.au',
    'www.perpetual.com.au',
})
_INITIALS_SPACE_RE = re.compile(r'\b([A-Za-z])\.\s+')
_YEAR_HEADING_RE = re.compile(
    r'^(?P<year>20\d{2})\s+miles franklin literary award$',
    re.IGNORECASE,
)
_WINNER_HEADING_RE = re.compile(
    r'^(?:(?P<year>20\d{2})\s+)?winner(?:\s*[-–—]\s*(?P<author>.+))?$',
    re.IGNORECASE,
)
_AUTHOR_STATUS_DASH_RE = re.compile(
    r'^(?P<author>.+?)\s*[-–—]\s*'
    r'(?P<status>Winner|Finalist|Shortlist|Shortlisted)\s*$',
    re.IGNORECASE,
)
_AUTHOR_STATUS_PAREN_RE = re.compile(
    r'^(?P<author>.+?)\s*\('
    r'(?P<status>Winner|Finalist|Shortlist|Shortlisted)\)\s*$',
    re.IGNORECASE,
)
_SEPARATOR_RE = re.compile(r'^[_—–-]{3,}$')
_LEADING_YEAR_RE = re.compile(r'^20\d{2}\s+')
_ARCHIVE_IDENTITY_MARKERS = (
    'miles franklin literary award',
    'judges and history of recipients',
)
_CURRENT_YEAR_STATES = frozenset({
    'absent',
    'longlist',
    'shortlist',
    'winner',
})
_STATUS_WEIGHT = {
    'Finalist': 1,
    'Winner': 2,
}
_FINALIST_MAX_PER_YEAR = 8
_TITLE_MAX_LEN = 180
_SKIP_PREFIXES = (
    'author photo credit',
    'read extract',
    'read an extract',
    'watch the',
)
_SKIP_CONTAINS = (
    'shortlist video',
    'winner announcement',
    'news archive',
)
_BIO_HEADERS = frozenset({
    'biography',
    'synopsis',
    "judge's comments",
    "judge's comment",
    'judges comments',
    "judges' comments",
    "judges' comment",
    'judges’ comments',
    'judges’ comment',
    'judge’s comments',
    'judge’s comment',
    'judge’s comment:',
})
_IGNORE_TAGS = frozenset({
    'table',
    'script',
    'style',
    'svg',
    'noscript',
    'iframe',
})
_YEAR_HEADING_TAGS = frozenset({'h2'})
_LINE_TAGS = frozenset({'p', 'button', 'h3', 'h4'})
_BROWSER_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/122.0.0.0 Safari/537.36'
    ),
    'Accept': (
        'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
    ),
    'Accept-Language': 'en-AU,en;q=0.9',
    'Accept-Encoding': 'identity',
}


class MilesFranklinSourceError(RuntimeError):
    """Raised when the official Miles Franklin archive is blocked or unusable."""


@dataclass(frozen=True, slots=True)
class _ParsedRecord:
    award_year: int
    category: str
    status: str
    work_title: str
    work_author: str
    source_url: str


@dataclass(frozen=True, slots=True)
class _ParseSnapshot:
    records: tuple[_ParsedRecord, ...]
    year_headings: tuple[int, ...]
    current_year_heading: bool


_PARSED_STATUSES = frozenset({'Winner', 'Finalist'})
_RECORD_CACHE_FIELDS = (
    'award_year',
    'category',
    'source_url',
    'status',
    'work_author',
    'work_title',
)
_COVERAGE_FIELDS = frozenset({
    'current_year',
    'current_year_state',
    'finalist_count',
    'max_year',
    'min_year',
    'record_count',
    'winner_count',
})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _current_calendar_year() -> int:
    """UTC calendar year. Tests may patch _utc_now or this helper."""
    return _utc_now().year


def _year_is_completed(award_year: int) -> bool:
    """Years before the current UTC calendar year are expected completed."""
    return award_year < _current_calendar_year()


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
        raise MilesFranklinSourceError(
            f'Miles Franklin request failed with HTTP {exc.code} for {url}'
        ) from exc
    except urllib.error.URLError as exc:
        raise MilesFranklinSourceError(
            f'Miles Franklin request failed for {url}: {exc.reason}'
        ) from exc
    if status != 200:
        raise MilesFranklinSourceError(
            f'Miles Franklin request failed with HTTP {status} for {url}'
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
# HTML parsing
# ---------------------------------------------------------------------------

class _HistoryParser(HTMLParser):
    """Collect year-h2 containers as ordered paragraph text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.year_order: list[int] = []
        self.year_lines: dict[int, list[str]] = {}
        self._current_year: int | None = None
        self._ignore_depth = 0
        self._capture: str | None = None
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _IGNORE_TAGS:
            self._finish_capture()
            self._ignore_depth += 1
            return
        if self._ignore_depth:
            return
        if tag == 'br' and self._capture is not None:
            self._buffer.append(' ')
            return
        if tag in _YEAR_HEADING_TAGS or tag in _LINE_TAGS:
            self._finish_capture()
            self._capture = tag
            self._buffer = []

    def handle_endtag(self, tag: str) -> None:
        if tag in _IGNORE_TAGS:
            if self._ignore_depth:
                self._ignore_depth -= 1
            return
        if self._ignore_depth:
            return
        if tag in _YEAR_HEADING_TAGS and self._capture == tag:
            text = _collapse_ws(''.join(self._buffer))
            self._capture = None
            self._buffer = []
            self._handle_heading(text)
            return
        if tag in _LINE_TAGS and self._capture == tag:
            text = _collapse_ws(''.join(self._buffer))
            self._capture = None
            self._buffer = []
            if text:
                self._append_line(text)

    def handle_data(self, data: str) -> None:
        if self._ignore_depth or self._capture is None:
            return
        self._buffer.append(data)

    def _handle_heading(self, text: str) -> None:
        match = _YEAR_HEADING_RE.fullmatch(text)
        if match:
            year = int(match.group('year'))
            if year not in self.year_lines:
                self.year_order.append(year)
                self.year_lines[year] = []
            self._current_year = year
            return
        folded = text.casefold()
        if folded.startswith('judges for the') or folded == 'news archive':
            self._current_year = None

    def _append_line(self, text: str) -> None:
        if self._current_year is None:
            return
        self.year_lines[self._current_year].append(text)

    def _finish_capture(self) -> None:
        if self._capture in _LINE_TAGS:
            text = _collapse_ws(''.join(self._buffer))
            self._capture = None
            self._buffer = []
            if text:
                self._append_line(text)
            return
        if self._capture in _YEAR_HEADING_TAGS:
            text = _collapse_ws(''.join(self._buffer))
            self._capture = None
            self._buffer = []
            self._handle_heading(text)
            return
        self._capture = None
        self._buffer = []


def _is_section_heading(text: str) -> bool:
    folded = _collapse_ws(text).casefold().replace('&', 'and')
    folded = _LEADING_YEAR_RE.sub('', folded)
    folded = re.sub(r'\s+', ' ', folded).strip()
    return folded in {
        'shortlist and longlist',
        'short and longlist',
        'shortlist',
        'longlist',
    }


def _is_bio_header(text: str) -> bool:
    folded = _collapse_ws(text).casefold().rstrip(':').strip()
    return folded in _BIO_HEADERS


def _is_skip_line(text: str) -> bool:
    if _SEPARATOR_RE.fullmatch(text):
        return True
    folded = text.casefold()
    if any(folded.startswith(prefix) for prefix in _SKIP_PREFIXES):
        return True
    if any(token in folded for token in _SKIP_CONTAINS):
        return True
    if folded.startswith('judges for the'):
        return True
    return False


def _is_bio_prose(text: str) -> bool:
    return len(text) > _TITLE_MAX_LEN


def _is_candidate_line(text: str) -> bool:
    if not text or _is_skip_line(text) or _is_section_heading(text):
        return False
    if _is_bio_header(text) or _is_bio_prose(text):
        return False
    return True


def _canonicalize_status(raw: str) -> str:
    folded = raw.casefold()
    if folded == 'winner':
        return 'Winner'
    if folded in {'finalist', 'shortlist', 'shortlisted'}:
        return 'Finalist'
    raise MilesFranklinSourceError(
        f'Miles Franklin archive produced an unexpected status token: {raw!r}'
    )


def _parse_status_author(text: str) -> tuple[str, str] | None:
    if _is_section_heading(text):
        return None
    match = _AUTHOR_STATUS_DASH_RE.fullmatch(text) or _AUTHOR_STATUS_PAREN_RE.fullmatch(
        text
    )
    if match is None:
        return None
    author = _collapse_ws(match.group('author'))
    if not author:
        return None
    return author, _canonicalize_status(match.group('status'))


def _next_candidate(
    lines: list[str],
    start: int,
) -> tuple[int, str] | None:
    for index in range(start, len(lines)):
        text = lines[index]
        if _is_candidate_line(text):
            return index, text
    return None


def _extract_winner(lines: list[str]) -> tuple[str, str] | None:
    """Return (author, title) for the year Winner, independent of the query."""
    index = 0
    while True:
        nxt = _next_candidate(lines, index)
        if nxt is None:
            return None
        pos, text = nxt
        heading = _WINNER_HEADING_RE.fullmatch(text)
        status_author = _parse_status_author(text)
        if heading is not None and heading.group('year'):
            heading_author = _collapse_ws(heading.group('author') or '')
            following = _next_candidate(lines, pos + 1)
            if following is None:
                return None
            follow_pos, follow_text = following
            follow_status = _parse_status_author(follow_text)
            if follow_status is not None and follow_status[1] == 'Winner':
                author = follow_status[0]
                title_line = _next_candidate(lines, follow_pos + 1)
            elif heading_author and _authors_match(heading_author, follow_text):
                author = heading_author
                title_line = _next_candidate(lines, follow_pos + 1)
            elif heading_author:
                author = heading_author
                if follow_status is not None:
                    title_line = _next_candidate(lines, follow_pos + 1)
                else:
                    title_line = following
            else:
                if follow_status is not None and follow_status[1] == 'Winner':
                    author = follow_status[0]
                    title_line = _next_candidate(lines, follow_pos + 1)
                else:
                    author = follow_text
                    title_line = _next_candidate(lines, follow_pos + 1)
            if title_line is None:
                return None
            title = title_line[1]
            if _parse_status_author(title) is not None or _is_section_heading(title):
                return None
            if not author or not title:
                return None
            return author, title
        if status_author is not None and status_author[1] == 'Winner':
            title_line = _next_candidate(lines, pos + 1)
            if title_line is None:
                return None
            title = title_line[1]
            if _parse_status_author(title) is not None or _is_section_heading(title):
                return None
            return status_author[0], title
        index = pos + 1


def _extract_finalists(lines: list[str]) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for index, text in enumerate(lines):
        if not _is_candidate_line(text) and _parse_status_author(text) is None:
            continue
        status_author = _parse_status_author(text)
        if status_author is None or status_author[1] != 'Finalist':
            continue
        title_line = _next_candidate(lines, index + 1)
        if title_line is None:
            continue
        title = title_line[1]
        if _parse_status_author(title) is not None or _is_section_heading(title):
            continue
        found.append((status_author[0], title))
    return found


def _record_for(year: int, status: str, title: str, author: str) -> _ParsedRecord:
    return _ParsedRecord(
        award_year=year,
        category=CATEGORY,
        status=status,
        work_title=title,
        work_author=author,
        source_url=HISTORY_URL,
    )


def _parse_year_lines(year: int, lines: list[str]) -> list[_ParsedRecord]:
    records: list[_ParsedRecord] = []
    winner = _extract_winner(lines)
    if winner is not None:
        records.append(_record_for(year, 'Winner', winner[1], winner[0]))
    for author, title in _extract_finalists(lines):
        records.append(_record_for(year, 'Finalist', title, author))
    return records


def _identity_key(record: _ParsedRecord) -> tuple[int, str, str]:
    return (
        record.award_year,
        _normalize_text(record.work_title),
        _normalize_text(record.work_author),
    )


def _apply_status_precedence(
    records: list[_ParsedRecord],
) -> list[_ParsedRecord]:
    """Keep Winner over Finalist for the same work/year identity."""
    order: list[tuple[int, str, str]] = []
    by_key: dict[tuple[int, str, str], _ParsedRecord] = {}
    seen_exact: set[tuple[int, str, str, str]] = set()
    for record in records:
        exact = (
            record.award_year,
            record.status,
            _normalize_text(record.work_title),
            _normalize_text(record.work_author),
        )
        if exact in seen_exact:
            continue
        seen_exact.add(exact)
        key = _identity_key(record)
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = record
            order.append(key)
            continue
        if _STATUS_WEIGHT[record.status] > _STATUS_WEIGHT[existing.status]:
            by_key[key] = record
    return [by_key[key] for key in order]


def _parse_archive_html(html: str) -> _ParseSnapshot:
    parser = _HistoryParser()
    parser.feed(html)
    parser.close()
    collected: list[_ParsedRecord] = []
    for year in parser.year_order:
        collected.extend(_parse_year_lines(year, parser.year_lines[year]))
    records = tuple(_apply_status_precedence(collected))
    headings = tuple(parser.year_order)
    current_year = _current_calendar_year()
    return _ParseSnapshot(
        records=records,
        year_headings=headings,
        current_year_heading=current_year in parser.year_lines,
    )


def _require_archive_identity(html: str) -> None:
    lowered = html.casefold()
    if not all(marker in lowered for marker in _ARCHIVE_IDENTITY_MARKERS):
        raise MilesFranklinSourceError(
            'Miles Franklin archive page did not match the official history listing'
        )
    if not re.search(
        r'20\d{2}\s+Miles Franklin Literary Award',
        html,
        flags=re.IGNORECASE,
    ):
        raise MilesFranklinSourceError(
            'Miles Franklin archive page did not contain year sections'
        )


def _source_url_is_usable(source_url: str) -> bool:
    if source_url != HISTORY_URL:
        return False
    parsed = urlparse(source_url)
    if parsed.scheme != 'https':
        return False
    host = (parsed.hostname or '').casefold().rstrip('.')
    return host in _OFFICIAL_HTML_HOSTS


def _validate_record(record: _ParsedRecord) -> None:
    if record.category != CATEGORY:
        raise MilesFranklinSourceError(
            'Miles Franklin archive produced an unsupported category: '
            f'{record.category!r}'
        )
    if record.status not in _PARSED_STATUSES:
        raise MilesFranklinSourceError(
            'Miles Franklin archive produced an unexpected status: '
            f'{record.status!r}'
        )
    if not record.work_title or not record.work_title.strip():
        raise MilesFranklinSourceError('Miles Franklin archive produced an empty title')
    if not record.work_author or not record.work_author.strip():
        raise MilesFranklinSourceError(
            'Miles Franklin archive produced an empty author'
        )
    if not _source_url_is_usable(record.source_url):
        raise MilesFranklinSourceError(
            'Miles Franklin archive produced an unexpected source URL: '
            f'{record.source_url!r}'
        )
    if (
        not isinstance(record.award_year, int)
        or isinstance(record.award_year, bool)
        or record.award_year < ARCHIVE_MIN_YEAR
    ):
        raise MilesFranklinSourceError(
            f'Miles Franklin archive produced an unexpected year: {record.award_year!r}'
        )


def _validate_year_headings(year_headings: tuple[int, ...]) -> None:
    if not year_headings:
        raise MilesFranklinSourceError(
            'Miles Franklin archive did not contain year headings'
        )
    unique = set(year_headings)
    minimum = min(unique)
    maximum = max(unique)
    if minimum != ARCHIVE_MIN_YEAR:
        raise MilesFranklinSourceError(
            f'Miles Franklin archive history did not begin at {ARCHIVE_MIN_YEAR}'
        )
    expected = set(range(ARCHIVE_MIN_YEAR, maximum + 1))
    if unique != expected:
        raise MilesFranklinSourceError(
            'Miles Franklin archive year headings were not contiguous from '
            f'{ARCHIVE_MIN_YEAR} through {maximum}'
        )
    current_year = _current_calendar_year()
    if maximum < current_year - 1:
        raise MilesFranklinSourceError(
            'Miles Franklin archive year headings did not cover completed years'
        )


def _state_from_records(
    records: tuple[_ParsedRecord, ...],
    year: int,
    *,
    heading_present: bool | None,
) -> str:
    has_winner = any(
        record.award_year == year and record.status == 'Winner' for record in records
    )
    has_finalist = any(
        record.award_year == year and record.status == 'Finalist' for record in records
    )
    if has_winner:
        return 'winner'
    if has_finalist:
        return 'shortlist'
    if heading_present is True:
        return 'longlist'
    if heading_present is False:
        return 'absent'
    return 'absent'


def _validate_records(records: tuple[_ParsedRecord, ...]) -> None:
    if not records:
        raise MilesFranklinSourceError(
            'Miles Franklin archive contained no prize records'
        )
    identities = [_identity_key(record) for record in records]
    if len(identities) != len(set(identities)):
        raise MilesFranklinSourceError(
            'Miles Franklin archive contained duplicate work/year identities'
        )
    winners_by_year: dict[int, int] = {}
    finalists_by_year: dict[int, int] = {}
    for record in records:
        _validate_record(record)
        if record.status == 'Winner':
            winners_by_year[record.award_year] = (
                winners_by_year.get(record.award_year, 0) + 1
            )
        elif record.status == 'Finalist':
            finalists_by_year[record.award_year] = (
                finalists_by_year.get(record.award_year, 0) + 1
            )
    current_year = _current_calendar_year()
    for year in range(ARCHIVE_MIN_YEAR, current_year):
        count = winners_by_year.get(year, 0)
        if count != 1:
            raise MilesFranklinSourceError(
                f'Miles Franklin archive year {year} had {count} Winner '
                'record(s); completed years must have exactly 1'
            )
        winner = next(
            record
            for record in records
            if record.award_year == year and record.status == 'Winner'
        )
        if not winner.work_title.strip() or not winner.work_author.strip():
            raise MilesFranklinSourceError(
                f'Miles Franklin archive year {year} had an empty Winner'
            )
    for year, count in winners_by_year.items():
        if year >= current_year and count > 1:
            raise MilesFranklinSourceError(
                f'Miles Franklin archive year {year} had an unexpected Winner count'
            )
    for year, count in finalists_by_year.items():
        if count < 0 or count > _FINALIST_MAX_PER_YEAR:
            raise MilesFranklinSourceError(
                f'Miles Franklin archive year {year} had {count} Finalist '
                'record(s); expected 0 through '
                f'{_FINALIST_MAX_PER_YEAR}'
            )


def _validate_archive(
    snapshot: _ParseSnapshot | tuple[_ParsedRecord, ...],
    year_headings: tuple[int, ...] | None = None,
) -> None:
    """Fail closed if parsed records are not a usable Miles Franklin archive."""
    if isinstance(snapshot, _ParseSnapshot):
        records = snapshot.records
        headings = snapshot.year_headings
        heading_present = snapshot.current_year_heading
    else:
        records = snapshot
        headings = year_headings
        heading_present = None
    if headings is not None:
        _validate_year_headings(headings)
    _validate_records(records)
    if isinstance(snapshot, _ParseSnapshot):
        current_year = _current_calendar_year()
        state = _state_from_records(
            records,
            current_year,
            heading_present=heading_present,
        )
        if state not in _CURRENT_YEAR_STATES:
            raise MilesFranklinSourceError(
                'Miles Franklin archive produced an unknown current-year state'
            )


def _validate_cached_archive(
    records: tuple[_ParsedRecord, ...],
    coverage: dict | None = None,
) -> None:
    _validate_records(records)
    if coverage is None:
        return
    _validate_cached_coverage(records, coverage)


def _validate_cached_coverage(
    records: tuple[_ParsedRecord, ...],
    coverage: dict,
) -> None:
    if not isinstance(coverage, dict) or set(coverage) != _COVERAGE_FIELDS:
        raise MilesFranklinSourceError(
            'Miles Franklin archive coverage metadata is incomplete'
        )
    current_year = _current_calendar_year()
    stored_year = coverage.get('current_year')
    state = coverage.get('current_year_state')
    if (
        isinstance(stored_year, bool)
        or not isinstance(stored_year, int)
        or stored_year < ARCHIVE_MIN_YEAR
        or stored_year > current_year
    ):
        raise MilesFranklinSourceError(
            'Miles Franklin archive coverage current year is stale or invalid'
        )
    if state not in _CURRENT_YEAR_STATES:
        raise MilesFranklinSourceError(
            'Miles Franklin archive coverage has an unknown current-year state'
        )
    if coverage.get('min_year') != ARCHIVE_MIN_YEAR:
        raise MilesFranklinSourceError(
            'Miles Franklin archive coverage does not begin at 2007'
        )
    if stored_year == current_year:
        derived = _state_from_records(
            records,
            current_year,
            heading_present=None if state == 'absent' else state == 'longlist',
        )
        if state == 'winner' and derived != 'winner':
            raise MilesFranklinSourceError(
                'Miles Franklin archive coverage Winner state does not match records'
            )
        if state == 'shortlist' and derived != 'shortlist':
            raise MilesFranklinSourceError(
                'Miles Franklin archive coverage shortlist state does not match records'
            )
        if state in {'absent', 'longlist'} and derived not in {'absent', 'longlist'}:
            raise MilesFranklinSourceError(
                'Miles Franklin archive coverage empty-year state does not match records'
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
    return (HISTORY_URL,)


def _coverage_from_records(
    records: tuple[_ParsedRecord, ...],
    *,
    current_year_heading: bool | None = None,
) -> dict:
    years = [record.award_year for record in records]
    current_year = _current_calendar_year()
    heading_present = current_year_heading
    if heading_present is None:
        heading_present = any(record.award_year == current_year for record in records)
    return {
        'current_year': current_year,
        'current_year_state': _state_from_records(
            records,
            current_year,
            heading_present=heading_present,
        ),
        'finalist_count': sum(
            1 for record in records if record.status == 'Finalist'
        ),
        'max_year': max(years) if years else None,
        'min_year': min(years) if years else None,
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
    except MilesFranklinSourceError:
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
    current_year_heading: bool | None = None,
) -> None:
    try:
        cache.save_source_cache(
            SOURCE_KEY,
            CACHE_VERSION,
            records=[_record_to_cache_dict(record) for record in records],
            source_urls=_archive_source_urls(),
            coverage=_coverage_from_records(
                records,
                current_year_heading=current_year_heading,
            ),
            ttl_seconds=CACHE_TTL_SECONDS,
        )
    except OSError:
        pass


def _fetch_parse_validate() -> _ParseSnapshot:
    html = _fetch_html(HISTORY_URL)
    _require_archive_identity(html)
    snapshot = _parse_archive_html(html)
    _validate_archive(snapshot)
    return snapshot


def _load_live_archive() -> tuple[_ParsedRecord, ...]:
    """Fetch the official archive, parse, and validate. HTML is not kept."""
    snapshot = _fetch_parse_validate()
    _load_live_archive.last_heading = snapshot.current_year_heading  # type: ignore[attr-defined]
    return snapshot.records


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
            _load_live_archive.last_heading = None  # type: ignore[attr-defined]
            live = _load_live_archive()
            heading = getattr(_load_live_archive, 'last_heading', None)
        except Exception:
            if records is not None:
                _archive_records_cache = records
                return records
            raise
        _save_persistent_archive(live, current_year_heading=heading)
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
    """Look up Miles Franklin Literary Award results for a title and author."""
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
