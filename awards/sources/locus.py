"""Official Locus Awards source (locusmag.com), winners only, 2018 forward.

Discovery uses the About the Locus Awards "Previous Winners" index. Annual
winner URLs are never guessed. Winner-post bodies are retrieved in one
WordPress REST collection request filtered by the slugs taken from those
discovered URLs. Only explicit WINNER: items in supported novel/book
categories are emitted. Rank is never inferred from list order.

Page-structure validation
-------------------------
A page is *recognized* only when an explicit WINNER: list item is associated
with a recognized Locus award-category heading.

- Supported category + WINNER: emit a record and prove structure.
- Recognized unsupported category + WINNER: prove structure, emit nothing.
- WINNER: with no recognized Locus category does not prove structure.
- Unrecognized page: LocusSourceError; harvest is incomplete and is not cached.
- Harvest that yields zero supported-category WINNER records overall:
  LocusSourceError; not cached.
"""

from __future__ import annotations

import html
import json
import re
import threading
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from urllib.parse import urlencode, urljoin, urlparse

from ..model import AwardResult

TIMEOUT_SECONDS = 30
ABOUT_URL = 'https://locusmag.com/about-the-locus-awards/'
POSTS_ENDPOINT = 'https://locusmag.com/wp-json/wp/v2/posts'
POSTS_FIELDS = 'slug,link,title,content'
EARLIEST_YEAR = 2018
MAX_POSTS_PER_PAGE = 100
OFFICIAL_HOSTS = frozenset({'locusmag.com', 'www.locusmag.com'})

_BROWSER_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/122.0.0.0 Safari/537.36'
    ),
    'Accept': (
        'application/json,text/html,application/xhtml+xml,'
        'application/xml;q=0.9,*/*;q=0.8'
    ),
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'identity',
}

_INITIALS_SPACE_RE = re.compile(r'\b([A-Za-z])\.\s+')
_YEAR_LABEL_RE = re.compile(r'(\d{4})\s*:')
_POST_TITLE_YEAR_RE = re.compile(
    r'^(\d{4}) Locus Awards Winners$',
    re.IGNORECASE,
)
_WINNER_PREFIX_RE = re.compile(r'^winner:\s*', re.IGNORECASE)
_TRAILING_RETAIL_RE = re.compile(
    r'(?:\s+(?:amazon|bookshop)(?:\s*/\s*(?:amazon|bookshop))?)+$',
    re.IGNORECASE,
)
_TRAILING_GENRE_TAG_RE = re.compile(r'\s*\[[A-Za-z]+\]\s*$')
_TRANSLATOR_RE = re.compile(r',\s*tr\.\s+.+$', re.IGNORECASE)

_SUPPORTED_CATEGORIES = {
    'science fiction novel': 'Science Fiction Novel',
    'fantasy novel': 'Fantasy Novel',
    'horror novel': 'Horror Novel',
    'first novel': 'First Novel',
    'young adult book': 'Young Adult Book',
    'young adult novel': 'Young Adult Novel',
    'translated novel': 'Translated Novel',
}

# Exact headings observed on official 2018-2026 winner pages. Not emitted.
_RECOGNIZED_UNSUPPORTED_HEADINGS = frozenset({
    'novella',
    'novelette',
    'short story',
    'anthology',
    'collection',
    'magazine',
    'publisher',
    'editor',
    'artist',
    'non-fiction',
    'art book',
    'illustrated and art book',
})


class LocusSourceError(RuntimeError):
    """Raised when official Locus winner pages cannot be retrieved or validated."""


@dataclass(frozen=True, slots=True)
class _ParsedRecord:
    award_year: int
    category: str
    work_title: str
    work_author: str
    source_url: str


@dataclass(frozen=True, slots=True)
class _WinnerPageParse:
    records: tuple[_ParsedRecord, ...]
    recognized_winner_structure: bool


# ---------------------------------------------------------------------------
# HTTP retrieval
# ---------------------------------------------------------------------------

def _build_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(CookieJar())
    )


def _read_response_body(response) -> str:
    return response.read().decode('utf-8', errors='replace')


def _header_value(headers: dict[str, str], name: str) -> str | None:
    target = name.casefold()
    for key, value in headers.items():
        if str(key).casefold() == target:
            text = str(value).strip()
            return text or None
    return None


