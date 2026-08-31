"""Official National Book Critics Circle Awards year-archive source.

Work-level Winners and Finalists come from /past-awards/YYYY/. Longlist is
ignored. Person, reviewer, institution, and fellowship honors are excluded.
REST is used only to discover archive years; award facts come from HTML.
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
SOURCE_KEY = 'national_book_critics_circle'
AWARD_NAME = 'National Book Critics Circle Award'
SOURCE_NAME = 'National Book Critics Circle'
SITE_ORIGIN = 'https://www.bookcritics.org'
SOURCE_HOME_URL = SITE_ORIGIN + '/awards/'
YEAR_URL_TEMPLATE = SITE_ORIGIN + '/past-awards/{year}/'
YEAR_INDEX_URL = SITE_ORIGIN + '/wp-json/wp/v2/award?per_page=100'
ARCHIVE_MIN_YEAR = 1975
YEAR_CACHE_VERSION = 1
INDEX_CACHE_VERSION = 1
INDEX_ENTRY_KIND = 'index'
INDEX_ENTRY_KEY = 'archive'
YEAR_ENTRY_KIND = 'years'
HISTORICAL_YEAR_CACHE_TTL_SECONDS = 180 * 24 * 60 * 60
CURRENT_CACHE_BASE_TTL_SECONDS = 7 * 24 * 60 * 60
CURRENT_CACHE_REFRESH_OFFSET_SECONDS = 12 * 60 * 60
CURRENT_CACHE_TTL_SECONDS = (
    CURRENT_CACHE_BASE_TTL_SECONDS + CURRENT_CACHE_REFRESH_OFFSET_SECONDS
)

_WORK_CATEGORIES = frozenset({
    'Fiction',
    'General Nonfiction',
    'Nonfiction',
    'Poetry',
    'Criticism',
    'Biography/Autobiography',
    'Biography',
    'Autobiography/Memoir',
    'Autobiography',
    'John Leonard Prize',
    'Gregg Barrios Book in Translation',
})
_SOURCEINFO_CATEGORIES = (
    'Fiction',
    'Nonfiction',
    'Biography',
    'Autobiography',
    'Poetry',
    'Criticism',
    'John Leonard Prize',
    'Gregg Barrios Book in Translation',
)
_CLASSIC_BARE_WINNER_HEADINGS = frozenset({
    'Autobiography',
    'John Leonard Prize',
})
_YEAR_STATES = frozenset({'absent', 'in_progress', 'completed'})
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
_YEAR_COVERAGE_FIELDS = frozenset({'award_year', 'state'})
_INDEX_COVERAGE_FIELDS = frozenset({'kind', 'max_year', 'min_year'})
_OFFICIAL_HTML_HOSTS = frozenset({
    'bookcritics.org',
    'www.bookcritics.org',
})
_IDENTITY_MARKER = 'national book critics circle'
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
_YEAR_ONLY_RE = re.compile(r'^\d{4}$')
_YEAR_IN_TEXT_RE = re.compile(r'\b(19|20)\d{2}\b')
_INITIALS_SPACE_RE = re.compile(r'\b([A-Za-z])\.\s+')
_HEADING_FINALISTS_RE = re.compile(
    r'^(?P<category>.+?)\s+Finalists?$',
    re.IGNORECASE,
)
_HEADING_WINNERS_RE = re.compile(
    r'^(?P<category>.+?)\s+Winners?$',
    re.IGNORECASE,
)
_CATEGORY_PREFIX_RE = re.compile(
    r'^(?P<category>Fiction|General Nonfiction|Poetry|Criticism)\s*:\s*'
    r'(?P<rest>.+)$',
    re.IGNORECASE | re.DOTALL,
)
_AUTHOR_TITLE_PUBLISHER_RE = re.compile(
    r'^(?P<author>.+?),\s+(?P<title>.+?)(?:\s+\((?P<publisher>[^()]+)\))?\s*$',
    re.DOTALL,
)
_POSSESSIVE_AUTHOR_RE = re.compile(r"['\u2019]s$", re.IGNORECASE)
_TRANSLATOR_CLAUSE_RES = (
    re.compile(
        r',?\s+translated from the [^,]+ by .+$',
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(r',?\s+translated by .+$', re.IGNORECASE | re.DOTALL),
    re.compile(r',?\s+translation by .+$', re.IGNORECASE | re.DOTALL),
    re.compile(r',?\s+trans\.\s*by .+$', re.IGNORECASE | re.DOTALL),
    re.compile(r'\s*\(\s*trans\.\s*.+\)\s*$', re.IGNORECASE | re.DOTALL),
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


class NationalBookCriticsCircleSourceError(RuntimeError):
    """Raised when official NBCC pages are blocked or unusable."""


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
    state: str
    source_url: str
    records: tuple[_ParsedRecord, ...]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _current_calendar_year() -> int:
    """UTC calendar year. Tests may patch _utc_now or this helper."""
    return _utc_now().year


def _collapse_ws(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def _canonical_year_url(year: int) -> str:
    return YEAR_URL_TEMPLATE.format(year=year)


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


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _build_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(CookieJar())
    )


def _read_response_body(response) -> str:
    return response.read().decode('utf-8', errors='replace')


def _fetch_response(url: str) -> tuple[int, str]:
    """Return (status, body). HTTP 404 is returned; other failures raise."""
    request = urllib.request.Request(url, headers=dict(_BROWSER_HEADERS))
    try:
        with _build_opener().open(request, timeout=TIMEOUT_SECONDS) as response:
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
        raise NationalBookCriticsCircleSourceError(
            f'NBCC request failed with HTTP {exc.code} for {url}'
        ) from exc
    except urllib.error.URLError as exc:
        raise NationalBookCriticsCircleSourceError(
            f'NBCC request failed for {url}: {exc.reason}'
        ) from exc
    if status == 404:
        return 404, body
    if status != 200:
        raise NationalBookCriticsCircleSourceError(
            f'NBCC request failed with HTTP {status} for {url}'
        )
    return int(status), body


def _fetch_html(url: str) -> str:
    status, body = _fetch_response(url)
    if status != 200:
        raise NationalBookCriticsCircleSourceError(
            f'NBCC request failed with HTTP {status} for {url}'
        )
    return body


_index_years_cache: tuple[int, ...] | None = None
_year_snapshot_cache: dict[int, _YearSnapshot] = {}
_cache_lock = threading.Lock()


def _reset_runtime_state() -> None:
    """Clear in-process NBCC caches. Does not delete disk cache."""
    global _index_years_cache
    with _cache_lock:
        _index_years_cache = None
        _year_snapshot_cache.clear()


# ---------------------------------------------------------------------------
# Identity / year
# ---------------------------------------------------------------------------

def _html_has_nbcc_identity(html: str) -> bool:
    return _IDENTITY_MARKER in html.casefold()


def _page_declares_year(html: str, award_year: int) -> bool:
    token = str(award_year)
    if f'award-{award_year}' in html.casefold():
        return True
    title_match = re.search(r'<title>([^<]+)</title>', html, re.IGNORECASE)
    if title_match is not None and token in title_match.group(1):
        return True
    h2_match = re.search(
        r'<h2[^>]*class="[^"]*entry-title[^"]*"[^>]*>(.*?)</h2>',
        html,
        re.IGNORECASE | re.DOTALL,
    )
    if h2_match is not None:
        heading = _collapse_ws(re.sub(r'<[^>]+>', ' ', h2_match.group(1)))
        if token in heading:
            return True
    return False


def _require_year_page_identity(html: str, award_year: int, url: str) -> None:
    if _official_page_url(url) is None:
        raise NationalBookCriticsCircleSourceError(
            f'NBCC year URL is not official: {url}'
        )
    if not _html_has_nbcc_identity(html):
        raise NationalBookCriticsCircleSourceError(
            f'NBCC {award_year} page did not identify National Book Critics Circle'
        )
    if not _page_declares_year(html, award_year):
        raise NationalBookCriticsCircleSourceError(
            f'NBCC {award_year} page did not declare archive year {award_year}'
        )


# ---------------------------------------------------------------------------
# Translator / title-author parsing
# ---------------------------------------------------------------------------

def _strip_translator_clause(author: str) -> str:
    text = _collapse_ws(author).rstrip(',;')
    if not text:
        return text
    for pattern in _TRANSLATOR_CLAUSE_RES:
        stripped = pattern.sub('', text)
        if stripped != text:
            text = _collapse_ws(stripped.rstrip(',;'))
            break
    return text


def _strip_trailing_possessive(author: str) -> str:
    text = _collapse_ws(author)
    if _POSSESSIVE_AUTHOR_RE.search(text):
        return _collapse_ws(_POSSESSIVE_AUTHOR_RE.sub('', text))
    return text


def _pair_from_markup(plain: str, em_titles: tuple[str, ...]) -> tuple[str, str] | None:
    collapsed = _collapse_ws(plain)
    if em_titles:
        title = _collapse_ws(em_titles[0])
        if not title:
            return None
        prefix = collapsed
        idx = prefix.casefold().find(title.casefold())
        if idx >= 0:
            prefix = prefix[:idx]
        author = _collapse_ws(prefix).rstrip(',;')
        author = _strip_translator_clause(author)
        author = _strip_trailing_possessive(author)
        author = _collapse_ws(author).rstrip(',;')
        if not author:
            return None
        return author, title
    match = _AUTHOR_TITLE_PUBLISHER_RE.fullmatch(collapsed)
    if match is None:
        return None
    author = _collapse_ws(match.group('author')).rstrip(',;')
    author = _strip_translator_clause(author)
    author = _collapse_ws(author).rstrip(',;')
    title = _collapse_ws(match.group('title'))
    if not author or not title:
        return None
    return author, title


def _classic_heading_status(heading: str) -> tuple[str, str] | None:
    text = _collapse_ws(heading)
    if not text:
        return None
    if text.casefold() == 'winners':
        return ('__1975__', 'Winner')
    finalists = _HEADING_FINALISTS_RE.fullmatch(text)
    if finalists is not None:
        category = _collapse_ws(finalists.group('category'))
        if category in _WORK_CATEGORIES:
            return (category, 'Finalist')
        return None
    winners = _HEADING_WINNERS_RE.fullmatch(text)
    if winners is not None:
        category = _collapse_ws(winners.group('category'))
        if category in _WORK_CATEGORIES:
            return (category, 'Winner')
        return None
    if text in _CLASSIC_BARE_WINNER_HEADINGS:
        return (text, 'Winner')
    return None


# ---------------------------------------------------------------------------
# HTML parser
# ---------------------------------------------------------------------------

class _YearPageParser(HTMLParser):
    """Extract work-level Winner/Finalist rows from one official year page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ignore = 0
        self.in_regular = False
        self.regular_depth = 0
        self.in_modern = False
        self.in_h3 = False
        self.h3_parts: list[str] = []
        self.heading: str | None = None
        self.in_li = False
        self.li_status = ''
        self.li_parts: list[str] = []
        self.li_em: list[str] = []
        self.in_em = False
        self.em_parts: list[str] = []
        self.classic_items: list[tuple[str, str, str, tuple[str, ...]]] = []
        self.modern_items: list[tuple[str, str, str, tuple[str, ...]]] = []
        self.saw_longlist = False

    def handle_starttag(self, tag: str, attrs) -> None:
        attr = {key: value or '' for key, value in attrs}
        classes = _classes(attr)
        if tag in ('script', 'style', 'svg', 'noscript'):
            self.ignore += 1
            return
        if self.ignore:
            return
        if tag == 'div' and 'content-regular' in classes:
            self.in_regular = True
            self.regular_depth = 1
        elif tag == 'div' and self.in_regular:
            self.regular_depth += 1
        if tag == 'ul' and 'award-year-list' in classes:
            self.in_modern = True
        if tag == 'h3' and (self.in_regular or self.in_modern):
            self.in_h3 = True
            self.h3_parts = []
        if tag == 'li' and (self.in_regular or self.in_modern):
            self.in_li = True
            self.li_status = next(iter(classes), '') if classes else ''
            self.li_parts = []
            self.li_em = []
        if tag == 'em' and self.in_li:
            self.in_em = True
            self.em_parts = []
        if tag in _VOID_TAGS:
            return

    def handle_endtag(self, tag: str) -> None:
        if tag in ('script', 'style', 'svg', 'noscript'):
            if self.ignore:
                self.ignore -= 1
            return
        if self.ignore:
            return
        if tag == 'h3' and self.in_h3:
            self.heading = _collapse_ws(''.join(self.h3_parts))
            self.in_h3 = False
        if tag == 'em' and self.in_em:
            self.li_em.append(_collapse_ws(''.join(self.em_parts)))
            self.in_em = False
        if tag == 'li' and self.in_li:
            text = _collapse_ws(''.join(self.li_parts))
            ems = tuple(part for part in self.li_em if part)
            heading = self.heading or ''
            if self.in_modern:
                if self.li_status.casefold() == 'longlist':
                    self.saw_longlist = True
                else:
                    self.modern_items.append(
                        (heading, self.li_status, text, ems)
                    )
            elif self.in_regular:
                self.classic_items.append((heading, self.li_status, text, ems))
            self.in_li = False
        if tag == 'ul' and self.in_modern:
            self.in_modern = False
        if tag == 'div' and self.in_regular:
            self.regular_depth -= 1
            if self.regular_depth <= 0:
                self.in_regular = False
                self.regular_depth = 0

    def handle_data(self, data: str) -> None:
        if self.ignore:
            return
        if self.in_h3:
            self.h3_parts.append(data)
        if self.in_em:
            self.em_parts.append(data)
        if self.in_li:
            self.li_parts.append(data)


