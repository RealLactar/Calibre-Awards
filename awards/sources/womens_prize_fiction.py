"""Official Women's Prize for Fiction winners and shortlists.

Phase 1 Winner pipeline: two HTTP GETs (previous-prizes cards plus the
current prize page). Phase 2 adds official Shortlisted records for
2017-present from first-party announcement pages, cached per year.
Longlist is ignored. Historical Orange Prize years use the current
award name.
"""

from __future__ import annotations

import json
import re
import threading
import unicodedata
import urllib.error
import urllib.parse
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
SHORTLIST_CACHE_VERSION = 1
SHORTLIST_ENTRY_KIND = 'shortlists'
SHORTLIST_MIN_YEAR = 2017
SHORTLIST_SIZE = 6
MAX_VERIFIED_SHORTLIST_YEAR = 2026
POST_SITEMAP_URL = SITE_ORIGIN + '/post-sitemap.xml'
REST_POSTS_SEARCH_URL = SITE_ORIGIN + '/wp-json/wp/v2/posts'
HISTORICAL_SHORTLIST_CACHE_TTL_SECONDS = 180 * 24 * 60 * 60
CURRENT_SHORTLIST_CACHE_BASE_TTL_SECONDS = 7 * 24 * 60 * 60
CURRENT_SHORTLIST_CACHE_REFRESH_OFFSET_SECONDS = 11 * 60 * 60
CURRENT_SHORTLIST_CACHE_TTL_SECONDS = (
    CURRENT_SHORTLIST_CACHE_BASE_TTL_SECONDS
    + CURRENT_SHORTLIST_CACHE_REFRESH_OFFSET_SECONDS
)
VERIFIED_SHORTLIST_URLS = {
    2017: SITE_ORIGIN + '/revealing-the-2017-shortlist/',
    2018: SITE_ORIGIN + '/revealing-the-2018-womens-prize-shortlist/',
    2019: SITE_ORIGIN + '/revealing-the-2019-womens-prize-for-fiction-shortlist/',
    2020: SITE_ORIGIN + '/announcing-the-2020-womens-prize-for-fiction-shortlist/',
    2021: SITE_ORIGIN + '/announcing-the-2021-womens-prize-shortlist/',
    2022: SITE_ORIGIN + '/announcing-the-2022-womens-prize-shortlist/',
    2023: SITE_ORIGIN + '/announcing-the-2023-womens-prize-shortlist/',
    2024: SITE_ORIGIN + '/announcing-the-2024-womens-prize-for-fiction-shortlist/',
    2025: SITE_ORIGIN + '/announcing-the-2025-womens-prize-for-fiction-shortlist/',
    2026: SITE_ORIGIN + '/revealing-the-2026-womens-prize-for-fiction-shortlist/',
}