def _fetch_response(
    opener: urllib.request.OpenerDirector,
    url: str,
) -> tuple[int, dict[str, str], str]:
    request = urllib.request.Request(url, headers=dict(_BROWSER_HEADERS))
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            status = getattr(response, 'status', None) or response.getcode()
            headers = {str(key): str(value) for key, value in response.headers.items()}
            body = _read_response_body(response)
    except urllib.error.HTTPError as exc:
        body = _read_response_body(exc)
        raise LocusSourceError(
            f'Locus request failed with HTTP {exc.code} for {url}'
            + (f': {body[:200].strip()}' if body.strip() else '')
        ) from exc
    except urllib.error.URLError as exc:
        raise LocusSourceError(
            f'Locus request failed for {url}: {exc.reason}'
        ) from exc
    return int(status), headers, body


def _fetch_html(opener: urllib.request.OpenerDirector, url: str) -> str:
    status, _headers, body = _fetch_response(opener, url)
    if status != 200:
        raise LocusSourceError(
            f'Locus request failed with HTTP {status} for {url}'
        )
    return body


def _posts_collection_url(slugs: list[str]) -> str:
    query = urlencode(
        {
            'slug': ','.join(slugs),
            'per_page': min(max(len(slugs), 1), MAX_POSTS_PER_PAGE),
            '_fields': POSTS_FIELDS,
        }
    )
    return f'{POSTS_ENDPOINT}?{query}'


def _fetch_posts_response(
    opener: urllib.request.OpenerDirector,
    slugs: list[str],
) -> tuple[int, dict[str, str], str]:
    return _fetch_response(opener, _posts_collection_url(slugs))


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def _collapse_ws(text: str) -> str:
    text = text.replace('\xa0', ' ')
    return re.sub(r'\s+', ' ', text).strip()


def _classify_heading(heading: str) -> tuple[str | None, str | None]:
    """Return (kind, supported_canonical_name).

    kind is 'supported', 'recognized', or None for an unrelated heading.
    """
    key = _collapse_ws(heading).casefold()
    if not key:
        return None, None
    supported = _SUPPORTED_CATEGORIES.get(key)
    if supported is not None:
        return 'supported', supported
    if key in _RECOGNIZED_UNSUPPORTED_HEADINGS:
        return 'recognized', None
    return None, None


def _is_official_winner_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {'http', 'https'}:
        return False
    host = (parsed.hostname or '').casefold().rstrip('.')
    return host in OFFICIAL_HOSTS


def _slug_from_url(url: str) -> str | None:
    path = (urlparse(url).path or '').strip('/')
    if not path:
        return None
    slug = path.rsplit('/', 1)[-1].strip()
    return slug or None


def _year_from_post_title(title: str) -> int | None:
    cleaned = _collapse_ws(html.unescape(title))
    match = _POST_TITLE_YEAR_RE.fullmatch(cleaned)
    if not match:
        return None
    return int(match.group(1))


def _strip_trailing_group(text: str, opener: str, closer: str) -> str:
    stripped = text.rstrip()
    if not stripped.endswith(closer):
        return stripped
    start = stripped.rfind(opener)
    if start < 0:
        return stripped
    return stripped[:start].rstrip()


def _clean_citation_text(text: str) -> str:
    cleaned = _collapse_ws(text)
    cleaned = _WINNER_PREFIX_RE.sub('', cleaned, count=1)
    cleaned = _TRAILING_RETAIL_RE.sub('', cleaned)
    cleaned = _TRAILING_GENRE_TAG_RE.sub('', cleaned)
    cleaned = _strip_trailing_group(cleaned, '(', ')')
    cleaned = _TRAILING_GENRE_TAG_RE.sub('', cleaned)
    return _collapse_ws(cleaned).rstrip(' ,')


def _clean_author(remainder: str) -> str | None:
    author = _collapse_ws(remainder)
    author = _TRANSLATOR_RE.sub('', author)
    author = _collapse_ws(author).rstrip(' ,')
    return author or None


