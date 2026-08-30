"""Official Prix Goncourt winners archive (principal prize only).

One HTTP GET of Tous les lauréats. Phase 1 emits Winner records only.
Staged selections, sibling Goncourt prizes, and vote totals are out of
scope. JavaScript is not required.
"""

from __future__ import annotations

import re
import threading
import unicodedata
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlparse

from .. import cache
from ..matching import normalize_title_conjunctions
from ..model import AwardResult

TIMEOUT_SECONDS = 30
SOURCE_KEY = 'prix_goncourt'
AWARD_NAME = 'Prix Goncourt'
CATEGORY = 'Fiction'
SOURCE_NAME = 'Prix Goncourt'
SITE_ORIGIN = 'https://www.academiegoncourt.com'
WINNERS_URL = SITE_ORIGIN + '/tous-les-laureats-prix-goncourt'
SOURCE_HOME_URL = SITE_ORIGIN + '/presentation-prix-goncourt'
ARCHIVE_MIN_YEAR = 1903
CACHE_VERSION = 1
# 7-day base plus an explicit stagger. Do not derive from AWARD_SOURCES order.
CACHE_BASE_TTL_SECONDS = 7 * 24 * 60 * 60
CACHE_REFRESH_OFFSET_SECONDS = 8 * 60 * 60
CACHE_TTL_SECONDS = CACHE_BASE_TTL_SECONDS + CACHE_REFRESH_OFFSET_SECONDS

_OFFICIAL_HTML_HOSTS = frozenset({
    'academiegoncourt.com',
    'www.academiegoncourt.com',
})
_YEAR_LINE_RE = re.compile(
    r'^(?P<year>(?:19|20)\d{2})\s*[-–—]\s*(?P<rest>.*)$'
)
_INITIALS_SPACE_RE = re.compile(r'\b([A-Za-z])\.\s+')
_ARCHIVE_IDENTITY_MARKERS = (
    'tous les lauréats',
    'prix goncourt',
)
_BLOCK_TAGS = frozenset({
    'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'tr', 'section',
})
_ITALIC_TAGS = frozenset({'i', 'em', 'span'})

_BROWSER_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/122.0.0.0 Safari/537.36'
    ),
    'Accept': (
        'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
    ),
    'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
    'Accept-Encoding': 'identity',
}


class PrixGoncourtSourceError(RuntimeError):
    """Raised when the official Prix Goncourt archive is blocked or unusable."""


@dataclass(frozen=True, slots=True)
class _ParsedRecord:
    award_year: int
    category: str
    status: str
    work_title: str
    work_author: str
    source_url: str


_PARSED_STATUSES = frozenset({'Winner'})
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