def _record(
    award_year: int,
    category: str,
    status: str,
    title: str,
    author: str,
    source_url: str,
) -> _ParsedRecord:
    return _ParsedRecord(
        award_year=award_year,
        category=category,
        status=status,
        work_title=title,
        work_author=author,
        source_url=source_url,
    )


def _parse_classic_items(
    items: list[tuple[str, str, str, tuple[str, ...]]],
    award_year: int,
    source_url: str,
) -> list[_ParsedRecord]:
    records: list[_ParsedRecord] = []
    for heading, _li_status, text, ems in items:
        mapped = _classic_heading_status(heading)
        if mapped is None:
            continue
        category, status = mapped
        if category == '__1975__':
            prefix = _CATEGORY_PREFIX_RE.fullmatch(text)
            if prefix is None:
                continue
            category = _collapse_ws(prefix.group('category'))
            if category not in _WORK_CATEGORIES:
                continue
            rest = prefix.group('rest')
            pair = _pair_from_markup(rest, ems)
        else:
            pair = _pair_from_markup(text, ems)
        if pair is None:
            continue
        author, title = pair
        records.append(
            _record(award_year, category, status, title, author, source_url)
        )
    return records


def _parse_modern_items(
    items: list[tuple[str, str, str, tuple[str, ...]]],
    award_year: int,
    source_url: str,
) -> list[_ParsedRecord]:
    records: list[_ParsedRecord] = []
    for heading, li_status, text, ems in items:
        category = _collapse_ws(heading)
        if category not in _WORK_CATEGORIES:
            continue
        if li_status not in _PARSED_STATUSES:
            continue
        pair = _pair_from_markup(text, ems)
        if pair is None:
            continue
        author, title = pair
        records.append(
            _record(award_year, category, li_status, title, author, source_url)
        )
    return records