_OFFICIAL_HTML_HOSTS = frozenset({
    'womensprize.com',
    'www.womensprize.com',
})
_LIBRARY_SLUG_RE = re.compile(r'^[0-9A-Za-z][0-9A-Za-z_-]*$')
_INITIALS_SPACE_RE = re.compile(r'\b([A-Za-z])\.\s+')
_APOSTROPHE_FOLLOWING_SPACE_RE = re.compile(r"'\s+")
_TITLE_BY_AUTHOR_RE = re.compile(
    r'^(?P<title>.+?)\s+by\s+(?P<author>.+)$',
    re.IGNORECASE,
)
_AUTHOR_BY_RE = re.compile(
    r'^by\s+(?P<author>.+)$',
    re.IGNORECASE,
)
_SITEMAP_LOC_RE = re.compile(r'<loc>\s*([^<]+?)\s*</loc>', re.IGNORECASE)
_DISCOVERY_REJECT_RE = re.compile(
    r'non-fiction|nonfiction|discoveries',
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
_SHORTLIST_STATES = frozenset({'absent', 'shortlist'})
_SHORTLIST_COVERAGE_FIELDS = frozenset({'award_year', 'state'})
_WORK_PATH_ROOTS = frozenset({'books', 'library'})
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


@dataclass(frozen=True, slots=True)
class _ShortlistLine:
    text: str
    link_title: str
    link_href: str | None


@dataclass(frozen=True, slots=True)
class _FeatureCard:
    title: str
    author_line: str
    href: str | None


@dataclass(frozen=True, slots=True)
class _ShortlistPage:
    heading: str
    main_text: str
    lines: tuple[_ShortlistLine, ...]
    cards: tuple[_FeatureCard, ...]


@dataclass(frozen=True, slots=True)
class _ShortlistYearSnapshot:
    award_year: int
    state: str
    source_url: str
    records: tuple[_ParsedRecord, ...]


_PARSED_STATUSES = frozenset({'Winner'})
_SHORTLIST_RECORD_STATUSES = frozenset({'Shortlisted'})
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
_shortlist_year_cache: dict[int, tuple[_ParsedRecord, ...]] = {}
_cache_lock = threading.Lock()


def _reset_runtime_state() -> None:
    """Clear in-process caches. Used by tests. Does not delete disk cache."""
    global _archive_records_cache, _shortlist_year_cache
    with _cache_lock:
        _archive_records_cache = None
        _shortlist_year_cache = {}


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


def _official_page_url(href: str | None) -> str | None:
    """Return a usable official womensprize.com page URL, or None."""
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
    if not parts:
        return None
    return f'{SITE_ORIGIN}/{"/".join(parts)}/'


def _official_work_url(href: str | None) -> str | None:
    """Return an official /books/ or /library/ work URL, preserving the path."""
    page = _official_page_url(href)
    if page is None:
        return None
    parsed = urlparse(page)
    parts = [piece for piece in parsed.path.split('/') if piece]
    if len(parts) != 2 or parts[0].casefold() not in _WORK_PATH_ROOTS:
        return None
    slug = parts[1]
    if not _LIBRARY_SLUG_RE.fullmatch(slug):
        return None
    root = parts[0].casefold()
    return f'{SITE_ORIGIN}/{root}/{slug}/'


def _shortlist_source_url_is_usable(source_url: str) -> bool:
    if _official_work_url(source_url) == source_url:
        return True
    reconstructed = _official_page_url(source_url)
    return reconstructed is not None and reconstructed == source_url


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


class _ShortlistArticleParser(HTMLParser):
    """Collect article heading, main-content lines, and feature-book cards."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.heading = ''
        self.main_parts: list[str] = []
        self.lines: list[_ShortlistLine] = []
        self.cards: list[_FeatureCard] = []
        self._ignore_depth = 0
        self._main_depth = 0
        self._wysiwyg_depth = 0
        self._card_depth = 0
        self._in_heading = False
        self._heading_parts: list[str] = []
        self._skip_rest = False
        self._skip_book_card = 0
        self._in_p = 0
        self._in_li = 0
        self._line_parts: list[str] = []
        self._line_link_title = ''
        self._line_link_href: str | None = None
        self._in_work_link = 0
        self._link_parts: list[str] = []
        self._card_title_parts: list[str] = []
        self._card_author_parts: list[str] = []
        self._card_href: str | None = None
        self._capture_card: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {name: (value or '') for name, value in attrs}
        classes = _class_tokens(attr.get('class', ''))
        if tag in _IGNORE_TAGS:
            self._ignore_depth += 1
            return
        if self._ignore_depth:
            return
        if tag == 'h1' and (
            'entry-title' in classes or 'product_title' in classes
        ):
            self._in_heading = True
            self._heading_parts = []
        if tag == 'div' and 'main-content' in classes and not self._main_depth:
            self._main_depth = 1
            return
        if tag == 'div' and self._main_depth:
            self._main_depth += 1
        if not self._main_depth or self._skip_rest:
            return
        if tag == 'nav' and 'post-navigation' in classes:
            self._skip_rest = True
            self._flush_line()
            return
        if tag == 'a' and 'book_card' in classes:
            self._skip_book_card += 1
            return
        if self._skip_book_card:
            return
        if tag == 'section' and 'wysiwyg-layout' in classes:
            self._wysiwyg_depth += 1
        if tag == 'div' and 'feature-book-card' in classes:
            self._flush_line()
            self._card_depth = 1
            self._card_title_parts = []
            self._card_author_parts = []
            self._card_href = None
            self._capture_card = None
            return
        if self._card_depth:
            if tag == 'div':
                self._card_depth += 1
            if tag == 'h2':
                self._capture_card = 'title'
                self._card_title_parts = []
            elif tag == 'p' and not self._card_author_parts:
                self._capture_card = 'author'
                self._card_author_parts = []
            elif tag == 'a' and 'explore-link' in classes:
                work = _official_work_url(attr.get('href'))
                if work is not None:
                    self._card_href = work
            return
        if not self._wysiwyg_depth:
            return
        if tag in {'p', 'li'}:
            if tag == 'p':
                self._in_p += 1
            else:
                self._in_li += 1
            self._start_line()
            return
        if tag == 'br' and (self._in_p or self._in_li):
            self._flush_line()
            self._start_line()
            return
        if tag == 'a' and (self._in_p or self._in_li):
            work = _official_work_url(attr.get('href'))
            if work is not None:
                self._in_work_link += 1
                self._link_parts = []
                self._line_link_href = work

    def handle_endtag(self, tag: str) -> None:
        if tag in _IGNORE_TAGS:
            if self._ignore_depth:
                self._ignore_depth -= 1
            return
        if self._ignore_depth:
            return
        if tag == 'h1' and self._in_heading:
            self.heading = _collapse_ws(''.join(self._heading_parts))
            self._in_heading = False
            self._heading_parts = []
        if tag == 'a' and self._skip_book_card:
            self._skip_book_card -= 1
            return
        if self._skip_book_card:
            if tag == 'div' and self._main_depth:
                self._main_depth -= 1
            return
        if self._card_depth:
            if tag in {'h2', 'p'} and self._capture_card:
                self._capture_card = None
            if tag == 'div':
                self._card_depth -= 1
                if self._card_depth == 0:
                    self._finish_card()
                if self._main_depth:
                    self._main_depth -= 1
                    if not self._main_depth:
                        self._skip_rest = True
            return
        if tag == 'a' and self._in_work_link:
            self._line_link_title = _collapse_ws(''.join(self._link_parts))
            self._in_work_link -= 1
            self._link_parts = []
        if tag == 'p' and self._in_p:
            self._flush_line()
            self._in_p -= 1
        elif tag == 'li' and self._in_li:
            self._flush_line()
            self._in_li -= 1
        if tag == 'section' and self._wysiwyg_depth:
            self._flush_line()
            self._wysiwyg_depth -= 1
        if tag == 'div' and self._main_depth:
            self._main_depth -= 1
            if not self._main_depth:
                self._flush_line()
                self._skip_rest = True

    def handle_data(self, data: str) -> None:
        if self._ignore_depth:
            return
        if self._in_heading:
            self._heading_parts.append(data)
        if not self._main_depth or self._skip_rest or self._skip_book_card:
            return
        if self._card_depth and self._capture_card == 'title':
            self._card_title_parts.append(data)
            return
        if self._card_depth and self._capture_card == 'author':
            self._card_author_parts.append(data)
            return
        if self._in_work_link:
            self._link_parts.append(data)
        if self._in_p or self._in_li:
            self._line_parts.append(data)
        self.main_parts.append(data)

    def _start_line(self) -> None:
        self._line_parts = []
        self._line_link_title = ''
        self._line_link_href = None
        self._link_parts = []

    def _flush_line(self) -> None:
        text = _collapse_ws(''.join(self._line_parts))
        title = _collapse_ws(self._line_link_title)
        href = self._line_link_href
        self._line_parts = []
        self._line_link_title = ''
        self._line_link_href = None
        self._link_parts = []
        if not text and not title:
            return
        self.lines.append(
            _ShortlistLine(text=text, link_title=title, link_href=href)
        )

    def _finish_card(self) -> None:
        title = _collapse_ws(''.join(self._card_title_parts))
        author_line = _collapse_ws(''.join(self._card_author_parts))
        href = self._card_href
        self._card_title_parts = []
        self._card_author_parts = []
        self._card_href = None
        self._capture_card = None
        if not title:
            return
        self.cards.append(
            _FeatureCard(title=title, author_line=author_line, href=href)
        )


def _parse_shortlist_page(html: str) -> _ShortlistPage:
    parser = _ShortlistArticleParser()
    parser.feed(html)
    parser.close()
    return _ShortlistPage(
        heading=parser.heading,
        main_text=_collapse_ws(''.join(parser.main_parts)),
        lines=tuple(parser.lines),
        cards=tuple(parser.cards),
    )


def _discovery_url_is_rejected(url: str) -> bool:
    return _DISCOVERY_REJECT_RE.search(url) is not None


def _require_shortlist_fiction_identity(
    page: _ShortlistPage,
    page_url: str,
) -> None:
    if _discovery_url_is_rejected(page_url):
        raise WomensPrizeFictionSourceError(
            "Women's Prize shortlist page is not the Fiction prize"
        )
    heading = _identity_text(page.heading)
    if 'discoveries' in heading or 'non-fiction' in heading or 'nonfiction' in heading:
        raise WomensPrizeFictionSourceError(
            "Women's Prize shortlist page is not the Fiction prize"
        )
    blob = _identity_text(f'{page.heading} {page.main_text}')
    if (
        "women's prize for fiction" in blob
        or "baileys women's prize for fiction" in blob
    ):
        return
    raise WomensPrizeFictionSourceError(
        "Women's Prize shortlist page did not match the official fiction prize"
    )


def _strip_author_tail(author: str) -> str:
    author = re.split(r',\s*published\b', author, maxsplit=1, flags=re.I)[0]
    author = re.split(r'\s*\(', author, maxsplit=1)[0]
    return _collapse_ws(author)


def _pair_from_title_by_author_line(
    line: _ShortlistLine,
    *,
    allow_missing_by: bool = False,
    article_url: str,
) -> tuple[str, str, str] | None:
    title = _collapse_ws(line.link_title) or ''
    text = _collapse_ws(line.text)
    href = line.link_href
    source_url = href if href is not None else article_url
    by_match = _TITLE_BY_AUTHOR_RE.fullmatch(text)
    if by_match is not None:
        parsed_title = _collapse_ws(by_match.group('title'))
        author = _strip_author_tail(by_match.group('author'))
        if not title:
            title = parsed_title
        if title and author:
            return title, author, source_url
    if title:
        remainder = text
        if remainder.casefold().startswith(title.casefold()):
            remainder = remainder[len(title):].strip()
        by_author = _AUTHOR_BY_RE.fullmatch(remainder)
        if by_author is not None:
            author = _strip_author_tail(by_author.group('author'))
            if author:
                return title, author, source_url
        if allow_missing_by:
            author = _strip_author_tail(remainder)
            if author:
                return title, author, source_url
    return None


def _pair_from_author_comma_title_line(
    line: _ShortlistLine,
    article_url: str,
) -> tuple[str, str, str] | None:
    title = _collapse_ws(line.link_title)
    if not title:
        return None
    text = _collapse_ws(line.text)
    prefix = text
    idx = text.casefold().rfind(title.casefold())
    if idx >= 0:
        prefix = text[:idx]
    author = _collapse_ws(prefix).rstrip(',').strip()
    if not author:
        return None
    href = line.link_href if line.link_href is not None else article_url
    return title, author, href


def _pairs_from_feature_cards(
    cards: tuple[_FeatureCard, ...],
    article_url: str,
) -> list[tuple[str, str, str]]:
    pairs: list[tuple[str, str, str]] = []
    for card in cards:
        title = _collapse_ws(card.title)
        author_match = _AUTHOR_BY_RE.fullmatch(_collapse_ws(card.author_line))
        if not title or author_match is None:
            continue
        author = _strip_author_tail(author_match.group('author'))
        if not author:
            continue
        href = card.href if card.href is not None else article_url
        pairs.append((title, author, href))
    return pairs


def _pairs_from_title_by_author_lines(
    lines: tuple[_ShortlistLine, ...],
    article_url: str,
    *,
    allow_missing_by: bool = False,
) -> list[tuple[str, str, str]]:
    pairs: list[tuple[str, str, str]] = []
    for line in lines:
        if line.link_href is None:
            continue
        if '16 books' in line.text.casefold():
            continue
        pair = _pair_from_title_by_author_line(
            line,
            allow_missing_by=allow_missing_by,
            article_url=article_url,
        )
        if pair is not None:
            pairs.append(pair)
    return pairs


def _extract_shortlist_pairs(
    page: _ShortlistPage,
    award_year: int,
    article_url: str,
) -> list[tuple[str, str, str]]:
    if award_year == 2018:
        pairs = []
        for line in page.lines:
            pair = _pair_from_author_comma_title_line(line, article_url)
            if pair is not None:
                pairs.append(pair)
        return pairs
    if award_year == 2021:
        return _pairs_from_feature_cards(page.cards, article_url)
    if award_year == 2017:
        return _pairs_from_title_by_author_lines(
            page.lines,
            article_url,
            allow_missing_by=True,
        )
    if 2024 <= award_year <= MAX_VERIFIED_SHORTLIST_YEAR:
        return _pairs_from_title_by_author_lines(page.lines, article_url)
    if award_year in VERIFIED_SHORTLIST_URLS:
        return _pairs_from_title_by_author_lines(page.lines, article_url)
    cards = _pairs_from_feature_cards(page.cards, article_url)
    if len(cards) == SHORTLIST_SIZE:
        return cards
    listed = _pairs_from_title_by_author_lines(page.lines, article_url)
    if len(listed) == SHORTLIST_SIZE:
        return listed
    author_comma = []
    for line in page.lines:
        pair = _pair_from_author_comma_title_line(line, article_url)
        if pair is not None:
            author_comma.append(pair)
    if len(author_comma) == SHORTLIST_SIZE:
        return author_comma
    if len(listed) > len(cards) and len(listed) > len(author_comma):
        return listed
    if len(cards) >= len(author_comma):
        return cards
    return author_comma


def _records_from_shortlist_pairs(
    award_year: int,
    pairs: list[tuple[str, str, str]],
    article_url: str,
) -> tuple[_ParsedRecord, ...]:
    if len(pairs) != SHORTLIST_SIZE:
        raise WomensPrizeFictionSourceError(
            f"Women's Prize {award_year} shortlist did not contain exactly "
            f'{SHORTLIST_SIZE} works'
        )
    records: list[_ParsedRecord] = []
    seen: set[tuple[int, str, str]] = set()
    for title, author, href in pairs:
        if not title or not author:
            raise WomensPrizeFictionSourceError(
                f"Women's Prize {award_year} shortlist entry was incomplete"
            )
        source_url = href if href else article_url
        if not _shortlist_source_url_is_usable(source_url):
            raise WomensPrizeFictionSourceError(
                f"Women's Prize {award_year} shortlist produced an unexpected "
                f'source URL: {source_url!r}'
            )
        record = _ParsedRecord(
            award_year=award_year,
            category=CATEGORY,
            status='Shortlisted',
            work_title=title,
            work_author=author,
            source_url=source_url,
        )
        key = _identity_key(record)
        if key in seen:
            raise WomensPrizeFictionSourceError(
                f"Women's Prize {award_year} shortlist contained duplicate works"
            )
        seen.add(key)
        records.append(record)
    return tuple(records)


def _parse_shortlist_article(
    html: str,
    award_year: int,
    article_url: str,
) -> tuple[_ParsedRecord, ...]:
    page = _parse_shortlist_page(html)
    _require_shortlist_fiction_identity(page, article_url)
    pairs = _extract_shortlist_pairs(page, award_year, article_url)
    return _records_from_shortlist_pairs(award_year, pairs, article_url)


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
        normalize_title_conjunctions(_normalize_text(record.work_title)),
        _normalize_author_for_compare(record.work_author),
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


def _year_entry_key(year: int) -> str:
    return str(year)


def _shortlist_years_to_load() -> tuple[int, ...]:
    current_year = _current_calendar_year()
    if current_year < SHORTLIST_MIN_YEAR:
        return ()
    return tuple(range(SHORTLIST_MIN_YEAR, current_year + 1))


def _year_has_winner(
    award_year: int,
    winner_years: frozenset[int],
) -> bool:
    return award_year in winner_years


def _shortlist_ttl_seconds(
    award_year: int,
    winner_years: frozenset[int],
) -> int:
    if _year_has_winner(award_year, winner_years):
        return HISTORICAL_SHORTLIST_CACHE_TTL_SECONDS
    return CURRENT_SHORTLIST_CACHE_TTL_SECONDS


def _shortlist_coverage(award_year: int, state: str) -> dict:
    return {'award_year': award_year, 'state': state}


def _shortlist_record_from_cache_dict(data) -> _ParsedRecord | None:
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
    if status not in _SHORTLIST_RECORD_STATUSES:
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
    if not _shortlist_source_url_is_usable(source_url):
        return None
    return _ParsedRecord(
        award_year=award_year,
        category=category,
        status=status,
        work_title=work_title,
        work_author=work_author,
        source_url=source_url,
    )


def _shortlist_snapshot_from_payload(
    payload: dict,
    award_year: int,
    *,
    completed: bool,
) -> _ShortlistYearSnapshot | None:
    coverage = payload.get('coverage')
    if not isinstance(coverage, dict) or set(coverage) != _SHORTLIST_COVERAGE_FIELDS:
        return None
    stored_year = coverage.get('award_year')
    state = coverage.get('state')
    if stored_year != award_year:
        return None
    if state not in _SHORTLIST_STATES:
        return None
    raw_records = payload.get('records')
    if not isinstance(raw_records, list):
        return None
    source_urls = payload.get('source_urls')
    if not isinstance(source_urls, list):
        return None
    if state == 'absent':
        if completed:
            return None
        if raw_records:
            return None
        return _ShortlistYearSnapshot(
            award_year=award_year,
            state='absent',
            source_url='',
            records=(),
        )
    if len(raw_records) != SHORTLIST_SIZE:
        return None
    if len(source_urls) != 1 or not isinstance(source_urls[0], str):
        return None
    article_url = source_urls[0]
    if not _shortlist_source_url_is_usable(article_url):
        return None
    records: list[_ParsedRecord] = []
    seen: set[tuple[int, str, str]] = set()
    for item in raw_records:
        record = _shortlist_record_from_cache_dict(item)
        if record is None or record.award_year != award_year:
            return None
        key = _identity_key(record)
        if key in seen:
            return None
        seen.add(key)
        records.append(record)
    restored = tuple(records)
    try:
        _records_from_shortlist_pairs(
            award_year,
            [
                (record.work_title, record.work_author, record.source_url)
                for record in restored
            ],
            article_url,
        )
    except WomensPrizeFictionSourceError:
        return None
    return _ShortlistYearSnapshot(
        award_year=award_year,
        state='shortlist',
        source_url=article_url,
        records=restored,
    )


def _load_persistent_shortlist_year(
    award_year: int,
    *,
    completed: bool,
) -> tuple[_ShortlistYearSnapshot, dict] | None:
    payload = cache.load_cache_entry(
        SOURCE_KEY,
        SHORTLIST_ENTRY_KIND,
        _year_entry_key(award_year),
        SHORTLIST_CACHE_VERSION,
    )
    if payload is None:
        return None
    snapshot = _shortlist_snapshot_from_payload(
        payload,
        award_year,
        completed=completed,
    )
    if snapshot is None:
        return None
    return snapshot, payload


def _save_persistent_shortlist_year(
    snapshot: _ShortlistYearSnapshot,
    winner_years: frozenset[int],
) -> None:
    source_urls = [snapshot.source_url] if snapshot.source_url else []
    try:
        cache.save_cache_entry(
            SOURCE_KEY,
            SHORTLIST_ENTRY_KIND,
            _year_entry_key(snapshot.award_year),
            SHORTLIST_CACHE_VERSION,
            records=[_record_to_cache_dict(record) for record in snapshot.records],
            source_urls=source_urls,
            coverage=_shortlist_coverage(snapshot.award_year, snapshot.state),
            ttl_seconds=_shortlist_ttl_seconds(snapshot.award_year, winner_years),
        )
    except OSError:
        pass


def _store_shortlist_year(
    award_year: int,
    records: tuple[_ParsedRecord, ...],
) -> None:
    with _cache_lock:
        _shortlist_year_cache[award_year] = records


def _ram_shortlist_year(
    award_year: int,
    *,
    completed: bool,
) -> tuple[_ParsedRecord, ...] | None:
    with _cache_lock:
        if award_year not in _shortlist_year_cache:
            return None
        records = _shortlist_year_cache[award_year]
    if completed and not records:
        return None
    return records


def _candidate_discovery_url(url: str, award_year: int) -> str | None:
    official = _official_page_url(url)
    if official is None:
        return None
    lowered = official.casefold()
    if str(award_year) not in official:
        return None
    if 'shortlist' not in lowered:
        return None
    if _discovery_url_is_rejected(official):
        return None
    return official


def _sitemap_shortlist_candidates(award_year: int, xml: str) -> tuple[str, ...]:
    found: list[str] = []
    seen: set[str] = set()
    for loc in _SITEMAP_LOC_RE.findall(xml):
        candidate = _candidate_discovery_url(loc.strip(), award_year)
        if candidate is None or candidate in seen:
            continue
        seen.add(candidate)
        found.append(candidate)
    return tuple(found)


def _rest_shortlist_candidates(award_year: int, payload) -> tuple[str, ...]:
    if not isinstance(payload, list):
        return ()
    found: list[str] = []
    seen: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        link = item.get('link')
        if not isinstance(link, str):
            continue
        candidate = _candidate_discovery_url(link, award_year)
        if candidate is None or candidate in seen:
            continue
        seen.add(candidate)
        found.append(candidate)
    return tuple(found)


def _discover_future_shortlist_url(award_year: int) -> str | None:
    sitemap = _fetch_html(POST_SITEMAP_URL)
    sitemap_hits = _sitemap_shortlist_candidates(award_year, sitemap)
    if len(sitemap_hits) > 1:
        raise WomensPrizeFictionSourceError(
            f"Women's Prize {award_year} shortlist discovery was ambiguous"
        )
    if len(sitemap_hits) == 1:
        return sitemap_hits[0]
    query = urllib.parse.urlencode(
        {
            'search': f"{award_year} Women's Prize for Fiction shortlist",
            'per_page': '20',
            '_fields': 'link,slug,title',
        }
    )
    rest_body = _fetch_html(f'{REST_POSTS_SEARCH_URL}?{query}')
    try:
        payload = json.loads(rest_body)
    except json.JSONDecodeError as exc:
        raise WomensPrizeFictionSourceError(
            f"Women's Prize {award_year} shortlist REST discovery was unreadable"
        ) from exc
    rest_hits = _rest_shortlist_candidates(award_year, payload)
    if len(rest_hits) > 1:
        raise WomensPrizeFictionSourceError(
            f"Women's Prize {award_year} shortlist discovery was ambiguous"
        )
    if len(rest_hits) == 1:
        return rest_hits[0]
    return None


def _resolve_shortlist_article_url(award_year: int) -> str | None:
    mapped = VERIFIED_SHORTLIST_URLS.get(award_year)
    if mapped is not None:
        return mapped
    if award_year <= MAX_VERIFIED_SHORTLIST_YEAR:
        return None
    return _discover_future_shortlist_url(award_year)


def _acquire_live_shortlist_year(
    award_year: int,
) -> _ShortlistYearSnapshot:
    article_url = _resolve_shortlist_article_url(award_year)
    if article_url is None:
        return _ShortlistYearSnapshot(
            award_year=award_year,
            state='absent',
            source_url='',
            records=(),
        )
    html = _fetch_html(article_url)
    records = _parse_shortlist_article(html, award_year, article_url)
    return _ShortlistYearSnapshot(
        award_year=award_year,
        state='shortlist',
        source_url=article_url,
        records=records,
    )


def _acquire_required_shortlist_year(
    award_year: int,
    winner_years: frozenset[int],
) -> tuple[_ParsedRecord, ...]:
    completed = _year_has_winner(award_year, winner_years)
    snapshot = _acquire_live_shortlist_year(award_year)
    if snapshot.state == 'absent' and completed:
        raise WomensPrizeFictionSourceError(
            f"Women's Prize {award_year} shortlist was not available"
        )
    if snapshot.state == 'absent' and award_year < _current_calendar_year():
        raise WomensPrizeFictionSourceError(
            f"Women's Prize {award_year} shortlist was not available"
        )
    _save_persistent_shortlist_year(snapshot, winner_years)
    return snapshot.records


def _get_one_shortlist_year(
    award_year: int,
    winner_years: frozenset[int],
) -> tuple[_ParsedRecord, ...]:
    completed = _year_has_winner(award_year, winner_years)
    ram = _ram_shortlist_year(award_year, completed=completed)
    if ram is not None:
        return ram
    loaded = _load_persistent_shortlist_year(award_year, completed=completed)
    if loaded is not None:
        snapshot, payload = loaded
        if cache.cache_is_fresh(payload) or not cache.try_claim_stale_refresh():
            _store_shortlist_year(award_year, snapshot.records)
            return snapshot.records
        try:
            live = _acquire_live_shortlist_year(award_year)
            if live.state == 'absent' and completed:
                raise WomensPrizeFictionSourceError(
                    f"Women's Prize {award_year} shortlist was not available"
                )
            _save_persistent_shortlist_year(live, winner_years)
            _store_shortlist_year(award_year, live.records)
            return live.records
        except Exception:
            _store_shortlist_year(award_year, snapshot.records)
            return snapshot.records
    records = _acquire_required_shortlist_year(award_year, winner_years)
    _store_shortlist_year(award_year, records)
    return records


def _get_shortlisted_records(
    winner_records: tuple[_ParsedRecord, ...],
) -> tuple[_ParsedRecord, ...]:
    winner_years = frozenset(
        record.award_year
        for record in winner_records
        if record.status == 'Winner'
    )
    collected: list[_ParsedRecord] = []
    for year in _shortlist_years_to_load():
        try:
            collected.extend(_get_one_shortlist_year(year, winner_years))
        except WomensPrizeFictionSourceError:
            continue
    return tuple(collected)


def _merge_winners_and_shortlisted(
    winners: tuple[_ParsedRecord, ...],
    shortlisted: tuple[_ParsedRecord, ...],
) -> tuple[_ParsedRecord, ...]:
    winner_keys = {_identity_key(record) for record in winners}
    extra = [
        record
        for record in shortlisted
        if record.status == 'Shortlisted' and _identity_key(record) not in winner_keys
    ]
    merged = list(winners) + extra
    return tuple(
        sorted(
            merged,
            key=lambda record: (
                record.award_year,
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


def _normalize_author_for_compare(value: str) -> str:
    """Author compare key: apostrophe variants plus space after apostrophe."""
    return _APOSTROPHE_FOLLOWING_SPACE_RE.sub("'", _normalize_text(value))


def _titles_match(query_title: str, record_title: str) -> bool:
    query_norm = normalize_title_conjunctions(_normalize_text(query_title))
    record_norm = normalize_title_conjunctions(_normalize_text(record_title))
    return query_norm == record_norm


def _authors_match(query_author: str, record_author: str) -> bool:
    return _normalize_author_for_compare(
        query_author
    ) == _normalize_author_for_compare(record_author)


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
    """Look up Women's Prize for Fiction winners and shortlisted works."""
    cleaned_title = title.strip()
    cleaned_author = author.strip()
    if not cleaned_title:
        raise ValueError('title must be a non-empty string')
    if not cleaned_author:
        raise ValueError('author must be a non-empty string')

    winners = _get_archive_records()
    shortlisted = _get_shortlisted_records(winners)
    merged = _merge_winners_and_shortlisted(winners, shortlisted)
    matches: list[AwardResult] = []
    for record in merged:
        if _record_matches(record, cleaned_title, cleaned_author):
            matches.append(_to_award_result(record))
    return matches