def _archive_max_year_is_current_enough(max_year: int) -> bool:
    """Latest listed prize year must be last year or the current UTC year."""
    current_year = _current_calendar_year()
    return current_year - 1 <= max_year <= current_year


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
        raise PrixGoncourtSourceError(
            f'Prix Goncourt request failed with HTTP {exc.code} for {url}'
        ) from exc
    except urllib.error.URLError as exc:
        raise PrixGoncourtSourceError(
            f'Prix Goncourt request failed for {url}: {exc.reason}'
        ) from exc
    if status != 200:
        raise PrixGoncourtSourceError(
            f'Prix Goncourt request failed with HTTP {status} for {url}'
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
    html = _fetch_html(WINNERS_URL)
    _require_archive_identity(html)
    records, laureate_years = _parse_winners_html(html)
    _validate_archive(records, laureate_years)
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


def _style_is_italic(style: str) -> bool:
    return 'italic' in (style or '').casefold()


def _clean_title(text: str) -> str:
    """Collapse whitespace and strip a trailing separator comma only."""
    cleaned = _collapse_ws(text)
    if cleaned.endswith(','):
        cleaned = cleaned[:-1].rstrip()
    return cleaned


def _clean_author(text: str) -> str:
    return _collapse_ws(text).strip(' ,')


def _italic_title_runs(parts: list[tuple[str, bool]]) -> list[str]:
    """Return italic title runs, joining adjacent italic fragments."""
    runs: list[str] = []
    current: list[str] = []
    pending_gap = ''
    for text, italic in parts:
        if italic:
            if pending_gap and current:
                if not _collapse_ws(pending_gap):
                    current.append(pending_gap)
                else:
                    title = _clean_title(''.join(current))
                    if title:
                        runs.append(title)
                    current = [text]
                    pending_gap = ''
                    continue
            current.append(text)
            pending_gap = ''
            continue
        if current:
            pending_gap += text
    if current:
        title = _clean_title(''.join(current))
        if title:
            runs.append(title)
    return runs


class _PrixGoncourtWinnersParser(HTMLParser):
    """Parse official YEAR - Author, italic Title laureate lines."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.records: list[_ParsedRecord] = []
        self.laureate_years: list[int] = []
        self._skip = 0
        self._italic_stack: list[bool] = []
        self._parts: list[tuple[str, bool]] = []

    def _in_italic(self) -> bool:
        return any(self._italic_stack)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {'script', 'style', 'noscript'}:
            self._skip += 1
            return
        if self._skip:
            return
        style = ''
        for name, value in attrs:
            if name == 'style' and value:
                style = value
                break
        if tag in _ITALIC_TAGS:
            contributes = tag in {'i', 'em'} or _style_is_italic(style)
            self._italic_stack.append(contributes)
        if tag == 'br' or tag in _BLOCK_TAGS:
            self._finish_line()

    def handle_endtag(self, tag: str) -> None:
        if tag in {'script', 'style', 'noscript'} and self._skip:
            self._skip -= 1
            return
        if self._skip:
            return
        if tag in _ITALIC_TAGS and self._italic_stack:
            self._italic_stack.pop()
        if tag in _BLOCK_TAGS:
            self._finish_line()

    def handle_data(self, data: str) -> None:
        if self._skip or not data:
            return
        self._parts.append((data, self._in_italic()))

    def close(self) -> None:
        self._finish_line()
        super().close()

    def _finish_line(self) -> None:
        parts = self._parts
        self._parts = []
        if not parts:
            return
        text = _collapse_ws(''.join(chunk for chunk, _italic in parts))
        match = _YEAR_LINE_RE.fullmatch(text)
        if match is None:
            return
        year = int(match.group('year'))
        titles = _italic_title_runs(parts)
        first_italic_at = next(
            (index for index, (_chunk, italic) in enumerate(parts) if italic),
            None,
        )
        if first_italic_at is None:
            author = ''
        else:
            author = _clean_author(
                ''.join(chunk for chunk, italic in parts[:first_italic_at])
            )
            author_match = _YEAR_LINE_RE.match(author)
            if author_match is not None:
                author = _clean_author(author_match.group('rest'))
        self.laureate_years.append(year)
        if not titles:
            self.records.append(
                _ParsedRecord(
                    award_year=year,
                    category=CATEGORY,
                    status='Winner',
                    work_title='',
                    work_author=author,
                    source_url=WINNERS_URL,
                )
            )
            return
        if not author:
            self.records.append(
                _ParsedRecord(
                    award_year=year,
                    category=CATEGORY,
                    status='Winner',
                    work_title=titles[0],
                    work_author='',
                    source_url=WINNERS_URL,
                )
            )
            return
        for title in titles:
            self.records.append(
                _ParsedRecord(
                    award_year=year,
                    category=CATEGORY,
                    status='Winner',
                    work_title=title,
                    work_author=author,
                    source_url=WINNERS_URL,
                )
            )


def _identity_key(record: _ParsedRecord) -> tuple[int, str, str]:
    return (
        record.award_year,
        _normalize_text(record.work_title),
        _normalize_text(record.work_author),
    )


def _parse_winners_html(
    html: str,
) -> tuple[tuple[_ParsedRecord, ...], tuple[int, ...]]:
    parser = _PrixGoncourtWinnersParser()
    parser.feed(html)
    parser.close()
    return tuple(parser.records), tuple(parser.laureate_years)


def _require_archive_identity(html: str) -> None:
    lowered = html.casefold()
    if all(marker in lowered for marker in _ARCHIVE_IDENTITY_MARKERS):
        return
    raise PrixGoncourtSourceError(
        'Prix Goncourt archive page did not match the official laureates listing'
    )


def _source_url_is_usable(source_url: str) -> bool:
    if source_url != WINNERS_URL:
        return False
    parsed = urlparse(source_url)
    if parsed.scheme != 'https':
        return False
    host = (parsed.hostname or '').casefold().rstrip('.')
    return host in _OFFICIAL_HTML_HOSTS


def _validate_record(record: _ParsedRecord) -> None:
    if record.category != CATEGORY:
        raise PrixGoncourtSourceError(
            'Prix Goncourt archive produced an unsupported category: '
            f'{record.category!r}'
        )
    if record.status not in _PARSED_STATUSES:
        raise PrixGoncourtSourceError(
            'Prix Goncourt archive produced an unexpected status: '
            f'{record.status!r}'
        )
    if not record.work_title or not record.work_title.strip():
        raise PrixGoncourtSourceError(
            'Prix Goncourt archive produced an empty title'
        )
    if not record.work_author or not record.work_author.strip():
        raise PrixGoncourtSourceError(
            'Prix Goncourt archive produced an empty author'
        )
    if not _source_url_is_usable(record.source_url):
        raise PrixGoncourtSourceError(
            'Prix Goncourt archive produced an unexpected source URL: '
            f'{record.source_url!r}'
        )
    if (
        not isinstance(record.award_year, int)
        or isinstance(record.award_year, bool)
        or record.award_year < ARCHIVE_MIN_YEAR
        or record.award_year > _current_calendar_year()
    ):
        raise PrixGoncourtSourceError(
            'Prix Goncourt archive produced an unexpected year: '
            f'{record.award_year!r}'
        )


def _validate_laureate_years(laureate_years: tuple[int, ...]) -> None:
    if not laureate_years:
        raise PrixGoncourtSourceError(
            'Prix Goncourt archive did not contain prize-year laureate lines'
        )
    counts = Counter(laureate_years)
    duplicates = sorted(year for year, count in counts.items() if count != 1)
    if duplicates:
        raise PrixGoncourtSourceError(
            'Prix Goncourt archive had more than one laureate line for '
            f'year {duplicates[0]}'
        )
    minimum = min(counts)
    maximum = max(counts)
    if minimum != ARCHIVE_MIN_YEAR:
        raise PrixGoncourtSourceError(
            f'Prix Goncourt archive history did not begin at {ARCHIVE_MIN_YEAR}'
        )
    if not _archive_max_year_is_current_enough(maximum):
        raise PrixGoncourtSourceError(
            'Prix Goncourt archive latest year '
            f'{maximum} does not reach {_current_calendar_year() - 1}'
        )
    expected = set(range(ARCHIVE_MIN_YEAR, maximum + 1))
    if set(counts) != expected:
        raise PrixGoncourtSourceError(
            'Prix Goncourt archive laureate years were not contiguous from '
            f'{ARCHIVE_MIN_YEAR} through {maximum}'
        )


def _validate_archive(
    records: tuple[_ParsedRecord, ...],
    laureate_years: tuple[int, ...] | None = None,
) -> None:
    """Fail closed if parsed records are not a usable Winner archive.

    Validation is one official laureate line per prize year. A laureate
    line may emit one or more work records when official markup names
    more than one italic title. The current UTC year may be absent.
    """
    if laureate_years is not None:
        _validate_laureate_years(laureate_years)
        expected_years = set(laureate_years)
    else:
        if not records:
            raise PrixGoncourtSourceError(
                'Prix Goncourt archive contained no prize records'
            )
        expected_years = {record.award_year for record in records}
        reconstructed = tuple(sorted(expected_years))
        _validate_laureate_years(reconstructed)
    if not records:
        raise PrixGoncourtSourceError(
            'Prix Goncourt archive contained no prize records'
        )
    identities = [_identity_key(record) for record in records]
    if len(identities) != len(set(identities)):
        raise PrixGoncourtSourceError(
            'Prix Goncourt archive contained duplicate work/year identities'
        )
    works_by_year: dict[int, int] = {}
    for record in records:
        _validate_record(record)
        works_by_year[record.award_year] = works_by_year.get(record.award_year, 0) + 1
    if set(works_by_year) != expected_years:
        raise PrixGoncourtSourceError(
            'Prix Goncourt archive work years did not match laureate years'
        )
    for year in expected_years:
        if works_by_year.get(year, 0) < 1:
            raise PrixGoncourtSourceError(
                f'Prix Goncourt archive year {year} had no Winner work record'
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
    return (WINNERS_URL,)


def _coverage_from_records(records: tuple[_ParsedRecord, ...]) -> dict:
    years = [record.award_year for record in records]
    return {
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
        _validate_cached_archive(restored)
    except PrixGoncourtSourceError:
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
        identity_kind='work',
    )


# ---------------------------------------------------------------------------
# Public lookup
# ---------------------------------------------------------------------------

def lookup(title: str, author: str, series: str | None = None) -> list[AwardResult]:
    """Look up Prix Goncourt Winner results for a title and author."""
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