def _parse_winner_citation(
    li_text: str,
    emphasized_title: str | None,
) -> tuple[str, str] | None:
    raw = _collapse_ws(li_text)
    if not raw or _WINNER_PREFIX_RE.match(raw) is None:
        return None
    citation = _clean_citation_text(raw)
    if not citation:
        return None

    title = None
    if emphasized_title:
        emphasized = _collapse_ws(emphasized_title)
        emphasized = _WINNER_PREFIX_RE.sub('', emphasized, count=1)
        emphasized = _collapse_ws(emphasized)
        if emphasized:
            title = emphasized

    remainder = citation
    if title:
        if remainder.casefold().startswith(title.casefold()):
            remainder = remainder[len(title):].lstrip(' ,')
        elif ',' in remainder:
            # Emphasized title could not be aligned; fall back to first comma.
            title, remainder = remainder.split(',', 1)
            title = _collapse_ws(title)
            remainder = remainder.lstrip(' ,')
        else:
            remainder = ''
    else:
        if ',' not in remainder:
            return None
        title, remainder = remainder.split(',', 1)
        title = _collapse_ws(title)
        remainder = remainder.lstrip(' ,')

    author = _clean_author(remainder)
    if not title or not author:
        return None
    return title, author


# ---------------------------------------------------------------------------
# About-page discovery
# ---------------------------------------------------------------------------

class _PreviousWinnersIndexParser(HTMLParser):
    """Collect official Winners links from the Previous Winners section only."""

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.pages: list[tuple[int, str]] = []
        self._skip_depth = 0
        self._in_h2 = False
        self._h2_parts: list[str] = []
        self._in_section = False
        self._line_parts: list[str] = []
        self._in_a = False
        self._a_href: str | None = None
        self._a_parts: list[str] = []
        self._year_at_link: int | None = None
        self._seen_urls: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {'script', 'style'}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == 'h2':
            self._in_h2 = True
            self._h2_parts = []
            return
        if tag in {'br', 'p'} and self._in_section and not self._in_a:
            self._line_parts = []
            return
        if tag == 'a' and self._in_section:
            attr = {name: (value or '') for name, value in attrs}
            self._in_a = True
            self._a_href = attr.get('href', '').strip()
            self._a_parts = []
            self._year_at_link = _year_from_line(''.join(self._line_parts))

    def handle_endtag(self, tag: str) -> None:
        if tag in {'script', 'style'} and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag == 'h2' and self._in_h2:
            heading = _collapse_ws(''.join(self._h2_parts))
            self._in_h2 = False
            self._h2_parts = []
            if heading.casefold() == 'previous winners':
                self._in_section = True
                self._line_parts = []
            elif self._in_section:
                self._in_section = False
            return
        if tag == 'a' and self._in_a:
            self._finish_link()

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in {'br', 'img', 'meta', 'link', 'hr', 'input'}:
            self.handle_endtag(tag)
        elif tag == 'br' and self._in_section and not self._in_a and not self._skip_depth:
            self._line_parts = []

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_h2:
            self._h2_parts.append(data)
        if self._in_section:
            self._line_parts.append(data)
        if self._in_a:
            self._a_parts.append(data)

    def _finish_link(self) -> None:
        href = self._a_href
        label = _collapse_ws(''.join(self._a_parts))
        year = self._year_at_link
        self._in_a = False
        self._a_href = None
        self._a_parts = []
        self._year_at_link = None
        if not href or label.casefold() != 'winners':
            return
        if year is None or year < EARLIEST_YEAR:
            return
        url = urljoin(self.base_url, href).strip()
        if not url or not _is_official_winner_url(url):
            return
        if url in self._seen_urls:
            return
        self._seen_urls.add(url)
        self.pages.append((year, url))


def _year_from_line(text: str) -> int | None:
    matches = _YEAR_LABEL_RE.findall(_collapse_ws(text))
    if not matches:
        return None
    return int(matches[-1])


def _discover_winner_pages(html: str, base_url: str = ABOUT_URL) -> list[tuple[int, str]]:
    parser = _PreviousWinnersIndexParser(base_url)
    parser.feed(html)
    parser.close()
    return parser.pages


# ---------------------------------------------------------------------------
# Winner-page parsing
# ---------------------------------------------------------------------------

