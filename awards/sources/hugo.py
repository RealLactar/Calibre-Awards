"""Official Hugo Awards Best Novel source (thehugoawards.org)."""

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

from ..model import AwardResult
from .hugo_rankings import HugoRanking, HUGO_BEST_NOVEL_RANKINGS

TIMEOUT_SECONDS = 30
PAGES_ENDPOINT = 'https://www.thehugoawards.org/wp-json/wp/v2/pages'
HISTORY_PARENT_PAGE_ID = 6
ARCHIVE_PER_PAGE = 100
ARCHIVE_FIELDS = 'title,link,slug,content'

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
_TRANSLATOR_AUTHOR_SUFFIX_RE = re.compile(
    r',\s*(?:translated by\s+.+|.+\s+translator)\s*$',
    re.IGNORECASE,
)
_WORD_SEPARATOR_HYPHEN_RE = re.compile(
    r'(\w)[\u2010\u2011\u2012\u2013\u2014\u2212-](\w)'
)


class HugoSourceError(RuntimeError):
    """Raised when the official Hugo archive cannot be retrieved or validated."""


@dataclass(frozen=True, slots=True)
class _ParsedRecord:
    award_year: int
    status: str
    work_title: str
    work_author: str
    source_url: str
    match_titles: tuple[str, ...]


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
    return bool(cleaned) and _BALLOT_COUNT_NOTE_RE.fullmatch(cleaned) is not None


def _is_non_work(text: str) -> bool:
    cleaned = _collapse_ws(text).casefold()
    if not cleaned:
        return True
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
    start = stripped.rfind(opener)
    if start < 0:
        return stripped
    return stripped[:start].rstrip()


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


def _primary_and_match_titles(displayed_title: str) -> tuple[str, tuple[str, ...]]:
    displayed = _collapse_ws(displayed_title)
    match = _ALT_TITLE_RE.fullmatch(displayed)
    if match is None:
        return displayed, (displayed,)
    primary = _collapse_ws(match.group('primary'))
    alternate = _collapse_ws(match.group('alt'))
    if not primary:
        return displayed, (displayed,)
    titles = [primary]
    if displayed not in titles:
        titles.append(displayed)
    if alternate and alternate not in titles:
        titles.append(alternate)
    return primary, tuple(titles)


class _HugoBestNovelParser(HTMLParser):
    """Parse one Hugo year page's exact Best Novel list."""

    def __init__(self, award_year: int, source_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.award_year = award_year
        self.source_url = source_url
        self.records: list[_ParsedRecord] = []
        self._strong_parts: list[str] = []
        self._in_strong = False
        self._pending_best_novel = False
        self._in_best_novel_list = False
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
        self._seen: set[tuple[int, str, str, str, str]] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {name: (value or '') for name, value in attrs}

        if tag == 'strong' and not self._capturing_li:
            self._in_strong = True
            self._strong_parts = []

        if (
            self._pending_best_novel
            and not self._in_best_novel_list
            and tag not in {'ul', 'br'}
        ):
            self._pending_best_novel = False

        if tag == 'ul':
            if self._pending_best_novel and not self._in_best_novel_list:
                self._in_best_novel_list = True
                self._list_depth = 1
                self._pending_best_novel = False
            elif self._in_best_novel_list:
                self._list_depth += 1

        if tag == 'li' and self._in_best_novel_list:
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
            if heading == 'Best Novel':
                self._pending_best_novel = True
            elif heading:
                self._pending_best_novel = False
            return

        if self._capturing_li and self._in_title_tag and tag == self._title_tag:
            self._title_depth -= 1
            if self._title_depth <= 0:
                self._in_title_tag = False
                self._title_tag = None
                self._title_finished = True
            return

        if tag == 'li' and self._in_best_novel_list and self._li_depth:
            self._li_depth -= 1
            if self._li_depth == 0:
                self._finish_li()
            return

        if tag == 'ul' and self._in_best_novel_list:
            self._list_depth -= 1
            if self._list_depth <= 0:
                self._in_best_novel_list = False
                self._list_depth = 0
                self._pending_best_novel = False

    def handle_data(self, data: str) -> None:
        if self._in_strong and not self._capturing_li:
            self._strong_parts.append(data)
        if (
            self._pending_best_novel
            and not self._in_best_novel_list
            and not self._capturing_li
            and _collapse_ws(data)
            and not _is_ballot_count_note(data)
        ):
            self._pending_best_novel = False
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

    def _finish_li(self) -> None:
        capturing = self._capturing_li
        winner = self._li_is_winner
        title_text = _collapse_ws(''.join(self._title_parts))
        remainder = ''.join(self._remainder_parts)
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
        if _is_non_work(full_text) or _is_non_work(title_text):
            return
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
                status=status,
                work_title=work_title,
                work_author=author,
                source_url=self.source_url,
                match_titles=match_titles,
            )
        )


def _parse_best_novel_html(
    page_html: str,
    award_year: int,
    source_url: str,
) -> list[_ParsedRecord]:
    parser = _HugoBestNovelParser(award_year, source_url)
    parser.feed(page_html)
    parser.close()
    return parser.records


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
        records.extend(_parse_best_novel_html(content, year, link))
    return tuple(records)


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_archive_records_cache: tuple[_ParsedRecord, ...] | None = None
_cache_lock = threading.Lock()


def _get_archive_records() -> tuple[_ParsedRecord, ...]:
    """Return cached Best Novel records, fetching once per process on success."""
    global _archive_records_cache
    with _cache_lock:
        if _archive_records_cache is not None:
            return _archive_records_cache
        status, headers, body = _fetch_archive_response()
        items = _validate_archive_payload(status, headers, body)
        records = _records_from_archive_items(items)
        if not records:
            raise HugoSourceError(
                'Hugo archive was retrieved but no Best Novel records '
                'could be parsed'
            )
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


def _normalize_title_for_match(value: str) -> str:
    text = _normalize_text(value)
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


def _record_matches(record: _ParsedRecord, title: str, author: str) -> bool:
    return _titles_match(title, record) and _authors_match(author, record.work_author)


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
    ranking = _ranking_for_record(record)
    if ranking is None or not _enrichment_is_consistent(record, ranking):
        return AwardResult(
            work_title=record.work_title,
            work_author=record.work_author,
            award_name='Hugo Award',
            award_year=record.award_year,
            category='Best Novel',
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
        category='Best Novel',
        status=record.status,
        rank=ranking.rank,
        source_name='Hugo Awards',
        source_url=ranking.source_url,
        notes='tie' if ranking.tied else None,
    )


# ---------------------------------------------------------------------------
# Public lookup
# ---------------------------------------------------------------------------

def lookup(title: str, author: str) -> list[AwardResult]:
    """Look up Hugo Award Best Novel results for a title and author."""
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
