"""Official World Fantasy Award Novel source (worldfantasy.org)."""

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
ANNUAL_2013_URL = 'https://worldfantasy.org/2013-world-fantasy-awards/'
ANNUAL_2024_URL = (
    'https://worldfantasy.org/2024-world-fantasy-nominations-and-winners/'
)
ANNUAL_2025_URL = 'https://worldfantasy.org/2025-wfc-nominations-and-winners/'

SOURCE_PAGE_URLS = (
    NOMINEES_URL,
    WINNERS_URL,
    ANNUAL_2013_URL,
    ANNUAL_2024_URL,
    ANNUAL_2025_URL,
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
class _ParsedRecord:
    award_year: int
    status: str
    work_title: str
    work_author: str
    source_url: str
    match_authors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _FetchedPages:
    nominees_html: str
    winners_html: str
    annual_2013_html: str
    annual_2024_html: str
    annual_2025_html: str


@dataclass(frozen=True, slots=True)
class _TableWork:
    award_year: int
    work_title: str
    authors: tuple[str, ...]


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
    """Return cached Novel records, fetching once per process on success."""
    global _records_cache
    with _cache_lock:
        if _records_cache is not None:
            return _records_cache
        opener = _build_opener()
        pages = _fetch_source_pages(opener)
        records = _build_records_from_pages(pages)
        if not records:
            raise WorldFantasySourceError(
                'World Fantasy pages were retrieved but no Novel records '
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


def _recover_novel_title(cells: list[str]) -> str | None:
    if len(cells) >= 6 and cells[3].casefold() == 'novel':
        return _clean_title(cells[4])
    if len(cells) == 5 and cells[3].casefold() == 'novel':
        jammed = cells[4]
        match = _TRAILING_STATUS_RE.match(jammed)
        if match is None:
            title = _clean_title(jammed)
            return title or None
        return _clean_title(match.group('title')) or None
    return None


def _novel_table_works(html: str) -> list[_TableWork]:
    grouped: dict[tuple[int, str], list[str]] = {}
    titles_by_group: dict[tuple[int, str], str] = {}
    order: list[tuple[int, str]] = []
    for cells in _parse_table_rows(html):
        if len(cells) < 5:
            continue
        if cells[0].casefold() == 'first name':
            continue
        if cells[3].casefold() != 'novel':
            continue
        year = _parse_year(cells[2])
        title = _recover_novel_title(cells)
        first = _collapse_ws(cells[0])
        last = _collapse_ws(cells[1])
        author = _collapse_ws(f'{first} {last}')
        if year is None or not title or not author:
            continue
        group_key = (year, _title_key(title))
        if group_key not in grouped:
            grouped[group_key] = []
            titles_by_group[group_key] = title
            order.append(group_key)
        if author not in grouped[group_key]:
            grouped[group_key].append(author)
    return [
        _TableWork(
            award_year=group_key[0],
            work_title=titles_by_group[group_key],
            authors=tuple(grouped[group_key]),
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


def _citation_from_fragments(
    em_title: str,
    strong_title: str,
    li_text: str,
) -> tuple[str, str] | None:
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
    """Capture one category <ul> that follows a target heading."""

    def __init__(self, target_heading: str, winner_mode: str) -> None:
        super().__init__(convert_charrefs=True)
        self._target = target_heading.casefold()
        self._winner_mode = winner_mode
        self.records: list[tuple[str, str, str]] = []
        self._in_p = False
        self._in_h4 = False
        self._heading_parts: list[str] = []
        self._want_ul = False
        self._in_target_ul = False
        self._ul_depth = 0
        self._done = False
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
        if self._done:
            return
        if tag in {'p', 'h3', 'h4'} and not self._in_li:
            self._in_p = tag == 'p'
            self._in_h4 = tag in {'h3', 'h4'}
            self._heading_parts = []
            return
        if tag == 'ul' and self._want_ul and not self._in_target_ul:
            self._in_target_ul = True
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
            if heading.casefold() == self._target:
                self._want_ul = True
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
                self._done = True

    def handle_data(self, data: str) -> None:
        if self._done:
            return
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
        if not li_text:
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
        parsed = _citation_from_fragments(em_title, strong_title, li_text)
        if parsed is None:
            return
        title, author = parsed
        self.records.append((status, title, author))


class _Annual2024Parser(HTMLParser):
    """Parse the 2024 NOVEL heading plus following paragraphs."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.records: list[tuple[str, str, str]] = []
        self._in_h4 = False
        self._h4_parts: list[str] = []
        self._in_novel = False
        self._in_p = False
        self._p_parts: list[str] = []
        self._seen: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == 'h4':
            if self._in_novel:
                self._in_novel = False
            self._in_h4 = True
            self._h4_parts = []
            return
        if self._in_novel and tag == 'p' and not self._in_p:
            self._in_p = True
            self._p_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == 'h4' and self._in_h4:
            heading = _collapse_ws(''.join(self._h4_parts))
            self._in_h4 = False
            self._h4_parts = []
            self._in_novel = heading.casefold() == 'novel'
            return
        if tag == 'p' and self._in_p:
            self._finish_p()
            self._in_p = False

    def handle_data(self, data: str) -> None:
        if self._in_h4:
            self._h4_parts.append(data)
        if self._in_p:
            self._p_parts.append(data)

    def _finish_p(self) -> None:
        text = _collapse_ws(''.join(self._p_parts))
        if not text:
            return
        is_winner = bool(_WINNER_PREFIX_RE.match(text))
        parsed = _parse_by_or_comma_citation(text)
        if parsed is None:
            return
        title, author = parsed
        title_key = _title_key(title)
        if title_key in self._seen:
            return
        self._seen.add(title_key)
        status = 'Winner' if is_winner else 'Nominee'
        self.records.append((status, title, author))


def _records_from_list(
    items: list[tuple[str, str, str]],
    award_year: int,
    source_url: str,
) -> list[_ParsedRecord]:
    records: list[_ParsedRecord] = []
    seen: set[tuple[str, str, str]] = set()
    for status, title, author in items:
        key = (status, _title_key(title), _author_key(author))
        if key in seen:
            continue
        seen.add(key)
        records.append(
            _make_record(award_year, status, title, (author,), source_url)
        )
    return records


def _parse_2013_novel_html(html: str) -> list[_ParsedRecord]:
    parser = _CategoryListParser('novel', winner_mode='strong')
    parser.feed(html)
    parser.close()
    return _records_from_list(parser.records, 2013, ANNUAL_2013_URL)


def _parse_2024_novel_html(html: str) -> list[_ParsedRecord]:
    parser = _Annual2024Parser()
    parser.feed(html)
    parser.close()
    return _records_from_list(parser.records, 2024, ANNUAL_2024_URL)


def _parse_2025_novel_html(html: str) -> list[_ParsedRecord]:
    parser = _CategoryListParser('best novel', winner_mode='prefix')
    parser.feed(html)
    parser.close()
    return _records_from_list(parser.records, 2025, ANNUAL_2025_URL)


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------

def _make_record(
    award_year: int,
    status: str,
    title: str,
    authors: tuple[str, ...],
    source_url: str,
) -> _ParsedRecord:
    author = _join_authors(authors)
    return _ParsedRecord(
        award_year=award_year,
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


def _work_identities(title: str, authors: tuple[str, ...] | str) -> set[tuple[str, str]]:
    title_key = _title_key(title)
    if isinstance(authors, str):
        name_list = _split_author_names(authors)
    else:
        name_list = authors
    identities = {(title_key, _author_key(name)) for name in name_list}
    identities.add((title_key, _author_key(_join_authors(tuple(name_list)))))
    return identities


def _identities_for_record(record: _ParsedRecord) -> set[tuple[str, str]]:
    return _work_identities(record.work_title, record.match_authors)


def _build_records_from_html(
    nominees_html: str,
    winners_html: str,
    annual_2013_html: str,
    annual_2024_html: str,
    annual_2025_html: str,
) -> tuple[_ParsedRecord, ...]:
    pages = _FetchedPages(
        nominees_html=nominees_html,
        winners_html=winners_html,
        annual_2013_html=annual_2013_html,
        annual_2024_html=annual_2024_html,
        annual_2025_html=annual_2025_html,
    )
    return _build_records_from_pages(pages)


def _annual_status_counts(records: list[_ParsedRecord]) -> tuple[int, int]:
    winners = sum(1 for record in records if record.status == 'Winner')
    nominees = sum(1 for record in records if record.status == 'Nominee')
    return winners, nominees


def _validate_source_components(
    nominee_works: list[_TableWork],
    winner_works: list[_TableWork],
    annual_2013: list[_ParsedRecord],
    annual_2024: list[_ParsedRecord],
    annual_2025: list[_ParsedRecord],
) -> None:
    """Fail closed if any required official page did not parse a usable Novel slate."""
    if not nominee_works:
        raise WorldFantasySourceError(
            'World Fantasy nominees table produced no Novel works'
        )
    if not winner_works:
        raise WorldFantasySourceError(
            'World Fantasy winners table produced no Novel works'
        )
    for label, records in (
        ('2013 annual page', annual_2013),
        ('2024 annual page', annual_2024),
        ('2025 annual page', annual_2025),
    ):
        winners, nominees = _annual_status_counts(records)
        if winners != 1 or nominees < 1:
            raise WorldFantasySourceError(
                f'World Fantasy {label} did not produce exactly one '
                f'Winner and at least one Nominee '
                f'(winners={winners}, nominees={nominees})'
            )


def _build_records_from_pages(pages: _FetchedPages) -> tuple[_ParsedRecord, ...]:
    winner_works = _novel_table_works(pages.winners_html)
    nominee_works = _novel_table_works(pages.nominees_html)
    annual_2013 = _parse_2013_novel_html(pages.annual_2013_html)
    annual_2024 = _parse_2024_novel_html(pages.annual_2024_html)
    annual_2025 = _parse_2025_novel_html(pages.annual_2025_html)
    _validate_source_components(
        nominee_works,
        winner_works,
        annual_2013,
        annual_2024,
        annual_2025,
    )

    records: list[_ParsedRecord] = []
    seen_identities: set[tuple[str, str]] = set()

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
                'Winner',
                work.work_title,
                work.authors,
                WINNERS_URL,
            )
        )

    correction_identities: set[tuple[str, str]] = set()
    for record in annual_2013:
        correction_identities.update(_identities_for_record(record))
        _add(record)

    for work in nominee_works:
        identities = _work_identities(work.work_title, work.authors)
        if identities & seen_identities:
            continue
        if identities & correction_identities:
            continue
        _add(
            _make_record(
                work.award_year,
                'Nominee',
                work.work_title,
                work.authors,
                NOMINEES_URL,
            )
        )

    for record in annual_2024:
        _add(record)
    for record in annual_2025:
        _add(record)

    return tuple(records)


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
        category='Novel',
        status=record.status,
        rank=None,
        source_name='World Fantasy Awards',
        source_url=record.source_url,
        notes=None,
    )


# ---------------------------------------------------------------------------
# Public lookup
# ---------------------------------------------------------------------------

def lookup(title: str, author: str) -> list[AwardResult]:
    """Look up World Fantasy Award Novel results for a title and author."""
    cleaned_title = title.strip()
    cleaned_author = author.strip()
    if not cleaned_title:
        raise ValueError('title must be a non-empty string')
    if not cleaned_author:
        raise ValueError('author must be a non-empty string')

    matches: list[AwardResult] = []
    seen: set[tuple[int, str, str, str, str]] = set()
    for record in _get_records():
        if not _record_matches(record, cleaned_title, cleaned_author):
            continue
        key = (
            record.award_year,
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
