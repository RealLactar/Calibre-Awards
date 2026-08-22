"""Official World Fantasy Award Novel, Novella, Short Fiction, and Collection source."""

from __future__ import annotations

import re
import threading
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from http.cookiejar import CookieJar

from ..matching import normalize_title_conjunctions
from ..model import AwardResult

TIMEOUT_SECONDS = 30
NOMINEES_URL = 'https://worldfantasy.org/awards/nominees/'
WINNERS_URL = 'https://worldfantasy.org/awards/winners/'
CONVENTION_1982_URL = (
    'https://worldfantasy.org/1982-the-8th-world-fantasy-convention/'
)
CONVENTION_1993_URL = (
    'https://worldfantasy.org/1993-the-19th-world-fantasy-convention/'
)
CONVENTION_2005_URL = (
    'https://worldfantasy.org/2005-world-fantasy-convention-2005/'
)
ANNUAL_2013_URL = 'https://worldfantasy.org/2013-world-fantasy-awards/'
ANNUAL_2024_URL = (
    'https://worldfantasy.org/2024-world-fantasy-nominations-and-winners/'
)
ANNUAL_2025_URL = 'https://worldfantasy.org/2025-wfc-nominations-and-winners/'

SOURCE_PAGE_URLS = (
    NOMINEES_URL,
    WINNERS_URL,
    CONVENTION_1982_URL,
    CONVENTION_1993_URL,
    CONVENTION_2005_URL,
    ANNUAL_2013_URL,
    ANNUAL_2024_URL,
    ANNUAL_2025_URL,
)

CATEGORY_NOVEL = 'Novel'
CATEGORY_NOVELLA = 'Novella'
CATEGORY_SHORT_FICTION = 'Short Fiction'
CATEGORY_COLLECTION = 'Collection'
LONG_FICTION_YEARS = frozenset({2016, 2017, 2018})
MASTER_WINNERS_THROUGH_YEAR = 2023
NOVEL_MASTER_WINNER_YEARS = frozenset(
    range(1975, MASTER_WINNERS_THROUGH_YEAR + 1)
)
NOVELLA_MASTER_WINNER_YEARS = frozenset(
    range(1982, MASTER_WINNERS_THROUGH_YEAR + 1)
)
SHORT_FICTION_MASTER_WINNER_YEARS = frozenset(
    range(1975, MASTER_WINNERS_THROUGH_YEAR + 1)
)
COLLECTION_MASTER_WINNER_YEARS = frozenset(
    range(1988, MASTER_WINNERS_THROUGH_YEAR + 1)
)
NOVELLA_OFFICIAL_LABELS = {
    2015: 'novella',
    2016: 'long fiction',
    2017: 'long fiction',
    2018: 'long fiction',
    2019: 'novella',
}

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
_WORD_SEPARATOR_HYPHEN_RE = re.compile(
    r'(\w)[\u2010\u2011\u2012\u2013\u2014\u2212-](\w)'
)
_TRANSLATOR_AUTHOR_SUFFIX_RE = re.compile(
    r',\s*(?:translated by\s+.+|.+\s+translator)\s*$',
    re.IGNORECASE,
)
_AUTHOR_SPLIT_RE = re.compile(r'\s+(?:and|&)\s+', re.IGNORECASE)
_WRAPPING_QUOTES = frozenset({'"', "'", '\u201c', '\u201d', '\u2018', '\u2019'})
_QUOTE_PAIRS = {
    '"': '"',
    "'": "'",
    '\u201c': '\u201d',
    '\u2018': '\u2019',
}
_EM_ARTIFACT_RE = re.compile(r',?\s*(?:</?em>|/em>)\s*$', re.IGNORECASE)
_TRAILING_STATUS_RE = re.compile(
    r'^(?P<title>.+?)(?:\t+|\s+)(?P<status>Winner|Nominee)\s*$',
    re.IGNORECASE | re.DOTALL,
)
_WINNER_PREFIX_RE = re.compile(r'^winner:\s*', re.IGNORECASE)
_BY_CITATION_RE = re.compile(
    r'^(?:winner:\s*)?(?P<title>.+?)\s+by\s+(?P<author>.+?)$',
    re.IGNORECASE | re.DOTALL,
)
_COMMA_CITATION_RE = re.compile(
    r'^(?:winner:\s*)?(?P<title>.+?),\s*(?P<author>.+)$',
    re.IGNORECASE | re.DOTALL,
)
_YEAR_RE = re.compile(r'^\d{4}$')


class WorldFantasySourceError(RuntimeError):
    """Raised when the official World Fantasy site cannot be retrieved."""


@dataclass(frozen=True, slots=True)
class _CategoryConfig:
    canonical: str
    table_aliases: frozenset[str]
    annual_heading_aliases: frozenset[str]
    first_year: int


@dataclass(frozen=True, slots=True)
class _ParsedRecord:
    award_year: int
    category: str
    status: str
    work_title: str
    work_author: str
    source_url: str
    match_authors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _FetchedPages:
    nominees_html: str
    winners_html: str
    convention_1982_html: str
    convention_1993_html: str
    convention_2005_html: str
    annual_2013_html: str
    annual_2024_html: str
    annual_2025_html: str


