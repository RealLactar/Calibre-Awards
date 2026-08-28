"""Official Hugo Awards written-work and series source (thehugoawards.org).

The WordPress pages API is the archive. Ordinary year pages establish
Winner/Finalist status, not ordinal placement. Curated statistics ranks are
applied later only when they match that live record exactly. A validated
parsed archive may also be loaded from the injected persistent cache.
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
from urllib.parse import urlencode

from .. import cache
from ..matching import normalize_title_conjunctions
from ..model import AwardResult
from .hugo_rankings import HugoRanking, HUGO_BEST_NOVEL_RANKINGS

TIMEOUT_SECONDS = 30
SOURCE_HOME_URL = 'https://www.thehugoawards.org/'
PAGES_ENDPOINT = 'https://www.thehugoawards.org/wp-json/wp/v2/pages'
HISTORY_PARENT_PAGE_ID = 6
# One complete API page is required. Extra WP pages must fail, not drop history.
ARCHIVE_PER_PAGE = 100
ARCHIVE_FIELDS = 'title,link,slug,content'

SOURCE_KEY = 'hugo'
CACHE_VERSION = 1
# 7-day base plus an explicit stagger. Do not derive from AWARD_SOURCES order.
CACHE_BASE_TTL_SECONDS = 7 * 24 * 60 * 60
CACHE_REFRESH_OFFSET_SECONDS = 2 * 60 * 60
CACHE_TTL_SECONDS = CACHE_BASE_TTL_SECONDS + CACHE_REFRESH_OFFSET_SECONDS

_BROWSER_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/122.0.0.0 Safari/537.36'
    ),
    'Accept': 'application/json,text/html;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'identity',
}

_REGULAR_YEAR_TITLE_RE = re.compile(r'^(\d{4}) Hugo Awards$')
_INITIALS_SPACE_RE = re.compile(r'\b([A-Za-z])\.\s+')
_ALT_TITLE_RE = re.compile(
    r'^(?P<primary>.*)\(\s*alt:\s*(?P<alt>.+)\)\s*$',
    re.IGNORECASE | re.DOTALL,
)
_BY_AUTHOR_RE = re.compile(r'^,?\s*by\s+(?P<author>.+)$', re.IGNORECASE | re.DOTALL)
_COMMA_AUTHOR_RE = re.compile(r'^,\s+(?P<author>.+)$', re.DOTALL)
_TIE_SUFFIX_RE = re.compile(r'\s*\(tie\)\s*$', re.IGNORECASE)
_BALLOT_COUNT_NOTE_RE = re.compile(
    r'^\(\s*'
    r'(?:\d{1,3}(?:,\d{3})+|\d+)'
    r'\s+final\s+ballots?'
    r',\s*'
    r'(?:\d{1,3}(?:,\d{3})+|\d+)'
    r'\s+nominating\s+ballots?'
    r'(?:\s*,\s*[^)]+)?'
    r'\s*\)$',
    re.IGNORECASE,
)
_NOMINATING_ONLY_BALLOT_NOTE_RE = re.compile(
    r'^\(\s*'
    r'(?:\d{1,3}(?:,\d{3})+|\d+)'
    r'\s+nominating\s+ballots?'
    r'\s*\)$',
    re.IGNORECASE,
)
_UNPAREN_BALLOT_NOTE_RE = re.compile(
    r'^(?:\d{1,3}(?:,\d{3})+|\d+)\s+'
    r'(?:final\s+ballots?\s+cast|nominating\s+ballots?)\b.*$',
    re.IGNORECASE,
)
_TRANSLATOR_AUTHOR_SUFFIX_RE = re.compile(
    r',\s*(?:translated by\s+.+|.+\s+translator)\s*$',
    re.IGNORECASE,
)
_WORD_SEPARATOR_HYPHEN_RE = re.compile(
    r'(\w)[\u2010\u2011\u2012\u2013\u2014\u2212-](\w)'
)
_QUOTATION_PUNCTUATION_APOSTROPHE_RE = re.compile(r"(?<!\w)'|'(?!\w)")
_SERIES_LEADING_THE_RE = re.compile(r'^the\s+')
_SERIES_TRAILING_WRAPPER_RE = re.compile(r'\s+(?:series|books)$')
_SERIES_BY_SPLIT_RE = re.compile(r',?\s+by\s+', re.IGNORECASE)
_LEADING_QUOTED_TITLE_RE = re.compile(
    r'^(?:'
    r'\u201c(?P<curly_title>.+?)\u201d'
    r'|'
    r'"(?P<straight_title>.+?)"'
    r')\s*(?P<remainder>.*)$',
    re.DOTALL,
)
_UNOPENED_QUOTED_TITLE_RE = re.compile(
    r'^(?P<title>[^\u201c"]+?)[\u201d"]\s*(?P<remainder>.*)$',
    re.DOTALL,
)
_RELATED_CALIBRE_ROLE_RE = re.compile(
    r'\(\s*(?:eds?\.?|editors?)\s*\)\s*$',
    re.IGNORECASE,
)
_RELATED_SOURCE_ROLE_RE = re.compile(
    r',\s*(?:eds?\.|editors?)\s*$',
    re.IGNORECASE,
)
_RELATED_AND_SPLIT_RE = re.compile(r'\s+(?:and|&)\s+', re.IGNORECASE)
_RELATED_COMPLEX_CREDIT_RE = re.compile(
    r';|\bwith\b|\bintro\.|\bfwd\.|\bappendix\b|\btranslated\s+by\b',
    re.IGNORECASE,
)
_RELATED_GENERATIONAL_SUFFIX_RE = re.compile(
    r'^(?:Jr\.?|Sr\.?|II|III|IV)$',
    re.IGNORECASE,
)
_CALIBRE_AMP_PLACEHOLDER = '\uffff'

CATEGORY_BEST_NOVEL = 'Best Novel'
CATEGORY_BEST_NOVELLA = 'Best Novella'
CATEGORY_BEST_NOVELETTE = 'Best Novelette'
CATEGORY_BEST_SHORT_STORY = 'Best Short Story'
CATEGORY_SHORT_FICTION = 'Short Fiction'
CATEGORY_BEST_NOVEL_OR_NOVELETTE = 'Best Novel or Novelette'
CATEGORY_BEST_SERIES = 'Best Series'
CATEGORY_BEST_ALL_TIME_SERIES = 'Best All-Time Series'
CATEGORY_BEST_POEM = 'Best Poem'
CATEGORY_BEST_RELATED_NON_FICTION_BOOK = 'Best Related Non-Fiction Book'
CATEGORY_BEST_RELATED_BOOK = 'Best Related Book'
_SUPPORTED_CATEGORIES = (
    CATEGORY_BEST_NOVEL,
    CATEGORY_BEST_NOVELLA,
    CATEGORY_BEST_NOVELETTE,
    CATEGORY_BEST_SHORT_STORY,
    CATEGORY_SHORT_FICTION,
    CATEGORY_BEST_NOVEL_OR_NOVELETTE,
    CATEGORY_BEST_POEM,
    CATEGORY_BEST_RELATED_NON_FICTION_BOOK,
    CATEGORY_BEST_RELATED_BOOK,
)
_RELATED_BOOK_CATEGORIES = frozenset(
    {
        CATEGORY_BEST_RELATED_NON_FICTION_BOOK,
        CATEGORY_BEST_RELATED_BOOK,
    }
)
_SERIES_CATEGORIES = frozenset(
    {
        CATEGORY_BEST_SERIES,
        CATEGORY_BEST_ALL_TIME_SERIES,
    }
)
_SUPPORTED_CATEGORY_SET = frozenset(_SUPPORTED_CATEGORIES)
_PARSED_CATEGORIES = _SUPPORTED_CATEGORIES + (
    CATEGORY_BEST_SERIES,
    CATEGORY_BEST_ALL_TIME_SERIES,
)
_NOVELLA_REQUIRED_FROM_YEAR = 1968
_EARLY_NOVELETTE_YEARS = frozenset({1955, 1956, 1959, 1967, 1968, 1969})
_NOVELETTE_REQUIRED_FROM_YEAR = 1973
_EARLY_SHORT_STORY_YEARS = frozenset({1955, 1956, 1958, 1959})
_SHORT_STORY_REQUIRED_FROM_YEAR = 1967
_SHORT_FICTION_FROM_YEAR = 1960
_SHORT_FICTION_THROUGH_YEAR = 1966
_BEST_NOVEL_GAP_YEARS = frozenset({1957, 1958})
_BEST_SERIES_REQUIRED_FROM_YEAR = 2017
_BEST_ALL_TIME_SERIES_YEARS = frozenset({1966})
_BEST_POEM_YEARS = frozenset({2025, 2026})
_BEST_RELATED_NON_FICTION_BOOK_YEARS = frozenset(range(1980, 1999)) | frozenset(
    {2003, 2004, 2005, 2006}
)
_BEST_RELATED_BOOK_YEARS = frozenset(
    {1999, 2000, 2001, 2002, 2007, 2008, 2009}
)


class HugoSourceError(RuntimeError):
    """Raised when the official Hugo archive cannot be retrieved or validated."""


@dataclass(frozen=True, slots=True)
class _ParsedRecord:
    award_year: int
    category: str
    status: str
    work_title: str
    work_author: str
    source_url: str
    match_titles: tuple[str, ...]


_PARSED_STATUSES = frozenset({'Winner', 'Finalist'})
_RECORD_CACHE_FIELDS = (
    'award_year',
    'category',
    'match_titles',
    'source_url',
    'status',
    'work_author',
    'work_title',
)
# Regular Worldcon years with no "YYYY Hugo Awards" page (1954 was Retro only).
_ARCHIVE_FIRST_REGULAR_YEAR = 1953
_ARCHIVE_SKIPPED_REGULAR_YEARS = frozenset({1954})


# ---------------------------------------------------------------------------
# HTTP retrieval
# ---------------------------------------------------------------------------

def _archive_url() -> str:
    query = urlencode(
        {
            'parent': HISTORY_PARENT_PAGE_ID,
            'per_page': ARCHIVE_PER_PAGE,
            '_fields': ARCHIVE_FIELDS,
        }
    )
    return f'{PAGES_ENDPOINT}?{query}'


def _build_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(CookieJar())
    )


def _read_response_body(response) -> str:
    return response.read().decode('utf-8', errors='replace')


def _header_value(headers, name: str) -> str | None:
    target = name.casefold()
    for key, value in headers.items():
        if str(key).casefold() == target:
            text = str(value).strip()
            return text or None
    return None


def _fetch_archive_response() -> tuple[int, dict[str, str], str]:
    request = urllib.request.Request(_archive_url(), headers=dict(_BROWSER_HEADERS))
    opener = _build_opener()
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            status = getattr(response, 'status', None) or response.getcode()
            headers = {str(key): str(value) for key, value in response.headers.items()}
            body = _read_response_body(response)
    except urllib.error.HTTPError as exc:
        body = _read_response_body(exc)
        raise HugoSourceError(
            f'Hugo request failed with HTTP {exc.code} for {_archive_url()}'
            + (f': {body[:200].strip()}' if body.strip() else '')
        ) from exc
    except urllib.error.URLError as exc:
        raise HugoSourceError(
            f'Hugo request failed for {_archive_url()}: {exc.reason}'
        ) from exc
    return int(status), headers, body


# ---------------------------------------------------------------------------
# Archive validation and year-page filtering
# ---------------------------------------------------------------------------

def _usable_title(item: object) -> str | None:
    if not isinstance(item, dict):
        return None
    title = item.get('title')
    rendered = title.get('rendered') if isinstance(title, dict) else title
    if not isinstance(rendered, str):
        return None
    text = html.unescape(rendered).strip()
    return text or None


def _usable_link(item: object) -> str | None:
    if not isinstance(item, dict):
        return None
    link = item.get('link')
    if not isinstance(link, str):
        return None
    text = link.strip()
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


def _validate_archive_payload(
    status: int,
    headers: dict[str, str],
    body: str,
) -> list[dict]:
    if status != 200:
        raise HugoSourceError(
            f'Hugo archive request failed with HTTP {status} for {_archive_url()}'
        )
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HugoSourceError(
            f'Hugo archive response was not valid JSON: {exc}'
        ) from exc
    if not isinstance(payload, list):
        raise HugoSourceError('Hugo archive response JSON was not a list')
    if not payload:
        raise HugoSourceError('Hugo archive response list was empty')

    total_pages = _header_value(headers, 'X-WP-TotalPages')
    if total_pages is not None and total_pages != '1':
        # Prefer a loud failure over silently omitting years beyond this page.
        raise HugoSourceError(
            'Hugo archive response was paginated unexpectedly: '
            f'X-WP-TotalPages={total_pages}'
        )
    total = _header_value(headers, 'X-WP-Total')
    if total is not None:
        try:
            total_count = int(total)
        except ValueError as exc:
            raise HugoSourceError(
                f'Hugo archive X-WP-Total was not an integer: {total!r}'
            ) from exc
        if len(payload) != total_count:
            raise HugoSourceError(
                'Hugo archive response length did not match X-WP-Total: '
                f'{len(payload)} != {total_count}'
            )

    items: list[dict] = []
    for index, item in enumerate(payload):
        if _usable_title(item) is None:
            raise HugoSourceError(
                f'Hugo archive item {index} is missing a usable title.rendered'
            )
        if _usable_link(item) is None:
            raise HugoSourceError(
                f'Hugo archive item {index} is missing a usable link'
            )
        if _usable_content(item) is None:
            raise HugoSourceError(
                f'Hugo archive item {index} is missing usable content.rendered'
            )
        items.append(item)
    return items


def _regular_year_from_title(title: str) -> int | None:
    match = _REGULAR_YEAR_TITLE_RE.fullmatch(title)
    if not match:
        return None
    return int(match.group(1))


# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------

def _collapse_ws(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def _is_ballot_count_note(text: str) -> bool:
    cleaned = _collapse_ws(text)
    if not cleaned:
        return False
    return (
        _BALLOT_COUNT_NOTE_RE.fullmatch(cleaned) is not None
        or _NOMINATING_ONLY_BALLOT_NOTE_RE.fullmatch(cleaned) is not None
        or _UNPAREN_BALLOT_NOTE_RE.fullmatch(cleaned) is not None
    )


def _is_non_work(text: str) -> bool:
    cleaned = _collapse_ws(text).casefold()
    if not cleaned:
        return True
    # No Award / insufficient nominations are archive notes, not works.
    if cleaned == 'no award':
        return True
    if cleaned == 'no winner chosen':
        return True
    if cleaned.startswith('insufficient nominations'):
        return True
    return False


def _strip_trailing_group(text: str, opener: str, closer: str) -> str:
    stripped = text.rstrip()
    if not stripped.endswith(closer):
        return stripped
    depth = 0
    for index in range(len(stripped) - 1, -1, -1):
        character = stripped[index]
        if character == closer:
            depth += 1
        elif character == opener:
            depth -= 1
            if depth == 0:
                return stripped[:index].rstrip()
    return stripped


def _parse_author_remainder(remainder: str) -> str | None:
    text = _collapse_ws(remainder)
    text = _TIE_SUFFIX_RE.sub('', text).rstrip()
    text = _strip_trailing_group(text, '[', ']')
    text = _strip_trailing_group(text, '(', ')')
    text = _collapse_ws(text).rstrip(' ,')
    if not text:
        return None
    by_match = _BY_AUTHOR_RE.match(text)
    if by_match:
        author = _collapse_ws(by_match.group('author'))
        return author or None
    comma_match = _COMMA_AUTHOR_RE.match(text)
    if comma_match:
        author = _collapse_ws(comma_match.group('author'))
        return author or None
    return None


def _strip_wrapping_quotes(title: str) -> str:
    text = _collapse_ws(title)
    if len(text) >= 2:
        curly = text[0] == '\u201c' and text[-1] == '\u201d'
        straight = text[0] == '"' and text[-1] == '"'
        if curly or straight:
            inner = text[1:-1].strip()
            if inner:
                return inner
    return text


def _parse_leading_quoted_title(text: str) -> tuple[str, str] | None:
    cleaned = _collapse_ws(text)
    match = _LEADING_QUOTED_TITLE_RE.match(cleaned)
    if match is None:
        return None
    title = _collapse_ws(
        match.group('curly_title') or match.group('straight_title') or ''
    )
    if not title or not any(character.isalpha() for character in title):
        return None
    if _is_non_work(title):
        return None
    return title, match.group('remainder') or ''


def _parse_unopened_quoted_title(text: str) -> tuple[str, str] | None:
    """Recover a title that ends with a closer but is missing its opener.

    Restricted to the known 2010 Best Novelette winner HTML
    (The Island”, Peter Watts). Do not reuse this as a generic
    malformed-title heuristic.
    """
    cleaned = _collapse_ws(text)
    match = _UNOPENED_QUOTED_TITLE_RE.match(cleaned)
    if match is None:
        return None
    title = _collapse_ws(match.group('title') or '')
    remainder = match.group('remainder') or ''
    if not title or not any(character.isalpha() for character in title):
        return None
    if _is_non_work(title):
        return None
    if _parse_author_remainder(remainder) is None:
        return None
    return title, remainder


def _primary_and_match_titles(displayed_title: str) -> tuple[str, tuple[str, ...]]:
    displayed = _collapse_ws(displayed_title)
    match = _ALT_TITLE_RE.fullmatch(displayed)
    if match is None:
        return displayed, (displayed,)
    primary = _collapse_ws(match.group('primary'))
    alternate = _collapse_ws(match.group('alt'))
    if not primary:
        return displayed, (displayed,)
    # Aliases are extra match keys; the displayed official title stays primary.
    titles = [primary]
    if displayed not in titles:
        titles.append(displayed)
    if alternate and alternate not in titles:
        titles.append(alternate)
    return primary, tuple(titles)


class _HugoCategoryParser(HTMLParser):
    """Parse one Hugo year page for one exact supported category heading."""

    def __init__(self, award_year: int, source_url: str, category: str) -> None:
        super().__init__(convert_charrefs=True)
        if category not in _SUPPORTED_CATEGORY_SET:
            raise ValueError(f'unsupported Hugo category: {category!r}')
        self.award_year = award_year
        self.source_url = source_url
        self.category = category
        self.records: list[_ParsedRecord] = []
        self._strong_parts: list[str] = []
        self._in_strong = False
        self._pending_category = False
        self._in_category_list = False
        self._list_depth = 0
        self._li_depth = 0
        self._capturing_li = False
        self._li_is_winner = False
        self._title_parts: list[str] = []
        self._remainder_parts: list[str] = []
        self._all_parts: list[str] = []
        self._in_title_tag = False
        self._title_tag: str | None = None
        self._title_depth = 0
        self._title_finished = False
        self._seen: set[tuple[int, str, str, str, str, str]] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {name: (value or '') for name, value in attrs}

        if tag == 'strong' and not self._capturing_li:
            self._in_strong = True
            self._strong_parts = []

        if (
            self._pending_category
            and not self._in_category_list
            and tag not in {'ul', 'br'}
        ):
            self._pending_category = False

        if tag == 'ul':
            if self._pending_category and not self._in_category_list:
                self._in_category_list = True
                self._list_depth = 1
                self._pending_category = False
            elif self._in_category_list:
                self._list_depth += 1

        if tag == 'li' and self._in_category_list:
            if self._li_depth == 0:
                classes = attr.get('class', '').split()
                self._start_li(winner='winner' in classes)
            self._li_depth += 1
            return

        if (
            self._capturing_li
            and not self._title_finished
            and tag in {'em', 'strong'}
        ):
            self._begin_title(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == 'strong' and self._in_strong and not self._capturing_li:
            heading = _collapse_ws(''.join(self._strong_parts))
            self._in_strong = False
            self._strong_parts = []
            if heading == self.category:
                self._pending_category = True
            elif heading:
                self._pending_category = False
            return

        if self._capturing_li and self._in_title_tag and tag == self._title_tag:
            self._title_depth -= 1
            if self._title_depth <= 0:
                self._in_title_tag = False
                self._title_tag = None
                self._title_finished = True
            return

        if tag == 'li' and self._in_category_list and self._li_depth:
            self._li_depth -= 1
            if self._li_depth == 0:
                self._finish_li()
            return

        if tag == 'ul' and self._in_category_list:
            self._list_depth -= 1
            if self._list_depth <= 0:
                self._in_category_list = False
                self._list_depth = 0
                self._pending_category = False

    def handle_data(self, data: str) -> None:
        if self._in_strong and not self._capturing_li:
            self._strong_parts.append(data)
        if (
            self._pending_category
            and not self._in_category_list
            and not self._capturing_li
            and _collapse_ws(data)
            and not _is_ballot_count_note(data)
        ):
            self._pending_category = False
        if not self._capturing_li:
            return
        self._all_parts.append(data)
        if self._in_title_tag:
            self._title_parts.append(data)
        else:
            self._remainder_parts.append(data)

    def _begin_title(self, tag: str) -> None:
        if self._in_title_tag and tag == self._title_tag:
            self._title_depth += 1
            return
        if self._in_title_tag or self._title_finished:
            return
        if _parse_leading_quoted_title(''.join(self._all_parts)) is not None:
            return
        self._in_title_tag = True
        self._title_tag = tag
        self._title_depth = 1
        self._remainder_parts = []

    def _start_li(self, *, winner: bool) -> None:
        self._capturing_li = True
        self._li_is_winner = winner
        self._title_parts = []
        self._remainder_parts = []
        self._all_parts = []
        self._in_title_tag = False
        self._title_tag = None
        self._title_depth = 0
        self._title_finished = False

    def _allows_unopened_quote_recovery(self) -> bool:
        # Exact year/category only; other malformed quotes stay unmatched.
        return (
            self.award_year == 2010
            and self.category == CATEGORY_BEST_NOVELETTE
        )

    def _try_unopened_quoted_title(self, full_text: str) -> tuple[str, str] | None:
        if not self._allows_unopened_quote_recovery():
            return None
        return _parse_unopened_quoted_title(full_text)

    def _finish_li(self) -> None:
        capturing = self._capturing_li
        winner = self._li_is_winner
        tagged_title = _strip_wrapping_quotes(''.join(self._title_parts))
        tagged_remainder = ''.join(self._remainder_parts)
        full_text = _collapse_ws(''.join(self._all_parts))
        self._capturing_li = False
        self._li_is_winner = False
        self._title_parts = []
        self._remainder_parts = []
        self._all_parts = []
        self._in_title_tag = False
        self._title_tag = None
        self._title_depth = 0
        self._title_finished = False
        if not capturing:
            return
        if _is_non_work(full_text):
            return
        quoted = _parse_leading_quoted_title(full_text)
        if quoted is not None:
            title_text, remainder = quoted
        elif tagged_title and not _is_non_work(tagged_title):
            tagged_author = _parse_author_remainder(tagged_remainder)
            if tagged_author:
                title_text = tagged_title
                remainder = tagged_remainder
            else:
                malformed = self._try_unopened_quoted_title(full_text)
                if malformed is None:
                    return
                title_text, remainder = malformed
        else:
            malformed = self._try_unopened_quoted_title(full_text)
            if malformed is None:
                return
            title_text, remainder = malformed
        if not title_text:
            return
        author = _parse_author_remainder(remainder)
        if not author:
            return
        work_title, match_titles = _primary_and_match_titles(title_text)
        if not work_title:
            return
        status = 'Winner' if winner else 'Finalist'
        key = (
            self.award_year,
            self.category,
            status,
            work_title.casefold(),
            author.casefold(),
            self.source_url,
        )
        if key in self._seen:
            return
        self._seen.add(key)
        self.records.append(
            _ParsedRecord(
                award_year=self.award_year,
                category=self.category,
                status=status,
                work_title=work_title,
                work_author=author,
                source_url=self.source_url,
                match_titles=match_titles,
            )
        )


def _parse_category_html(
    page_html: str,
    award_year: int,
    source_url: str,
    category: str,
) -> list[_ParsedRecord]:
    parser = _HugoCategoryParser(award_year, source_url, category)
    parser.feed(page_html)
    parser.close()
    return parser.records


def _parse_best_novel_html(
    page_html: str,
    award_year: int,
    source_url: str,
) -> list[_ParsedRecord]:
    return _parse_category_html(
        page_html,
        award_year,
        source_url,
        CATEGORY_BEST_NOVEL,
    )


def _split_series_name_and_author(full_text: str) -> tuple[str, str] | None:
    """Split a series-category ballot row into official series name and author."""
    text = _collapse_ws(full_text)
    if _is_non_work(text):
        return None
    text = _TIE_SUFFIX_RE.sub('', text).rstrip()
    text = _strip_trailing_group(text, '[', ']')
    text = _strip_trailing_group(text, '(', ')')
    text = _collapse_ws(text).rstrip(' ,')
    if not text:
        return None
    by_match = _SERIES_BY_SPLIT_RE.search(text)
    if by_match is not None:
        series_name = _collapse_ws(text[: by_match.start()])
        author = _collapse_ws(text[by_match.end() :])
    else:
        comma_at = text.find(', ')
        if comma_at <= 0:
            return None
        series_name = _collapse_ws(text[:comma_at])
        author = _collapse_ws(text[comma_at + 1 :])
    if not series_name or not author:
        return None
    if _is_non_work(series_name) or _is_non_work(author):
        return None
    return series_name, author


class _HugoBestSeriesParser(HTMLParser):
    """Parse the first ballot list for one series-level Hugo category.

    Book-title parsing is intentionally not used. Series identity is the
    visible list-item text, not the first <em> or <strong>. Later
    eligibility/declined note blocks are ignored after the first ballot
    list. Definition text (including 2017 <small>) does not cancel the
    wait for that list.
    """

    def __init__(
        self,
        award_year: int,
        source_url: str,
        category: str = CATEGORY_BEST_SERIES,
    ) -> None:
        super().__init__(convert_charrefs=True)
        if category not in _SERIES_CATEGORIES:
            raise ValueError(f'unsupported Hugo series category: {category!r}')
        self.award_year = award_year
        self.source_url = source_url
        self.category = category
        self.records: list[_ParsedRecord] = []
        self._strong_parts: list[str] = []
        self._in_strong = False
        self._pending_ballot = False
        self._have_ballot_list = False
        self._in_ballot_list = False
        self._list_depth = 0
        self._li_depth = 0
        self._capturing_li = False
        self._li_is_winner = False
        self._all_parts: list[str] = []
        self._seen: set[tuple[int, str, str, str, str, str]] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {name: (value or '') for name, value in attrs}

        if tag == 'strong' and not self._capturing_li:
            self._in_strong = True
            self._strong_parts = []

        if tag == 'ul':
            if (
                self._pending_ballot
                and not self._have_ballot_list
                and not self._in_ballot_list
            ):
                self._in_ballot_list = True
                self._list_depth = 1
                self._pending_ballot = False
            elif self._in_ballot_list:
                self._list_depth += 1

        if tag == 'li' and self._in_ballot_list:
            if self._li_depth == 0:
                classes = attr.get('class', '').split()
                self._start_li(winner='winner' in classes)
            self._li_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == 'strong' and self._in_strong and not self._capturing_li:
            heading = _collapse_ws(''.join(self._strong_parts))
            self._in_strong = False
            self._strong_parts = []
            if heading == self.category and not self._have_ballot_list:
                self._pending_ballot = True
            elif heading:
                self._pending_ballot = False
            return

        if tag == 'li' and self._in_ballot_list and self._li_depth:
            self._li_depth -= 1
            if self._li_depth == 0:
                self._finish_li()
            return

        if tag == 'ul' and self._in_ballot_list:
            self._list_depth -= 1
            if self._list_depth <= 0:
                self._in_ballot_list = False
                self._list_depth = 0
                self._have_ballot_list = True
                self._pending_ballot = False

    def handle_data(self, data: str) -> None:
        if self._in_strong and not self._capturing_li:
            self._strong_parts.append(data)
        if self._capturing_li:
            self._all_parts.append(data)

    def _start_li(self, *, winner: bool) -> None:
        self._capturing_li = True
        self._li_is_winner = winner
        self._all_parts = []

    def _finish_li(self) -> None:
        capturing = self._capturing_li
        winner = self._li_is_winner
        full_text = _collapse_ws(''.join(self._all_parts))
        self._capturing_li = False
        self._li_is_winner = False
        self._all_parts = []
        if not capturing:
            return
        parsed = _split_series_name_and_author(full_text)
        if parsed is None:
            return
        series_name, author = parsed
        status = 'Winner' if winner else 'Finalist'
        key = (
            self.award_year,
            self.category,
            status,
            series_name.casefold(),
            author.casefold(),
            self.source_url,
        )
        if key in self._seen:
            return
        self._seen.add(key)
        self.records.append(
            _ParsedRecord(
                award_year=self.award_year,
                category=self.category,
                status=status,
                work_title=series_name,
                work_author=author,
                source_url=self.source_url,
                match_titles=(series_name,),
            )
        )


def _parse_series_category_html(
    page_html: str,
    award_year: int,
    source_url: str,
    category: str,
) -> list[_ParsedRecord]:
    parser = _HugoBestSeriesParser(award_year, source_url, category=category)
    parser.feed(page_html)
    parser.close()
    return parser.records


def _parse_best_series_html(
    page_html: str,
    award_year: int,
    source_url: str,
) -> list[_ParsedRecord]:
    return _parse_series_category_html(
        page_html,
        award_year,
        source_url,
        CATEGORY_BEST_SERIES,
    )


def _parse_supported_categories_html(
    page_html: str,
    award_year: int,
    source_url: str,
) -> list[_ParsedRecord]:
    records: list[_ParsedRecord] = []
    for category in _SUPPORTED_CATEGORIES:
        records.extend(
            _parse_category_html(page_html, award_year, source_url, category)
        )
    records.extend(
        _parse_series_category_html(
            page_html, award_year, source_url, CATEGORY_BEST_SERIES
        )
    )
    records.extend(
        _parse_series_category_html(
            page_html,
            award_year,
            source_url,
            CATEGORY_BEST_ALL_TIME_SERIES,
        )
    )
    return records


def _regular_years_from_items(items: list[dict]) -> set[int]:
    years: set[int] = set()
    for item in items:
        title = _usable_title(item)
        if title is None:
            continue
        year = _regular_year_from_title(title)
        if year is not None:
            years.add(year)
    return years


def _year_requires_best_novel(year: int) -> bool:
    return year not in _BEST_NOVEL_GAP_YEARS


def _year_requires_novelette(year: int) -> bool:
    return year in _EARLY_NOVELETTE_YEARS or year >= _NOVELETTE_REQUIRED_FROM_YEAR


def _year_requires_short_story(year: int) -> bool:
    return year in _EARLY_SHORT_STORY_YEARS or year >= _SHORT_STORY_REQUIRED_FROM_YEAR


def _year_requires_short_fiction(year: int) -> bool:
    return _SHORT_FICTION_FROM_YEAR <= year <= _SHORT_FICTION_THROUGH_YEAR


def _year_requires_novel_or_novelette(year: int) -> bool:
    return year == 1958


def _year_requires_best_series(year: int) -> bool:
    return year >= _BEST_SERIES_REQUIRED_FROM_YEAR


def _year_requires_best_all_time_series(year: int) -> bool:
    return year in _BEST_ALL_TIME_SERIES_YEARS


def _year_requires_best_poem(year: int) -> bool:
    return year in _BEST_POEM_YEARS


def _year_requires_best_related_non_fiction_book(year: int) -> bool:
    return year in _BEST_RELATED_NON_FICTION_BOOK_YEARS


def _year_requires_best_related_book(year: int) -> bool:
    return year in _BEST_RELATED_BOOK_YEARS


def _year_has_required_category(year: int) -> bool:
    return (
        _year_requires_best_novel(year)
        or year >= _NOVELLA_REQUIRED_FROM_YEAR
        or _year_requires_novelette(year)
        or _year_requires_short_story(year)
        or _year_requires_short_fiction(year)
        or _year_requires_novel_or_novelette(year)
        or _year_requires_best_series(year)
        or _year_requires_best_all_time_series(year)
        or _year_requires_best_poem(year)
        or _year_requires_best_related_non_fiction_book(year)
        or _year_requires_best_related_book(year)
    )


def _required_cached_regular_years() -> set[int]:
    """Regular years current category rules require a complete archive to cover.

    Live validation uses API year pages. Disk has no WP payload, so this
    span is the equivalent historical floor (through the latest year named
    by current category constants).
    """
    latest = max(_BEST_POEM_YEARS)
    return {
        year
        for year in range(_ARCHIVE_FIRST_REGULAR_YEAR, latest + 1)
        if year not in _ARCHIVE_SKIPPED_REGULAR_YEARS
        and _year_has_required_category(year)
    }


def _fail_if_expected_years_missing(
    category: str,
    records: list[_ParsedRecord],
    expected_years: set[int],
) -> None:
    if not expected_years:
        return
    if not records:
        raise HugoSourceError(
            f'Hugo archive was retrieved but no {category} records could be parsed'
        )
    parsed_years = {record.award_year for record in records}
    missing = sorted(expected_years - parsed_years)
    if missing:
        extra = f' (+{len(missing) - 1} more)' if len(missing) > 1 else ''
        raise HugoSourceError(
            'Hugo archive was retrieved but '
            f'{category} records were missing for expected year(s): '
            f'{missing[0]}{extra}'
        )


def _validate_supported_category_records(
    records: tuple[_ParsedRecord, ...],
    regular_years: set[int],
) -> None:
    # Historical category ranges: a silent markup change must not drop a decade.
    records_by_category: dict[str, list[_ParsedRecord]] = {
        category: [] for category in _PARSED_CATEGORIES
    }
    for record in records:
        if record.category not in records_by_category:
            raise HugoSourceError(
                f'Hugo archive produced an unsupported category: {record.category!r}'
            )
        records_by_category[record.category].append(record)

    _fail_if_expected_years_missing(
        CATEGORY_BEST_NOVEL,
        records_by_category[CATEGORY_BEST_NOVEL],
        {year for year in regular_years if _year_requires_best_novel(year)},
    )
    _fail_if_expected_years_missing(
        CATEGORY_BEST_NOVELLA,
        records_by_category[CATEGORY_BEST_NOVELLA],
        {year for year in regular_years if year >= _NOVELLA_REQUIRED_FROM_YEAR},
    )
    _fail_if_expected_years_missing(
        CATEGORY_BEST_NOVELETTE,
        records_by_category[CATEGORY_BEST_NOVELETTE],
        {year for year in regular_years if _year_requires_novelette(year)},
    )
    _fail_if_expected_years_missing(
        CATEGORY_BEST_SHORT_STORY,
        records_by_category[CATEGORY_BEST_SHORT_STORY],
        {year for year in regular_years if _year_requires_short_story(year)},
    )
    _fail_if_expected_years_missing(
        CATEGORY_SHORT_FICTION,
        records_by_category[CATEGORY_SHORT_FICTION],
        {year for year in regular_years if _year_requires_short_fiction(year)},
    )
    _fail_if_expected_years_missing(
        CATEGORY_BEST_NOVEL_OR_NOVELETTE,
        records_by_category[CATEGORY_BEST_NOVEL_OR_NOVELETTE],
        {year for year in regular_years if _year_requires_novel_or_novelette(year)},
    )
    _fail_if_expected_years_missing(
        CATEGORY_BEST_SERIES,
        records_by_category[CATEGORY_BEST_SERIES],
        {year for year in regular_years if _year_requires_best_series(year)},
    )
    _fail_if_expected_years_missing(
        CATEGORY_BEST_ALL_TIME_SERIES,
        records_by_category[CATEGORY_BEST_ALL_TIME_SERIES],
        {
            year
            for year in regular_years
            if _year_requires_best_all_time_series(year)
        },
    )
    _fail_if_expected_years_missing(
        CATEGORY_BEST_POEM,
        records_by_category[CATEGORY_BEST_POEM],
        {year for year in regular_years if _year_requires_best_poem(year)},
    )
    _fail_if_expected_years_missing(
        CATEGORY_BEST_RELATED_NON_FICTION_BOOK,
        records_by_category[CATEGORY_BEST_RELATED_NON_FICTION_BOOK],
        {
            year
            for year in regular_years
            if _year_requires_best_related_non_fiction_book(year)
        },
    )
    _fail_if_expected_years_missing(
        CATEGORY_BEST_RELATED_BOOK,
        records_by_category[CATEGORY_BEST_RELATED_BOOK],
        {
            year
            for year in regular_years
            if _year_requires_best_related_book(year)
        },
    )


def _records_from_archive_items(items: list[dict]) -> tuple[_ParsedRecord, ...]:
    records: list[_ParsedRecord] = []
    for item in items:
        title = _usable_title(item)
        link = _usable_link(item)
        content = _usable_content(item)
        if title is None or link is None or content is None:
            continue
        year = _regular_year_from_title(title)
        if year is None:
            continue
        records.extend(_parse_supported_categories_html(content, year, link))
    return tuple(records)


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_archive_records_cache: tuple[_ParsedRecord, ...] | None = None
_cache_lock = threading.Lock()


def _reset_runtime_state() -> None:
    """Clear in-process caches. Used by tests. Does not delete disk cache."""
    global _archive_records_cache
    with _cache_lock:
        _archive_records_cache = None


def _get_archive_records() -> tuple[_ParsedRecord, ...]:
    """Return records: RAM, then disk, then live fetch/parse/validate.

    A fresh disk cache is used immediately. A stale-but-valid disk cache
    live-refreshes only if this lookup still has a stale-refresh slot;
    otherwise the stale archive is used with no network. A missing or
    invalid cache still live-fetches.
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


