"""Official Nebula Awards written-work source (nebulas.sfwa.org).

Categories are fetched independently, but a lookup treats the official archive
as one unit: every configured category must parse, and one category failure
fails the source. Pagination follows official rel=next links. Caches store
validated pages and records only.
"""

from __future__ import annotations

import re
import threading
import unicodedata
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from urllib.parse import urljoin

from ..matching import normalize_title_conjunctions
from ..model import AwardResult

TIMEOUT_SECONDS = 30
SOURCE_HOME_URL = 'https://nebulas.sfwa.org/'

CATEGORY_BEST_NOVEL = 'Best Novel'
CATEGORY_BEST_NOVELLA = 'Best Novella'
CATEGORY_BEST_NOVELETTE = 'Best Novelette'
CATEGORY_BEST_SHORT_STORY = 'Best Short Story'
CATEGORY_BEST_POEM = 'Best Poem'
NORTON_AWARD_NAME = 'Andre Norton Award'
NORTON_CATEGORY = 'Middle Grade and Young Adult Fiction'
AWARD_NAME_NEBULA = 'Nebula Award'

BEST_NOVEL_URL = 'https://nebulas.sfwa.org/award/best-novel/'
BEST_NOVELLA_URL = 'https://nebulas.sfwa.org/award/best-novella/'
BEST_NOVELETTE_URL = 'https://nebulas.sfwa.org/award/best-novelette/'
BEST_SHORT_STORY_URL = 'https://nebulas.sfwa.org/award/best-short-story/'
BEST_POEM_URL = 'https://nebulas.sfwa.org/award/best-poem/'
NORTON_URL = 'https://nebulas.sfwa.org/award/andre-norton-award/'

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

_NEXT_LINK_RE = re.compile(
    r'<link[^>]+rel=["\']next["\'][^>]*href=["\']([^"\']+)["\']'
    r'|<link[^>]+href=["\']([^"\']+)["\'][^>]*rel=["\']next["\']',
    re.IGNORECASE,
)
_H2_YEAR_RE = re.compile(r'<h2[^>]*>\s*(\d{4})\s*</h2>', re.IGNORECASE)
_COMPACT_CITATION_RE = re.compile(
    r'^(?P<title>.+?),\s*by\s+(?P<author>.+?)(?:\s*\((?P<publisher>.*)\))?\s*$',
    re.IGNORECASE | re.DOTALL,
)
_INITIALS_SPACE_RE = re.compile(r'\b([A-Za-z])\.\s+')
_QUOTE_CHARS = '"“”\'‘’«»'
_CALIBRE_AMP_PLACEHOLDER = '\uffff'
_UNSAFE_AUTHOR_ROLE_RE = re.compile(
    r'\b(?:'
    r'with|translated\s+by|edited\s+by|editors?|introduction\s+by'
    r')\b',
    re.IGNORECASE,
)
_GENERATIONAL_SUFFIX_RE = re.compile(
    r'^(?:Jr\.?|Sr\.?|II|III|IV)$',
    re.IGNORECASE,
)
# Official Best Novella 1990 archive row omits the nominee-author link.
# The official nominated-work page identifies The Hemingway Hoax as a
# work by Joe Haldeman and as Winner, Best Novella in 1990.
_MISSING_AUTHOR_OVERRIDES: dict[tuple[str, int, str], str] = {
    (
        CATEGORY_BEST_NOVELLA,
        1990,
        'https://nebulas.sfwa.org/nominated-work/hemingway-hoax/',
    ): 'Joe Haldeman',
}


class NebulaSourceError(RuntimeError):
    """Raised when the official Nebula site blocks or fails retrieval."""


@dataclass(frozen=True, slots=True)
class _NebulaAwardConfig:
    key: str
    archive_url: str
    award_name: str
    category: str
    status_labels: tuple[str, ...]
    first_year: int
    winner_year_optional: bool = False
    no_work_winner_years: frozenset[int] = frozenset()