@dataclass(frozen=True, slots=True)
class _TableWork:
    award_year: int
    category: str
    official_category: str
    work_title: str
    authors: tuple[str, ...]
    status: str


_CATEGORY_CONFIGS: tuple[_CategoryConfig, ...] = (
    _CategoryConfig(
        canonical=CATEGORY_NOVEL,
        table_aliases=frozenset({'Novel'}),
        annual_heading_aliases=frozenset({
            'Novel',
            'Best Novel',
        }),
        first_year=1975,
    ),
    _CategoryConfig(
        canonical=CATEGORY_NOVELLA,
        table_aliases=frozenset({'Novella'}),
        annual_heading_aliases=frozenset({
            'Novella',
            'Best Novella',
        }),
        first_year=1982,
    ),
    _CategoryConfig(
        canonical=CATEGORY_SHORT_FICTION,
        table_aliases=frozenset({'Short Fiction'}),
        annual_heading_aliases=frozenset({
            'Short Fiction',
            'Short Story',
            'Best Short Fiction',
        }),
        first_year=1975,
    ),
    _CategoryConfig(
        canonical=CATEGORY_COLLECTION,
        table_aliases=frozenset({'Collection'}),
        annual_heading_aliases=frozenset({
            'Collection',
            'Best Collection',
        }),
        first_year=1988,
    ),
)

_CANONICAL_CATEGORIES = tuple(config.canonical for config in _CATEGORY_CONFIGS)
_CATEGORY_FIRST_YEAR = {
    config.canonical: config.first_year for config in _CATEGORY_CONFIGS
}


# ---------------------------------------------------------------------------
# HTTP retrieval
# ---------------------------------------------------------------------------

def _build_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(CookieJar())
    )


def _decode_html_bytes(raw: bytes) -> str:
    """Decode official HTML. Nominees pages may be Windows-1252 mislabeled as UTF-8."""
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        return raw.decode('cp1252')


def _read_response_body(response) -> str:
    return _decode_html_bytes(response.read())


def _fetch_html(opener: urllib.request.OpenerDirector, url: str) -> str:
    request = urllib.request.Request(url, headers=dict(_BROWSER_HEADERS))
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            status = getattr(response, 'status', None) or response.getcode()
            html = _read_response_body(response)
    except urllib.error.HTTPError as exc:
        body = _read_response_body(exc)
        raise WorldFantasySourceError(
            f'World Fantasy request failed with HTTP {exc.code} for {url}'
            + (f': {body[:200].strip()}' if body.strip() else '')
        ) from exc
    except urllib.error.URLError as exc:
        raise WorldFantasySourceError(
            f'World Fantasy request failed for {url}: {exc.reason}'
        ) from exc

    if status != 200:
        raise WorldFantasySourceError(
            f'World Fantasy request failed with HTTP {status} for {url}'
        )
    return html


def _fetch_source_pages(opener: urllib.request.OpenerDirector) -> _FetchedPages:
    return _FetchedPages(
        nominees_html=_fetch_html(opener, NOMINEES_URL),
        winners_html=_fetch_html(opener, WINNERS_URL),
        convention_1982_html=_fetch_html(opener, CONVENTION_1982_URL),
        convention_1993_html=_fetch_html(opener, CONVENTION_1993_URL),
        convention_2005_html=_fetch_html(opener, CONVENTION_2005_URL),
        annual_2013_html=_fetch_html(opener, ANNUAL_2013_URL),
        annual_2024_html=_fetch_html(opener, ANNUAL_2024_URL),
        annual_2025_html=_fetch_html(opener, ANNUAL_2025_URL),
    )


_records_cache: tuple[_ParsedRecord, ...] | None = None
_cache_lock = threading.Lock()


def _reset_runtime_state() -> None:
    """Clear in-process caches. Used by tests."""
    global _records_cache
    with _cache_lock:
        _records_cache = None