def _identity_key(record: _ParsedRecord) -> tuple[int, str, str, str]:
    return (
        record.award_year,
        _normalize_text(record.category),
        normalize_title_conjunctions(_normalize_text(record.work_title)),
        _normalize_text(record.work_author),
    )


def _dedupe_records(records: list[_ParsedRecord]) -> tuple[_ParsedRecord, ...]:
    best: dict[tuple[int, str, str, str], _ParsedRecord] = {}
    order: list[tuple[int, str, str, str]] = []
    for record in records:
        key = _identity_key(record)
        existing = best.get(key)
        if existing is None:
            best[key] = record
            order.append(key)
            continue
        if _STATUS_WEIGHT.get(record.status, 0) > _STATUS_WEIGHT.get(
            existing.status, 0
        ):
            best[key] = record
    return tuple(best[key] for key in order)


def _parse_year_html(
    html: str,
    award_year: int,
    source_url: str,
) -> tuple[tuple[_ParsedRecord, ...], bool]:
    parser = _YearPageParser()
    parser.feed(html)
    if parser.modern_items:
        raw = _parse_modern_items(parser.modern_items, award_year, source_url)
    else:
        raw = _parse_classic_items(parser.classic_items, award_year, source_url)
    return _dedupe_records(raw), parser.saw_longlist


