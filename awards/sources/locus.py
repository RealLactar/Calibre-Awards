"""Science Fiction Awards Database Locus Awards source.

Runtime lookup is a bounded two-stage retrieval:

1. Construct a small set of SFADB author-page slugs from the queried author.
2. Parse the author page's Locus Awards and Poll section as a discovery index.
3. Fetch only the annual Locus_Awards_YYYY page(s) referenced by title-matched
   book-category entries.

Rank is taken only from explicit annual-page ``li value`` attributes.
Qualification is not applied here.
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
from urllib.parse import quote, urljoin, urlparse

from ..matching import normalize_title_conjunctions
from ..model import AwardResult

TIMEOUT_SECONDS = 30
SFADB_ORIGIN = 'https://www.sfadb.com/'
SOURCE_NAME = 'Science Fiction Awards Database'
OFFICIAL_HOSTS = frozenset({'sfadb.com', 'www.sfadb.com'})

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

_INITIALS_SPACE_RE = re.compile(r'\b([A-Za-z])\.\s+')
_YEAR_HREF_RE = re.compile(r'Locus_Awards_(\d{4})/?$', re.IGNORECASE)
_PLACE_RE = re.compile(
    r'(\d+)(?:st|nd|rd|th)\s+place(?:\s*\(\s*tie\s*\))?',
    re.IGNORECASE,
)
_DASH_SPLIT_RE = re.compile(r'[\u2014\u2013\u0097]+')

_SUPPORTED_CATEGORY_LABELS = (
    'Novel',
    'Sf Novel',
    'Fantasy Novel',
    'Horror Novel',
    'First Novel',
    'Young Adult Book',
    'Young Adult Novel',
    'Translated Novel',
)
_SUPPORTED_CATEGORY_KEYS = frozenset(
    label.casefold() for label in _SUPPORTED_CATEGORY_LABELS
)
_DISCOVERY_TO_ANNUAL_CATEGORY = {
    'novel': 'Novel',
    'sf novel': 'Sf Novel',
    'fantasy novel': 'Fantasy Novel',
    'horror novel': 'Horror Novel',
    'horror/dark fantasy novel': 'Horror Novel',
    'dark fantasy/horror novel': 'Horror Novel',
    'first novel': 'First Novel',
    'young adult book': 'Young Adult Book',
    'young adult novel': 'Young Adult Novel',
    'translated novel': 'Translated Novel',
}
_DISCOVERY_SUPPORTED_KEYS = frozenset(_DISCOVERY_TO_ANNUAL_CATEGORY)
_TRANSLATED_BY_RE = re.compile(r'translated\s+by', re.IGNORECASE)
_TRANS_GLITCH_RE = re.compile(r',\s*trans(?:lators?|\d+)\b', re.IGNORECASE)
_RECOGNIZED_UNSUPPORTED_KEYS = frozenset({
    'novella',
    'novelette',
    'short story',
    'short fiction',
    'anthology',
    'collection',
    'anthology/collection',
    'magazine',
    'publisher',
    'publisher/imprint',
    'book publisher',
    'editor',
    'artist',
    'nonfiction',
    'non-fiction',
    'art book',
    'illustrated and art book',
})


class LocusSourceError(RuntimeError):
    """Raised when SFADB Locus pages cannot be retrieved or validated."""


@dataclass(frozen=True, slots=True)
class _DiscoveryEntry:
    award_year: int
    annual_url: str
    work_title: str
    category_text: str
    rank: int | None
    winner: bool


@dataclass(frozen=True, slots=True)
class _AuthorPage:
    page_url: str
    page_name: str
    entries: tuple[_DiscoveryEntry, ...]


@dataclass(frozen=True, slots=True)
class _AnnualRecord:
    award_year: int
    category: str
    work_title: str
    work_author: str
    linked_authors: tuple[str, ...]
    rank: int
    winner: bool
    tied: bool
    source_url: str


_cache_lock = threading.Lock()
_author_page_cache: dict[str, _AuthorPage] = {}
_annual_page_cache: dict[str, tuple[_AnnualRecord, ...]] = {}


def _reset_runtime_state() -> None:
    """Clear in-process caches. Used by tests."""
    with _cache_lock:
        _author_page_cache.clear()
        _annual_page_cache.clear()


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _build_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(CookieJar())
    )


def _read_response_body(response) -> str:
    charset = None
    headers = getattr(response, 'headers', None)
    if headers is not None:
        getter = getattr(headers, 'get_content_charset', None)
        if callable(getter):
            charset = getter()
    return response.read().decode(charset or 'utf-8', errors='replace')


def _request_html(opener: urllib.request.OpenerDirector, url: str) -> tuple[int, str]:
    request = urllib.request.Request(url, headers=dict(_BROWSER_HEADERS))
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            status = getattr(response, 'status', None) or response.getcode()
            body = _read_response_body(response)
            final_url = response.geturl() or url
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return 404, ''
        body = _read_response_body(exc)
        raise LocusSourceError(
            f'Locus request failed with HTTP {exc.code} for {url}'
            + (f': {body[:200].strip()}' if body.strip() else '')
        ) from exc
    except urllib.error.URLError as exc:
        raise LocusSourceError(
            f'Locus request failed for {url}: {exc.reason}'
        ) from exc
    if int(status) not in {200, 404}:
        raise LocusSourceError(
            f'Locus request failed with HTTP {status} for {url}'
        )
    if int(status) == 200 and not _is_sfadb_url(final_url):
        raise LocusSourceError(
            f'Locus request redirected off SFADB: {url} -> {final_url}'
        )
    return int(status), body


def _is_sfadb_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {'http', 'https'}:
        return False
    host = (parsed.hostname or '').casefold().rstrip('.')
    return host in OFFICIAL_HOSTS


def _author_page_url(slug: str) -> str:
    return urljoin(SFADB_ORIGIN, quote(slug, safe='_-'))


def _absolute_sfadb_url(href: str, base: str) -> str | None:
    joined = urljoin(base, href.strip())
    if not _is_sfadb_url(joined):
        return None
    return joined


def _year_from_locus_href(href: str) -> int | None:
    parsed = urlparse(href.strip())
    path = parsed.path.rstrip('/')
    match = _YEAR_HREF_RE.search(path)
    if match is None:
        return None
    return int(match.group(1))


# ---------------------------------------------------------------------------
# Normalization / matching
# ---------------------------------------------------------------------------

def _collapse_ws(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def _ascii_fold(text: str) -> str:
    return ''.join(
        char
        for char in unicodedata.normalize('NFKD', text)
        if not unicodedata.combining(char)
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
        .replace('\u2026', '...')
    )
    text = _collapse_ws(text)
    text = text.casefold()
    text = _INITIALS_SPACE_RE.sub(r'\1.', text)
    return text


def _titles_equivalent(query_title: str, record_title: str) -> bool:
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


def _authors_equivalent(left: str, right: str) -> bool:
    if _normalize_text(left) == _normalize_text(right):
        return True
    return _normalize_text(_ascii_fold(left)) == _normalize_text(_ascii_fold(right))


def _author_matches_record(query_author: str, record: _AnnualRecord) -> bool:
    if _authors_equivalent(query_author, record.work_author):
        return True
    return any(
        _authors_equivalent(query_author, name) for name in record.linked_authors
    )


def _record_matches(record: _AnnualRecord, title: str, author: str) -> bool:
    return _titles_equivalent(title, record.work_title) and _author_matches_record(
        author, record
    )


def _slug_from_author(author: str, *, fold: bool) -> str | None:
    text = unicodedata.normalize('NFKC', author)
    if fold:
        text = _ascii_fold(text)
    text = _collapse_ws(text)
    text = text.replace('.', '')
    text = re.sub(r"['’`´‘]", '', text)
    text = text.replace(',', '')
    text = _collapse_ws(text)
    if not text:
        return None
    slug = re.sub(r'_+', '_', text.replace(' ', '_')).strip('_')
    return slug or None


def _author_slug_candidates(author: str) -> tuple[str, ...]:
    folded = _slug_from_author(author, fold=True)
    raw = _slug_from_author(author, fold=False)
    candidates: list[str] = []
    for slug in (folded, raw):
        if slug and slug not in candidates:
            candidates.append(slug)
    return tuple(candidates)


def _ordinal(rank: int) -> str:
    if 11 <= rank % 100 <= 13:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(rank % 10, 'th')
    return f'{rank}{suffix}'


def _status_for_rank(rank: int, *, winner: bool) -> str:
    if winner:
        return 'Winner'
    return f'{_ordinal(rank)} place'


def _category_kind(heading: str) -> str | None:
    key = heading.casefold()
    if key in _SUPPORTED_CATEGORY_KEYS:
        return 'supported'
    if key in _RECOGNIZED_UNSUPPORTED_KEYS:
        return 'recognized'
    return None


def _annual_category_for_discovery(category_text: str) -> str | None:
    return _DISCOVERY_TO_ANNUAL_CATEGORY.get(category_text.casefold())


def _discovery_category_supported(category_text: str) -> bool:
    return _annual_category_for_discovery(category_text) is not None


def _work_authors_from_links(
    linked: tuple[str, ...], li_text: str
) -> tuple[str, ...]:
    collapsed = _collapse_ws(li_text)
    translated_by = _TRANSLATED_BY_RE.search(collapsed)
    if translated_by is not None:
        before = collapsed[: translated_by.start()]
        return tuple(name for name in linked if name in before)
    if _TRANS_GLITCH_RE.search(collapsed):
        return linked[:1]
    return linked


# ---------------------------------------------------------------------------
# Author-page parsing (discovery only)
# ---------------------------------------------------------------------------

def _parse_discovery_placement(
    text: str, *, winner_markup: bool
) -> tuple[int | None, bool, bool]:
    collapsed = _collapse_ws(text)
    tied = bool(re.search(r'\(\s*tie\s*\)', collapsed, re.IGNORECASE))
    if winner_markup or re.search(r'\bwinner\b', collapsed, re.IGNORECASE):
        return 1, True, tied
    match = _PLACE_RE.search(collapsed)
    if match is None:
        return None, False, tied
    rank = int(match.group(1))
    if rank <= 0:
        return None, False, tied
    return rank, False, tied


def _parse_discovery_category(text: str, title: str) -> str:
    collapsed = _collapse_ws(text)
    remainder = collapsed
    title_collapsed = _collapse_ws(title)
    if title_collapsed and collapsed.casefold().startswith(title_collapsed.casefold()):
        remainder = collapsed[len(title_collapsed):].strip()
    remainder = re.sub(r'^\([^)]*\)\s*', '', remainder)
    remainder = remainder.lstrip(' \t\u2014\u2013\u0097-')
    parts = [
        _collapse_ws(part)
        for part in _DASH_SPLIT_RE.split(remainder)
        if _collapse_ws(part)
    ]
    if parts:
        candidate = parts[0]
        if candidate.casefold() in _DISCOVERY_SUPPORTED_KEYS:
            return candidate
    folded = remainder.casefold()
    for key in sorted(_DISCOVERY_SUPPORTED_KEYS, key=len, reverse=True):
        if re.search(r'(?<![a-z])' + re.escape(key) + r'(?![a-z])', folded):
            return key
    return ''


class _AuthorPageParser(HTMLParser):
    """Parse pagetitle identity and the Locus Awards and Poll discovery list."""

    def __init__(self, page_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.page_url = page_url
        self.page_name = ''
        self.entries: list[_DiscoveryEntry] = []
        self.locus_header_seen = False
        self.year_links_in_section = 0
        self._in_pagetitle = False
        self._pagetitle_parts: list[str] = []
        self._in_header = False
        self._header_parts: list[str] = []
        self._in_locus_section = False
        self._in_date = False
        self._date_href: str | None = None
        self._in_titlemid = False
        self._title_parts: list[str] = []
        self._titlemid_parts: list[str] = []
        self._in_b = False
        self._winner_markup = False
        self._pending_year: int | None = None
        self._pending_annual_url: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {name: (value or '') for name, value in attrs}
        classes = attr.get('class', '').split()
        if tag == 'div' and 'pagetitle' in classes:
            self._in_pagetitle = True
            self._pagetitle_parts = []
        if tag == 'div' and 'awardlistingsectionheader' in classes:
            self._flush_pending()
            self._in_header = True
            self._header_parts = []
        if not self._in_locus_section:
            if tag == 'a' and self._in_date:
                return
            return
        if tag == 'div' and 'dateleftindent' in classes:
            self._flush_pending()
            self._in_date = True
            self._date_href = None
        if tag == 'div' and 'titlemid' in classes:
            self._in_titlemid = True
            self._title_parts = []
            self._titlemid_parts = []
            self._winner_markup = False
        if tag == 'a' and self._in_date and self._date_href is None:
            href = attr.get('href', '').strip()
            if href:
                self._date_href = href
        if tag == 'b' and self._in_titlemid and not self._title_parts:
            self._in_b = True
        if (
            tag == 'span'
            and self._in_titlemid
            and 'win' in classes
        ):
            self._winner_markup = True

    def handle_endtag(self, tag: str) -> None:
        if tag == 'div' and self._in_pagetitle:
            self.page_name = _collapse_ws(''.join(self._pagetitle_parts))
            self._in_pagetitle = False
            self._pagetitle_parts = []
        if tag == 'div' and self._in_header:
            heading = _collapse_ws(''.join(self._header_parts))
            self._in_header = False
            self._header_parts = []
            if 'locus awards and poll' in heading.casefold():
                self.locus_header_seen = True
                self._in_locus_section = True
            elif self._in_locus_section:
                self._flush_pending()
                self._in_locus_section = False
        if tag == 'b' and self._in_b:
            self._in_b = False
        if tag == 'div' and self._in_date:
            self._capture_pending_year()
            self._in_date = False
        if tag == 'div' and self._in_titlemid:
            self._finish_titlemid()
            self._in_titlemid = False

    def handle_data(self, data: str) -> None:
        if self._in_pagetitle:
            self._pagetitle_parts.append(data)
        if self._in_header:
            self._header_parts.append(data)
        if self._in_titlemid:
            self._titlemid_parts.append(data)
            if self._in_b:
                self._title_parts.append(data)

    def _capture_pending_year(self) -> None:
        href = self._date_href
        self._date_href = None
        if not href:
            return
        annual_url = _absolute_sfadb_url(href, self.page_url)
        year = _year_from_locus_href(href)
        if annual_url is None or year is None:
            return
        self.year_links_in_section += 1
        self._pending_year = year
        self._pending_annual_url = annual_url

    def _finish_titlemid(self) -> None:
        title = _collapse_ws(''.join(self._title_parts))
        meta_text = ''.join(self._titlemid_parts)
        winner_markup = self._winner_markup
        year = self._pending_year
        annual_url = self._pending_annual_url
        self._title_parts = []
        self._titlemid_parts = []
        self._winner_markup = False
        self._pending_year = None
        self._pending_annual_url = None
        if not title or year is None or annual_url is None:
            return
        rank, winner, _tied = _parse_discovery_placement(
            meta_text, winner_markup=winner_markup
        )
        category_text = _parse_discovery_category(meta_text, title)
        self.entries.append(
            _DiscoveryEntry(
                award_year=year,
                annual_url=annual_url,
                work_title=title,
                category_text=category_text,
                rank=rank,
                winner=winner,
            )
        )

    def _flush_pending(self) -> None:
        self._pending_year = None
        self._pending_annual_url = None


def _parse_author_page(html: str, page_url: str) -> _AuthorPage:
    parser = _AuthorPageParser(page_url)
    parser.feed(html)
    parser.close()
    if parser.locus_header_seen and parser.year_links_in_section and not parser.entries:
        raise LocusSourceError(
            f'SFADB author page Locus section was malformed: {page_url}'
        )
    return _AuthorPage(
        page_url=page_url,
        page_name=parser.page_name,
        entries=tuple(parser.entries),
    )


def _author_page_matches_query(page: _AuthorPage, author: str) -> bool:
    if not page.page_name:
        return False
    return _authors_equivalent(author, page.page_name)


def _resolve_author_page(
    opener: urllib.request.OpenerDirector,
    author: str,
) -> _AuthorPage | None:
    candidates = _author_slug_candidates(author)
    if not candidates:
        return None
    for slug in candidates:
        with _cache_lock:
            cached = _author_page_cache.get(slug)
        if cached is not None:
            if _author_page_matches_query(cached, author):
                return cached
            continue
        url = _author_page_url(slug)
        status, body = _request_html(opener, url)
        if status == 404:
            continue
        if status != 200 or not body.strip():
            raise LocusSourceError(
                f'Locus author page request failed with HTTP {status} for {url}'
            )
        page = _parse_author_page(body, url)
        if not _author_page_matches_query(page, author):
            continue
        with _cache_lock:
            _author_page_cache[slug] = page
        return page
    return None


# ---------------------------------------------------------------------------
# Annual-page parsing (authoritative ranks)
# ---------------------------------------------------------------------------

class _AnnualPageParser(HTMLParser):
    """Parse SFADB annual Locus categoryblock / ol / li value lists."""

    def __init__(self, award_year: int, source_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.award_year = award_year
        self.source_url = source_url
        self.records: list[_AnnualRecord] = []
        self.supported_rank_error: str | None = None
        self._in_category = False
        self._category_parts: list[str] = []
        self._current_category: str | None = None
        self._current_kind: str | None = None
        self._in_ol = False
        self._ol_depth = 0
        self._in_li = False
        self._li_depth = 0
        self._li_value: str | None = None
        self._li_parts: list[str] = []
        self._title_parts: list[str] = []
        self._in_b = False
        self._captured_title = False
        self._author_parts: list[str] = []
        self._in_author_a = False
        self._linked_authors: list[str] = []
        self._winner_markup = False
        self._after_translated_by = False
        self._supported_li_count = 0
        self._supported_ranked_count = 0
        self._category_ranks: dict[str, list[int]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.supported_rank_error is not None:
            return
        attr = {name: (value or '') for name, value in attrs}
        classes = attr.get('class', '').split()
        if tag == 'div' and 'category' in classes and 'categoryblock' not in classes:
            self._in_category = True
            self._category_parts = []
        if tag == 'ol' and self._current_kind is not None:
            if not self._in_ol:
                self._in_ol = True
                self._ol_depth = 1
            else:
                self._ol_depth += 1
        if tag == 'li' and self._in_ol:
            if self._li_depth == 0:
                self._start_li(attr.get('value'))
            self._li_depth += 1
            return
        if not self._in_li:
            return
        if tag == 'span' and 'winner' in classes:
            self._winner_markup = True
        if tag == 'b' and not self._captured_title:
            self._in_b = True
        if tag == 'a' and not self._in_b and not self._after_translated_by:
            href = attr.get('href', '').strip()
            if href:
                self._in_author_a = True
                self._author_parts = []

    def handle_endtag(self, tag: str) -> None:
        if self.supported_rank_error is not None:
            return
        if tag == 'div' and self._in_category:
            heading = _collapse_ws(''.join(self._category_parts))
            self._in_category = False
            self._category_parts = []
            self._current_category = heading or None
            self._current_kind = (
                _category_kind(heading) if heading else None
            )
        if tag == 'b' and self._in_b:
            self._in_b = False
            title = _collapse_ws(''.join(self._title_parts))
            if title:
                self._captured_title = True
        if tag == 'a' and self._in_author_a:
            name = _collapse_ws(''.join(self._author_parts))
            self._in_author_a = False
            self._author_parts = []
            if name:
                self._linked_authors.append(name)
        if tag == 'li' and self._in_ol and self._li_depth:
            self._li_depth -= 1
            if self._li_depth == 0:
                self._finish_li()
        if tag == 'ol' and self._in_ol:
            self._ol_depth -= 1
            if self._ol_depth <= 0:
                self._finish_supported_list()
                self._in_ol = False
                self._ol_depth = 0
                self._current_category = None
                self._current_kind = None

    def handle_data(self, data: str) -> None:
        if self.supported_rank_error is not None:
            return
        if self._in_category:
            self._category_parts.append(data)
        if self._in_li:
            self._li_parts.append(data)
            if self._in_b:
                self._title_parts.append(data)
            if self._in_author_a:
                self._author_parts.append(data)
            if (
                not self._in_b
                and not self._after_translated_by
                and _TRANSLATED_BY_RE.search(data)
            ):
                self._after_translated_by = True

    def _start_li(self, value: str | None) -> None:
        self._in_li = True
        self._li_value = value
        self._li_parts = []
        self._title_parts = []
        self._captured_title = False
        self._author_parts = []
        self._in_author_a = False
        self._linked_authors = []
        self._winner_markup = False
        self._after_translated_by = False
        self._in_b = False

    def _parse_rank(self, raw: str | None) -> int | None:
        if raw is None:
            return None
        text = raw.strip()
        if not text or not re.fullmatch(r'[0-9]+', text):
            return None
        rank = int(text)
        if rank <= 0:
            return None
        return rank

    def _finish_li(self) -> None:
        in_li = self._in_li
        raw_value = self._li_value
        title = _collapse_ws(''.join(self._title_parts))
        linked = tuple(self._linked_authors)
        winner = self._winner_markup
        li_text = ''.join(self._li_parts)
        kind = self._current_kind
        category = self._current_category
        self._in_li = False
        self._li_value = None
        self._li_parts = []
        self._title_parts = []
        self._captured_title = False
        self._linked_authors = []
        self._winner_markup = False
        if not in_li or kind is None or not category:
            return
        rank = self._parse_rank(raw_value)
        if kind == 'supported':
            self._supported_li_count += 1
            if rank is None:
                self.supported_rank_error = (
                    'SFADB Locus annual page has a supported category '
                    f'item without an explicit positive li value: {self.source_url}'
                )
                return
            self._supported_ranked_count += 1
        linked = _work_authors_from_links(linked, li_text)
        if rank is None or not title or not linked:
            return
        if winner and rank != 1:
            self.supported_rank_error = (
                'SFADB Locus annual page marked Winner on a non-first '
                f'placement: {self.source_url}'
            )
            return
        if rank == 1 and kind == 'supported' and not winner:
            self.supported_rank_error = (
                'SFADB Locus annual page rank 1 is missing Winner markup: '
                f'{self.source_url}'
            )
            return
        tied = bool(re.search(r'\(\s*tie\s*\)', li_text, re.IGNORECASE))
        work_author = ' & '.join(linked)
        record = _AnnualRecord(
            award_year=self.award_year,
            category=category,
            work_title=title,
            work_author=work_author,
            linked_authors=linked,
            rank=rank,
            winner=winner,
            tied=tied,
            source_url=self.source_url,
        )
        self.records.append(record)
        self._category_ranks.setdefault(category, []).append(rank)

    def _finish_supported_list(self) -> None:
        if self._current_kind != 'supported':
            self._supported_li_count = 0
            self._supported_ranked_count = 0
            return
        if self._supported_li_count and not self._supported_ranked_count:
            self.supported_rank_error = (
                'SFADB Locus annual page supported category has no usable '
                f'explicit ranks: {self.source_url}'
            )
        self._supported_li_count = 0
        self._supported_ranked_count = 0

    def mark_shared_value_ties(self) -> None:
        shared = {
            category
            for category, ranks in self._category_ranks.items()
            if len(ranks) != len(set(ranks))
        }
        if not shared:
            return
        tied_records = []
        for record in self.records:
            if record.category in shared:
                counts = self._category_ranks[record.category].count(record.rank)
                if counts > 1:
                    tied_records.append(
                        _AnnualRecord(
                            award_year=record.award_year,
                            category=record.category,
                            work_title=record.work_title,
                            work_author=record.work_author,
                            linked_authors=record.linked_authors,
                            rank=record.rank,
                            winner=record.winner,
                            tied=True,
                            source_url=record.source_url,
                        )
                    )
                    continue
            tied_records.append(record)
        self.records = tied_records


def _parse_annual_page(
    html: str, award_year: int, source_url: str
) -> tuple[_AnnualRecord, ...]:
    parser = _AnnualPageParser(award_year, source_url)
    parser.feed(html)
    parser.close()
    if parser.supported_rank_error:
        raise LocusSourceError(parser.supported_rank_error)
    parser.mark_shared_value_ties()
    supported = [record for record in parser.records if record.category.casefold() in _SUPPORTED_CATEGORY_KEYS]
    if not supported:
        recognized = any(
            record.category.casefold() in _RECOGNIZED_UNSUPPORTED_KEYS
            for record in parser.records
        )
        if not recognized:
            raise LocusSourceError(
                'SFADB Locus annual page did not contain recognizable '
                f'category structure: {source_url}'
            )
    seen: set[tuple[int, str, str, str, int]] = set()
    unique: list[_AnnualRecord] = []
    for record in parser.records:
        if record.category.casefold() not in _SUPPORTED_CATEGORY_KEYS:
            continue
        key = (
            record.award_year,
            record.category,
            record.work_title.casefold(),
            record.work_author.casefold(),
            record.rank,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(record)
    return tuple(unique)


def _get_annual_records(
    opener: urllib.request.OpenerDirector,
    annual_url: str,
) -> tuple[_AnnualRecord, ...]:
    year = _year_from_locus_href(annual_url)
    if year is None or not _is_sfadb_url(annual_url):
        raise LocusSourceError(
            f'SFADB Locus annual URL is not a usable year page: {annual_url}'
        )
    with _cache_lock:
        cached = _annual_page_cache.get(annual_url)
    if cached is not None:
        return cached
    status, body = _request_html(opener, annual_url)
    if status != 200 or not body.strip():
        raise LocusSourceError(
            f'Locus annual page request failed with HTTP {status} for {annual_url}'
        )
    records = _parse_annual_page(body, year, annual_url)
    with _cache_lock:
        _annual_page_cache[annual_url] = records
    return records


def _to_award_result(record: _AnnualRecord) -> AwardResult:
    return AwardResult(
        work_title=record.work_title,
        work_author=record.work_author,
        award_name='Locus Award',
        award_year=record.award_year,
        category=record.category,
        status=_status_for_rank(record.rank, winner=record.winner),
        rank=record.rank,
        source_name=SOURCE_NAME,
        source_url=record.source_url,
        notes='tie' if record.tied else None,
    )


# ---------------------------------------------------------------------------
# Public lookup
# ---------------------------------------------------------------------------

def lookup(title: str, author: str) -> list[AwardResult]:
    """Look up Locus Award book-category results from SFADB."""
    cleaned_title = title.strip()
    cleaned_author = author.strip()
    if not cleaned_title:
        raise ValueError('title must be a non-empty string')
    if not cleaned_author:
        raise ValueError('author must be a non-empty string')

    opener = _build_opener()
    page = _resolve_author_page(opener, cleaned_author)
    if page is None:
        return []

    discoveries = [
        entry
        for entry in page.entries
        if _titles_equivalent(cleaned_title, entry.work_title)
        and _discovery_category_supported(entry.category_text)
    ]
    if not discoveries:
        return []

    matches: list[AwardResult] = []
    seen: set[tuple[int, str, str, str, int, str]] = set()
    fetched_urls: set[str] = set()
    for entry in discoveries:
        if entry.annual_url not in fetched_urls:
            records = _get_annual_records(opener, entry.annual_url)
            fetched_urls.add(entry.annual_url)
        else:
            records = _get_annual_records(opener, entry.annual_url)
        expected_category = _annual_category_for_discovery(entry.category_text)
        if expected_category is None:
            continue
        found = [
            record
            for record in records
            if record.category == expected_category
            and _record_matches(record, cleaned_title, cleaned_author)
        ]
        if not found:
            raise LocusSourceError(
                'SFADB author-page Locus entry was not present on the '
                f'annual results page: {entry.annual_url}'
            )
        for record in found:
            if entry.rank is not None and record.rank != entry.rank:
                raise LocusSourceError(
                    'SFADB author-page Locus placement disagreed with the '
                    f'annual page: discovery={entry.rank} annual={record.rank} '
                    f'url={entry.annual_url}'
                )
            if entry.winner and not record.winner:
                raise LocusSourceError(
                    'SFADB author-page Locus winner disagreed with the '
                    f'annual page: {entry.annual_url}'
                )
            key = (
                record.award_year,
                record.category,
                record.work_title.casefold(),
                record.work_author.casefold(),
                record.rank,
                record.source_url,
            )
            if key in seen:
                continue
            seen.add(key)
            matches.append(_to_award_result(record))
    matches.sort(
        key=lambda result: (
            result.award_year or 0,
            result.category or '',
            result.rank or 0,
            result.work_title.casefold(),
        )
    )
    return matches