@dataclass(frozen=True, slots=True)
class _ParsedRecord:
    award_year: int
    award_name: str
    category: str
    status: str
    work_title: str
    work_author: str
    source_url: str | None


_BEST_NOVEL_CONFIG = _NebulaAwardConfig(
    key='best-novel',
    archive_url=BEST_NOVEL_URL,
    award_name=AWARD_NAME_NEBULA,
    category=CATEGORY_BEST_NOVEL,
    status_labels=(CATEGORY_BEST_NOVEL,),
    first_year=1965,
)
_BEST_NOVELLA_CONFIG = _NebulaAwardConfig(
    key='best-novella',
    archive_url=BEST_NOVELLA_URL,
    award_name=AWARD_NAME_NEBULA,
    category=CATEGORY_BEST_NOVELLA,
    status_labels=(CATEGORY_BEST_NOVELLA,),
    first_year=1965,
)
_BEST_NOVELETTE_CONFIG = _NebulaAwardConfig(
    key='best-novelette',
    archive_url=BEST_NOVELETTE_URL,
    award_name=AWARD_NAME_NEBULA,
    category=CATEGORY_BEST_NOVELETTE,
    status_labels=(CATEGORY_BEST_NOVELETTE,),
    first_year=1965,
)
_BEST_SHORT_STORY_CONFIG = _NebulaAwardConfig(
    key='best-short-story',
    archive_url=BEST_SHORT_STORY_URL,
    award_name=AWARD_NAME_NEBULA,
    category=CATEGORY_BEST_SHORT_STORY,
    status_labels=(CATEGORY_BEST_SHORT_STORY,),
    first_year=1965,
    # Official 1970 archive lists a starred "No award" row, not a work.
    no_work_winner_years=frozenset({1970}),
)
_BEST_POEM_CONFIG = _NebulaAwardConfig(
    key='best-poem',
    archive_url=BEST_POEM_URL,
    award_name=AWARD_NAME_NEBULA,
    category=CATEGORY_BEST_POEM,
    status_labels=(CATEGORY_BEST_POEM,),
    first_year=2025,
)
_NORTON_CONFIG = _NebulaAwardConfig(
    key='norton',
    archive_url=NORTON_URL,
    award_name=NORTON_AWARD_NAME,
    category=NORTON_CATEGORY,
    status_labels=(
        'Andre Norton Nebula Award for Middle Grade and Young Adult Fiction',
        'The Andre Norton Award for Middle Grade and Young Adult Fiction',
        'Andre Norton Award for Young Adult Science Fiction and Fantasy',
    ),
    first_year=2005,
    # Some Norton winner lines omit the year.
    winner_year_optional=True,
)
_AWARD_CONFIGS: tuple[_NebulaAwardConfig, ...] = (
    _BEST_NOVEL_CONFIG,
    _BEST_NOVELLA_CONFIG,
    _BEST_NOVELETTE_CONFIG,
    _BEST_SHORT_STORY_CONFIG,
    _BEST_POEM_CONFIG,
    _NORTON_CONFIG,
)


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
        raise NebulaSourceError(
            f'Nebula request failed with HTTP {exc.code} for {url}'
            + (f': {body[:200].strip()}' if body.strip() else '')
        ) from exc
    except urllib.error.URLError as exc:
        raise NebulaSourceError(
            f'Nebula request failed for {url}: {exc.reason}'
        ) from exc

    if status != 200:
        raise NebulaSourceError(
            f'Nebula request failed with HTTP {status} for {url}'
        )
    return html


def _next_page_url(html: str) -> str | None:
    match = _NEXT_LINK_RE.search(html)
    if not match:
        return None
    return match.group(1) or match.group(2)


def _fetch_category_pages(
    opener: urllib.request.OpenerDirector,
    config: _NebulaAwardConfig,
) -> list[tuple[str, str]]:
    """Return list of (page_url, html) following official rel=next links."""
    pages: list[tuple[str, str]] = []
    url: str | None = config.archive_url
    seen: set[str] = set()
    while url and url not in seen:
        seen.add(url)
        html = _fetch_html(opener, url)
        pages.append((url, html))
        nxt = _next_page_url(html)
        url = urljoin(url, nxt) if nxt else None
    if not pages:
        raise NebulaSourceError(
            f'Nebula {config.category} archive returned no pages'
        )
    return pages