# ---------------------------------------------------------------------------
# Completion
# ---------------------------------------------------------------------------

def _winner_categories(records: tuple[_ParsedRecord, ...]) -> set[str]:
    return {
        record.category
        for record in records
        if record.status == 'Winner'
    }


def _has_autobiography_family_winner(winners: set[str]) -> bool:
    return 'Autobiography' in winners or 'Autobiography/Memoir' in winners


def _year_has_required_core_winners(
    award_year: int,
    records: tuple[_ParsedRecord, ...],
) -> bool:
    winners = _winner_categories(records)
    if award_year <= 1982:
        required = {
            'Fiction',
            'General Nonfiction',
            'Poetry',
            'Criticism',
        }
        return required <= winners
    if award_year <= 2002:
        required = {
            'Fiction',
            'General Nonfiction',
            'Poetry',
            'Criticism',
            'Biography/Autobiography',
        }
        return required <= winners
    if award_year <= 2004:
        required = {
            'Fiction',
            'General Nonfiction',
            'Poetry',
            'Criticism',
            'Biography',
        }
        return required <= winners
    if award_year <= 2016:
        required = {
            'Fiction',
            'General Nonfiction',
            'Poetry',
            'Criticism',
            'Biography',
        }
        return required <= winners and _has_autobiography_family_winner(winners)
    required = {
        'Fiction',
        'Nonfiction',
        'Biography',
        'Autobiography',
        'Poetry',
        'Criticism',
    }
    return required <= winners


