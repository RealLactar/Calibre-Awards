"""Official Romantic Novelists' Association RoNA source.

Winners come from the server-rendered /past-winners archive. Shortlists
come from official RNA news announcements from 2018 onward. Industry,
Joan Hessayon, Elizabeth Goudge, and person/service honors are excluded.
"""

from __future__ import annotations

import html as html_module
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
SOURCE_KEY = 'romantic_novel_awards'
AWARD_NAME = 'Romantic Novel of the Year Award'
SOURCE_NAME = "Romantic Novelists' Association"
SITE_ORIGIN = 'https://romanticnovelistsassociation.org'
SOURCE_HOME_URL = SITE_ORIGIN + '/awards/the-romantic-novel-awards'
WINNERS_ARCHIVE_URL = SITE_ORIGIN + '/past-winners'
NEWS_CATEGORIES_REST_URL = SITE_ORIGIN + '/wp-json/wp/v2/news_categories'
NEWS_REST_URL = SITE_ORIGIN + '/wp-json/wp/v2/news'
NEWS_CATEGORY_SLUG = 'the-romantic-novel-awards'
MIN_SUPPORTED_YEAR = 1960
SHORTLIST_MIN_YEAR = 2018
PILLOW_TALK_SLUG = 'pillow-talk'
PILLOW_TALK_YEAR = 2008
WINNERS_ENTRY_KIND = 'winners'
WINNERS_ENTRY_KEY = 'archive'
NEWS_INDEX_ENTRY_KIND = 'news_index'
NEWS_INDEX_ENTRY_KEY = 'index'
YEAR_ENTRY_KIND = 'year'
WINNERS_CACHE_VERSION = 1
NEWS_INDEX_CACHE_VERSION = 1
YEAR_CACHE_VERSION = 1
HISTORICAL_CACHE_TTL_SECONDS = 180 * 24 * 60 * 60
CACHE_BASE_TTL_SECONDS = 7 * 24 * 60 * 60
CACHE_REFRESH_OFFSET_SECONDS = 18 * 60 * 60
CURRENT_CACHE_TTL_SECONDS = (
    CACHE_BASE_TTL_SECONDS + CACHE_REFRESH_OFFSET_SECONDS
)
SOURCEINFO_CATEGORIES = (
    'Debut Romance Novel Award',
    'Romantasy/Romantic Fantasy Award',
    'The Romantic Thriller Award',
    'The Festive/Holiday Romance Novel Award',
    'The Shorter Romance Novel Award',
    'The Saga Romance Award',
    'The Historical Romance Award',
    'The Contemporary Romance Novel Award',
    'The Contemporary Spicy Romance Novel Award',
    'The Romantic Comedy Award',
    'The Romance Bestseller Award',
    'The Fantasy Romantic Novel Award',
    'The Popular Romantic Fiction Award',
    'Best historical',
    'Best modern',
    'Epic Romantic Novel',
    'Young Adult Romantic Novel',
)

