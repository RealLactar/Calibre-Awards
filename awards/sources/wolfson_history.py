"""Official Wolfson History Prize archive source.

One HTTP GET of the published all-winners page. Lifetime contribution
honors are skipped. JavaScript is not required. Year pages are not fetched.
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

from .. import cache
from ..matching import normalize_title_conjunctions
from ..model import AwardResult

TIMEOUT_SECONDS = 30
SOURCE_KEY = 'wolfson_history'
AWARD_NAME = 'Wolfson History Prize'
SOURCE_NAME = 'Wolfson History Prize'
SOURCE_HOME_URL = (
    'https://www.wolfsonhistoryprize.org.uk/past-winners/all-winners/'
)
SOURCEINFO_CATEGORIES = ('History',)
ARCHIVE_MIN_YEAR = 1972
SHORTLIST_START_YEAR = 2017
# The official archive and year index both omit this year. Do not invent a cause.
ABSENT_YEAR = 1988
ANCHOR_YEARS = (1972, 1979, 2007, 2016, 2017, 2025)
CACHE_VERSION = 1
# 7-day base plus an explicit stagger. Do not derive from AWARD_SOURCES order.
CACHE_BASE_TTL_SECONDS = 7 * 24 * 60 * 60
CACHE_REFRESH_OFFSET_SECONDS = 20 * 60 * 60
CACHE_TTL_SECONDS = CACHE_BASE_TTL_SECONDS + CACHE_REFRESH_OFFSET_SECONDS

_YEAR_RE = re.compile(r'\d{4}')
_SHORTLIST_RE = re.compile(r'^(?:(\d{4}) )?Shortlist:$')
_PUBLISHER_RE = re.compile(r'\([^()]+\)')
_INITIALS_SPACE_RE = re.compile(r'\b([A-Za-z])\.\s+')
# The 1979 archive title has a stray space before a comma. Matching ignores
# that space. The stored title stays as published.
_SPACE_BEFORE_PUNCT_RE = re.compile(r' +([,:;])')
_CONTRIBUTION_TITLE = 'for distinguished contribution to the writing of history'
# br/img are empty tags. Counting them in element depth would leave the
# parser inside entry-content after the real block has ended.
_VOID_TAGS = frozenset({
    'area',
    'br',
    'col',
    'embed',
    'hr',
    'img',
    'input',
    'link',
    'meta',
    'source',
    'wbr',
})
_STATUS_WEIGHT = {
    'Shortlisted': 1,
    'Winner': 2,
}
_PARSED_STATUSES = frozenset({'Winner', 'Shortlisted'})
_RECORD_CACHE_FIELDS = (
    'award_year',
    'category',
    'source_url',
    'status',
    'work_author',
    'work_title',
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


class WolfsonSourceError(RuntimeError):
    """Raised when the official Wolfson archive is blocked or unusable."""


@dataclass(frozen=True, slots=True)
class _ParsedRecord:
    award_year: int
    category: None
    status: str
    work_title: str
    work_author: str
    source_url: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _collapse_ws(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def _class_set(attrs: list[tuple[str, str | None]]) -> set[str]:
    for key, value in attrs:
        if key == 'class' and value:
            return set(value.split())
    return set()


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
            body = _read_response_body(exc)
            detail = f': {body[:200].strip()}' if body.strip() else ''
            raise WolfsonSourceError(
                f'Wolfson History Prize request failed with HTTP {exc.code} '
                f'for {url}{detail}'
            ) from exc
        finally:
            exc.close()
    except urllib.error.URLError as exc:
        raise WolfsonSourceError(
            f'Wolfson History Prize request failed for {url}: {exc.reason}'
        ) from exc
    if status != 200:
        raise WolfsonSourceError(
            f'Wolfson History Prize request failed with HTTP {status} for {url}'
        )
    return html


_archive_records_cache: tuple[_ParsedRecord, ...] | None = None
_cache_lock = threading.RLock()


def _reset_runtime_state() -> None:
    """Clear in-process caches. Does not delete disk cache."""
    global _archive_records_cache
    with _cache_lock:
        _archive_records_cache = None


def _load_live_archive() -> tuple[_ParsedRecord, ...]:
    """Fetch the official archive, parse, and validate. HTML is not kept."""
    html = _fetch_html(SOURCE_HOME_URL)
    records, years = _parse_archive_html(html)
    _validate_archive(records, years)
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
            if not cache.try_claim_stale_refresh(SOURCE_KEY):
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

def _is_contribution_title(title: str) -> bool:
    """True for the official lifetime-honor label, not a book with a subtitle."""
    label = _collapse_ws(title).casefold()
    if label.endswith(':'):
        label = label[:-1].rstrip()
    return label == _CONTRIBUTION_TITLE


def _is_book_shape(lines: list[str]) -> bool:
    return len(lines) == 3 and _PUBLISHER_RE.fullmatch(lines[2]) is not None


class _WolfsonArchiveParser(HTMLParser):
    """Parse book rows inside the all-winners entry-content block.

    Strong text is inline. A br separates the title line, the author line,
    and the parenthesized publisher. The publisher is not part of the author.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.records: list[_ParsedRecord] = []
        self.years: list[int] = []
        self._seen_entry = False
        self._in_entry = False
        self._depth = 0
        self._in_h5 = False
        self._h5_parts: list[str] = []
        self._in_p = False
        self._lines: list[list[str]] = []
        self._year: int | None = None
        self._mode = 'winner'
        self._saw_shortlist = False
        self._seen_years: set[int] = set()

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self._enter(tag, attrs)
        if not self._in_entry:
            return
        if tag == 'br' and self._in_p:
            self._lines.append([])
            return
        if tag == 'h5':
            self._in_h5 = True
            self._h5_parts = []
            return
        if tag == 'p':
            self._in_p = True
            self._lines = [[]]

    def handle_endtag(self, tag: str) -> None:
        if self._in_entry:
            if tag == 'h5' and self._in_h5:
                self._finish_h5()
            elif tag == 'p' and self._in_p:
                self._finish_p()
        self._leave(tag)

    def handle_data(self, data: str) -> None:
        if not self._in_entry:
            return
        if self._in_h5:
            self._h5_parts.append(data)
        elif self._in_p and self._lines:
            self._lines[-1].append(data)

    def close(self) -> None:
        super().close()
        if not self._seen_entry:
            raise WolfsonSourceError(
                'Wolfson archive page had no entry-content section'
            )

    def _enter(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _VOID_TAGS:
            return
        if not self._in_entry:
            if 'entry-content' in _class_set(attrs):
                self._seen_entry = True
                self._in_entry = True
                self._depth = 1
            return
        self._depth += 1

    def _leave(self, tag: str) -> None:
        if tag in _VOID_TAGS or not self._in_entry:
            return
        self._depth -= 1
        if self._depth <= 0:
            self._in_entry = False
            self._depth = 0

    def _finish_h5(self) -> None:
        raw = ''.join(self._h5_parts).replace('\u200b', '').replace('\ufeff', '')
        text = _collapse_ws(raw)
        self._in_h5 = False
        self._h5_parts = []
        if not text:
            return
        if not _YEAR_RE.fullmatch(text):
            raise WolfsonSourceError(
                f'Wolfson archive contained an unexpected heading: {text!r}'
            )
        year = int(text)
        if year in self._seen_years:
            raise WolfsonSourceError(
                f'Wolfson archive repeated year heading {year}'
            )
        self._seen_years.add(year)
        self.years.append(year)
        self._year = year
        self._mode = 'winner'
        self._saw_shortlist = False

    def _finish_p(self) -> None:
        lines = [_collapse_ws(''.join(parts)) for parts in self._lines]
        lines = [line for line in lines if line]
        self._in_p = False
        self._lines = []
        if not lines:
            return
        if self._year is None:
            if _SHORTLIST_RE.fullmatch(lines[0]) or _is_book_shape(lines):
                raise WolfsonSourceError(
                    'Wolfson archive book entry appeared before a year heading'
                )
            return
        if len(lines) == 1 and (match := _SHORTLIST_RE.fullmatch(lines[0])):
            labeled_year = match.group(1)
            if self._year < SHORTLIST_START_YEAR:
                raise WolfsonSourceError(
                    f'Wolfson archive year {self._year} had a shortlist label '
                    f'before {SHORTLIST_START_YEAR}'
                )
            if self._saw_shortlist:
                raise WolfsonSourceError(
                    f'Wolfson archive year {self._year} repeated a shortlist label'
                )
            if labeled_year is not None and int(labeled_year) != self._year:
                raise WolfsonSourceError(
                    f'Wolfson archive year {self._year} had a shortlist label '
                    f'for {labeled_year}'
                )
            self._mode = 'shortlist'
            self._saw_shortlist = True
            return
        if _is_contribution_title(lines[0]):
            return
        if not _is_book_shape(lines):
            raise WolfsonSourceError(
                f'Wolfson archive year {self._year} had an unreadable book '
                f'entry: {lines!r}'
            )
        title, author = lines[0], lines[1]
        status = 'Winner' if self._mode == 'winner' else 'Shortlisted'
        self.records.append(
            _ParsedRecord(
                award_year=self._year,
                category=None,
                status=status,
                work_title=title,
                work_author=author,
                source_url=SOURCE_HOME_URL,
            )
        )


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


def _match_title(value: str) -> str:
    text = normalize_title_conjunctions(_normalize_text(value))
    return _SPACE_BEFORE_PUNCT_RE.sub(r'\1', text)


def _identity_key(record: _ParsedRecord) -> tuple[int, str, str]:
    return (
        record.award_year,
        _match_title(record.work_title),
        _normalize_text(record.work_author),
    )


def _apply_status_precedence(
    records: list[_ParsedRecord],
) -> list[_ParsedRecord]:
    """Keep one row per work/year/author. Winner replaces Shortlisted."""
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
    parser = _WolfsonArchiveParser()
    parser.feed(html)
    parser.close()
    records = tuple(_apply_status_precedence(parser.records))
    return records, tuple(parser.years)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _counts_for_year(
    records: tuple[_ParsedRecord, ...],
    year: int,
) -> tuple[int, int]:
    winners = 0
    shortlisted = 0
    for record in records:
        if record.award_year != year:
            continue
        if record.status == 'Winner':
            winners += 1
        elif record.status == 'Shortlisted':
            shortlisted += 1
    return winners, shortlisted


def _validate_record(record: _ParsedRecord) -> None:
    if record.category is not None:
        raise WolfsonSourceError(
            f'Wolfson archive produced an unexpected category: {record.category!r}'
        )
    if record.status not in _PARSED_STATUSES:
        raise WolfsonSourceError(
            f'Wolfson archive produced an unexpected status: {record.status!r}'
        )
    if (
        not isinstance(record.work_title, str)
        or not record.work_title.strip()
        or record.work_title != record.work_title.strip()
    ):
        raise WolfsonSourceError('Wolfson archive produced an empty title')
    if (
        not isinstance(record.work_author, str)
        or not record.work_author.strip()
        or record.work_author != record.work_author.strip()
    ):
        raise WolfsonSourceError('Wolfson archive produced an empty author')
    if record.source_url != SOURCE_HOME_URL:
        raise WolfsonSourceError(
            f'Wolfson archive produced an unexpected source URL: '
            f'{record.source_url!r}'
        )
    if (
        not isinstance(record.award_year, int)
        or isinstance(record.award_year, bool)
        or record.award_year < ARCHIVE_MIN_YEAR
    ):
        raise WolfsonSourceError(
            f'Wolfson archive produced an unexpected year: {record.award_year!r}'
        )


def _validate_year_headings(years: tuple[int, ...]) -> int:
    if not years:
        raise WolfsonSourceError(
            'Wolfson archive did not contain year headings'
        )
    year_set = set(years)
    if len(year_set) != len(years):
        raise WolfsonSourceError('Wolfson archive repeated a year heading')
    if any(year < ARCHIVE_MIN_YEAR for year in year_set):
        raise WolfsonSourceError(
            'Wolfson archive contained a year before '
            f'{ARCHIVE_MIN_YEAR}'
        )
    if ARCHIVE_MIN_YEAR not in year_set:
        raise WolfsonSourceError(
            f'Wolfson archive history did not include {ARCHIVE_MIN_YEAR}'
        )
    for anchor in ANCHOR_YEARS:
        if anchor not in year_set:
            raise WolfsonSourceError(
                f'Wolfson archive is missing reviewed year {anchor}'
            )
    maximum = max(year_set)
    expected = set(range(ARCHIVE_MIN_YEAR, maximum + 1))
    unexpected_missing = sorted(expected - year_set - {ABSENT_YEAR})
    if unexpected_missing:
        raise WolfsonSourceError(
            f'Wolfson archive is missing year {unexpected_missing[0]}'
        )
    return maximum


def _validate_year_shape(
    year: int,
    winners: int,
    shortlisted: int,
    *,
    newest: int,
) -> None:
    if year < SHORTLIST_START_YEAR:
        if shortlisted != 0 or winners not in (1, 2, 3):
            raise WolfsonSourceError(
                f'Wolfson archive year {year} had {winners} Winner and '
                f'{shortlisted} Shortlisted record(s); historical years must '
                'have 1 to 3 Winners and no Shortlisted records'
            )
        return
    if year == newest:
        if (winners, shortlisted) not in {(0, 6), (1, 5)}:
            raise WolfsonSourceError(
                f'Wolfson archive year {year} had {winners} Winner and '
                f'{shortlisted} Shortlisted record(s); the newest year must '
                'have 0 Winners and 6 Shortlisted, or 1 Winner and 5 Shortlisted'
            )
        return
    if (winners, shortlisted) != (1, 5):
        raise WolfsonSourceError(
            f'Wolfson archive year {year} had {winners} Winner and '
            f'{shortlisted} Shortlisted record(s); completed shortlist years '
            'must have 1 Winner and 5 Shortlisted'
        )


def _validate_archive(
    records: tuple[_ParsedRecord, ...],
    years: tuple[int, ...],
) -> None:
    """Fail closed when the parsed archive is not a usable Wolfson history.

    1988 may be absent. Contribution honors are already omitted and do not
    count. The newest year may still be a six-book shortlist with no Winner.
    """
    maximum = _validate_year_headings(years)
    if not records:
        raise WolfsonSourceError('Wolfson archive contained no book records')
    identities = [_identity_key(record) for record in records]
    if len(identities) != len(set(identities)):
        raise WolfsonSourceError(
            'Wolfson archive contained duplicate work/year identities'
        )
    year_set = set(years)
    for record in records:
        _validate_record(record)
        if record.award_year not in year_set:
            raise WolfsonSourceError(
                f'Wolfson archive record year {record.award_year} had no heading'
            )
    for year in sorted(year_set):
        winners, shortlisted = _counts_for_year(records, year)
        _validate_year_shape(
            year,
            winners,
            shortlisted,
            newest=maximum,
        )


def _validate_cached_archive(records: tuple[_ParsedRecord, ...]) -> None:
    years = tuple(sorted({record.award_year for record in records}))
    _validate_archive(records, years)


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
    if data.get('category') is not None:
        return None
    status = data.get('status')
    work_title = data.get('work_title')
    work_author = data.get('work_author')
    source_url = data.get('source_url')
    if status not in _PARSED_STATUSES:
        return None
    if not isinstance(work_title, str) or not work_title.strip() or work_title != work_title.strip():
        return None
    if not isinstance(work_author, str) or not work_author.strip() or work_author != work_author.strip():
        return None
    if source_url != SOURCE_HOME_URL:
        return None
    return _ParsedRecord(
        award_year=award_year,
        category=None,
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
    if not isinstance(raw_records, list) or not raw_records:
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
    except WolfsonSourceError:
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
# Lookup
# ---------------------------------------------------------------------------

def _titles_match(query_title: str, record_title: str) -> bool:
    return _match_title(query_title) == _match_title(record_title)


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
        notes=None,
    )


def lookup(title: str, author: str, series: str | None = None) -> list[AwardResult]:
    """Look up Wolfson History Prize results for a title and author."""
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


# Coordinate RAM freshness and explicit refresh on retrieval workers.
import sys as _runtime_sys
from ..cache import source_runtime_guard as _runtime_guard
lookup = _runtime_guard(_runtime_sys.modules[__name__], lookup)
_get_archive_records = _runtime_guard(_runtime_sys.modules[__name__], _get_archive_records)