def _classify_year_state(
    award_year: int,
    records: tuple[_ParsedRecord, ...],
    saw_longlist: bool,
    *,
    indexed: bool,
) -> str:
    if _year_has_required_core_winners(award_year, records):
        return 'completed'
    has_finalist = any(record.status == 'Finalist' for record in records)
    if has_finalist or saw_longlist or records:
        return 'in_progress'
    if indexed:
        raise NationalBookCriticsCircleSourceError(
            f'NBCC {award_year} archive page did not contain required work-level awards'
        )
    return 'in_progress'


def _validate_records(records: tuple[_ParsedRecord, ...], award_year: int) -> None:
    seen: set[tuple[int, str, str, str]] = set()
    for record in records:
        if record.award_year != award_year:
            raise NationalBookCriticsCircleSourceError(
                f'NBCC {award_year} contained a mismatched year'
            )
        if record.category not in _WORK_CATEGORIES:
            raise NationalBookCriticsCircleSourceError(
                f'NBCC {award_year} contained a non-work category'
            )
        if record.status not in _PARSED_STATUSES:
            raise NationalBookCriticsCircleSourceError(
                f'NBCC {award_year} contained an unsupported status'
            )
        if not record.work_title or not record.work_author:
            raise NationalBookCriticsCircleSourceError(
                f'NBCC {award_year} contained an incomplete work record'
            )
        key = _identity_key(record)
        if key in seen:
            raise NationalBookCriticsCircleSourceError(
                f'NBCC {award_year} contained duplicate work records'
            )
        seen.add(key)


# ---------------------------------------------------------------------------
# Index discovery
# ---------------------------------------------------------------------------

def _years_from_rest_payload(payload) -> tuple[int, ...]:
    if not isinstance(payload, list):
        raise NationalBookCriticsCircleSourceError(
            'NBCC award index was not a JSON list'
        )
    years: list[int] = []
    seen: set[int] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        slug = item.get('slug')
        if not isinstance(slug, str) or not _YEAR_ONLY_RE.fullmatch(slug.strip()):
            continue
        year = int(slug.strip())
        if year < ARCHIVE_MIN_YEAR:
            continue
        link = item.get('link')
        if isinstance(link, str):
            official = _official_page_url(link)
            if official is None:
                continue
        if year in seen:
            continue
        seen.add(year)
        years.append(year)
    if not years:
        raise NationalBookCriticsCircleSourceError(
            'NBCC award index did not contain archive years'
        )
    ordered = tuple(sorted(years))
    if ordered[0] != ARCHIVE_MIN_YEAR:
        raise NationalBookCriticsCircleSourceError(
            'NBCC award index did not begin at 1975'
        )
    return ordered