class _LocusWinnerPageParser(HTMLParser):
    """Parse explicit WINNER: list items from an official Locus winners post."""

    def __init__(self, award_year: int, source_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.award_year = award_year
        self.source_url = source_url
        self.records: list[_ParsedRecord] = []
        self.recognized_winner_structure = False
        self._skip_depth = 0
        self._in_p = False
        self._p_parts: list[str] = []
        self._in_p_strong = False
        self._p_strong_tag: str | None = None
        self._p_strong_depth = 0
        self._p_strong_parts: list[str] = []
        self._in_li = False
        self._li_depth = 0
        self._skip_li_data_depth = 0
        self._li_parts: list[str] = []
        self._title_parts: list[str] = []
        self._capturing_title = False
        self._title_tag: str | None = None
        self._title_depth = 0
        self._current_kind: str | None = None
        self._current_category: str | None = None
        self._seen: set[tuple[int, str, str, str, str]] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {name: (value or '') for name, value in attrs}
        classes = attr.get('class', '').split()
        if tag in {'script', 'style'}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if self._in_li and 'purchase_links' in classes:
            self._skip_li_data_depth += 1
        if tag == 'p' and not self._in_li:
            self._in_p = True
            self._p_parts = []
            self._in_p_strong = False
            self._p_strong_tag = None
            self._p_strong_depth = 0
            self._p_strong_parts = []
            return
        if (
            self._in_p
            and not self._in_li
            and tag in {'strong', 'b'}
            and not self._in_p_strong
            and not self._p_strong_parts
        ):
            self._in_p_strong = True
            self._p_strong_tag = tag
            self._p_strong_depth = 1
        elif (
            self._in_p
            and not self._in_li
            and self._in_p_strong
            and tag == self._p_strong_tag
        ):
            self._p_strong_depth += 1
        if tag == 'li':
            if self._li_depth == 0:
                self._start_li()
            self._li_depth += 1
            return
        if (
            self._in_li
            and not self._skip_li_data_depth
            and tag in {'strong', 'b', 'em'}
            and not self._capturing_title
            and not self._title_parts
        ):
            self._capturing_title = True
            self._title_tag = tag
            self._title_depth = 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {'script', 'style'} and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if self._in_li and self._skip_li_data_depth and tag == 'span':
            self._skip_li_data_depth -= 1
        if (
            self._in_li
            and self._capturing_title
            and tag == self._title_tag
        ):
            self._title_depth -= 1
            if self._title_depth <= 0:
                self._capturing_title = False
                self._title_tag = None
            return
        if (
            self._in_p
            and not self._in_li
            and self._in_p_strong
            and tag == self._p_strong_tag
        ):
            self._p_strong_depth -= 1
            if self._p_strong_depth <= 0:
                self._in_p_strong = False
                self._p_strong_tag = None
        if tag == 'p' and self._in_p and not self._in_li:
            heading_emphasis = _collapse_ws(''.join(self._p_strong_parts))
            heading_full = _collapse_ws(''.join(self._p_parts))
            heading = heading_emphasis or heading_full
            self._in_p = False
            self._p_parts = []
            self._in_p_strong = False
            self._p_strong_tag = None
            self._p_strong_depth = 0
            self._p_strong_parts = []
            if heading:
                kind, supported = _classify_heading(heading)
                self._current_kind = kind
                self._current_category = supported
            return
        if tag == 'li' and self._li_depth:
            self._li_depth -= 1
            if self._li_depth == 0:
                self._finish_li()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_p and not self._in_li:
            self._p_parts.append(data)
            if self._in_p_strong:
                self._p_strong_parts.append(data)
        if not self._in_li or self._skip_li_data_depth:
            return
        self._li_parts.append(data)
        if self._capturing_title:
            self._title_parts.append(data)

    def _start_li(self) -> None:
        self._in_li = True
        self._skip_li_data_depth = 0
        self._li_parts = []
        self._title_parts = []
        self._capturing_title = False
        self._title_tag = None
        self._title_depth = 0

    def _finish_li(self) -> None:
        li_text = _collapse_ws(''.join(self._li_parts))
        emphasized = _collapse_ws(''.join(self._title_parts)) or None
        self._in_li = False
        self._skip_li_data_depth = 0
        self._li_parts = []
        self._title_parts = []
        self._capturing_title = False
        self._title_tag = None
        self._title_depth = 0
        if not li_text:
            return
        if _WINNER_PREFIX_RE.match(li_text) is None:
            return
        if self._current_kind in {'supported', 'recognized'}:
            self.recognized_winner_structure = True
        if self._current_kind != 'supported' or self._current_category is None:
            return
        parsed = _parse_winner_citation(li_text, emphasized)
        if parsed is None:
            return
        title, author = parsed
        key = (
            self.award_year,
            self._current_category,
            title.casefold(),
            author.casefold(),
            self.source_url,
        )
        if key in self._seen:
            return
        self._seen.add(key)
        self.records.append(
            _ParsedRecord(
                award_year=self.award_year,
                category=self._current_category,
                work_title=title,
                work_author=author,
                source_url=self.source_url,
            )
        )


def _parse_winner_page(
    html: str,
    award_year: int,
    source_url: str,
) -> _WinnerPageParse:
    parser = _LocusWinnerPageParser(award_year, source_url)
    parser.feed(html)
    parser.close()
    return _WinnerPageParse(
        records=tuple(parser.records),
        recognized_winner_structure=parser.recognized_winner_structure,
    )


# ---------------------------------------------------------------------------
# Harvest / cache
# ---------------------------------------------------------------------------

_archive_records_cache: tuple[_ParsedRecord, ...] | None = None
_cache_lock = threading.Lock()


def _usable_slug(item: object) -> str | None:
    if not isinstance(item, dict):
        return None
    slug = item.get('slug')
    if not isinstance(slug, str):
        return None
    text = slug.strip()
    return text or None


def _usable_link(item: object) -> str | None:
    if not isinstance(item, dict):
        return None
    link = item.get('link')
    if not isinstance(link, str):
        return None
    text = link.strip()
    return text or None


def _usable_title(item: object) -> str | None:
    if not isinstance(item, dict):
        return None
    title = item.get('title')
    rendered = title.get('rendered') if isinstance(title, dict) else title
    if not isinstance(rendered, str):
        return None
    text = html.unescape(rendered).strip()
    return text or None


def _usable_content(item: object) -> str | None:
    if not isinstance(item, dict):
        return None
    content = item.get('content')
    rendered = content.get('rendered') if isinstance(content, dict) else None
    if not isinstance(rendered, str):
        return None
    text = rendered.strip()
    return text or None


def _validate_posts_payload(
    status: int,
    headers: dict[str, str],
    body: str,
    expected_slugs: list[str],
    request_url: str,
) -> dict[str, dict]:
    if status != 200:
        raise LocusSourceError(
            f'Locus posts request failed with HTTP {status} for {request_url}'
        )
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise LocusSourceError(
            f'Locus posts response was not valid JSON: {exc}'
        ) from exc
    if not isinstance(payload, list):
        raise LocusSourceError('Locus posts response JSON was not a list')

    total_pages = _header_value(headers, 'X-WP-TotalPages')
    if total_pages is not None and total_pages != '1':
        raise LocusSourceError(
            'Locus posts response was paginated unexpectedly: '
            f'X-WP-TotalPages={total_pages}'
        )
    total = _header_value(headers, 'X-WP-Total')
    if total is not None:
        try:
            total_count = int(total)
        except ValueError as exc:
            raise LocusSourceError(
                f'Locus posts X-WP-Total was not an integer: {total!r}'
            ) from exc
        if len(payload) != total_count:
            raise LocusSourceError(
                'Locus posts response length did not match X-WP-Total: '
                f'{len(payload)} != {total_count}'
            )

    by_slug: dict[str, dict] = {}
    for index, item in enumerate(payload):
        slug = _usable_slug(item)
        if slug is None:
            raise LocusSourceError(
                f'Locus posts item {index} is missing a usable slug'
            )
        if _usable_link(item) is None:
            raise LocusSourceError(
                f'Locus posts item {index} is missing a usable link'
            )
        if _usable_title(item) is None:
            raise LocusSourceError(
                f'Locus posts item {index} is missing a usable title.rendered'
            )
        if _usable_content(item) is None:
            raise LocusSourceError(
                f'Locus posts item {index} is missing usable content.rendered'
            )
        if slug in by_slug:
            raise LocusSourceError(
                f'Locus posts response contained duplicate slug {slug!r}'
            )
        by_slug[slug] = item

    expected_set = set(expected_slugs)
    extra = sorted(set(by_slug) - expected_set)
    if extra:
        raise LocusSourceError(
            'Locus posts response contained unexpected slugs: '
            + ', '.join(extra)
        )
    missing = [slug for slug in expected_slugs if slug not in by_slug]
    if missing:
        raise LocusSourceError(
            'Locus posts response was missing discovered winner slugs: '
            + ', '.join(missing)
        )
    return by_slug


def _discovered_slugs(discovered: list[tuple[int, str]]) -> list[str]:
    slugs: list[str] = []
    seen: set[str] = set()
    for year, url in discovered:
        slug = _slug_from_url(url)
        if slug is None:
            raise LocusSourceError(
                f'Locus winner URL has no usable slug: {url}'
            )
        if slug in seen:
            raise LocusSourceError(
                f'Locus About page mapped multiple years to slug {slug!r}'
            )
        seen.add(slug)
        slugs.append(slug)
    return slugs


def _harvest_records() -> tuple[_ParsedRecord, ...]:
    opener = _build_opener()
    about_html = _fetch_html(opener, ABOUT_URL)
    discovered = _discover_winner_pages(about_html, ABOUT_URL)
    if not discovered:
        raise LocusSourceError(
            'Locus About page did not yield any 2018+ official winner pages'
        )
    if len(discovered) > MAX_POSTS_PER_PAGE:
        raise LocusSourceError(
            'Locus About page listed more winner years than one REST '
            f'collection page can retrieve ({len(discovered)} > {MAX_POSTS_PER_PAGE})'
        )
    slugs = _discovered_slugs(discovered)
    request_url = _posts_collection_url(slugs)
    status, headers, body = _fetch_posts_response(opener, slugs)
    posts_by_slug = _validate_posts_payload(
        status, headers, body, slugs, request_url
    )
    records: list[_ParsedRecord] = []
    for year, url in discovered:
        slug = _slug_from_url(url)
        if slug is None:
            raise LocusSourceError(
                f'Locus winner URL has no usable slug: {url}'
            )
        item = posts_by_slug[slug]
        title = _usable_title(item)
        content = _usable_content(item)
        if title is None or content is None:
            raise LocusSourceError(
                f'Locus posts item for {url} lost usable title or content'
            )
        title_year = _year_from_post_title(title)
        if title_year is None:
            raise LocusSourceError(
                'Locus post title did not identify a single award year: '
                f'{title!r} for {url}'
            )
        if title_year != year:
            raise LocusSourceError(
                'Locus About-page year did not match official post title: '
                f'about={year} title={title!r} url={url}'
            )
        parsed = _parse_winner_page(content, year, url)
        if not parsed.recognized_winner_structure:
            raise LocusSourceError(
                'Locus winner page did not contain recognizable WINNER: '
                f'structure: {url}'
            )
        records.extend(parsed.records)
    if not records:
        raise LocusSourceError(
            'Locus winner pages were retrieved but no explicit '
            'supported-category WINNER records could be parsed'
        )
    return tuple(records)


def _get_archive_records() -> tuple[_ParsedRecord, ...]:
    """Return cached winner records, fetching once per process on success."""
    global _archive_records_cache
    with _cache_lock:
        if _archive_records_cache is not None:
            return _archive_records_cache
        records = _harvest_records()
        _archive_records_cache = records
        return _archive_records_cache


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
        .replace('\u2026', '...')
    )
    text = _collapse_ws(text)
    text = text.casefold()
    text = _INITIALS_SPACE_RE.sub(r'\1.', text)
    return text


