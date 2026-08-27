"""Official ALA John Newbery Medal HTML archive parsers.

This phase parses listing tables and winner-page bylines only. It does not
fetch the network, register an engine source, or cover 1922-1929 / 2024+.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from ..matching import normalize_title_conjunctions

AWARD_NAME = 'Newbery Medal'
CATEGORY = "Children's Literature"
SOURCE_HOME_URL = 'https://www.ala.org/'
DETAIL_ORIGIN = 'https://www.ala.org'

ARCHIVE_URL_2004_2023 = (
    'https://www.ala.org/awards/books-media/john-newbery-medal-2'
)
ARCHIVE_URL_1992_2003 = (
    'https://www.ala.org/awards/books-media/john-newbery-medal'
)
ARCHIVE_URL_1930_1991 = (
    'https://www.ala.org/awards/books-media/john-newbery-medal-1'
)
ARCHIVE_URLS = (
    ARCHIVE_URL_2004_2023,
    ARCHIVE_URL_1992_2003,
    ARCHIVE_URL_1930_1991,
)
# Drupal listing pages currently cover these years. Earlier and later years
# are out of scope for this parser phase and are not a structural failure.
ARCHIVE_MIN_YEAR = 1930
ARCHIVE_MAX_YEAR = 2023

_OFFICIAL_HTML_HOSTS = frozenset({'ala.org', 'www.ala.org'})
_DETAIL_SLUG_RE = re.compile(r'^[0-9A-Za-z][0-9A-Za-z_-]*$')
_HEADING_YEAR_RE = re.compile(r'^(\d{4})$')
_WINNER_HONOR_RANK_RE = re.compile(
    r'^(?P<year>\d{4})\s*-\s*(?P<label>Winner|Honor)\(s\)\s*$',
    re.IGNORECASE,
)
_RUNNER_UP_RANK_RE = re.compile(
    r'^(?P<year>\d{4})\s*-\s*Runner(?:-|\s+)up(?:s|\(s\))?\s*$',
    re.IGNORECASE,
)
_INITIALS_SPACE_RE = re.compile(r'\b([A-Za-z])\.\s+')
_QUOTED_TITLE_PREFIX_RE = re.compile(
    r'^(?:'
    r'"[^"]+"'
    r'|\u201c[^\u201d]+\u201d'
    r")\s*"
)
_BYLINE_LEAD_RE = re.compile(
    r'^(?:written\s+by|by)\s+(?P<author>.+)$',
    re.IGNORECASE | re.DOTALL,
)
_PUBLISHER_CUT_RE = re.compile(
    r'[.,]?\s*(?:,\s*)?(?:and\s+)?published\s+by\b.*$',
    re.IGNORECASE | re.DOTALL,
)
_MAX_AUTHOR_LENGTH = 80


class NewberySourceError(RuntimeError):
    """Raised when official Newbery HTML cannot be parsed safely."""


@dataclass(frozen=True, slots=True)
class _ListingRecord:
    """One ALA listing-table row. Author is not present on listing pages."""

    work_title: str
    award_year: int
    status: str
    detail_url: str
    source_url: str


def _collapse_ws(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def _class_set(attrs: list[tuple[str, str | None]]) -> set[str]:
    attr = {name: (value or '') for name, value in attrs}
    return set(attr.get('class', '').split())


def _attr_map(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
    return {name: (value or '') for name, value in attrs}


def _safe_detail_url(href: str | None) -> str | None:
    """Return an official https://www.ala.org/winner/{slug} URL, or None."""
    if not href or not href.strip():
        return None
    resolved = urljoin(f'{DETAIL_ORIGIN}/', href.strip())
    parsed = urlparse(resolved)
    if parsed.scheme != 'https':
        return None
    host = (parsed.hostname or '').casefold().rstrip('.')
    if host not in _OFFICIAL_HTML_HOSTS:
        return None
    parts = [piece for piece in parsed.path.split('/') if piece]
    if len(parts) != 2:
        return None
    kind, slug = parts
    if kind.casefold() != 'winner' or not _DETAIL_SLUG_RE.fullmatch(slug):
        return None
    return f'{DETAIL_ORIGIN}/winner/{slug}'