def _normalize_title_quote_punctuation(text: str) -> str:
    """Treat lone apostrophes as quote marks; keep internal apostrophes."""
    return _QUOTATION_PUNCTUATION_APOSTROPHE_RE.sub('"', text)


def _normalize_title_for_match(value: str) -> str:
    text = _normalize_text(value)
    text = _normalize_title_quote_punctuation(text)
    text = normalize_title_conjunctions(text)
    text = _WORD_SEPARATOR_HYPHEN_RE.sub(r'\1 \2', text)
    return _collapse_ws(text)


def _titles_equivalent(query_title: str, record_title: str) -> bool:
    query_norm = _normalize_title_for_match(query_title)
    record_norm = _normalize_title_for_match(record_title)
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


def _normalize_series_for_match(value: str) -> str:
    """Normalize a series name for conservative series-only matching."""
    text = _normalize_title_for_match(value)
    stripped_the = _SERIES_LEADING_THE_RE.sub('', text, count=1)
    if stripped_the:
        text = stripped_the
    while True:
        stripped_wrapper = _SERIES_TRAILING_WRAPPER_RE.sub('', text)
        if stripped_wrapper == text or not stripped_wrapper.strip():
            break
        text = stripped_wrapper.strip()
    return _collapse_ws(text)


def _series_names_match(query_series: str, record_series: str) -> bool:
    query_norm = _normalize_series_for_match(query_series)
    record_norm = _normalize_series_for_match(record_series)
    return bool(query_norm) and query_norm == record_norm