def _acquire_live_index_years() -> tuple[int, ...]:
    body = _fetch_html(YEAR_INDEX_URL)
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise NationalBookCriticsCircleSourceError(
            'NBCC award index was unreadable'
        ) from exc
    if isinstance(payload, dict) and payload.get('content'):
        raise NationalBookCriticsCircleSourceError(
            'NBCC award index unexpectedly contained rendered content'
        )
    return _years_from_rest_payload(payload)


def _index_coverage(years: tuple[int, ...]) -> dict:
    return {
        'kind': 'archive',
        'max_year': max(years),
        'min_year': min(years),
    }


def _index_years_from_payload(payload: dict) -> tuple[int, ...] | None:
    coverage = payload.get('coverage')
    if not isinstance(coverage, dict) or set(coverage) != _INDEX_COVERAGE_FIELDS:
        return None
    if coverage.get('kind') != 'archive':
        return None
    raw_records = payload.get('records')
    if not isinstance(raw_records, list) or not raw_records:
        return None
    years: list[int] = []
    for item in raw_records:
        if not isinstance(item, dict) or set(item) != {'award_year'}:
            return None
        year = item.get('award_year')
        if isinstance(year, bool) or not isinstance(year, int) or year < ARCHIVE_MIN_YEAR:
            return None
        years.append(year)
    ordered = tuple(sorted(years))
    if ordered[0] != coverage.get('min_year'):
        return None
    if ordered[-1] != coverage.get('max_year'):
        return None
    if ordered[0] != ARCHIVE_MIN_YEAR:
        return None
    return ordered


def _save_persistent_index(years: tuple[int, ...]) -> None:
    try:
        cache.save_cache_entry(
            SOURCE_KEY,
            INDEX_ENTRY_KIND,
            INDEX_ENTRY_KEY,
            INDEX_CACHE_VERSION,
            records=[{'award_year': year} for year in years],
            source_urls=[YEAR_INDEX_URL],
            coverage=_index_coverage(years),
            ttl_seconds=CURRENT_CACHE_TTL_SECONDS,
        )
    except OSError:
        pass


def _load_persistent_index() -> tuple[tuple[int, ...], dict] | None:
    payload = cache.load_cache_entry(
        SOURCE_KEY,
        INDEX_ENTRY_KIND,
        INDEX_ENTRY_KEY,
        INDEX_CACHE_VERSION,
    )
    if payload is None:
        return None
    years = _index_years_from_payload(payload)
    if years is None:
        return None
    return years, payload


def _get_index_years() -> tuple[int, ...]:
    """REST year discovery. Cached; stale index is reused without the slot.

    New publishing years after the indexed max are handled by the probe year,
    so a stale index does not need to claim the shared refresh budget.
    """
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


# ---------------------------------------------------------------------------
# Year cache
# ---------------------------------------------------------------------------

def _year_ttl_seconds(state: str) -> int:
    if state == 'completed':
        return HISTORICAL_YEAR_CACHE_TTL_SECONDS
    return CURRENT_CACHE_TTL_SECONDS


def _year_coverage(award_year: int, state: str) -> dict:
    return {'award_year': award_year, 'state': state}


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
    if category not in _WORK_CATEGORIES:
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


def _snapshot_from_payload(
    payload: dict,
    award_year: int,
    *,
    indexed: bool,
) -> _YearSnapshot | None:
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
        if indexed:
            return None
        if raw_records:
            return None
        return _YearSnapshot(
            award_year=award_year,
            state='absent',
            source_url='',
            records=(),
        )
    if len(source_urls) != 1 or not isinstance(source_urls[0], str):
        return None
    source_url = source_urls[0]
    if source_url != _canonical_year_url(award_year):
        return None
    records: list[_ParsedRecord] = []
    for item in raw_records:
        record = _record_from_cache_dict(item)
        if record is None or record.award_year != award_year:
            return None
        records.append(record)
    restored = _dedupe_records(records)
    try:
        _validate_records(restored, award_year)
    except NationalBookCriticsCircleSourceError:
        return None
    if state == 'completed':
        if not _year_has_required_core_winners(award_year, restored):
            return None
    elif state == 'in_progress':
        if _year_has_required_core_winners(award_year, restored):
            return None
    return _YearSnapshot(
        award_year=award_year,
        state=state,
        source_url=source_url,
        records=restored,
    )