def _normalize_status(label: str) -> str:
    key = _collapse_ws(label).casefold()
    if key == 'winner':
        return 'Winner'
    if key in {'honor', 'runner-up', 'runner up'}:
        return 'Honor'
    raise NewberySourceError(
        f'Newbery listing row has an unrecognized status {label!r}'
    )


def _parse_rank_text(text: str) -> tuple[int, str]:
    cleaned = _collapse_ws(text)
    match = _WINNER_HONOR_RANK_RE.fullmatch(cleaned)
    if match is not None:
        return int(match.group('year')), _normalize_status(match.group('label'))
    match = _RUNNER_UP_RANK_RE.fullmatch(cleaned)
    if match is not None:
        return int(match.group('year')), 'Honor'
    raise NewberySourceError(
        'Newbery listing row has a malformed award status '
        f'{cleaned!r}; expected "YYYY - Winner(s)" or "YYYY - Honor(s)"'
    )


class _NewberyListingParser(HTMLParser):
    """Parse one ALA Newbery Drupal winners-table page into listing records."""

    def __init__(self, source_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.source_url = source_url
        self.records: list[_ListingRecord] = []
        self._section_year: int | None = None
        self._in_year_heading = False
        self._heading_buffer: list[str] = []
        self._listing_table_depth = 0
        self._in_thead = False
        self._in_row = False
        self._td_kind: str | None = None
        self._in_title_p = False
        self._title_buffer: list[str] = []
        self._title_href: str | None = None
        self._rank_buffer: list[str] = []
        self._seen: set[tuple[int, str, str, str]] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = _class_set(attrs)
        attr = _attr_map(attrs)

        if tag == 'h3' and 'accordion-item__heading' in classes:
            self._in_year_heading = True
            self._heading_buffer = []
            return

        if tag == 'table' and 'views-table' in classes:
            self._listing_table_depth = 1
            return
        if tag == 'table' and self._listing_table_depth:
            self._listing_table_depth += 1
            return

        if not self._listing_table_depth:
            return

        if tag == 'thead':
            self._in_thead = True
            return
        if self._in_thead:
            return

        if tag == 'tr':
            self._in_row = True
            self._td_kind = None
            self._in_title_p = False
            self._title_buffer = []
            self._title_href = None
            self._rank_buffer = []
            return

        if not self._in_row:
            return

        if tag == 'td':
            if 'views-field-title-1' in classes:
                self._td_kind = 'title'
            elif 'views-field-field-winner-rank' in classes:
                self._td_kind = 'rank'
            else:
                self._td_kind = 'other'
            return

        if tag == 'p' and self._td_kind == 'title':
            self._in_title_p = True
            return

        if tag == 'a' and self._td_kind == 'title' and self._title_href is None:
            self._title_href = attr.get('href') or None

    def handle_endtag(self, tag: str) -> None:
        if tag == 'h3' and self._in_year_heading:
            heading = _collapse_ws(''.join(self._heading_buffer))
            year_match = _HEADING_YEAR_RE.fullmatch(heading)
            self._section_year = int(year_match.group(1)) if year_match else None
            self._in_year_heading = False
            self._heading_buffer = []
            return

        if tag == 'thead' and self._listing_table_depth:
            self._in_thead = False
            return

        if tag == 'p' and self._in_title_p:
            self._in_title_p = False
            return

        if tag == 'td' and self._in_row:
            self._td_kind = None
            self._in_title_p = False
            return

        if tag == 'tr' and self._in_row:
            self._finish_row()
            self._in_row = False
            return

        if tag == 'table' and self._listing_table_depth:
            self._listing_table_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_year_heading:
            self._heading_buffer.append(data)
            return
        if self._td_kind == 'title' and not self._in_title_p:
            self._title_buffer.append(data)
            return
        if self._td_kind == 'rank':
            self._rank_buffer.append(data)

    def _finish_row(self) -> None:
        title = _collapse_ws(''.join(self._title_buffer))
        rank_text = _collapse_ws(''.join(self._rank_buffer))
        href = self._title_href
        if not title and not rank_text and not href:
            return
        if not title:
            raise NewberySourceError(
                'Newbery listing row is missing a title for '
                f'{self.source_url}'
            )
        if not rank_text:
            raise NewberySourceError(
                'Newbery listing row is missing an award status for '
                f'{title!r} on {self.source_url}'
            )
        award_year, status = _parse_rank_text(rank_text)
        if (
            self._section_year is not None
            and award_year != self._section_year
        ):
            raise NewberySourceError(
                'Newbery listing row year does not match its accordion '
                f'section: row={award_year}, section={self._section_year} '
                f'for {title!r} on {self.source_url}'
            )
        detail_url = _safe_detail_url(href)
        if detail_url is None:
            raise NewberySourceError(
                'Newbery listing row is missing an official winner URL for '
                f'{title!r} on {self.source_url}'
            )
        key = (
            award_year,
            status.casefold(),
            title.casefold(),
            detail_url.casefold(),
        )
        if key in self._seen:
            return
        self._seen.add(key)
        self.records.append(
            _ListingRecord(
                work_title=title,
                award_year=award_year,
                status=status,
                detail_url=detail_url,
                source_url=self.source_url,
            )
        )


def _parse_listing_html(html: str, source_url: str) -> list[_ListingRecord]:
    """Parse one official Newbery listing page. Malformed rows raise."""
    parser = _NewberyListingParser(source_url)
    parser.feed(html)
    parser.close()
    return parser.records


def _author_from_byline(text: str) -> str | None:
    """Extract a work author from an ALA winner-page byline, or None.

    Stops before publisher information. Does not guess from blurbs.
    """
    cleaned = _collapse_ws(text)
    if not cleaned:
        return None
    remainder = _QUOTED_TITLE_PREFIX_RE.sub('', cleaned, count=1).strip()
    match = _BYLINE_LEAD_RE.fullmatch(remainder)
    if match is None:
        return None
    author = _PUBLISHER_CUT_RE.sub('', match.group('author')).strip()
    author = author.strip(' ,.;')
    if not author:
        return None
    if 'published by' in author.casefold():
        return None
    if len(author) > _MAX_AUTHOR_LENGTH:
        return None
    return author


class _NewberyDetailParser(HTMLParser):
    """Capture the first paragraph after h1; ignore About/body blurbs."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.byline: str | None = None
        self._in_h1 = False
        self._seen_h1 = False
        self._in_byline_p = False
        self._byline_buffer: list[str] = []
        self._byline_done = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == 'h1':
            self._in_h1 = True
            return
        if self._byline_done or self._in_h1:
            return
        if tag == 'h2' and self._seen_h1:
            self._byline_done = True
            return
        if tag == 'p' and self._seen_h1 and not self._in_byline_p:
            self._in_byline_p = True
            self._byline_buffer = []

    def handle_endtag(self, tag: str) -> None:
        if tag == 'h1' and self._in_h1:
            self._in_h1 = False
            self._seen_h1 = True
            return
        if tag == 'p' and self._in_byline_p:
            self.byline = _collapse_ws(''.join(self._byline_buffer))
            self._in_byline_p = False
            self._byline_done = True

    def handle_data(self, data: str) -> None:
        if self._in_byline_p:
            self._byline_buffer.append(data)


def _parse_detail_author(html: str) -> str | None:
    """Return the winner-page byline author, or None if none is usable."""
    parser = _NewberyDetailParser()
    parser.feed(html)
    parser.close()
    if not parser.byline:
        return None
    return _author_from_byline(parser.byline)


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