def _series_record_matches(
    record: _ParsedRecord, series: str, author: str
) -> bool:
    if record.category not in _SERIES_CATEGORIES:
        return False
    return _series_names_match(series, record.work_title) and _authors_match(
        author, record.work_author
    )


def _titles_match(query_title: str, record: _ParsedRecord) -> bool:
    return any(
        _titles_equivalent(query_title, candidate)
        for candidate in record.match_titles
    )


def _strip_trailing_name_parenthetical(author: str) -> str:
    stripped = author.rstrip()
    if not stripped.endswith(')'):
        return stripped
    start = stripped.rfind('(')
    if start <= 0:
        return stripped
    group = stripped[start:]
    remainder = stripped[:start].rstrip(' ,')
    if not remainder or not any(character.isalpha() for character in group):
        return stripped
    return remainder


def _canonical_author(author: str) -> str:
    stripped = _TRANSLATOR_AUTHOR_SUFFIX_RE.sub('', author).rstrip(' ,')
    stripped = _strip_trailing_name_parenthetical(stripped)
    return stripped or author


def _author_match_forms(author: str) -> set[str]:
    forms = {_normalize_text(author)}
    forms.add(_normalize_text(_canonical_author(author)))
    return forms


def _authors_match(query_author: str, record_author: str) -> bool:
    return bool(_author_match_forms(query_author) & _author_match_forms(record_author))