def _load_persistent_year(
    award_year: int,
    *,
    indexed: bool,
) -> tuple[_YearSnapshot, dict] | None:
    payload = cache.load_cache_entry(
        SOURCE_KEY,
        YEAR_ENTRY_KIND,
        _year_entry_key(award_year),
        YEAR_CACHE_VERSION,
    )
    if payload is None:
        return None
    snapshot = _snapshot_from_payload(payload, award_year, indexed=indexed)
    if snapshot is None:
        return None
    return snapshot, payload


def _save_persistent_year(snapshot: _YearSnapshot) -> None:
    source_urls = [snapshot.source_url] if snapshot.source_url else []
    try:
        cache.save_cache_entry(
            SOURCE_KEY,
            YEAR_ENTRY_KIND,
            _year_entry_key(snapshot.award_year),
            YEAR_CACHE_VERSION,
            records=[_record_to_cache_dict(record) for record in snapshot.records],
            source_urls=source_urls,
            coverage=_year_coverage(snapshot.award_year, snapshot.state),
            ttl_seconds=_year_ttl_seconds(snapshot.state),
        )
    except OSError:
        pass


def _store_year_snapshot(snapshot: _YearSnapshot) -> None:
    with _cache_lock:
        _year_snapshot_cache[snapshot.award_year] = snapshot


def _ram_year(award_year: int) -> _YearSnapshot | None:
    with _cache_lock:
        return _year_snapshot_cache.get(award_year)


def _acquire_live_year(award_year: int, *, indexed: bool) -> _YearSnapshot:
    url = _canonical_year_url(award_year)
    status, body = _fetch_response(url)
    if status == 404:
        if indexed:
            raise NationalBookCriticsCircleSourceError(
                f'NBCC {award_year} official archive year was missing'
            )
        return _YearSnapshot(
            award_year=award_year,
            state='absent',
            source_url='',
            records=(),
        )
    _require_year_page_identity(body, award_year, url)
    records, saw_longlist = _parse_year_html(body, award_year, url)
    _validate_records(records, award_year)
    state = _classify_year_state(
        award_year,
        records,
        saw_longlist,
        indexed=indexed,
    )
    return _YearSnapshot(
        award_year=award_year,
        state=state,
        source_url=url,
        records=records,
    )


def _get_one_year(award_year: int, *, indexed: bool) -> _YearSnapshot:
    ram = _ram_year(award_year)
    if ram is not None and not (ram.state == 'absent' and indexed):
        return ram
    loaded = _load_persistent_year(award_year, indexed=indexed)
    if loaded is not None:
        snapshot, payload = loaded
        if cache.cache_is_fresh(payload) or not cache.try_claim_stale_refresh():
            _store_year_snapshot(snapshot)
            return snapshot
        try:
            live = _acquire_live_year(award_year, indexed=indexed)
        except Exception:
            _store_year_snapshot(snapshot)
            return snapshot
        _save_persistent_year(live)
        _store_year_snapshot(live)
        return live
    live = _acquire_live_year(award_year, indexed=indexed)
    _save_persistent_year(live)
    _store_year_snapshot(live)
    return live


def _probe_year(max_index_year: int) -> int | None:
    probe = max_index_year + 1
    if probe < ARCHIVE_MIN_YEAR:
        return None
    if probe > _current_calendar_year():
        return None
    return probe


def _get_archive_records() -> tuple[_ParsedRecord, ...]:
    index_years = _get_index_years()
    collected: list[_ParsedRecord] = []
    for year in index_years:
        try:
            snapshot = _get_one_year(year, indexed=True)
        except NationalBookCriticsCircleSourceError:
            continue
        collected.extend(snapshot.records)
    probe = _probe_year(max(index_years))
    if probe is not None and probe not in index_years:
        try:
            snapshot = _get_one_year(probe, indexed=False)
        except NationalBookCriticsCircleSourceError:
            snapshot = None
        if snapshot is not None:
            collected.extend(snapshot.records)
    return tuple(
        sorted(
            collected,
            key=lambda record: (
                record.award_year,
                record.category,
                0 if record.status == 'Winner' else 1,
                record.work_title.casefold(),
            ),
        )
    )


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
        notes=None,
        identity_kind='work',
    )


def lookup(title: str, author: str, series: str | None = None) -> list[AwardResult]:
    """Look up National Book Critics Circle results for a title and author.

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