def _titles_equivalent(query_title: str, record_title: str) -> bool:
    query_norm = _normalize_text(query_title)
    record_norm = _normalize_text(record_title)
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


def _record_matches(record: _ParsedRecord, title: str, author: str) -> bool:
    return _titles_equivalent(title, record.work_title) and (
        _normalize_text(author) == _normalize_text(record.work_author)
    )


def _to_award_result(record: _ParsedRecord) -> AwardResult:
    return AwardResult(
        work_title=record.work_title,
        work_author=record.work_author,
        award_name='Locus Award',
        award_year=record.award_year,
        category=record.category,
        status='Winner',
        rank=None,
        source_name='Locus Awards',
        source_url=record.source_url,
        notes=None,
    )


# ---------------------------------------------------------------------------
# Public lookup
# ---------------------------------------------------------------------------

def lookup(title: str, author: str) -> list[AwardResult]:
    """Look up Locus Award novel/book winners for a title and author."""
    cleaned_title = title.strip()
    cleaned_author = author.strip()
    if not cleaned_title:
        raise ValueError('title must be a non-empty string')
    if not cleaned_author:
        raise ValueError('author must be a non-empty string')

    matches: list[AwardResult] = []
    seen: set[tuple[int, str, str, str, str]] = set()
    for record in _get_archive_records():
        if not _record_matches(record, cleaned_title, cleaned_author):
            continue
        key = (
            record.award_year,
            record.category,
            record.work_title.casefold(),
            record.work_author.casefold(),
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
            result.work_title.casefold(),
        )
    )
    return matches