def _split_calibre_author_query(query_author: str) -> tuple[str, ...]:
    """Invert Calibre authors_to_string: split on ' & ', restore '&&' to '&'."""
    protected = query_author.replace('&&', _CALIBRE_AMP_PLACEHOLDER)
    people: list[str] = []
    for piece in protected.split(' & '):
        restored = piece.replace(_CALIBRE_AMP_PLACEHOLDER, '&').strip()
        if restored:
            people.append(restored)
    return tuple(people)


def _strip_related_calibre_role(author: str) -> str:
    stripped = _RELATED_CALIBRE_ROLE_RE.sub('', author).strip()
    return stripped or author


def _strip_related_source_role(author: str) -> str:
    stripped = _RELATED_SOURCE_ROLE_RE.sub('', author).strip().rstrip(',')
    return stripped or author


def _glue_related_generational_suffixes(parts: list[str]) -> list[str]:
    glued: list[str] = []
    for part in parts:
        piece = part.strip()
        if not piece:
            continue
        if glued and _RELATED_GENERATIONAL_SUFFIX_RE.fullmatch(piece):
            glued[-1] = f'{glued[-1]}, {piece}'
        else:
            glued.append(piece)
    return glued


def _related_person_token_count(person: str) -> int:
    return len([token for token in person.split() if token])


