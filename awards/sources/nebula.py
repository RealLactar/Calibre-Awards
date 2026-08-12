"""Official Nebula Awards Best Novel source (nebulas.sfwa.org)."""

from __future__ import annotations

import re
import threading
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from urllib.parse import urljoin

from ..model import AwardResult

TIMEOUT_SECONDS = 30
BEST_NOVEL_URL = 'https://nebulas.sfwa.org/award/best-novel/'

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
_WINNER_BEST_NOVEL_RE = re.compile(
    r'Winner,\s*Best Novel\s+in\s+(\d{4})',
    re.IGNORECASE,
)
_NOMINATED_BEST_NOVEL_RE = re.compile(
    r'Nominated for\b.*?Best Novel\s+in\s+(\d{4})',
    re.IGNORECASE | re.DOTALL,
)
_COMPACT_CITATION_RE = re.compile(
    r'^(?P<title>.+?),\s*by\s+(?P<author>.+?)(?:\s*\((?P<publisher>.*)\))?\s*$',
    re.IGNORECASE | re.DOTALL,
)
_INITIALS_SPACE_RE = re.compile(r'\b([A-Za-z])\.\s+')


class NebulaSourceError(RuntimeError):
    """Raised when the official Nebula site blocks or fails retrieval."""


@dataclass(frozen=True, slots=True)
class _ParsedRecord:
    award_year: int
    status: str
    work_title: str
    work_author: str
    source_url: str | None


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


def _fetch_best_novel_pages(
    opener: urllib.request.OpenerDirector,
) -> list[tuple[str, str]]:
    """Return list of (page_url, html) following official rel=next links."""
    pages: list[tuple[str, str]] = []
    url: str | None = BEST_NOVEL_URL
    seen: set[str] = set()
    while url and url not in seen:
        seen.add(url)
        html = _fetch_html(opener, url)
        pages.append((url, html))
        url = _next_page_url(html)
    if not pages:
        raise NebulaSourceError('Nebula Best Novel archive returned no pages')
    return pages


_best_novel_pages_cache: tuple[tuple[str, str], ...] | None = None
_cache_lock = threading.Lock()


def _get_best_novel_pages() -> tuple[tuple[str, str], ...]:
    """Return cached Best Novel pages, fetching once per process on success."""
    global _best_novel_pages_cache
    with _cache_lock:
        if _best_novel_pages_cache is not None:
            return _best_novel_pages_cache
        opener = _build_opener()
        pages = tuple(_fetch_best_novel_pages(opener))
        _best_novel_pages_cache = pages
        return pages


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


def _parse_compact_citation(em_text: str) -> tuple[str, str] | None:
    match = _COMPACT_CITATION_RE.match(_collapse_ws(em_text))
    if not match:
        return None
    title = _collapse_ws(match.group('title'))
    author = _collapse_ws(match.group('author'))
    if not title or not author:
        return None
    return title, author


def _best_novel_status(li_text: str) -> str | None:
    """Return Winner/Nominated from Best Novel-specific wording only."""
    # Star icons are ignored: other awards on the same row may be starred.
    if _WINNER_BEST_NOVEL_RE.search(li_text):
        return 'Winner'
    if _NOMINATED_BEST_NOVEL_RE.search(li_text):
        return 'Nominated'
    return None


class _NebulaBestNovelParser(HTMLParser):
    """Parse Best Novel archive pages into winner/nominated records."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
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
        self._li_parts: list[str] = []
        self._em_parts: list[str] = []
        self._author_parts: list[str] = []
        self._work_href: str | None = None
        self._seen: set[tuple[int, str, str, str, str | None]] = set()

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
            self._work_href = None
            self._in_em = False
            self._in_author_link = False
            return

        if self._in_li and tag == 'li':
            self._li_depth += 1

        if self._in_li and tag == 'em':
            self._in_em = True

        if self._in_li and tag == 'a':
            href = attr.get('href', '')
            if '/nominated-work/' in href and self._work_href is None:
                self._work_href = urljoin(BEST_NOVEL_URL, href)
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
            if self._in_author_link:
                self._author_parts.append(data)

    def _finish_li(self) -> None:
        if self._year is None:
            return

        li_text = _collapse_ws(''.join(self._li_parts))
        status = _best_novel_status(li_text)
        if status is None:
            return

        em_text = _collapse_ws(''.join(self._em_parts))
        authors = [
            _collapse_ws(part)
            for part in ''.join(self._author_parts).split('\0')
            if _collapse_ws(part)
        ]

        title = ''
        author = ''
        compact = _parse_compact_citation(em_text) if em_text else None
        if compact is not None:
            title, author = compact
        elif em_text and authors:
            title = em_text
            author = _join_authors(authors)
        elif em_text and not authors:
            # Compact layout should already have matched; skip incomplete rows.
            return
        else:
            return

        if not title or not author:
            return

        key = (self._year, status, title.casefold(), author.casefold(), self._work_href)
        if key in self._seen:
            return
        self._seen.add(key)

        self.records.append(
            _ParsedRecord(
                award_year=self._year,
                status=status,
                work_title=title,
                work_author=author,
                source_url=self._work_href,
            )
        )


def _parse_best_novel_html(html: str) -> list[_ParsedRecord]:
    parser = _NebulaBestNovelParser()
    parser.feed(html)
    parser.close()
    return parser.records


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
        award_name='Nebula Award',
        award_year=record.award_year,
        category='Best Novel',
        status=record.status,
        rank=None,
        source_name='Nebula Awards',
        source_url=record.source_url,
        notes=None,
    )


# ---------------------------------------------------------------------------
# Public lookup
# ---------------------------------------------------------------------------

def lookup(title: str, author: str) -> list[AwardResult]:
    """Look up Nebula Best Novel results for a title and author."""
    cleaned_title = title.strip()
    cleaned_author = author.strip()
    if not cleaned_title:
        raise ValueError('title must be a non-empty string')
    if not cleaned_author:
        raise ValueError('author must be a non-empty string')

    pages = _get_best_novel_pages()

    matches: list[AwardResult] = []
    seen_results: set[tuple[int, str, str, str, str | None]] = set()
    for _page_url, html in pages:
        for record in _parse_best_novel_html(html):
            if not _record_matches(record, cleaned_title, cleaned_author):
                continue
            key = (
                record.award_year,
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