_OFFICIAL_HOSTS = frozenset({
    'romanticnovelistsassociation.org',
    'www.romanticnovelistsassociation.org',
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
_JSON_HEADERS = {
    **_BROWSER_HEADERS,
    'Accept': 'application/json, text/javascript;q=0.9, */*;q=0.8',
}
_INITIALS_SPACE_RE = re.compile(r'\b([A-Za-z])\.\s+')
_WINNER_SLUG_RE = re.compile(
    r'^https?://[^/]+/past-winners/([0-9A-Za-z][0-9A-Za-z_-]*)/?$',
    re.IGNORECASE,
)
_PAGE_HREF_RE = re.compile(
    r'/past-winners/page/(\d+)/?',
    re.IGNORECASE,
)
_PAGE_OF_RE = re.compile(r'Page\s+(\d+)\s+of\s+(\d+)', re.IGNORECASE)
_YEAR_RE = re.compile(r'\b(19[6-9]\d|20\d{2})\b')
_TITLE_BY_AUTHOR_RE = re.compile(
    r'^(?P<title>.+?)\s+by\s+(?P<author>.+)$',
    re.IGNORECASE,
)
_LEADING_ARTICLE_RE = re.compile(r'^(the|a|an)\b', re.IGNORECASE)
_PROGRAMME_HEADING_RE = re.compile(
    r'^(?:the\s+)?'
    r'(?:romantic novelists[\'’] association\s+)?'
    r'(?:rna\s+)?'
    r'romantic novel(?:ists)?(?:\s+of\s+the\s+year)?\s+awards?'
    r'(?:\s+\d{4})?'
    r'$',
    re.IGNORECASE,
)
_SAME_LINE_WINNER_RE = re.compile(r'^WINNER:\s+\S', re.IGNORECASE)
_CHALLENGE_MARKERS = (
    'just a moment',
    'attention required',
    'cf-browser-verification',
    'enable javascript and cookies to continue',
    'checking your browser',
    'cf-challenge',
    'why have i been blocked',
)
_ERROR_MARKERS = (
    'there has been a critical error on this website',
    'this page doesn\'t exist',
)
_ARCHIVE_IDENTITY_MARKERS = (
    'past-winners',
    'past winners',
    'romantic novelists',
)
_RONA_FAMILY_SLUGS = frozenset({
    'the-romantic-novel-of-the-year-awards',
})
_EXCLUDED_FAMILY_SLUGS = frozenset({
    'the-rna-industry-awards',
    'joan-hessayon-award',
})
_EXCLUDED_CATEGORY_SLUGS = frozenset({
    'outstanding-achievement-award',
    'the-joan-hessayon-award',
    'agent-of-the-year',
    'cover-designer-of-the-year',
    'editor-of-the-year',
    'inclusion-award',
    'indie-champion-of-the-year',
    'indie-editor-of-the-year',
    'library-or-librarian-of-the-year',
    'media-star-of-the-year',
    'narrator-of-the-year',
    'publisher-and-or-editor-of-the-year',
    'publisher-of-the-year',
    'rising-star-of-the-year',
    'romance-champion-of-the-year',
    'the-romantic-bookseller-of-the-year',
    'romantic-publisher-of-the-year',
})
_OVERALL_CATEGORY_SLUGS = frozenset({
    'romantic-novel-of-the-year',
})
_EXCLUDED_HEADING_MARKERS = (
    'joan hessayon',
    'elizabeth goudge',
    'lifetime achievement',
    'outstanding achievement',
    'industry award',
    'agent of the year',
    'editor of the year',
    'publisher of the year',
    'bookseller',
    'narrator of the year',
    'cover designer',
    'library or librarian',
    'media star',
    'indie champion',
    'indie editor',
    'inclusion award',
    'rising star',
    'romance champion',
)
_SPONSOR_PREFIX_RE = re.compile(
    r'^(?:the\s+)?'
    r'(?:goldsboro books|katie fforde|jackie collins|'
    r'jane wenham-?jones|sapere books|libert[aà]|rna\'s|rna’s|rna)\s+',
    re.IGNORECASE,
)
_IGNORE_TAGS = frozenset({'script', 'style', 'svg', 'noscript', 'iframe'})
_PARSED_STATUSES = frozenset({'Winner', 'Shortlisted'})
_YEAR_STATES = frozenset({'absent', 'shortlisted', 'winner'})
_STATUS_WEIGHT = {
    'Shortlisted': 1,
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
_MAX_REST_PAGES = 50
_REST_PER_PAGE = 100

# Matching-only aliases. AwardResult.category always uses announcement
# wording when an official announcement was parsed.
_CATEGORY_MATCH_ALIASES = {
    'debut romantic novel': 'debut romance novel',
    'the debut romantic novel award': 'debut romance novel',
    'debut romance novel award': 'debut romance novel',
    'debut romance novel': 'debut romance novel',
    'katie fforde debut romantic novel': 'debut romance novel',
    'the katie fforde debut romantic novel award': 'debut romance novel',
    'romantasy romantic fantasy': 'romantasy romantic fantasy',
    'the romantasy romantic fantasy award': 'romantasy romantic fantasy',
    'fantasy romantic novel': 'fantasy romantic novel',
    'the fantasy romantic novel award': 'fantasy romantic novel',
    'festive holiday romantic novel': 'festive holiday romance novel',
    'the festive holiday romantic novel award': 'festive holiday romance novel',
    'festive holiday romance novel': 'festive holiday romance novel',
    'christmas festive holiday romantic novel': 'festive holiday romance novel',
    'shorter romantic novel': 'shorter romance novel',
    'the shorter romantic novel award': 'shorter romance novel',
    'shorter romance novel': 'shorter romance novel',
    'rona rose for shorter romantic novels': 'shorter romance novel',
    'historical romantic novel': 'historical romance',
    'the historical romantic novel award': 'historical romance',
    'the historical romance award': 'historical romance',
    'historical romance': 'historical romance',
    'historical romance novel': 'historical romance',
    'contemporary romantic novel': 'contemporary romance novel',
    'the contemporary romantic novel award': 'contemporary romance novel',
    'the contemporary romance novel award': 'contemporary romance novel',
    'contemporary romance novel': 'contemporary romance novel',
    'contemporary spicy romance novel': 'contemporary spicy romance novel',
    'the contemporary spicy romance novel award': (
        'contemporary spicy romance novel'
    ),
    'romantic comedy': 'romantic comedy',
    'the romantic comedy award': 'romantic comedy',
    'romantic comedy novel': 'romantic comedy',
    'the jane wenham jones award for romantic comedy': 'romantic comedy',
    'saga romance': 'saga romance',
    'the saga romance award': 'saga romance',
    'romantic saga': 'romantic saga',
    'the romantic saga award': 'romantic saga',
    'romantic thriller': 'romantic thriller',
    'the romantic thriller award': 'romantic thriller',
    'jackie collins award for romantic thrillers': 'romantic thriller',
    'jackie collins romantic thriller': 'romantic thriller',
    'romance bestseller': 'romance bestseller',
    'the romance bestseller award': 'romance bestseller',
    'popular romantic fiction': 'popular romantic fiction',
    'the popular romantic fiction award': 'popular romantic fiction',
    'popular fiction romantic novel': 'popular romantic fiction',
    'epic romantic novel': 'epic romantic novel',
    'paranormal or speculative romantic novel': (
        'paranormal or speculative romantic novel'
    ),
    'young adult romantic novel': 'young adult romantic novel',
    'best historical': 'best historical',
    'best modern': 'best modern',
    'contemporary fade to black romance': 'contemporary fade to black romance',
    'contemporary romantic women s fiction': (
        'contemporary romantic women s fiction'
    ),
}

# MATCH-ONLY. Does not rewrite stored or emitted author credits.
# 2025 Historical Winner: the winner announcement credits
# "Elena Collins (Judy Leigh)" while the Winners Archive credits
# "Elena Collins". Overlay/lookup identity uses this exact pair only.
# Unrelated parentheticals are preserved.
_AUTHOR_MATCH_ONLY_ALIASES = {
    ('the wicked lady', 'elena collins (judy leigh)'): 'elena collins',
}
_IDENTITY_CONTAMINATION_MARKERS = (
    'prowritingaid',
    'pro writing aid',
    'was a creative force',
    'queen of the bonkbuster',
    'uses ai to check',
)


class RomanticNovelAwardsSourceError(RuntimeError):
    """Raised when official RNA pages are blocked or unusable."""


@dataclass(frozen=True, slots=True)
class _ParsedRecord:
    award_year: int
    category: str | None
    status: str
    work_title: str
    work_author: str
    source_url: str


@dataclass(frozen=True, slots=True)
class _WinnerCard:
    award_year: int | None
    family_slug: str
    family_slugs: tuple[str, ...]
    category_slug: str
    category_label: str
    work_title: str
    work_author: str
    source_url: str
    slug: str


@dataclass(frozen=True, slots=True)
class _NewsPost:
    post_id: int
    award_year: int
    kind: str
    url: str
    slug: str
    title: str
    date: str
    combined: bool


@dataclass(frozen=True, slots=True)
class _NewsIndex:
    category_id: int
    posts: tuple[_NewsPost, ...]


@dataclass(frozen=True, slots=True)
class _YearSnapshot:
    award_year: int
    state: str
    source_urls: tuple[str, ...]
    records: tuple[_ParsedRecord, ...]


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _IGNORE_TAGS:
            self._skip += 1
        if tag in {'p', 'div', 'h1', 'h2', 'h3', 'li', 'br', 'tr', 'section'}:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in _IGNORE_TAGS and self._skip:
            self._skip -= 1
        if tag in {'p', 'div', 'h1', 'h2', 'h3', 'li', 'section'}:
            self.parts.append('\n')

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


class _ArchivePageParser(HTMLParser):
    """Parse server-rendered /past-winners listing cards."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cards: list[_WinnerCard] = []
        self.page_numbers: set[int] = set()
        self.page_of: tuple[int, int] | None = None
        self._skip = 0
        self._in_h2 = False
        self._h2_parts: list[str] = []
        self._h2_href: str | None = None
        self._current: dict | None = None
        self._in_info = False
        self._info_parts: list[str] = []
        self._capture_link = False
        self._link_href = ''
        self._link_parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _IGNORE_TAGS:
            self._skip += 1
            return
        if self._skip:
            return
        attrs_dict = dict(attrs)
        href = attrs_dict.get('href', '') or ''
        classes = attrs_dict.get('class', '') or ''
        if tag == 'h2':
            self._in_h2 = True
            self._h2_parts = []
            self._h2_href = None
        if tag == 'a' and href:
            page_match = _PAGE_HREF_RE.search(href)
            if page_match:
                self.page_numbers.add(int(page_match.group(1)))
            if self._in_h2:
                self._h2_href = href
            slug = _winner_slug(href)
            if slug and self._in_h2:
                self._flush_card()
                self._current = {
                    'slug': slug,
                    'source_url': _canonical_winner_url(slug),
                    'work_title': '',
                    'work_author': '',
                    'family_slug': '',
                    'family_slugs': [],
                    'category_slug': '',
                    'category_label': '',
                    'award_year': None,
                }
            if self._current is not None:
                self._capture_link = True
                self._link_href = href
                self._link_parts = []
        if tag == 'ul' and 'info' in classes.split():
            self._in_info = True
            self._info_parts = []

    def handle_endtag(self, tag):
        if tag in _IGNORE_TAGS and self._skip:
            self._skip -= 1
            return
        if self._skip:
            return
        if tag == 'a' and self._capture_link:
            text = _collapse_ws(''.join(self._link_parts))
            href = self._link_href
            self._capture_link = False
            if self._current is not None:
                self._apply_link(href, text)
        if tag == 'h2' and self._in_h2:
            text = _collapse_ws(''.join(self._h2_parts))
            if self._current is not None:
                if not self._current['work_title'] and self._h2_href:
                    self._current['work_title'] = text
                elif (
                    self._current['work_title']
                    and not self._current['work_author']
                    and not self._h2_href
                ):
                    self._current['work_author'] = text
            self._in_h2 = False
            self._h2_href = None
        if tag == 'ul' and self._in_info:
            self._in_info = False

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_h2:
            self._h2_parts.append(data)
        if self._capture_link:
            self._link_parts.append(data)
        match = _PAGE_OF_RE.search(data)
        if match:
            self.page_of = (int(match.group(1)), int(match.group(2)))

    def _apply_link(self, href: str, text: str) -> None:
        assert self._current is not None
        parsed = urlparse(href)
        path = parsed.path.rstrip('/')
        if '/past_winners_awards/' in path:
            family_slug = path.rsplit('/', 1)[-1]
            self._current['family_slug'] = family_slug
            families = self._current['family_slugs']
            if family_slug and family_slug not in families:
                families.append(family_slug)
        elif '/past_winners_award_categories/' in path:
            self._current['category_slug'] = path.rsplit('/', 1)[-1]
            if text:
                self._current['category_label'] = text
        elif '/past_winners_years/' in path:
            year_text = path.rsplit('/', 1)[-1]
            if year_text.isdigit():
                self._current['award_year'] = int(year_text)

    def _flush_card(self) -> None:
        if not self._current:
            return
        title = self._current['work_title']
        slug = self._current['slug']
        if title and slug:
            self.cards.append(
                _WinnerCard(
                    award_year=self._current['award_year'],
                    family_slug=self._current['family_slug'],
                    family_slugs=tuple(self._current['family_slugs']),
                    category_slug=self._current['category_slug'],
                    category_label=self._current['category_label'],
                    work_title=title,
                    work_author=self._current['work_author'],
                    source_url=self._current['source_url'],
                    slug=slug,
                )
            )
        self._current = None

    def close(self):
        self._flush_card()
        super().close()


class _AccordionNewsParser(HTMLParser):
    """Parse 2026-style accordion shortlist/winner announcements."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.entries: list[tuple[str, str, str, bool, str | None]] = []
        self._skip = 0
        self._in_accordion = False
        self._in_heading = False
        self._heading_tag = ''
        self._heading_parts: list[str] = []
        self._heading_href: str | None = None
        self._category = ''
        self._in_accordion_h2 = False
        self._open_sections: list[bool] = []

    def handle_starttag(self, tag, attrs):
        if tag in _IGNORE_TAGS:
            self._skip += 1
            return
        if self._skip:
            return
        attrs_dict = dict(attrs)
        classes = attrs_dict.get('class', '') or ''
        href = attrs_dict.get('href', '') or ''
        if tag == 'section':
            is_accordion = 'accordion' in classes.split()
            self._open_sections.append(is_accordion)
            if is_accordion:
                self._in_accordion = True
        if not self._in_accordion:
            return
        if tag == 'h2':
            self._in_heading = True
            self._in_accordion_h2 = True
            self._heading_tag = 'h2'
            self._heading_parts = []
            self._heading_href = None
        elif tag == 'h3':
            self._in_heading = True
            self._heading_tag = 'h3'
            self._heading_parts = []
            self._heading_href = None
        if tag == 'a' and href and self._in_heading:
            self._heading_href = href

    def handle_endtag(self, tag):
        if tag in _IGNORE_TAGS and self._skip:
            self._skip -= 1
            return
        if self._skip:
            return
        if tag == 'section' and self._open_sections:
            closed_accordion = self._open_sections.pop()
            if closed_accordion:
                self._category = ''
            self._in_accordion = any(self._open_sections)
            if not self._in_accordion:
                self._category = ''
        if tag in {'h2', 'h3'} and self._in_heading:
            text = _collapse_ws(''.join(self._heading_parts))
            self._in_heading = False
            if tag == 'h2' and self._in_accordion_h2:
                self._in_accordion_h2 = False
                if text.upper().startswith('WINNER'):
                    self._emit_book(text, winner=True, href=self._heading_href)
                elif text:
                    heading = _canonical_category_heading(text)
                    if _heading_is_excluded(heading) or _is_programme_or_press_heading(heading):
                        self._category = ''
                    else:
                        self._category = heading
            elif tag == 'h3' and text:
                winner = text.upper().startswith('WINNER')
                self._emit_book(text, winner=winner, href=self._heading_href)

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_heading:
            self._heading_parts.append(data)

    def _emit_book(self, text: str, *, winner: bool, href: str | None) -> None:
        if not self._category:
            return
        cleaned = re.sub(r'^WINNER:\s*', '', text, flags=re.IGNORECASE)
        parsed = _parse_title_author_line(cleaned)
        if parsed is None:
            return
        title, author = parsed
        self.entries.append(
            (self._category, title, author, winner, href)
        )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _current_calendar_year() -> int:
    return _utc_now().year


def _collapse_ws(text: str) -> str:
    text = (
        text.replace('\xa0', ' ')
        .replace('\u2009', ' ')
        .replace('\u202f', ' ')
    )
    return re.sub(r'\s+', ' ', text).strip()


def _decode_text(value: str) -> str:
    return _collapse_ws(html_module.unescape(value))


def _absolute_href(href: str) -> str:
    return urljoin(SITE_ORIGIN + '/', href.strip())


def _winner_slug(href: str) -> str | None:
    if not href:
        return None
    absolute = _absolute_href(href.split('#', 1)[0].split('?', 1)[0])
    match = _WINNER_SLUG_RE.match(absolute)
    if match:
        slug = match.group(1).casefold()
        if slug not in {'page'} and not slug.isdigit():
            return match.group(1)
    return None


def _canonical_winner_url(slug: str) -> str:
    return f'{WINNERS_ARCHIVE_URL}/{slug}'


def _official_page_url(url: str) -> str | None:
    parsed = urlparse(url)
    host = (parsed.hostname or '').casefold()
    if parsed.scheme != 'https' or host not in _OFFICIAL_HOSTS:
        return None
    return url


def _require_official_url(url: str) -> str:
    official = _official_page_url(url)
    if official is None:
        raise RomanticNovelAwardsSourceError(
            f'RNA request redirected off-host: {url}'
        )
    return official


def _reject_challenge_or_error(body: str, url: str) -> None:
    lowered = body.casefold()
    if any(marker in lowered for marker in _CHALLENGE_MARKERS):
        raise RomanticNovelAwardsSourceError(
            f'RNA challenge page at {url}'
        )
    if 'just a moment' in lowered and 'cloudflare' in lowered:
        raise RomanticNovelAwardsSourceError(
            f'RNA challenge page at {url}'
        )
    if any(marker in lowered for marker in _ERROR_MARKERS):
        raise RomanticNovelAwardsSourceError(
            f'RNA error page at {url}'
        )
    if 'page not found' in lowered and 'past-winners' not in url:
        if '<body class="' in lowered and 'error404' in lowered:
            raise RomanticNovelAwardsSourceError(
                f'RNA 404 page at {url}'
            )


def _read_response_body(response) -> str:
    return response.read().decode('utf-8', errors='replace')


def _fetch(url: str, *, headers: dict[str, str] | None = None) -> str:
    request = urllib.request.Request(
        url,
        headers=dict(headers or _BROWSER_HEADERS),
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            status = getattr(response, 'status', None) or response.getcode()
            final = _require_official_url(response.geturl())
            body = _read_response_body(response)
    except urllib.error.HTTPError as exc:
        raise RomanticNovelAwardsSourceError(
            f'RNA request failed with HTTP {exc.code} for {url}'
        ) from exc
    except urllib.error.URLError as exc:
        raise RomanticNovelAwardsSourceError(
            f'RNA request failed for {url}: {exc.reason}'
        ) from exc
    if status != 200:
        raise RomanticNovelAwardsSourceError(
            f'RNA request failed with HTTP {status} for {url}'
        )
    _reject_challenge_or_error(body, final)
    return body


def _fetch_html(url: str) -> str:
    return _fetch(url, headers=_BROWSER_HEADERS)


def _fetch_json(url: str):
    body = _fetch(url, headers=_JSON_HEADERS)
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RomanticNovelAwardsSourceError(
            f'RNA JSON was malformed at {url}'
        ) from exc


def _require_archive_identity(html: str) -> None:
    lowered = html.casefold()
    if 'error404' in lowered and 'post-type-archive-past_winners' not in lowered:
        raise RomanticNovelAwardsSourceError(
            'RNA winners archive identity failed'
        )
    if not any(marker in lowered for marker in _ARCHIVE_IDENTITY_MARKERS):
        raise RomanticNovelAwardsSourceError(
            'RNA winners archive identity failed'
        )


def _discover_archive_page_count(html: str, parsed: _ArchivePageParser) -> int:
    last = 1
    if parsed.page_of is not None:
        last = max(last, parsed.page_of[1])
    if parsed.page_numbers:
        last = max(last, max(parsed.page_numbers))
    match = _PAGE_OF_RE.search(html)
    if match:
        last = max(last, int(match.group(2)))
    if last < 1:
        raise RomanticNovelAwardsSourceError(
            'RNA winners archive pagination was unusable'
        )
    return last


def _parse_archive_page(html: str) -> _ArchivePageParser:
    parser = _ArchivePageParser()
    parser.feed(html)
    parser.close()
    return parser


def _archive_page_url(page: int) -> str:
    if page <= 1:
        return WINNERS_ARCHIVE_URL
    return f'{WINNERS_ARCHIVE_URL}/page/{page}/'


def _is_pillow_talk_exception(card: _WinnerCard) -> bool:
    return (
        card.slug == PILLOW_TALK_SLUG
        and card.award_year == PILLOW_TALK_YEAR
        and not card.family_slug
        and not card.category_slug
        and bool(card.work_title.strip())
        and bool(card.work_author.strip())
        and card.source_url == _canonical_winner_url(PILLOW_TALK_SLUG)
    )


def _is_excluded_category(card: _WinnerCard) -> bool:
    slug = card.category_slug.casefold()
    label = card.category_label.casefold()
    if slug in _EXCLUDED_CATEGORY_SLUGS:
        return True
    if 'outstanding achievement' in label:
        return True
    if 'joan hessayon' in label:
        return True
    if 'goudge' in label:
        return True
    return False


def _archive_category(card: _WinnerCard) -> str | None:
    slug = card.category_slug.casefold()
    if slug in _OVERALL_CATEGORY_SLUGS:
        return None
    label = card.category_label.strip()
    if not label:
        return None
    if label.casefold() in {'romantic novel of the year', 'the romantic novel of the year'}:
        return None
    return label


def _winner_card_to_record(card: _WinnerCard) -> _ParsedRecord | None:
    if not card.work_title.strip() or not card.work_author.strip():
        return None
    if card.award_year is None or card.award_year < MIN_SUPPORTED_YEAR:
        return None
    if _is_pillow_talk_exception(card):
        return _ParsedRecord(
            award_year=PILLOW_TALK_YEAR,
            category=None,
            status='Winner',
            work_title=card.work_title,
            work_author=card.work_author,
            source_url=card.source_url,
        )
    family_slugs = tuple(
        slug.casefold() for slug in (card.family_slugs or (card.family_slug,))
        if slug
    )
    if any(slug in _EXCLUDED_FAMILY_SLUGS for slug in family_slugs):
        return None
    if _is_excluded_category(card):
        return None
    if 'the-romantic-novel-of-the-year-awards' not in family_slugs:
        if card.family_slug.casefold() not in _RONA_FAMILY_SLUGS:
            return None
    return _ParsedRecord(
        award_year=card.award_year,
        category=_archive_category(card),
        status='Winner',
        work_title=card.work_title,
        work_author=card.work_author,
        source_url=card.source_url,
    )


def _visible_lines(html: str) -> tuple[str, ...]:
    extractor = _TextExtractor()
    extractor.feed(html)
    extractor.close()
    text = html_module.unescape(''.join(extractor.parts))
    lines = []
    for raw in text.splitlines():
        line = _collapse_ws(raw)
        if line:
            lines.append(line)
    return tuple(lines)


def _strip_heading_icons(text: str) -> str:
    return _collapse_ws(re.sub(r'\s+', ' ', text))


def _heading_is_excluded(heading: str) -> bool:
    lowered = heading.casefold()
    return any(marker in lowered for marker in _EXCLUDED_HEADING_MARKERS)


def _canonical_category_heading(text: str) -> str:
    heading = _strip_heading_icons(text).strip(' :')
    heading = re.sub(r'\s+\((?:sponsored|sponsor)[^)]*\)\s*$', '', heading, flags=re.IGNORECASE)
    return heading.strip(' :')


def _is_programme_or_press_heading(line: str) -> bool:
    heading = _canonical_category_heading(line)
    if not heading:
        return True
    lowered = heading.casefold()
    if _PROGRAMME_HEADING_RE.match(heading):
        return True
    if 'romantic novelists' in lowered:
        return True
    if 'press release' in lowered:
        return True
    if re.search(r'\b20\d{2}\b', heading) and 'award' in lowered:
        return True
    return False


def _looks_like_category_heading(line: str) -> bool:
    lowered = line.casefold()
    if _is_programme_or_press_heading(line):
        return False
    if _parse_title_author_line(line) is not None:
        return False
    if lowered.startswith('publisher:') or lowered.startswith('agent:'):
        return False
    if lowered in {'independently published', 'self published', 'self-published'}:
        return False
    if len(line) > 90:
        return False
    if line.endswith('.') or line.endswith('!') or line.endswith('?'):
        return False
    if lowered.startswith('#') or lowered.startswith('(') or lowered.startswith('winner,'):
        return False
    if re.search(r'\bwinners?\b', lowered) and 'joint winner' not in lowered:
        return False
    rejected = (
        'announced',
        'press release',
        'delighted',
        'about the',
        'lifetime achievement',
        'outstanding achievement',
        'reader-judge',
        'interested in becoming',
        'compèred',
        'compered',
        'ceremony',
        'shortlists for',
        'winners announced',
        'finalists announced',
        'step down',
        'president',
        'romance matters',
        'category winners',
    )
    if any(marker in lowered for marker in rejected):
        return False
    markers = (
        'award',
        'novel',
        'romance',
        'romantic',
        'rona rose',
        'best historical',
        'best modern',
        'bestseller',
        'thriller',
        'comedy',
        'saga',
        'fantasy',
        'romantasy',
        'debut',
        'shorter',
        'festive',
        'holiday',
        'popular',
        'epic',
        'young adult',
        'paranormal',
        'spicy',
        'fade-to-black',
        'women',
    )
    return any(marker in lowered for marker in markers)


def _looks_like_person_name(text: str) -> bool:
    words = [word for word in text.replace('-', ' ').split() if word]
    if not (2 <= len(words) <= 4):
        return False
    if _LEADING_ARTICLE_RE.match(text):
        return False
    return all(word[:1].isalpha() and word[:1].isupper() for word in words)


def _looks_like_book_title(text: str) -> bool:
    return bool(_LEADING_ARTICLE_RE.match(text))


def _usable_book_identity(title: str, author: str) -> bool:
    blob = f'{title} {author}'.casefold()
    if 'outstanding achievement' in blob or 'joan hessayon' in blob:
        return False
    if 'elizabeth goudge' in blob:
        return False
    if any(marker in blob for marker in _IDENTITY_CONTAMINATION_MARKERS):
        return False
    if _looks_like_person_name(title) and _looks_like_book_title(author):
        return False
    return True


def _parse_title_author_line(line: str) -> tuple[str, str] | None:
    text = _collapse_ws(line)
    text = re.sub(r'^WINNER:\s*', '', text, flags=re.IGNORECASE)
    text = text.strip(' *')
    if not text or text.casefold().startswith('publisher:'):
        return None
    if text.casefold().startswith('agent:'):
        return None
    match = _TITLE_BY_AUTHOR_RE.match(text)
    if match:
        title = _collapse_ws(match.group('title').strip(' "\'“”‘’*'))
        author = _collapse_ws(match.group('author'))
        if (
            title
            and author
            and len(title) <= 120
            and len(author.split()) <= 8
            and 'award' not in author.casefold()
            and 'http' not in author.casefold()
        ):
            if _usable_book_identity(title, author):
                return title, author
    parts = [part.strip() for part in text.split(',') if part.strip()]
    if len(parts) >= 2 and ' by ' not in text.casefold():
        title = parts[0].strip(' "\'“”‘’*')
        author = _collapse_ws(parts[1])
        if (
            title
            and author
            and not title.casefold().startswith('publisher')
            and 'http' not in author.casefold()
            and 'award' not in author.casefold()
            and len(title) <= 120
            and len(author.split()) <= 8
        ):
            if _usable_book_identity(title, author):
                return title, author
    return None


def _parse_accordion_entries(html: str) -> list[tuple[str, str, str, bool, str | None]]:
    parser = _AccordionNewsParser()
    parser.feed(html)
    parser.close()
    return parser.entries


def _parse_announcement_html(
    html: str,
    *,
    source_url: str,
    award_year: int,
    default_status: str,
    winners_only: bool = False,
) -> tuple[_ParsedRecord, ...]:
    records: list[_ParsedRecord] = []
    accordion = _parse_accordion_entries(html)
    if accordion:
        for category, title, author, winner, href in accordion:
            if _heading_is_excluded(category) or _is_programme_or_press_heading(category):
                continue
            if winners_only and not winner:
                continue
            status = 'Winner' if winner else default_status
            url = source_url
            slug = _winner_slug(href) if href else None
            if slug:
                url = _canonical_winner_url(slug)
            records.append(
                _ParsedRecord(
                    award_year=award_year,
                    category=category,
                    status=status,
                    work_title=title,
                    work_author=author,
                    source_url=url,
                )
            )
        return tuple(_dedupe_records(records))

    category = None
    winner_pending = False
    for line in _visible_lines(html):
        lowered = line.casefold()
        if lowered in {'the category shortlists', 'about the award sponsors:'}:
            continue
        same_line_winner = bool(_SAME_LINE_WINNER_RE.match(line))
        if line.upper() == 'WINNER:' or lowered == 'winner':
            winner_pending = True
            continue
        if _looks_like_category_heading(line) and _parse_title_author_line(line) is None:
            heading = _canonical_category_heading(line)
            if _heading_is_excluded(heading) or _is_programme_or_press_heading(heading):
                category = None
            else:
                category = heading
            winner_pending = False
            continue
        parsed = _parse_title_author_line(line)
        if parsed is None or category is None:
            continue
        marked_winner = winner_pending or same_line_winner
        if winners_only and not marked_winner:
            continue
        title, author = parsed
        status = 'Winner' if (marked_winner or default_status == 'Winner') else default_status
        winner_pending = False
        records.append(
            _ParsedRecord(
                award_year=award_year,
                category=category,
                status=status,
                work_title=title,
                work_author=author,
                source_url=source_url,
            )
        )
    return tuple(_dedupe_records(records))


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


def _author_match_key(author: str, title: str = '') -> str:
    author_norm = _normalize_text(author)
    title_norm = _normalize_text(title)
    aliased = _AUTHOR_MATCH_ONLY_ALIASES.get((title_norm, author_norm))
    if aliased is not None:
        return aliased
    return author_norm


def _authors_match(query_author: str, record_author: str) -> bool:
    return _normalize_text(query_author) == _normalize_text(record_author)


def _record_matches(record: _ParsedRecord, title: str, author: str) -> bool:
    if not _titles_match(title, record.work_title):
        return False
    return _author_match_key(author, title) == _author_match_key(
        record.work_author, record.work_title
    )


def _category_match_key(value: str | None) -> str:
    if not value:
        return ''
    text = unicodedata.normalize('NFKC', value).casefold()
    text = text.replace('\u2019', "'").replace('\u2018', "'")
    text = _SPONSOR_PREFIX_RE.sub('', text)
    text = text.replace('/', ' ').replace('-', ' ')
    text = re.sub(r'[^a-z0-9]+', ' ', text)
    text = re.sub(r'\bthe\b', ' ', text)
    text = re.sub(r'\bawards?\b', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'\bromantic\b', 'romance', text)
    aliased = _CATEGORY_MATCH_ALIASES.get(text, text)
    return _CATEGORY_MATCH_ALIASES.get(aliased, aliased)


def _categories_equivalent(left: str | None, right: str | None) -> bool:
    if not left and not right:
        return True
    if not left or not right:
        return False
    return _category_match_key(left) == _category_match_key(right)


def _factual_key(record: _ParsedRecord) -> tuple:
    return (
        record.award_year,
        _category_match_key(record.category),
        _normalize_text(record.work_title),
        _author_match_key(record.work_author, record.work_title),
        record.status,
    )


def _dedupe_records(records: list[_ParsedRecord]) -> list[_ParsedRecord]:
    by_key: dict[tuple, _ParsedRecord] = {}
    order: list[tuple] = []
    for record in records:
        key = _factual_key(record)
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = record
            order.append(key)
            continue
        if _STATUS_WEIGHT[record.status] > _STATUS_WEIGHT[existing.status]:
            by_key[key] = record
        elif (
            record.status == existing.status
            and '/past-winners/' in record.source_url
            and '/past-winners/' not in existing.source_url
        ):
            by_key[key] = record
    return [by_key[key] for key in order]


def _is_news_url(url: str) -> bool:
    return '/news/' in urlparse(url).path.casefold()


def _is_winner_news_url(url: str) -> bool:
    path = urlparse(url).path.casefold()
    return '/news/' in path and 'winner' in path


def _prefer_shortlisted_url(existing: str, record: str) -> str:
    if _is_winner_news_url(record) and not _is_winner_news_url(existing):
        return existing
    if _is_news_url(record) and not _is_winner_news_url(record):
        return record
    if _is_news_url(existing):
        return existing
    return record


def _is_archive_url(url: str) -> bool:
    return '/past-winners/' in urlparse(url).path.casefold()


def _merge_status(records: list[_ParsedRecord]) -> list[_ParsedRecord]:
    grouped: dict[tuple, _ParsedRecord] = {}
    order: list[tuple] = []
    for record in records:
        key = (
            record.award_year,
            _category_match_key(record.category),
            _normalize_text(record.work_title),
            _author_match_key(record.work_author, record.work_title),
        )
        existing = grouped.get(key)
        if existing is None:
            grouped[key] = record
            order.append(key)
            continue
        status = (
            record.status
            if _STATUS_WEIGHT[record.status] >= _STATUS_WEIGHT[existing.status]
            else existing.status
        )
        if _is_news_url(record.source_url) and not _is_news_url(existing.source_url):
            category = record.category
        elif _is_news_url(existing.source_url):
            category = existing.category
        else:
            category = existing.category or record.category
        if _is_archive_url(existing.source_url):
            title = existing.work_title
            author = existing.work_author
        elif _is_archive_url(record.source_url):
            title = record.work_title
            author = record.work_author
        elif _is_news_url(record.source_url) and not _is_news_url(existing.source_url):
            title = record.work_title
            author = record.work_author
        elif _is_news_url(existing.source_url):
            title = existing.work_title
            author = existing.work_author
        else:
            title = existing.work_title
            author = existing.work_author
        if status == 'Winner':
            if _is_archive_url(record.source_url):
                source_url = record.source_url
            elif _is_archive_url(existing.source_url):
                source_url = existing.source_url
            elif _is_news_url(record.source_url) and record.status == 'Winner':
                source_url = record.source_url
            elif existing.status == 'Winner':
                source_url = existing.source_url
            else:
                source_url = record.source_url
        else:
            source_url = _prefer_shortlisted_url(existing.source_url, record.source_url)
        grouped[key] = _ParsedRecord(
            award_year=existing.award_year,
            category=category,
            status=status,
            work_title=title,
            work_author=author,
            source_url=source_url,
        )
    return [grouped[key] for key in order]


def _year_from_blob(blob: str, date: str = '') -> int | None:
    years = [int(match) for match in _YEAR_RE.findall(blob)]
    if years:
        return max(years)
    if date:
        match = _YEAR_RE.search(date)
        if match:
            return int(match.group(1))
    return None


def _is_combined_announcement(title: str, slug: str) -> bool:
    blob = f'{title} {slug}'.casefold()
    if blob.startswith('finalists:'):
        return False
    if re.search(r'finalists-the-|finalists-debut-|finalists-shorter', slug.casefold()):
        return False
    combined_markers = (
        'shortlists',
        'finalists announced',
        'reveals shortlists',
        'ronas',
        'romantic novel of the year awards',
        'romantic novel awards',
        'winners announced',
        'announces the',
    )
    return any(marker in blob for marker in combined_markers)


def _classify_news_post(
    *,
    post_id: int,
    title: str,
    slug: str,
    url: str,
    date: str,
) -> _NewsPost | None:
    blob = f'{title} {slug}'.casefold()
    if any(
        marker in blob
        for marker in (
            'industry award',
            'rna industry',
            'agent of the year',
            'editor of the year',
            'publisher of the year',
            'bookseller of the year',
            'narrator of the year',
            'cover designer',
            'indie champion',
            'indie editor',
            'inclusion award',
            'library or librarian',
            'media star',
            'rising star',
            'romance champion',
            'outstanding achievement',
            'elizabeth goudge',
            'marketing tip',
            'marktingtips',
            'register as a judge',
            'judge registration',
            'call for judges',
            'entries open',
            'now open for entries',
            'how to enter',
            'entry process',
            'submissions open',
            'author interview',
            'author profile',
            'meet the finalist',
            'finalist profile',
            'category explained',
            'explaining the categor',
        )
    ):
        return None
    if 'hessayon' in blob and 'rona' not in blob and 'romantic novel' not in blob:
        return None
    is_shortlist = any(word in blob for word in ('shortlist', 'finalist'))
    is_winner = 'winner' in blob
    if not is_shortlist and not is_winner:
        return None
    if is_winner and is_shortlist:
        kind = 'winner' if 'winner' in title.casefold() else 'shortlist'
    elif is_winner:
        kind = 'winner'
    else:
        kind = 'shortlist'
    year = _year_from_blob(f'{title} {slug}', date)
    if year is None or year < SHORTLIST_MIN_YEAR:
        return None
    official = _official_page_url(url)
    if official is None:
        return None
    return _NewsPost(
        post_id=post_id,
        award_year=year,
        kind=kind,
        url=official,
        slug=slug,
        title=_decode_text(title),
        date=date,
        combined=_is_combined_announcement(title, slug),
    )


def _discover_news_category_id() -> int:
    url = (
        f'{NEWS_CATEGORIES_REST_URL}?slug={NEWS_CATEGORY_SLUG}'
        '&per_page=100&_fields=id,slug,name'
    )
    payload = _fetch_json(url)
    if not isinstance(payload, list) or not payload:
        raise RomanticNovelAwardsSourceError(
            'RNA news category taxonomy was unusable'
        )
    for item in payload:
        if not isinstance(item, dict):
            continue
        if item.get('slug') == NEWS_CATEGORY_SLUG:
            category_id = item.get('id')
            if isinstance(category_id, int) and category_id > 0:
                return category_id
    raise RomanticNovelAwardsSourceError(
        'RNA news category taxonomy was unusable'
    )


def _enumerate_news_posts(category_id: int) -> list[dict]:
    collected: list[dict] = []
    seen_ids: set[int] = set()
    for page in range(1, _MAX_REST_PAGES + 1):
        url = (
            f'{NEWS_REST_URL}?news_categories={category_id}'
            f'&per_page={_REST_PER_PAGE}&page={page}'
            '&_fields=id,date,slug,link,title'
        )
        payload = _fetch_json(url)
        if not isinstance(payload, list):
            raise RomanticNovelAwardsSourceError(
                'RNA news index JSON was unusable'
            )
        if not payload:
            break
        for item in payload:
            if not isinstance(item, dict):
                continue
            post_id = item.get('id')
            if not isinstance(post_id, int) or post_id in seen_ids:
                continue
            seen_ids.add(post_id)
            collected.append(item)
        if len(payload) < _REST_PER_PAGE:
            break
    return collected


def _news_index_from_posts(category_id: int, raw_posts: list[dict]) -> _NewsIndex:
    posts: list[_NewsPost] = []
    for item in raw_posts:
        title_obj = item.get('title')
        if isinstance(title_obj, dict):
            title = str(title_obj.get('rendered') or '')
        else:
            title = str(title_obj or '')
        classified = _classify_news_post(
            post_id=int(item.get('id') or 0),
            title=html_module.unescape(title),
            slug=str(item.get('slug') or ''),
            url=str(item.get('link') or ''),
            date=str(item.get('date') or ''),
        )
        if classified is not None:
            posts.append(classified)
    return _NewsIndex(category_id=category_id, posts=tuple(posts))


def _year_urls_from_index(index: _NewsIndex, award_year: int) -> tuple[list[str], list[str]]:
    shortlists = [
        post for post in index.posts
        if post.award_year == award_year and post.kind == 'shortlist'
    ]
    winners = [
        post for post in index.posts
        if post.award_year == award_year and post.kind == 'winner'
    ]
    combined_short = [post for post in shortlists if post.combined]
    if combined_short:
        short_urls = [combined_short[0].url]
    else:
        short_urls = [post.url for post in shortlists]
    combined_win = [post for post in winners if post.combined]
    if combined_win:
        win_urls = [combined_win[0].url]
    else:
        win_urls = [post.url for post in winners if 'hessayon' not in post.slug.casefold()]
    return short_urls, win_urls


def _apply_winner_urls(
    records: list[_ParsedRecord],
    archive_winners: tuple[_ParsedRecord, ...],
) -> list[_ParsedRecord]:
    updated: list[_ParsedRecord] = []
    for record in records:
        source_url = record.source_url
        if record.status == 'Winner':
            for winner in archive_winners:
                if (
                    winner.award_year == record.award_year
                    and _record_matches(winner, record.work_title, record.work_author)
                ):
                    source_url = winner.source_url
                    break
        updated.append(
            _ParsedRecord(
                award_year=record.award_year,
                category=record.category,
                status=record.status,
                work_title=record.work_title,
                work_author=record.work_author,
                source_url=source_url,
            )
        )
    return updated


def _shortlist_category_vocabulary(
    records: list[_ParsedRecord],
) -> tuple[str, ...]:
    seen: list[str] = []
    keys: set[str] = set()
    for record in records:
        if not record.category:
            continue
        if _heading_is_excluded(record.category):
            continue
        if _is_programme_or_press_heading(record.category):
            continue
        key = _category_match_key(record.category)
        if not key or key in keys:
            continue
        keys.add(key)
        seen.append(record.category)
    return tuple(seen)


def _reconcile_to_vocabulary(
    category: str | None,
    vocabulary: tuple[str, ...],
) -> str | None:
    if not category or not vocabulary:
        return None
    for official in vocabulary:
        if _categories_equivalent(category, official):
            return official
    return None


def _filter_year_records(
    records: list[_ParsedRecord],
    vocabulary: tuple[str, ...],
) -> list[_ParsedRecord]:
    filtered: list[_ParsedRecord] = []
    for record in records:
        category = record.category
        if category and (
            _heading_is_excluded(category) or _is_programme_or_press_heading(category)
        ):
            continue
        if vocabulary and category:
            reconciled = _reconcile_to_vocabulary(category, vocabulary)
            if reconciled is None:
                if _is_archive_url(record.source_url) and record.status == 'Winner':
                    filtered.append(record)
                continue
            if reconciled != category:
                record = _ParsedRecord(
                    award_year=record.award_year,
                    category=reconciled,
                    status=record.status,
                    work_title=record.work_title,
                    work_author=record.work_author,
                    source_url=record.source_url,
                )
        filtered.append(record)
    return filtered


def _parse_year_pages(
    award_year: int,
    shortlist_urls: list[str],
    winner_urls: list[str],
    archive_winners: tuple[_ParsedRecord, ...],
) -> _YearSnapshot:
    collected: list[_ParsedRecord] = []
    used_urls: list[str] = []
    if award_year == 2018:
        winner_urls = []
    shortlist_records: list[_ParsedRecord] = []
    for url in shortlist_urls:
        html = _fetch_html(url)
        parsed = _parse_announcement_html(
            html,
            source_url=url,
            award_year=award_year,
            default_status='Shortlisted',
        )
        if not parsed:
            raise RomanticNovelAwardsSourceError(
                f'RNA shortlist announcement was unusable at {url}'
            )
        shortlist_records.extend(parsed)
        used_urls.append(url)
    vocabulary = _shortlist_category_vocabulary(shortlist_records)
    collected.extend(shortlist_records)
    for url in winner_urls:
        html = _fetch_html(url)
        parsed = _parse_announcement_html(
            html,
            source_url=url,
            award_year=award_year,
            default_status='Shortlisted',
            winners_only=True,
        )
        for record in parsed:
            if record.status != 'Winner':
                continue
            if record.category and (
                _heading_is_excluded(record.category)
                or _is_programme_or_press_heading(record.category)
            ):
                continue
            if vocabulary and record.category:
                reconciled = _reconcile_to_vocabulary(record.category, vocabulary)
                if reconciled is None:
                    continue
                record = _ParsedRecord(
                    award_year=record.award_year,
                    category=reconciled,
                    status=record.status,
                    work_title=record.work_title,
                    work_author=record.work_author,
                    source_url=record.source_url,
                )
            collected.append(record)
        used_urls.append(url)
    year_archive = tuple(
        record for record in archive_winners if record.award_year == award_year
    )
    if award_year != 2018:
        collected.extend(year_archive)
        collected = _merge_status(collected)
        collected = _apply_winner_urls(collected, year_archive)
        collected = _filter_year_records(collected, vocabulary)
    else:
        collected = [
            record for record in collected if record.status == 'Shortlisted'
        ]
        collected = _dedupe_records(collected)
    if not collected:
        state = 'absent'
    elif any(record.status == 'Winner' for record in collected):
        state = 'winner'
    else:
        state = 'shortlisted'
    return _YearSnapshot(
        award_year=award_year,
        state=state,
        source_urls=tuple(dict.fromkeys(used_urls)),
        records=tuple(collected),
    )


def _combine_all_records(
    archive_winners: tuple[_ParsedRecord, ...],
    year_snapshots: tuple[_YearSnapshot, ...],
) -> tuple[_ParsedRecord, ...]:
    combined: list[_ParsedRecord] = []
    news_years = {snapshot.award_year for snapshot in year_snapshots}
    for record in archive_winners:
        if record.award_year < SHORTLIST_MIN_YEAR:
            combined.append(record)
        elif record.award_year == 2018:
            if record.category is None:
                combined.append(record)
        elif record.award_year not in news_years:
            combined.append(record)
    for snapshot in year_snapshots:
        combined.extend(snapshot.records)
    return tuple(_dedupe_records(_merge_status(combined)))


# ---------------------------------------------------------------------------
# Cache / RAM
# ---------------------------------------------------------------------------

_winners_cache: tuple[_ParsedRecord, ...] | None = None
_news_index_cache: _NewsIndex | None = None
_year_cache: dict[int, _YearSnapshot] = {}
_cache_lock = threading.Lock()


def _reset_runtime_state() -> None:
    """Clear in-process caches. Used by tests. Does not delete disk cache."""
    global _winners_cache, _news_index_cache
    with _cache_lock:
        _winners_cache = None
        _news_index_cache = None
        _year_cache.clear()


def _record_to_cache_dict(record: _ParsedRecord) -> dict:
    return {
        'award_year': record.award_year,
        'category': record.category,
        'source_url': record.source_url,
        'status': record.status,
        'work_author': record.work_author,
        'work_title': record.work_title,
    }


def _record_from_cache_dict(item) -> _ParsedRecord | None:
    if not isinstance(item, dict):
        return None
    if set(item) != set(_RECORD_CACHE_FIELDS):
        extra = set(item) - set(_RECORD_CACHE_FIELDS)
        missing = set(_RECORD_CACHE_FIELDS) - set(item)
        if missing or extra - {'notes'}:
            if missing:
                return None
    try:
        year = int(item['award_year'])
        status = str(item['status'])
        title = str(item['work_title'])
        author = str(item['work_author'])
        source_url = str(item['source_url'])
        category = item.get('category')
        if category is not None:
            category = str(category)
            if not category.strip():
                category = None
    except (KeyError, TypeError, ValueError):
        return None
    if status not in _PARSED_STATUSES:
        return None
    if not title.strip() or not author.strip():
        return None
    if _official_page_url(source_url) is None:
        return None
    return _ParsedRecord(
        award_year=year,
        category=category,
        status=status,
        work_title=title,
        work_author=author,
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


def _year_ttl_seconds(award_year: int, state: str) -> int:
    calendar_year = _current_calendar_year()
    if award_year >= calendar_year:
        return CURRENT_CACHE_TTL_SECONDS
    if award_year == calendar_year - 1 and state != 'winner':
        return CURRENT_CACHE_TTL_SECONDS
    if state == 'winner':
        return HISTORICAL_CACHE_TTL_SECONDS
    return CURRENT_CACHE_TTL_SECONDS


def _save_winners(records: tuple[_ParsedRecord, ...], source_urls: list[str]) -> None:
    try:
        cache.save_cache_entry(
            SOURCE_KEY,
            WINNERS_ENTRY_KIND,
            WINNERS_ENTRY_KEY,
            WINNERS_CACHE_VERSION,
            records=[_record_to_cache_dict(record) for record in records],
            source_urls=source_urls,
            coverage={
                'min_year': min((record.award_year for record in records), default=None),
                'max_year': max((record.award_year for record in records), default=None),
                'record_count': len(records),
            },
            ttl_seconds=HISTORICAL_CACHE_TTL_SECONDS,
        )
    except OSError:
        pass


def _load_winners_disk() -> tuple[tuple[_ParsedRecord, ...], dict] | None:
    payload = cache.load_cache_entry(
        SOURCE_KEY,
        WINNERS_ENTRY_KIND,
        WINNERS_ENTRY_KEY,
        WINNERS_CACHE_VERSION,
    )
    if payload is None:
        return None
    records = _records_from_payload(payload)
    if records is None:
        return None
    return records, payload


def _save_news_index(index: _NewsIndex) -> None:
    try:
        cache.save_cache_entry(
            SOURCE_KEY,
            NEWS_INDEX_ENTRY_KIND,
            NEWS_INDEX_ENTRY_KEY,
            NEWS_INDEX_CACHE_VERSION,
            records=[
                {
                    'post_id': post.post_id,
                    'award_year': post.award_year,
                    'kind': post.kind,
                    'url': post.url,
                    'slug': post.slug,
                    'title': post.title,
                    'date': post.date,
                    'combined': post.combined,
                }
                for post in index.posts
            ],
            source_urls=[NEWS_CATEGORIES_REST_URL, NEWS_REST_URL],
            coverage={
                'category_id': index.category_id,
                'post_count': len(index.posts),
            },
            ttl_seconds=CURRENT_CACHE_TTL_SECONDS,
        )
    except OSError:
        pass


def _load_news_index_disk() -> tuple[_NewsIndex, dict] | None:
    payload = cache.load_cache_entry(
        SOURCE_KEY,
        NEWS_INDEX_ENTRY_KIND,
        NEWS_INDEX_ENTRY_KEY,
        NEWS_INDEX_CACHE_VERSION,
    )
    if payload is None:
        return None
    raw_records = payload.get('records')
    coverage = payload.get('coverage')
    if not isinstance(raw_records, list) or not isinstance(coverage, dict):
        return None
    category_id = coverage.get('category_id')
    if not isinstance(category_id, int):
        return None
    posts: list[_NewsPost] = []
    for item in raw_records:
        if not isinstance(item, dict):
            return None
        try:
            posts.append(
                _NewsPost(
                    post_id=int(item['post_id']),
                    award_year=int(item['award_year']),
                    kind=str(item['kind']),
                    url=str(item['url']),
                    slug=str(item['slug']),
                    title=str(item['title']),
                    date=str(item['date']),
                    combined=bool(item['combined']),
                )
            )
        except (KeyError, TypeError, ValueError):
            return None
        if posts[-1].kind not in {'shortlist', 'winner'}:
            return None
        if _official_page_url(posts[-1].url) is None:
            return None
    return _NewsIndex(category_id=category_id, posts=tuple(posts)), payload


def _save_year(snapshot: _YearSnapshot) -> None:
    try:
        cache.save_cache_entry(
            SOURCE_KEY,
            YEAR_ENTRY_KIND,
            str(snapshot.award_year),
            YEAR_CACHE_VERSION,
            records=[_record_to_cache_dict(record) for record in snapshot.records],
            source_urls=list(snapshot.source_urls),
            coverage={
                'award_year': snapshot.award_year,
                'state': snapshot.state,
            },
            ttl_seconds=_year_ttl_seconds(snapshot.award_year, snapshot.state),
        )
    except OSError:
        pass


def _load_year_disk(award_year: int) -> tuple[_YearSnapshot, dict] | None:
    payload = cache.load_cache_entry(
        SOURCE_KEY,
        YEAR_ENTRY_KIND,
        str(award_year),
        YEAR_CACHE_VERSION,
    )
    if payload is None:
        return None
    records = _records_from_payload(payload)
    coverage = payload.get('coverage')
    urls = payload.get('source_urls')
    if records is None or not isinstance(coverage, dict) or not isinstance(urls, list):
        return None
    state = coverage.get('state')
    if state not in _YEAR_STATES:
        return None
    source_urls = []
    for item in urls:
        if not isinstance(item, str) or _official_page_url(item) is None:
            return None
        source_urls.append(item)
    snapshot = _YearSnapshot(
        award_year=award_year,
        state=state,
        source_urls=tuple(source_urls),
        records=tuple(
            record for record in records if record.award_year == award_year
        ),
    )
    return snapshot, payload


def _load_live_winners() -> tuple[tuple[_ParsedRecord, ...], list[str]]:
    first_html = _fetch_html(WINNERS_ARCHIVE_URL)
    _require_archive_identity(first_html)
    first = _parse_archive_page(first_html)
    if not first.cards:
        raise RomanticNovelAwardsSourceError(
            'RNA winners archive contained no winner cards'
        )
    page_count = _discover_archive_page_count(first_html, first)
    cards = list(first.cards)
    urls = [WINNERS_ARCHIVE_URL]
    for page in range(2, page_count + 1):
        page_url = _archive_page_url(page)
        html = _fetch_html(page_url)
        _require_archive_identity(html)
        parsed = _parse_archive_page(html)
        cards.extend(parsed.cards)
        urls.append(page_url)
    included: list[_ParsedRecord] = []
    seen_slugs: set[str] = set()
    for card in cards:
        if card.slug in seen_slugs and not _is_pillow_talk_exception(card):
            continue
        seen_slugs.add(card.slug)
        record = _winner_card_to_record(card)
        if record is not None:
            included.append(record)
    if not included:
        raise RomanticNovelAwardsSourceError(
            'RNA winners archive contained no RoNA bibliographic winners'
        )
    return tuple(included), urls


def _get_news_index() -> _NewsIndex:
    global _news_index_cache
    with _cache_lock:
        if _news_index_cache is not None:
            return _news_index_cache
    disk = _load_news_index_disk()
    if disk is not None:
        index, payload = disk
        if cache.cache_is_fresh(payload) or not cache.try_claim_stale_refresh():
            with _cache_lock:
                _news_index_cache = index
            return index
        try:
            live = _acquire_live_news_index()
        except Exception:
            with _cache_lock:
                _news_index_cache = index
            return index
        _save_news_index(live)
        with _cache_lock:
            _news_index_cache = live
        return live
    live = _acquire_live_news_index()
    _save_news_index(live)
    with _cache_lock:
        _news_index_cache = live
    return live


def _acquire_live_news_index() -> _NewsIndex:
    category_id = _discover_news_category_id()
    raw_posts = _enumerate_news_posts(category_id)
    return _news_index_from_posts(category_id, raw_posts)


def _get_winners() -> tuple[_ParsedRecord, ...]:
    global _winners_cache
    with _cache_lock:
        if _winners_cache is not None:
            return _winners_cache
    disk = _load_winners_disk()
    if disk is not None:
        records, payload = disk
        if cache.cache_is_fresh(payload) or not cache.try_claim_stale_refresh():
            with _cache_lock:
                _winners_cache = records
            return records
        try:
            live, urls = _load_live_winners()
        except Exception:
            with _cache_lock:
                _winners_cache = records
            return records
        _save_winners(live, urls)
        with _cache_lock:
            _winners_cache = live
        return live
    live, urls = _load_live_winners()
    _save_winners(live, urls)
    with _cache_lock:
        _winners_cache = live
    return live


def _get_year(
    award_year: int,
    index: _NewsIndex,
    archive_winners: tuple[_ParsedRecord, ...],
) -> _YearSnapshot:
    with _cache_lock:
        ram = _year_cache.get(award_year)
    if ram is not None:
        return ram
    disk = _load_year_disk(award_year)
    if disk is not None:
        snapshot, payload = disk
        if cache.cache_is_fresh(payload) or not cache.try_claim_stale_refresh():
            with _cache_lock:
                _year_cache[award_year] = snapshot
            return snapshot
        try:
            live = _acquire_live_year(award_year, index, archive_winners)
        except Exception:
            with _cache_lock:
                _year_cache[award_year] = snapshot
            return snapshot
        _save_year(live)
        with _cache_lock:
            _year_cache[award_year] = live
        return live
    live = _acquire_live_year(award_year, index, archive_winners)
    _save_year(live)
    with _cache_lock:
        _year_cache[award_year] = live
    return live


def _acquire_live_year(
    award_year: int,
    index: _NewsIndex,
    archive_winners: tuple[_ParsedRecord, ...],
) -> _YearSnapshot:
    short_urls, win_urls = _year_urls_from_index(index, award_year)
    if not short_urls and not win_urls:
        year_archive = tuple(
            record for record in archive_winners if record.award_year == award_year
        )
        state = 'winner' if year_archive else 'absent'
        return _YearSnapshot(
            award_year=award_year,
            state=state,
            source_urls=(),
            records=year_archive if award_year != 2018 else (),
        )
    return _parse_year_pages(award_year, short_urls, win_urls, archive_winners)


def _years_to_load(index: _NewsIndex) -> tuple[int, ...]:
    years = sorted({post.award_year for post in index.posts})
    calendar_year = _current_calendar_year()
    preferred = tuple(
        year for year in (calendar_year, calendar_year - 1) if year in years
    )
    rest = tuple(year for year in years if year not in preferred)
    return preferred + rest


def _get_all_records() -> tuple[_ParsedRecord, ...]:
    index = _get_news_index()
    winners = _get_winners()
    snapshots = []
    for year in _years_to_load(index):
        try:
            snapshots.append(_get_year(year, index, winners))
        except RomanticNovelAwardsSourceError:
            continue
    return _combine_all_records(winners, tuple(snapshots))


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
        identity_kind='work',
    )


def lookup(title: str, author: str, series: str | None = None) -> list[AwardResult]:
    """Look up Romantic Novel of the Year Award results for a title and author."""
    cleaned_title = title.strip()
    cleaned_author = author.strip()
    if not cleaned_title:
        raise ValueError('title must be a non-empty string')
    if not cleaned_author:
        raise ValueError('author must be a non-empty string')

    matches: list[AwardResult] = []
    for record in _get_all_records():
        if _record_matches(record, cleaned_title, cleaned_author):
            matches.append(_to_award_result(record))
    return matches