def _parse_related_book_people(record_author: str) -> tuple[str, ...] | None:
    """Parse a simple official Related Book credit into people, or None.

    Complex credits (with, translated by, introductions) are rejected rather
    than partially guessed.
    """
    text = _collapse_ws(record_author)
    if not text:
        return None
    stripped = _strip_related_source_role(text)
    if not stripped or _RELATED_COMPLEX_CREDIT_RE.search(stripped):
        return None
    has_and = _RELATED_AND_SPLIT_RE.search(stripped) is not None
    if not has_and and ',' not in stripped:
        return (stripped,)
    people: list[str] = []
    and_bits = _RELATED_AND_SPLIT_RE.split(stripped) if has_and else [stripped]
    for bit in and_bits:
        comma_parts = [part.strip() for part in bit.split(',')]
        people.extend(_glue_related_generational_suffixes(comma_parts))
    if not people:
        return None
    if len(people) == 1:
        return (people[0],)
    for person in people:
        if _related_person_token_count(person) < 2:
            return None
    return tuple(people)


def _related_person_matches(query_person: str, source_person: str) -> bool:
    query_norm = _normalize_text(_strip_related_calibre_role(query_person))
    source_norm = _normalize_text(source_person)
    return bool(query_norm) and query_norm == source_norm


def _related_book_authors_match(query_author: str, record_author: str) -> bool:
    if _authors_match(query_author, record_author):
        return True
    source_people = _parse_related_book_people(record_author)
    if source_people is None:
        return False
    query_people = _split_calibre_author_query(query_author)
    if not query_people:
        return False
    return all(
        any(
            _related_person_matches(query_person, source_person)
            for query_person in query_people
        )
        for source_person in source_people
    )