def _get_records() -> tuple[_ParsedRecord, ...]:
    """Return cached records, fetching once per process on success."""
    global _records_cache
    with _cache_lock:
        if _records_cache is not None:
            return _records_cache
        opener = _build_opener()
        pages = _fetch_source_pages(opener)
        records = _build_records_from_pages(pages, validate_full_archive=True)
        if not records:
            raise WorldFantasySourceError(
                'World Fantasy pages were retrieved but no records '
                'could be parsed'
            )
        _records_cache = records
        return _records_cache


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def _collapse_ws(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def _ascii_fold(text: str) -> str:
    return ''.join(
        char
        for char in unicodedata.normalize('NFKD', text)
        if not unicodedata.combining(char)
    )


def _strip_wrapping_quotes(text: str) -> str:
    cleaned = _collapse_ws(text)
    while (
        len(cleaned) >= 2
        and cleaned[0] in _WRAPPING_QUOTES
        and cleaned[-1] in _WRAPPING_QUOTES
    ):
        cleaned = cleaned[1:-1].strip()
    return cleaned


def _strip_em_artifact(text: str) -> str:
    return _EM_ARTIFACT_RE.sub('', text).rstrip(' ,')


def _strip_trailing_parenthetical(text: str) -> str:
    stripped = text.rstrip()
    if not stripped.endswith(')'):
        return stripped
    start = stripped.rfind('(')
    if start <= 0:
        return stripped
    remainder = stripped[:start].rstrip(' ,')
    return remainder or stripped


def _clean_title(text: str) -> str:
    cleaned = _strip_em_artifact(_collapse_ws(text))
    cleaned = _strip_wrapping_quotes(cleaned)
    return _collapse_ws(cleaned)


def _clean_author(text: str) -> str:
    cleaned = _collapse_ws(text)
    cleaned = _TRANSLATOR_AUTHOR_SUFFIX_RE.sub('', cleaned).rstrip(' ,')
    cleaned = _strip_trailing_parenthetical(cleaned)
    return _collapse_ws(cleaned)


def _join_authors(authors: list[str] | tuple[str, ...]) -> str:
    cleaned = [_collapse_ws(author) for author in authors if _collapse_ws(author)]
    if not cleaned:
        return ''
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f'{cleaned[0]} and {cleaned[1]}'
    return f'{", ".join(cleaned[:-1])} and {cleaned[-1]}'


def _split_author_names(author: str) -> tuple[str, ...]:
    parts = tuple(
        part.strip()
        for part in _AUTHOR_SPLIT_RE.split(author)
        if part.strip()
    )
    return parts or (author,)


def _parse_year(text: str) -> int | None:
    cleaned = _collapse_ws(text)
    if not _YEAR_RE.fullmatch(cleaned):
        return None
    year = int(cleaned)
    if year <= 0:
        return None
    return year


def _canonical_status(text: str) -> str | None:
    cleaned = _collapse_ws(text)
    if cleaned.casefold() == 'winner':
        return 'Winner'
    if cleaned.casefold() == 'nominee':
        return 'Nominee'
    return None


def _annual_heading_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for config in _CATEGORY_CONFIGS:
        for alias in config.annual_heading_aliases:
            mapping[alias.casefold()] = config.canonical
    return mapping


def _resolve_table_category(raw_category: str, year: int) -> str | None:
    """Map an official table category to a canonical plugin category.

    Long Fiction is Novella only for 2016–2018. Any other year fails closed.
    """
    folded = _collapse_ws(raw_category).casefold()
    if not folded:
        return None
    if folded == 'long fiction':
        if year not in LONG_FICTION_YEARS:
            raise WorldFantasySourceError(
                'World Fantasy table used Long Fiction in '
                f'{year}, outside the official 2016–2018 interval'
            )
        return CATEGORY_NOVELLA
    if folded == 'collection/anthology':
        return None
    for config in _CATEGORY_CONFIGS:
        aliases = {alias.casefold() for alias in config.table_aliases}
        if folded in aliases:
            return config.canonical
    return None


# ---------------------------------------------------------------------------
# Table parsing
# ---------------------------------------------------------------------------

class _SortableTableParser(HTMLParser):
    """Collect cell text from the first HTML table."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._in_table = False
        self._saw_table = False
        self._in_row = False
        self._in_cell = False
        self._cell_parts: list[str] = []
        self._row: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == 'table' and not self._saw_table:
            self._in_table = True
            self._saw_table = True
            return
        if not self._in_table:
            return
        if tag == 'tr':
            self._in_row = True
            self._row = []
            return
        if tag in {'td', 'th'}:
            self._in_cell = True
            self._cell_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {'td', 'th'} and self._in_cell:
            self._row.append(_collapse_ws(''.join(self._cell_parts)))
            self._in_cell = False
            return
        if tag == 'tr' and self._in_row:
            if self._row:
                self.rows.append(self._row)
            self._in_row = False
            return
        if tag == 'table' and self._in_table:
            self._in_table = False

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_parts.append(data)


def _parse_table_rows(html: str) -> list[list[str]]:
    parser = _SortableTableParser()
    parser.feed(html)
    parser.close()
    return parser.rows


def _recover_title_and_status(cells: list[str]) -> tuple[str | None, str | None]:
    """Recover title and Winner/Nominee from a six- or five-cell official row."""
    if len(cells) >= 6:
        title = _clean_title(cells[4])
        status = _canonical_status(cells[5])
        if not title or status is None:
            return None, None
        return title, status
    if len(cells) == 5:
        jammed = cells[4]
        match = _TRAILING_STATUS_RE.match(jammed)
        if match is None:
            return None, None
        title = _clean_title(match.group('title'))
        status = _canonical_status(match.group('status'))
        if not title or status is None:
            return None, None
        return title, status
    return None, None


def _table_works(html: str) -> list[_TableWork]:
    grouped: dict[tuple[int, str, str], list[str]] = {}
    titles_by_group: dict[tuple[int, str, str], str] = {}
    official_by_group: dict[tuple[int, str, str], str] = {}
    status_by_group: dict[tuple[int, str, str], str] = {}
    order: list[tuple[int, str, str]] = []
    for cells in _parse_table_rows(html):
        if len(cells) < 5:
            continue
        if cells[0].casefold() == 'first name':
            continue
        year = _parse_year(cells[2])
        official_category = _collapse_ws(cells[3])
        if year is None or not official_category:
            continue
        category = _resolve_table_category(official_category, year)
        if category is None:
            continue
        title, status = _recover_title_and_status(cells)
        first = _collapse_ws(cells[0])
        last = _collapse_ws(cells[1])
        author = _collapse_ws(f'{first} {last}')
        if not title or status is None or not author:
            continue
        group_key = (year, category, _title_key(title))
        if group_key not in grouped:
            grouped[group_key] = []
            titles_by_group[group_key] = title
            official_by_group[group_key] = official_category
            status_by_group[group_key] = status
            order.append(group_key)
        elif status == 'Winner':
            status_by_group[group_key] = 'Winner'
        if author not in grouped[group_key]:
            grouped[group_key].append(author)
    return [
        _TableWork(
            award_year=group_key[0],
            category=group_key[1],
            official_category=official_by_group[group_key],
            work_title=titles_by_group[group_key],
            authors=tuple(grouped[group_key]),
            status=status_by_group[group_key],
        )
        for group_key in order
    ]


# ---------------------------------------------------------------------------
# Annual-page parsing
# ---------------------------------------------------------------------------

def _parse_by_or_comma_citation(text: str) -> tuple[str, str] | None:
    cleaned = _clean_author(_WINNER_PREFIX_RE.sub('', _collapse_ws(text)))
    cleaned = _strip_trailing_parenthetical(cleaned)
    match = _BY_CITATION_RE.match(cleaned)
    if match is None:
        match = _COMMA_CITATION_RE.match(cleaned)
    if match is None:
        return None
    title = _clean_title(match.group('title'))
    author = _clean_author(match.group('author'))
    if not title or not author:
        return None
    return title, author


def _quoted_span_indexes(text: str) -> tuple[int, int] | None:
    opener_index = None
    closer = None
    for index, char in enumerate(text):
        pair = _QUOTE_PAIRS.get(char)
        if pair is None:
            continue
        opener_index = index
        closer = pair
        break
    if opener_index is None or closer is None:
        return None
    closer_index = text.find(closer, opener_index + 1)
    if closer_index < 0:
        return None
    return opener_index, closer_index


def _has_another_quoted_title(text: str) -> bool:
    """True when remainder still contains a double-quoted title span."""
    for opener, closer in (('"', '"'), ('\u201c', '\u201d')):
        start = text.find(opener)
        if start < 0:
            continue
        if text.find(closer, start + 1) >= 0:
            return True
    return False


def _parse_quoted_story_citation(text: str) -> tuple[str, str] | None:
    """Parse a Short Fiction annual citation from matching quotation marks.

    Title punctuation inside the quotes is preserved. The venue parenthetical
    is not treated as an author. Ambiguous unquoted or multi-title lines fail
    closed instead of falling back to the Novel/Novella comma parser.
    """
    cleaned = _WINNER_PREFIX_RE.sub('', _collapse_ws(text))
    span = _quoted_span_indexes(cleaned)
    if span is None:
        return None
    opener_index, closer_index = span
    raw_title = cleaned[opener_index + 1 : closer_index]
    remainder = cleaned[closer_index + 1 :]
    if _has_another_quoted_title(remainder):
        return None
    title = _collapse_ws(_EM_ARTIFACT_RE.sub('', raw_title))
    remainder = remainder.strip()
    if not remainder or (
        remainder.startswith('(') and remainder.endswith(')')
    ):
        return None
    remainder = _strip_trailing_parenthetical(remainder).strip()
    remainder = remainder.lstrip(' ,;:')
    remainder = re.sub(r'^by\s+', '', remainder, flags=re.IGNORECASE)
    author = _clean_author(remainder)
    if not title or not author or author.startswith('('):
        return None
    return title, author


def _parse_annual_citation(text: str, category: str) -> tuple[str, str] | None:
    if category == CATEGORY_SHORT_FICTION:
        return _parse_quoted_story_citation(text)
    return _parse_by_or_comma_citation(text)


def _citation_from_fragments(
    em_title: str,
    strong_title: str,
    li_text: str,
    category: str,
) -> tuple[str, str] | None:
    if category == CATEGORY_SHORT_FICTION:
        return _parse_quoted_story_citation(li_text)
    title = _clean_title(em_title or strong_title)
    cleaned_li = _collapse_ws(li_text)
    if title:
        remainder = cleaned_li
        remainder = _WINNER_PREFIX_RE.sub('', remainder)
        if remainder.casefold().startswith(title.casefold()):
            remainder = remainder[len(title) :].lstrip(' :,')
        remainder = re.sub(r'^by\s+', '', remainder, flags=re.IGNORECASE)
        author = _clean_author(_strip_trailing_parenthetical(remainder))
        if title and author:
            return title, author
    return _parse_by_or_comma_citation(cleaned_li)


class _CategoryListParser(HTMLParser):
    """Capture configured category <ul> lists that follow matching headings."""

    def __init__(self, heading_to_category: dict[str, str], winner_mode: str) -> None:
        super().__init__(convert_charrefs=True)
        self._targets = heading_to_category
        self._winner_mode = winner_mode
        self.records: list[tuple[str, str, str, str]] = []
        self._in_p = False
        self._in_h4 = False
        self._heading_parts: list[str] = []
        self._want_ul = False
        self._pending_category = ''
        self._in_target_ul = False
        self._current_category = ''
        self._ul_depth = 0
        self._in_li = False
        self._li_depth = 0
        self._li_parts: list[str] = []
        self._em_parts: list[str] = []
        self._strong_parts: list[str] = []
        self._in_em = False
        self._in_strong = False
        self._li_has_strong = False

    def _heading_text(self) -> str:
        return _collapse_ws(''.join(self._heading_parts))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {'p', 'h3', 'h4'} and not self._in_li:
            self._in_p = tag == 'p'
            self._in_h4 = tag in {'h3', 'h4'}
            self._heading_parts = []
            return
        if tag == 'ul' and self._want_ul and not self._in_target_ul:
            self._in_target_ul = True
            self._current_category = self._pending_category
            self._want_ul = False
            self._ul_depth = 1
            return
        if self._in_target_ul and tag == 'ul':
            self._ul_depth += 1
        if self._in_target_ul and tag == 'li' and not self._in_li:
            self._in_li = True
            self._li_depth = 1
            self._li_parts = []
            self._em_parts = []
            self._strong_parts = []
            self._in_em = False
            self._in_strong = False
            self._li_has_strong = False
            return
        if self._in_li and tag == 'li':
            self._li_depth += 1
        if self._in_li and tag == 'em':
            self._in_em = True
        if self._in_li and tag == 'strong':
            self._in_strong = True
            self._li_has_strong = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {'p', 'h3', 'h4'} and (self._in_p or self._in_h4):
            heading = self._heading_text()
            self._in_p = False
            self._in_h4 = False
            self._heading_parts = []
            category = self._targets.get(heading.casefold())
            if category is not None:
                self._want_ul = True
                self._pending_category = category
            return
        if self._in_li and tag == 'em' and self._in_em:
            self._in_em = False
            return
        if self._in_li and tag == 'strong' and self._in_strong:
            self._in_strong = False
            return
        if self._in_li and tag == 'li':
            self._li_depth -= 1
            if self._li_depth <= 0:
                self._finish_li()
                self._in_li = False
            return
        if self._in_target_ul and tag == 'ul':
            self._ul_depth -= 1
            if self._ul_depth <= 0:
                self._in_target_ul = False
                self._current_category = ''

    def handle_data(self, data: str) -> None:
        if self._in_p or self._in_h4:
            self._heading_parts.append(data)
        if self._in_li:
            self._li_parts.append(data)
            if self._in_em:
                self._em_parts.append(data)
            if self._in_strong:
                self._strong_parts.append(data)

    def _finish_li(self) -> None:
        li_text = _collapse_ws(''.join(self._li_parts))
        if not li_text or not self._current_category:
            return
        if self._winner_mode == 'prefix':
            status = 'Winner' if _WINNER_PREFIX_RE.match(li_text) else 'Nominee'
            strong_title = '' if status == 'Winner' else _collapse_ws(
                ''.join(self._strong_parts)
            )
        else:
            status = 'Winner' if self._li_has_strong else 'Nominee'
            strong_title = _collapse_ws(''.join(self._strong_parts))
        em_title = _collapse_ws(''.join(self._em_parts))
        parsed = _citation_from_fragments(
            em_title, strong_title, li_text, self._current_category
        )
        if parsed is None:
            return
        title, author = parsed
        self.records.append((self._current_category, status, title, author))


class _Annual2024Parser(HTMLParser):
    """Parse 2024 h4 category headings plus following paragraphs.

    Collection is a heading-only paragraph (not h4) on the official 2024 page.
    """

    def __init__(self, heading_to_category: dict[str, str]) -> None:
        super().__init__(convert_charrefs=True)
        self._targets = heading_to_category
        self.records: list[tuple[str, str, str, str]] = []
        self._in_h4 = False
        self._h4_parts: list[str] = []
        self._current_category = ''
        self._in_p = False
        self._p_parts: list[str] = []
        self._seen: set[tuple[str, str]] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == 'h4':
            self._current_category = ''
            self._in_h4 = True
            self._h4_parts = []
            return
        if tag == 'p' and not self._in_p and not self._in_h4:
            self._in_p = True
            self._p_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == 'h4' and self._in_h4:
            heading = _collapse_ws(''.join(self._h4_parts))
            self._in_h4 = False
            self._h4_parts = []
            self._current_category = self._targets.get(heading.casefold(), '')
            return
        if tag == 'p' and self._in_p:
            self._finish_p()
            self._in_p = False

    def handle_data(self, data: str) -> None:
        if self._in_h4:
            self._h4_parts.append(data)
        if self._in_p:
            self._p_parts.append(data)

    def _paragraph_heading_category(self, text: str) -> str | None:
        """Recognize a heading-only paragraph whose entire text is Collection."""
        category = self._targets.get(text.casefold())
        if category == CATEGORY_COLLECTION:
            return category
        return None

    def _finish_p(self) -> None:
        text = _collapse_ws(''.join(self._p_parts))
        if not text:
            return
        heading_category = self._paragraph_heading_category(text)
        if heading_category is not None:
            self._current_category = heading_category
            return
        if not self._current_category:
            return
        is_winner = bool(_WINNER_PREFIX_RE.match(text))
        parsed = _parse_annual_citation(text, self._current_category)
        if parsed is None:
            return
        title, author = parsed
        seen_key = (self._current_category, _title_key(title))
        if seen_key in self._seen:
            return
        self._seen.add(seen_key)
        status = 'Winner' if is_winner else 'Nominee'
        self.records.append((self._current_category, status, title, author))


def _records_from_list(
    items: list[tuple[str, str, str, str]],
    award_year: int,
    source_url: str,
) -> list[_ParsedRecord]:
    records: list[_ParsedRecord] = []
    seen: set[tuple[str, str, str, str]] = set()
    for category, status, title, author in items:
        key = (category, status, _title_key(title), _author_key(author))
        if key in seen:
            continue
        seen.add(key)
        records.append(
            _make_record(
                award_year, category, status, title, (author,), source_url
            )
        )
    return records


def _parse_2013_html(html: str) -> list[_ParsedRecord]:
    parser = _CategoryListParser(_annual_heading_map(), winner_mode='strong')
    parser.feed(html)
    parser.close()
    return _records_from_list(parser.records, 2013, ANNUAL_2013_URL)


def _parse_2024_html(html: str) -> list[_ParsedRecord]:
    parser = _Annual2024Parser(_annual_heading_map())
    parser.feed(html)
    parser.close()
    return _records_from_list(parser.records, 2024, ANNUAL_2024_URL)


def _parse_2025_html(html: str) -> list[_ParsedRecord]:
    parser = _CategoryListParser(_annual_heading_map(), winner_mode='prefix')
    parser.feed(html)
    parser.close()
    return _records_from_list(parser.records, 2025, ANNUAL_2025_URL)


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------

def _make_record(
    award_year: int,
    category: str,
    status: str,
    title: str,
    authors: tuple[str, ...],
    source_url: str,
) -> _ParsedRecord:
    author = _join_authors(authors)
    return _ParsedRecord(
        award_year=award_year,
        category=category,
        status=status,
        work_title=title,
        work_author=author,
        source_url=source_url,
        match_authors=tuple(authors) if len(authors) > 1 else (author,),
    )


def _title_key(title: str) -> str:
    return _normalize_title_for_match(title)


def _author_key(author: str) -> str:
    return _normalize_text(_ascii_fold(author))


def _author_identity_keys(authors: tuple[str, ...] | str) -> tuple[str, ...]:
    if isinstance(authors, str):
        name_list = _split_author_names(authors)
    else:
        name_list = authors
    keys = [_author_key(name) for name in name_list]
    keys.append(_author_key(_join_authors(tuple(name_list))))
    return tuple(dict.fromkeys(key for key in keys if key))


def _record_identities(
    award_year: int,
    category: str,
    title: str,
    authors: tuple[str, ...] | str,
) -> set[tuple[int, str, str, str]]:
    """Normal year-scoped identity for merge/dedupe."""
    title_key = _title_key(title)
    return {
        (award_year, category, title_key, author_key)
        for author_key in _author_identity_keys(authors)
    }


def _correction_identities(
    category: str,
    title: str,
    authors: tuple[str, ...] | str,
) -> set[tuple[str, str, str]]:
    """Yearless 2013-correction identity. Do not use for ordinary dedupe."""
    title_key = _title_key(title)
    return {
        (category, title_key, author_key)
        for author_key in _author_identity_keys(authors)
    }


def _identities_for_record(
    record: _ParsedRecord,
) -> set[tuple[int, str, str, str]]:
    return _record_identities(
        record.award_year,
        record.category,
        record.work_title,
        record.match_authors,
    )


def _correction_identities_for_record(
    record: _ParsedRecord,
) -> set[tuple[str, str, str]]:
    return _correction_identities(
        record.category, record.work_title, record.match_authors
    )


def _works_for_category(
    works: list[_TableWork],
    category: str,
) -> list[_TableWork]:
    return [work for work in works if work.category == category]


def _records_for_category(
    records: list[_ParsedRecord],
    category: str,
) -> list[_ParsedRecord]:
    return [record for record in records if record.category == category]


def _annual_status_counts(records: list[_ParsedRecord]) -> tuple[int, int]:
    winners = sum(1 for record in records if record.status == 'Winner')
    nominees = sum(1 for record in records if record.status == 'Nominee')
    return winners, nominees


def _validate_novella_official_names(table_works: list[_TableWork]) -> None:
    by_year: dict[int, set[str]] = {}
    for work in table_works:
        if work.category != CATEGORY_NOVELLA:
            continue
        by_year.setdefault(work.award_year, set()).add(
            work.official_category.casefold()
        )
    expected = {
        2015: frozenset({'novella'}),
        2016: frozenset({'long fiction'}),
        2017: frozenset({'long fiction'}),
        2018: frozenset({'long fiction'}),
        2019: frozenset({'novella'}),
    }
    for year, names in expected.items():
        if year not in by_year:
            continue
        if by_year[year] != set(names):
            raise WorldFantasySourceError(
                'World Fantasy official Novella category name for '
                f'{year} was {sorted(by_year[year])}, expected {sorted(names)}'
            )


def _validate_source_components(
    nominee_works: list[_TableWork],
    winner_works: list[_TableWork],
    convention_1982: list[_TableWork],
    convention_1993: list[_TableWork],
    convention_2005: list[_TableWork],
    annual_2013: list[_ParsedRecord],
    annual_2024: list[_ParsedRecord],
    annual_2025: list[_ParsedRecord],
) -> None:
    """Fail closed if a required official page did not parse a usable slate."""
    for category in _CANONICAL_CATEGORIES:
        if not _works_for_category(nominee_works, category):
            raise WorldFantasySourceError(
                f'World Fantasy nominees table produced no {category} works'
            )
        if not _works_for_category(winner_works, category):
            raise WorldFantasySourceError(
                f'World Fantasy winners table produced no {category} works'
            )

    convention_required = (
        (
            '1982 convention page',
            convention_1982,
            (CATEGORY_NOVEL, CATEGORY_NOVELLA, CATEGORY_SHORT_FICTION),
        ),
        (
            '1993 convention page',
            convention_1993,
            (
                CATEGORY_NOVEL,
                CATEGORY_NOVELLA,
                CATEGORY_SHORT_FICTION,
                CATEGORY_COLLECTION,
            ),
        ),
        (
            '2005 convention page',
            convention_2005,
            (CATEGORY_NOVEL, CATEGORY_NOVELLA),
        ),
    )
    for label, works, required_categories in convention_required:
        for category in required_categories:
            category_works = _works_for_category(works, category)
            nominees = [work for work in category_works if work.status == 'Nominee']
            if not category_works or not nominees:
                raise WorldFantasySourceError(
                    f'World Fantasy {label} did not produce a usable '
                    f'{category} nominee slate'
                )

    for label, records in (
        ('2013 annual page', annual_2013),
        ('2024 annual page', annual_2024),
        ('2025 annual page', annual_2025),
    ):
        for category in _CANONICAL_CATEGORIES:
            winners, nominees = _annual_status_counts(
                _records_for_category(records, category)
            )
            if winners < 1 or nominees < 1:
                raise WorldFantasySourceError(
                    f'World Fantasy {label} did not produce at least one '
                    f'{category} Winner and at least one Nominee '
                    f'(winners={winners}, nominees={nominees})'
                )

    _validate_novella_official_names(
        nominee_works + winner_works + convention_1982
        + convention_1993 + convention_2005
    )


def _validate_merged_records(
    records: tuple[_ParsedRecord, ...],
    annual_2013: list[_ParsedRecord],
) -> None:
    correction_identities: set[tuple[str, str, str]] = set()
    for record in annual_2013:
        correction_identities.update(_correction_identities_for_record(record))
    for record in records:
        if record.award_year != 2012:
            continue
        if _correction_identities_for_record(record) & correction_identities:
            raise WorldFantasySourceError(
                'World Fantasy 2013 correction left a 2012 record for '
                f'{record.category} {record.work_title!r}'
            )

    for category in _CANONICAL_CATEGORIES:
        first_year = _CATEGORY_FIRST_YEAR[category]
        for year in (1982, 1993, 2005):
            if year < first_year:
                continue
            has_nominee = any(
                record.category == category
                and record.award_year == year
                and record.status == 'Nominee'
                for record in records
            )
            if not has_nominee:
                raise WorldFantasySourceError(
                    f'World Fantasy {category} {year} has no nominee slate'
                )


def _novella_official_labels_by_year(
    winner_works: list[_TableWork],
) -> dict[int, set[str]]:
    official_by_year: dict[int, set[str]] = {}
    for work in winner_works:
        if work.category != CATEGORY_NOVELLA:
            continue
        official_by_year.setdefault(work.award_year, set()).add(
            work.official_category.casefold()
        )
    return official_by_year


def _validate_full_archive_history(winner_works: list[_TableWork]) -> None:
    """Require the stable official master winners-table baseline."""
    novel_winner_years = {
        work.award_year
        for work in winner_works
        if work.category == CATEGORY_NOVEL and work.status == 'Winner'
    }
    missing_novel = sorted(NOVEL_MASTER_WINNER_YEARS - novel_winner_years)
    if missing_novel:
        raise WorldFantasySourceError(
            'World Fantasy Novel winners are missing required master-table '
            'years: ' + ', '.join(str(year) for year in missing_novel)
        )

    novella_winner_years = {
        work.award_year
        for work in winner_works
        if work.category == CATEGORY_NOVELLA and work.status == 'Winner'
    }
    missing_novella = sorted(NOVELLA_MASTER_WINNER_YEARS - novella_winner_years)
    if missing_novella:
        raise WorldFantasySourceError(
            'World Fantasy Novella winners are missing required master-table '
            'years: ' + ', '.join(str(year) for year in missing_novella)
        )

    official_by_year = _novella_official_labels_by_year(winner_works)
    for year, expected in NOVELLA_OFFICIAL_LABELS.items():
        names = official_by_year.get(year)
        if not names or names != {expected}:
            raise WorldFantasySourceError(
                'World Fantasy winners table did not establish '
                f'{expected} for Novella-slot {year}'
            )

    short_fiction_winner_years = {
        work.award_year
        for work in winner_works
        if work.category == CATEGORY_SHORT_FICTION and work.status == 'Winner'
    }
    missing_short_fiction = sorted(
        SHORT_FICTION_MASTER_WINNER_YEARS - short_fiction_winner_years
    )
    if missing_short_fiction:
        raise WorldFantasySourceError(
            'World Fantasy Short Fiction winners are missing required '
            'master-table years: '
            + ', '.join(str(year) for year in missing_short_fiction)
        )

    collection_winner_years = {
        work.award_year
        for work in winner_works
        if work.category == CATEGORY_COLLECTION and work.status == 'Winner'
    }
    missing_collection = sorted(
        COLLECTION_MASTER_WINNER_YEARS - collection_winner_years
    )
    if missing_collection:
        raise WorldFantasySourceError(
            'World Fantasy Collection winners are missing required '
            'master-table years: '
            + ', '.join(str(year) for year in missing_collection)
        )


def _build_records_from_pages(
    pages: _FetchedPages,
    *,
    validate_full_archive: bool = False,
) -> tuple[_ParsedRecord, ...]:
    winner_works = _table_works(pages.winners_html)
    nominee_works = _table_works(pages.nominees_html)
    convention_1982 = _table_works(pages.convention_1982_html)
    convention_1993 = _table_works(pages.convention_1993_html)
    convention_2005 = _table_works(pages.convention_2005_html)
    annual_2013 = _parse_2013_html(pages.annual_2013_html)
    annual_2024 = _parse_2024_html(pages.annual_2024_html)
    annual_2025 = _parse_2025_html(pages.annual_2025_html)
    _validate_source_components(
        nominee_works,
        winner_works,
        convention_1982,
        convention_1993,
        convention_2005,
        annual_2013,
        annual_2024,
        annual_2025,
    )

    records: list[_ParsedRecord] = []
    seen_identities: set[tuple[int, str, str, str]] = set()

    def _add(record: _ParsedRecord) -> None:
        identities = _identities_for_record(record)
        if identities & seen_identities:
            return
        seen_identities.update(identities)
        records.append(record)

    for work in winner_works:
        _add(
            _make_record(
                work.award_year,
                work.category,
                'Winner',
                work.work_title,
                work.authors,
                WINNERS_URL,
            )
        )

    correction_identities: set[tuple[str, str, str]] = set()
    for record in annual_2013:
        correction_identities.update(_correction_identities_for_record(record))
        _add(record)

    def _is_misfiled_2013_copy(
        award_year: int,
        category: str,
        title: str,
        authors: tuple[str, ...],
    ) -> bool:
        if award_year != 2012:
            return False
        return bool(
            _correction_identities(category, title, authors)
            & correction_identities
        )

    for work in nominee_works:
        identities = _record_identities(
            work.award_year, work.category, work.work_title, work.authors
        )
        if identities & seen_identities:
            continue
        if _is_misfiled_2013_copy(
            work.award_year, work.category, work.work_title, work.authors
        ):
            continue
        _add(
            _make_record(
                work.award_year,
                work.category,
                'Nominee',
                work.work_title,
                work.authors,
                NOMINEES_URL,
            )
        )

    for works, source_url in (
        (convention_1982, CONVENTION_1982_URL),
        (convention_1993, CONVENTION_1993_URL),
        (convention_2005, CONVENTION_2005_URL),
    ):
        for work in works:
            identities = _record_identities(
                work.award_year, work.category, work.work_title, work.authors
            )
            if identities & seen_identities:
                continue
            if _is_misfiled_2013_copy(
                work.award_year, work.category, work.work_title, work.authors
            ):
                continue
            _add(
                _make_record(
                    work.award_year,
                    work.category,
                    work.status,
                    work.work_title,
                    work.authors,
                    source_url,
                )
            )

    for record in annual_2024:
        _add(record)
    for record in annual_2025:
        _add(record)

    merged = tuple(records)
    _validate_merged_records(merged, annual_2013)
    if validate_full_archive:
        _validate_full_archive_history(winner_works)
    return merged


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


def _normalize_title_for_match(value: str) -> str:
    text = _clean_title(value)
    text = _normalize_text(text)
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


def _author_forms(author: str) -> set[str]:
    forms: set[str] = set()
    candidates = [author, *_split_author_names(author)]
    for candidate in candidates:
        forms.add(_normalize_text(candidate))
        forms.add(_normalize_text(_ascii_fold(candidate)))
    return {form for form in forms if form}


def _authors_match(query_author: str, record: _ParsedRecord) -> bool:
    query_forms = _author_forms(query_author)
    record_forms = _author_forms(record.work_author)
    for name in record.match_authors:
        record_forms.update(_author_forms(name))
    return bool(query_forms & record_forms)


def _record_matches(record: _ParsedRecord, title: str, author: str) -> bool:
    return _titles_equivalent(title, record.work_title) and _authors_match(
        author, record
    )


def _to_award_result(record: _ParsedRecord) -> AwardResult:
    return AwardResult(
        work_title=record.work_title,
        work_author=record.work_author,
        award_name='World Fantasy Award',
        award_year=record.award_year,
        category=record.category,
        status=record.status,
        rank=None,
        source_name='World Fantasy Awards',
        source_url=record.source_url,
        notes=None,
    )


# ---------------------------------------------------------------------------
# Public lookup
# ---------------------------------------------------------------------------

def lookup(title: str, author: str, series: str | None = None) -> list[AwardResult]:
    """Look up World Fantasy Award Novel, Novella, Short Fiction, and Collection results."""
    cleaned_title = title.strip()
    cleaned_author = author.strip()
    if not cleaned_title:
        raise ValueError('title must be a non-empty string')
    if not cleaned_author:
        raise ValueError('author must be a non-empty string')

    matches: list[AwardResult] = []
    seen: set[tuple[int, str, str, str, str, str]] = set()
    for record in _get_records():
        if not _record_matches(record, cleaned_title, cleaned_author):
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