_pages_cache: dict[str, tuple[tuple[str, str], ...]] = {}
_records_cache: dict[str, tuple[_ParsedRecord, ...]] = {}
_category_locks: dict[str, threading.Lock] = {}
_category_locks_guard = threading.Lock()
# Intra-source bound: avoid opening every category archive at once.
_MAX_CATEGORY_WORKERS = 2


def _clear_caches_for_tests() -> None:
    """Reset process caches. Tests only; not public plugin API."""
    _pages_cache.clear()
    _records_cache.clear()


def _lock_for_category(key: str) -> threading.Lock:
    with _category_locks_guard:
        lock = _category_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _category_locks[key] = lock
        return lock


def _load_category(
    config: _NebulaAwardConfig,
) -> tuple[tuple[tuple[str, str], ...], tuple[_ParsedRecord, ...]]:
    """Fetch/parse/validate one category; cache pages and records together.

    Per-category locks prevent duplicate simultaneous loads of the same archive.
    Failed retrieval is not written into the success caches.
    """
    lock = _lock_for_category(config.key)
    with lock:
        cached_records = _records_cache.get(config.key)
        cached_pages = _pages_cache.get(config.key)
        if cached_records is not None:
            return cached_pages if cached_pages is not None else (), cached_records
        if cached_pages is not None:
            records_list = _records_from_pages(config, cached_pages)
            _validate_category_archive(config, cached_pages, records_list)
            records = tuple(records_list)
            _records_cache[config.key] = records
            return cached_pages, records
        opener = _build_opener()
        pages = tuple(_fetch_category_pages(opener, config))
        records_list = _records_from_pages(config, pages)
        _validate_category_archive(config, pages, records_list)
        records = tuple(records_list)
        _pages_cache[config.key] = pages
        _records_cache[config.key] = records
        return pages, records


def _get_category_pages(config: _NebulaAwardConfig) -> tuple[tuple[str, str], ...]:
    """Return cached archive pages for one configured award."""
    pages, _records = _load_category(config)
    return pages


def _get_category_records(
    config: _NebulaAwardConfig,
) -> tuple[_ParsedRecord, ...]:
    _pages, records = _load_category(config)
    return records


def _get_best_novel_pages() -> tuple[tuple[str, str], ...]:
    """Return cached Best Novel pages, fetching once per process on success."""
    return _get_category_pages(_BEST_NOVEL_CONFIG)


def _fetch_best_novel_pages(
    opener: urllib.request.OpenerDirector,
) -> list[tuple[str, str]]:
    return _fetch_category_pages(opener, _BEST_NOVEL_CONFIG)


# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------