def _record_matches(record: _ParsedRecord, title: str, author: str) -> bool:
    if record.category in _SERIES_CATEGORIES:
        return False
    if not _titles_match(title, record):
        return False
    if record.category in _RELATED_BOOK_CATEGORIES:
        return _related_book_authors_match(author, record.work_author)
    return _authors_match(author, record.work_author)


def _ranking_matches_record(ranking: HugoRanking, record: _ParsedRecord) -> bool:
    if ranking.award_year != record.award_year:
        return False
    title_ok = any(
        _titles_equivalent(ranking.work_title, candidate)
        for candidate in record.match_titles
    )
    if not title_ok:
        return False
    return _authors_match(ranking.work_author, record.work_author)


def _ranking_for_record(record: _ParsedRecord) -> HugoRanking | None:
    if record.category != CATEGORY_BEST_NOVEL:
        return None
    found = [
        ranking
        for ranking in HUGO_BEST_NOVEL_RANKINGS
        if _ranking_matches_record(ranking, record)
    ]
    if len(found) != 1:
        return None
    return found[0]


def _enrichment_is_consistent(record: _ParsedRecord, ranking: HugoRanking) -> bool:
    if ranking.rank == 1:
        return record.status == 'Winner'
    return record.status != 'Winner'


def _to_award_result(record: _ParsedRecord) -> AwardResult:
    if record.category in _SERIES_CATEGORIES:
        return AwardResult(
            work_title=record.work_title,
            work_author=record.work_author,
            award_name='Hugo Award',
            award_year=record.award_year,
            category=record.category,
            status=record.status,
            rank=None,
            source_name='Hugo Awards',
            source_url=record.source_url,
            notes=None,
            identity_kind='series',
        )
    ranking = _ranking_for_record(record)
    if ranking is None or not _enrichment_is_consistent(record, ranking):
        # History pages do not establish ordinal rank; leave rank unknown.
        return AwardResult(
            work_title=record.work_title,
            work_author=record.work_author,
            award_name='Hugo Award',
            award_year=record.award_year,
            category=record.category,
            status=record.status,
            rank=None,
            source_name='Hugo Awards',
            source_url=record.source_url,
            notes=None,
        )
    return AwardResult(
        work_title=record.work_title,
        work_author=record.work_author,
        award_name='Hugo Award',
        award_year=record.award_year,
        category=record.category,
        status=record.status,
        rank=ranking.rank,
        source_name='Hugo Awards',
        source_url=ranking.source_url,
        notes='tie' if ranking.tied else None,
    )


# ---------------------------------------------------------------------------
# Persistent archive cache
# ---------------------------------------------------------------------------

def _record_to_cache_dict(record: _ParsedRecord) -> dict:
    return {
        'award_year': record.award_year,
        'category': record.category,
        'match_titles': list(record.match_titles),
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
    if not isinstance(category, str) or not category.strip() or category != category.strip():
        return None
    if status not in _PARSED_STATUSES:
        return None
    if not isinstance(work_title, str) or not work_title.strip() or work_title != work_title.strip():
        return None
    if not isinstance(work_author, str) or work_author != work_author.strip():
        return None
    if (
        not isinstance(source_url, str)
        or not source_url.strip()
        or source_url != source_url.strip()
    ):
        return None
    match_titles = _match_titles_from_cache(data.get('match_titles'))
    if match_titles is None:
        return None
    return _ParsedRecord(
        award_year=award_year,
        category=category,
        status=status,
        work_title=work_title,
        work_author=work_author,
        source_url=source_url,
        match_titles=match_titles,
    )


def _match_titles_from_cache(value) -> tuple[str, ...] | None:
    if isinstance(value, (str, bytes, bytearray)):
        return None
    if not isinstance(value, (list, tuple)) or not value:
        return None
    titles: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or item != item.strip():
            return None
        titles.append(item)
    return tuple(titles)


def _archive_source_urls() -> tuple[str, ...]:
    return (_archive_url(),)


def _coverage_from_records(records: tuple[_ParsedRecord, ...]) -> dict:
    categories = []
    for category in _PARSED_CATEGORIES:
        subset = [record for record in records if record.category == category]
        years = [record.award_year for record in subset]
        categories.append(
            {
                'category': category,
                'min_year': min(years) if years else None,
                'max_year': max(years) if years else None,
                'record_count': len(subset),
                'winner_count': sum(
                    1 for record in subset if record.status == 'Winner'
                ),
                'finalist_count': sum(
                    1 for record in subset if record.status == 'Finalist'
                ),
            }
        )
    years = [record.award_year for record in records]
    return {
        'categories': categories,
        'max_year': max(years) if years else None,
        'min_year': min(years) if years else None,
        'record_count': len(records),
        'regular_years': sorted({record.award_year for record in records}),
    }


def _validate_cached_archive(records: tuple[_ParsedRecord, ...]) -> None:
    """Fail closed if reconstructed records are not a usable full archive."""
    if not records:
        raise HugoSourceError('Hugo persistent cache contained no records')
    for record in records:
        if record.category not in _PARSED_CATEGORIES:
            raise HugoSourceError(
                f'Hugo archive produced an unsupported category: {record.category!r}'
            )
        if record.status not in _PARSED_STATUSES:
            raise HugoSourceError(
                'Hugo archive produced an unexpected status: '
                f'{record.status!r}'
            )
        if not record.source_url.startswith(SOURCE_HOME_URL):
            raise HugoSourceError(
                'Hugo archive produced an unexpected source URL: '
                f'{record.source_url!r}'
            )
        if record.award_year < _ARCHIVE_FIRST_REGULAR_YEAR:
            raise HugoSourceError(
                f'Hugo archive year {record.award_year} is before first '
                f'regular year {_ARCHIVE_FIRST_REGULAR_YEAR}'
            )
        if not record.match_titles:
            raise HugoSourceError('Hugo archive record is missing match_titles')

    present_years = {record.award_year for record in records}
    missing = sorted(_required_cached_regular_years() - present_years)
    if missing:
        extra = f' (+{len(missing) - 1} more)' if len(missing) > 1 else ''
        raise HugoSourceError(
            'Hugo persistent cache is missing required year(s): '
            f'{missing[0]}{extra}'
        )
    _validate_supported_category_records(records, present_years)


def _records_from_cache_payload(
    payload: dict,
) -> tuple[_ParsedRecord, ...] | None:
    expected_urls = list(_archive_source_urls())
    if payload.get('source_urls') != expected_urls:
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
    except HugoSourceError:
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


def _load_live_archive() -> tuple[_ParsedRecord, ...]:
    status, headers, body = _fetch_archive_response()
    items = _validate_archive_payload(status, headers, body)
    records = _records_from_archive_items(items)
    _validate_supported_category_records(records, _regular_years_from_items(items))
    return records


# ---------------------------------------------------------------------------
# Public lookup
# ---------------------------------------------------------------------------

def lookup(
    title: str,
    author: str,
    series: str | None = None,
) -> list[AwardResult]:
    """Look up Hugo Award written-work and series results."""
    cleaned_title = title.strip()
    cleaned_author = author.strip()
    if not cleaned_title:
        raise ValueError('title must be a non-empty string')
    if not cleaned_author:
        raise ValueError('author must be a non-empty string')
    cleaned_series = None if series is None else str(series).strip() or None

    matches: list[AwardResult] = []
    seen: set[tuple[int, str, str, str, str, str]] = set()
    for record in _get_archive_records():
        if record.category in _SERIES_CATEGORIES:
            if cleaned_series is None:
                continue
            if not _series_record_matches(record, cleaned_series, cleaned_author):
                continue
        elif not _record_matches(record, cleaned_title, cleaned_author):
            continue
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
        matches.append(_to_award_result(record))
    return matches