def _collapse_ws(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def _join_authors(authors: list[str]) -> str:
    cleaned = [_collapse_ws(author) for author in authors if _collapse_ws(author)]
    if not cleaned:
        return ''
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f'{cleaned[0]} and {cleaned[1]}'
    return f'{", ".join(cleaned[:-1])} and {cleaned[-1]}'


def _is_no_award_title(title: str) -> bool:
    return _collapse_ws(title).casefold() in {'no award', 'no awards'}


def _strip_wrapping_quotes(text: str) -> str:
    cleaned = _collapse_ws(text)
    while cleaned and cleaned[0] in _QUOTE_CHARS:
        cleaned = cleaned[1:].lstrip()
        if cleaned and cleaned[-1] in _QUOTE_CHARS:
            cleaned = cleaned[:-1].rstrip()
    if cleaned and cleaned[-1] in _QUOTE_CHARS and cleaned[0] not in _QUOTE_CHARS:
        cleaned = cleaned[:-1].rstrip()
    return _collapse_ws(cleaned)


def _parse_compact_citation(text: str) -> tuple[str, str] | None:
    match = _COMPACT_CITATION_RE.match(_collapse_ws(text))
    if not match:
        return None
    title = _strip_wrapping_quotes(match.group('title') or '')
    author = _collapse_ws(match.group('author') or '')
    if not title or not author:
        return None
    return title, author


def _winner_label_re(label: str, *, year_optional: bool) -> re.Pattern[str]:
    suffix = r'(?:\s+in\s+\d{4})?' if year_optional else r'\s+in\s+\d{4}'
    return re.compile(
        r'Winner,\s*' + re.escape(label) + suffix,
        re.IGNORECASE,
    )


def _nominated_label_re(label: str) -> re.Pattern[str]:
    return re.compile(
        r'Nominated for\b.*?' + re.escape(label),
        re.IGNORECASE | re.DOTALL,
    )


def _category_status(li_text: str, config: _NebulaAwardConfig) -> str | None:
    """Return Winner/Nominated from this award's wording only.

    Star icons are ignored: other awards on the same row may be starred.
    """
    labels = tuple(
        sorted(config.status_labels, key=len, reverse=True)
    )
    for label in labels:
        if _winner_label_re(
            label, year_optional=config.winner_year_optional
        ).search(li_text):
            return 'Winner'
    for label in labels:
        if _nominated_label_re(label).search(li_text):
            return 'Nominated'
    return None


def _best_novel_status(li_text: str) -> str | None:
    """Return Winner/Nominated from Best Novel-specific wording only."""
    return _category_status(li_text, _BEST_NOVEL_CONFIG)


def _extract_title_author(
    em_text: str,
    work_link_text: str,
    authors: list[str],
) -> tuple[str, str] | None:
    author_joined = _join_authors(authors)
    candidates = []
    if em_text:
        candidates.append(em_text)
    stripped_link = _strip_wrapping_quotes(work_link_text)
    if stripped_link and stripped_link not in candidates:
        candidates.append(stripped_link)
    if work_link_text and work_link_text not in candidates:
        candidates.append(work_link_text)

    for candidate in candidates:
        compact = _parse_compact_citation(candidate)
        if compact is not None:
            return compact
        compact = _parse_compact_citation(_strip_wrapping_quotes(candidate))
        if compact is not None:
            return compact

    if em_text and author_joined:
        return _strip_wrapping_quotes(em_text), author_joined
    if stripped_link and author_joined:
        return stripped_link, author_joined

    # Official listings occasionally omit the nominee-author link, e.g.
    # 1990 Best Novella winner "The Hemingway Hoax". Keep the title so
    # fail-closed can see the Winner; a keyed override may fill the author.
    title_only = ''
    if em_text:
        title_only = _strip_wrapping_quotes(em_text)
    elif stripped_link:
        title_only = stripped_link
    if title_only and not _is_no_award_title(title_only):
        return title_only, ''
    return None


class _NebulaCategoryParser(HTMLParser):
    """Parse one configured Nebula/Norton archive page."""

    def __init__(self, config: _NebulaAwardConfig) -> None:
        super().__init__(convert_charrefs=True)
        self.config = config
        self.records: list[_ParsedRecord] = []
        self._year: int | None = None
        self._in_h2 = False
        self._h2_parts: list[str] = []
        self._in_award_list = False
        self._award_list_depth = 0
        self._in_li = False
        self._li_depth = 0
        self._in_em = False
        self._in_author_link = False
        self._in_work_link = False
        self._li_parts: list[str] = []
        self._em_parts: list[str] = []
        self._author_parts: list[str] = []
        self._work_link_parts: list[str] = []
        self._work_href: str | None = None
        self._seen: set[tuple[int, str, str, str, str, str | None]] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {name: (value or '') for name, value in attrs}
        classes = attr.get('class', '').split()

        if tag == 'h2':
            self._in_h2 = True
            self._h2_parts = []
            return

        if tag == 'ul' and 'award_list' in classes:
            self._in_award_list = True
            self._award_list_depth = 1
            return

        if self._in_award_list and tag == 'ul':
            self._award_list_depth += 1

        if self._in_award_list and tag == 'li' and not self._in_li:
            self._in_li = True
            self._li_depth = 1
            self._li_parts = []
            self._em_parts = []
            self._author_parts = []
            self._work_link_parts = []
            self._work_href = None
            self._in_em = False
            self._in_author_link = False
            self._in_work_link = False
            return

        if self._in_li and tag == 'li':
            self._li_depth += 1

        if self._in_li and tag == 'em':
            self._in_em = True

        if self._in_li and tag == 'a':
            href = attr.get('href', '')
            if '/nominated-work/' in href and self._work_href is None:
                self._work_href = urljoin(self.config.archive_url, href)
                self._in_work_link = True
            if '/nominees/' in href:
                self._in_author_link = True
                self._author_parts.append('\0')

    def handle_endtag(self, tag: str) -> None:
        if tag == 'h2' and self._in_h2:
            heading = _collapse_ws(''.join(self._h2_parts))
            if re.fullmatch(r'\d{4}', heading):
                self._year = int(heading)
            self._in_h2 = False
            self._h2_parts = []
            return

        if self._in_li and tag == 'em' and self._in_em:
            self._in_em = False
            return

        if self._in_li and tag == 'a' and self._in_work_link:
            self._in_work_link = False
            return

        if self._in_li and tag == 'a' and self._in_author_link:
            self._in_author_link = False
            return

        if self._in_li and tag == 'li':
            self._li_depth -= 1
            if self._li_depth <= 0:
                self._finish_li()
                self._in_li = False
                self._li_depth = 0
            return

        if self._in_award_list and tag == 'ul':
            self._award_list_depth -= 1
            if self._award_list_depth <= 0:
                self._in_award_list = False
                self._award_list_depth = 0

    def handle_data(self, data: str) -> None:
        if self._in_h2:
            self._h2_parts.append(data)
        if self._in_li:
            self._li_parts.append(data)
            if self._in_em:
                self._em_parts.append(data)
            if self._in_work_link:
                self._work_link_parts.append(data)
            if self._in_author_link:
                self._author_parts.append(data)

    def _finish_li(self) -> None:
        if self._year is None:
            return

        li_text = _collapse_ws(''.join(self._li_parts))
        status = _category_status(li_text, self.config)
        if status is None:
            return

        em_text = _collapse_ws(''.join(self._em_parts))
        work_link_text = _collapse_ws(''.join(self._work_link_parts))
        authors = [
            _collapse_ws(part)
            for part in ''.join(self._author_parts).split('\0')
            if _collapse_ws(part)
        ]
        parsed = _extract_title_author(em_text, work_link_text, authors)
        if parsed is None:
            return
        title, author = parsed
        if not title or _is_no_award_title(title):
            return
        author = _author_with_official_override(
            category=self.config.category,
            award_year=self._year,
            source_url=self._work_href,
            parsed_author=author,
        )

        key = (
            self._year,
            self.config.category,
            status,
            title.casefold(),
            author.casefold(),
            self._work_href,
        )
        if key in self._seen:
            return
        self._seen.add(key)
        self.records.append(
            _ParsedRecord(
                award_year=self._year,
                award_name=self.config.award_name,
                category=self.config.category,
                status=status,
                work_title=title,
                work_author=author,
                source_url=self._work_href,
            )
        )


_NebulaBestNovelParser = _NebulaCategoryParser


def _parse_category_html(
    html: str, config: _NebulaAwardConfig
) -> list[_ParsedRecord]:
    parser = _NebulaCategoryParser(config)
    parser.feed(html)
    parser.close()
    return parser.records


def _parse_best_novel_html(html: str) -> list[_ParsedRecord]:
    return _parse_category_html(html, _BEST_NOVEL_CONFIG)


def _records_from_pages(
    config: _NebulaAwardConfig,
    pages: tuple[tuple[str, str], ...] | list[tuple[str, str]],
) -> list[_ParsedRecord]:
    records: list[_ParsedRecord] = []
    seen: set[tuple[int, str, str, str, str, str | None]] = set()
    for _page_url, html in pages:
        for record in _parse_category_html(html, config):
            key = (
                record.award_year,
                record.category,
                record.status,
                record.work_title.casefold(),
                record.work_author.casefold(),
                record.source_url,
            )
            if key in seen:
                continue
            seen.add(key)
            records.append(record)
    return records


def _displayed_years(
    pages: tuple[tuple[str, str], ...] | list[tuple[str, str]],
) -> set[int]:
    years: set[int] = set()
    for _page_url, html in pages:
        years.update(int(year) for year in _H2_YEAR_RE.findall(html))
    return years


def _validate_category_archive(
    config: _NebulaAwardConfig,
    pages: tuple[tuple[str, str], ...] | list[tuple[str, str]],
    records: list[_ParsedRecord],
) -> None:
    displayed = _displayed_years(pages)
    if not displayed:
        raise NebulaSourceError(
            f'Nebula {config.category} archive had no year headings'
        )
    latest = max(displayed)
    if latest < config.first_year:
        raise NebulaSourceError(
            f'Nebula {config.category} archive latest year {latest} '
            f'is before first year {config.first_year}'
        )
    expected = set(range(config.first_year, latest + 1))
    missing_headings = sorted(expected - displayed)
    if missing_headings:
        extra = (
            f' (+{len(missing_headings) - 1} more)'
            if len(missing_headings) > 1
            else ''
        )
        raise NebulaSourceError(
            'Nebula archive was retrieved but '
            f'{config.category} year heading(s) were missing: '
            f'{missing_headings[0]}{extra}'
        )
    unexpected = sorted(year for year in displayed if year < config.first_year)
    if unexpected:
        raise NebulaSourceError(
            f'Nebula {config.category} archive included unexpected year '
            f'{unexpected[0]}'
        )

    by_year: dict[int, list[_ParsedRecord]] = {year: [] for year in expected}
    for record in records:
        if record.category != config.category:
            raise NebulaSourceError(
                'Nebula archive produced an unexpected category: '
                f'{record.category!r}'
            )
        if record.award_year in by_year:
            by_year[record.award_year].append(record)

    missing_records = [
        year for year, year_records in by_year.items() if not year_records
    ]
    if missing_records:
        extra = (
            f' (+{len(missing_records) - 1} more)'
            if len(missing_records) > 1
            else ''
        )
        raise NebulaSourceError(
            'Nebula archive was retrieved but no '
            f'{config.category} records could be parsed for year '
            f'{missing_records[0]}{extra}'
        )

    missing_winners = [
        year
        for year, year_records in by_year.items()
        if year not in config.no_work_winner_years
        and not any(record.status == 'Winner' for record in year_records)
    ]
    if missing_winners:
        extra = (
            f' (+{len(missing_winners) - 1} more)'
            if len(missing_winners) > 1
            else ''
        )
        raise NebulaSourceError(
            'Nebula archive was retrieved but no '
            f'{config.category} Winner records could be parsed for year '
            f'{missing_winners[0]}{extra}'
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


def _author_with_official_override(
    *,
    category: str,
    award_year: int,
    source_url: str | None,
    parsed_author: str,
) -> str:
    """Fill a known empty author from an exact official-page identity.

    Applied only when the archive row parsed no author. A non-empty
    official author is never replaced.
    """
    if parsed_author or not source_url:
        return parsed_author
    return _MISSING_AUTHOR_OVERRIDES.get(
        (category, award_year, source_url),
        parsed_author,
    )


def _split_calibre_author_query(query_author: str) -> tuple[str, ...]:
    """Invert Calibre authors_to_string: split on ' & ', restore '&&' to '&'."""
    protected = query_author.replace('&&', _CALIBRE_AMP_PLACEHOLDER)
    people: list[str] = []
    for piece in protected.split(' & '):
        restored = piece.replace(_CALIBRE_AMP_PLACEHOLDER, '&').strip()
        if restored:
            people.append(restored)
    return tuple(people)


def _glue_generational_suffixes(parts: list[str]) -> list[str]:
    glued: list[str] = []
    for part in parts:
        piece = part.strip()
        if not piece:
            continue
        if glued and _GENERATIONAL_SUFFIX_RE.fullmatch(piece):
            glued[-1] = f'{glued[-1]}, {piece}'
            continue
        glued.append(piece)
    return glued


def _split_official_author_list(author: str) -> tuple[str, ...] | None:
    """Parse a simple official person list, or None if the string is unsafe.

    Role phrases such as "with" or "edited by" are not guessed into authors.
    A missing author is left empty unless a keyed override supplies it.
    """
    text = _collapse_ws(author)
    if not text:
        return None
    if _UNSAFE_AUTHOR_ROLE_RE.search(text):
        return None
    unified = re.sub(r'\s*,\s*and\s+', ', ', text, flags=re.IGNORECASE)
    unified = re.sub(r'\s+and\s+', ', ', unified, flags=re.IGNORECASE)
    parts = _glue_generational_suffixes(
        [piece.strip() for piece in unified.split(',')]
    )
    if not parts:
        return None
    return tuple(parts)


def _authors_match(query_author: str, record_author: str) -> bool:
    if _normalize_text(query_author) == _normalize_text(record_author):
        return True
    query_people = _split_calibre_author_query(query_author)
    record_people = _split_official_author_list(record_author)
    if not query_people or record_people is None:
        return False
    if len(query_people) != len(record_people):
        return False
    return all(
        _normalize_text(query_person) == _normalize_text(record_person)
        for query_person, record_person in zip(
            query_people, record_people, strict=True
        )
    )


def _record_matches(record: _ParsedRecord, title: str, author: str) -> bool:
    return _titles_match(title, record.work_title) and _authors_match(
        author, record.work_author
    )


def _to_award_result(record: _ParsedRecord) -> AwardResult:
    return AwardResult(
        work_title=record.work_title,
        work_author=record.work_author,
        award_name=record.award_name,
        award_year=record.award_year,
        category=record.category,
        status=record.status,
        rank=None,
        source_name='Nebula Awards',
        source_url=record.source_url,
        notes=None,
    )


# ---------------------------------------------------------------------------
# Public lookup
# ---------------------------------------------------------------------------

def lookup(title: str, author: str, series: str | None = None) -> list[AwardResult]:
    """Look up Nebula written-work and Andre Norton Award results."""
    cleaned_title = title.strip()
    cleaned_author = author.strip()
    if not cleaned_title:
        raise ValueError('title must be a non-empty string')
    if not cleaned_author:
        raise ValueError('author must be a non-empty string')

    matches: list[AwardResult] = []
    seen_results: set[tuple[int, str, str, str, str, str, str | None]] = set()
    loaded: dict[str, tuple[_ParsedRecord, ...] | Exception] = {}
    max_workers = min(_MAX_CATEGORY_WORKERS, len(_AWARD_CONFIGS))
    # Load categories concurrently, then raise any failure so the archive is all-or-nothing.
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_map = {
            pool.submit(_get_category_records, config): config
            for config in _AWARD_CONFIGS
        }
        for future in as_completed(future_map):
            config = future_map[future]
            try:
                loaded[config.key] = future.result()
            except Exception as exc:
                loaded[config.key] = exc
    for config in _AWARD_CONFIGS:
        value = loaded[config.key]
        if isinstance(value, Exception):
            raise value
        for record in value:
            if not record.work_author:
                continue
            if not _record_matches(record, cleaned_title, cleaned_author):
                continue
            key = (
                record.award_year,
                record.award_name,
                record.category,
                record.status,
                record.work_title.casefold(),
                record.work_author.casefold(),
                record.source_url,
            )
            if key in seen_results:
                continue
            seen_results.add(key)
            matches.append(_to_award_result(record))
    return matches
