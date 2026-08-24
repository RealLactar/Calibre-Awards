"""Official Nobel Prize in Literature source (api.nobelprize.org)."""

from __future__ import annotations

import json
import re
import threading
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.cookiejar import CookieJar
from urllib.parse import urlparse

from ..model import AwardResult
from ..presentation import CITED_WORK_SCOPE_NOTE

TIMEOUT_SECONDS = 30
LAUREATES_URL = (
    'https://api.nobelprize.org/2.1/laureates'
    '?nobelPrizeCategory=lit&limit=200&offset=0'
)
SOURCE_NAME = 'NobelPrize.org'
AWARD_NAME = 'Nobel Prize'
CATEGORY_LITERATURE = 'Literature'
LAUREATE_FALLBACK_URL = 'https://www.nobelprize.org/laureate/{id}'

_BROWSER_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/122.0.0.0 Safari/537.36'
    ),
    'Accept': 'application/json,text/plain;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'identity',
}

_INITIALS_SPACE_RE = re.compile(r'\b([A-Za-z])\.\s+')
_CALIBRE_AMP_PLACEHOLDER = '\uffff'
_SAFE_LAUREATE_ID_RE = re.compile(r'^[0-9A-Za-z_-]+$')
_OFFICIAL_HTML_HOSTS = frozenset({'nobelprize.org', 'www.nobelprize.org'})
_FACTS_CLASS = 'laureate facts'


class NobelSourceError(RuntimeError):
    """Raised when the official Nobel API cannot be retrieved or validated."""


@dataclass(frozen=True, slots=True)
class _CitedWorkMapping:
    laureate_id: str
    award_year: int
    canonical_title: str
    title_aliases: tuple[str, ...]


# Finite official specifically-cited works. No motivation parsing.
# Sholokhov 1965 is intentionally omitted: Nobel names "his epic of the Don".
_CITED_WORKS: tuple[_CitedWorkMapping, ...] = (
    _CitedWorkMapping(
        '571',
        1902,
        'A History of Rome',
        ('A History of Rome', 'A history of Rome', 'Römische Geschichte'),
    ),
    _CitedWorkMapping(
        '588',
        1919,
        'Olympian Spring',
        ('Olympian Spring',),
    ),
    _CitedWorkMapping(
        '589',
        1920,
        'Growth of the Soil',
        ('Growth of the Soil', 'Markens Grøde'),
    ),
    _CitedWorkMapping(
        '594',
        1924,
        'The Peasants',
        ('The Peasants',),
    ),
    _CitedWorkMapping(
        '602',
        1929,
        'Buddenbrooks',
        ('Buddenbrooks',),
    ),
    _CitedWorkMapping(
        '605',
        1932,
        'The Forsyte Saga',
        ('The Forsyte Saga',),
    ),
    _CitedWorkMapping(
        '609',
        1937,
        'Les Thibault',
        ('Les Thibault',),
    ),
    _CitedWorkMapping(
        '625',
        1954,
        'The Old Man and the Sea',
        ('The Old Man and the Sea', 'Old Man and the Sea'),
    ),
)
_CITED_WORKS_BY_ID = {
    item.laureate_id: item for item in _CITED_WORKS
}


@dataclass(frozen=True, slots=True)
class _LiteraturePrize:
    award_year: int
    prize_status: str
    source_url: str
    notes: str | None


@dataclass(frozen=True, slots=True)
class _Laureate:
    laureate_id: str
    known_name: str
    match_names: tuple[str, ...]
    prize: _LiteraturePrize


_cache_lock = threading.Lock()
_laureates_cache: tuple[_Laureate, ...] | None = None


def _reset_runtime_state() -> None:
    """Clear in-process caches. Used by tests."""
    global _laureates_cache
    with _cache_lock:
        _laureates_cache = None


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


def _request_json() -> tuple[int, str]:
    request = urllib.request.Request(
        LAUREATES_URL, headers=dict(_BROWSER_HEADERS)
    )
    opener = _build_opener()
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            status = getattr(response, 'status', None) or response.getcode()
            body = _read_response_body(response)
    except urllib.error.HTTPError as exc:
        body = _read_response_body(exc)
        raise NobelSourceError(
            f'Nobel request failed with HTTP {exc.code} for {LAUREATES_URL}'
            + (f': {body[:200].strip()}' if body.strip() else '')
        ) from exc
    except urllib.error.URLError as exc:
        raise NobelSourceError(
            f'Nobel request failed for {LAUREATES_URL}: {exc.reason}'
        ) from exc
    except TimeoutError as exc:
        raise NobelSourceError(
            f'Nobel request timed out for {LAUREATES_URL}'
        ) from exc
    return int(status), body


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


def _author_match_forms(name: str) -> frozenset[str]:
    forms: list[str] = []
    for candidate in (name, _ascii_fold(name)):
        normalized = _normalize_text(candidate)
        if normalized and normalized not in forms:
            forms.append(normalized)
    return frozenset(forms)


def _split_calibre_author_query(query_author: str) -> tuple[str, ...]:
    """Invert Calibre authors_to_string: split on ' & ', restore '&&' to '&'."""
    protected = query_author.replace('&&', _CALIBRE_AMP_PLACEHOLDER)
    people: list[str] = []
    for piece in protected.split(' & '):
        restored = piece.replace(_CALIBRE_AMP_PLACEHOLDER, '&').strip()
        if restored:
            people.append(restored)
    return tuple(people)


def _localized_en(value: object) -> str | None:
    if isinstance(value, str):
        text = _collapse_ws(value)
        return text or None
    if isinstance(value, dict):
        english = value.get('en')
        if isinstance(english, str):
            text = _collapse_ws(english)
            return text or None
    return None


def _pen_name_of_full(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    return _localized_en(value.get('fullName'))


def _link_classes(link: dict) -> tuple[str, ...]:
    raw = link.get('class')
    if isinstance(raw, str):
        text = _collapse_ws(raw)
        return (text,) if text else ()
    if isinstance(raw, list):
        classes: list[str] = []
        for item in raw:
            if isinstance(item, str):
                text = _collapse_ws(item)
                if text:
                    classes.append(text)
        return tuple(classes)
    return ()


def _is_official_nobel_html_url(url: str) -> bool:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {'http', 'https'}:
        return False
    host = (parsed.hostname or '').casefold().rstrip('.')
    return host in _OFFICIAL_HTML_HOSTS


def _is_laureate_facts_url(url: str) -> bool:
    if not _is_official_nobel_html_url(url):
        return False
    path = urlparse(url.strip()).path.casefold()
    return '/prizes/literature/' in path and path.rstrip('/').endswith('/facts')


def _facts_href_from_links(links: object) -> str | None:
    if not isinstance(links, list):
        return None
    for item in links:
        if not isinstance(item, dict):
            continue
        rel = item.get('rel')
        if not isinstance(rel, str) or rel.strip().casefold() != 'external':
            continue
        if _FACTS_CLASS not in _link_classes(item):
            continue
        href = item.get('href')
        if not isinstance(href, str):
            continue
        url = href.strip()
        if _is_laureate_facts_url(url):
            return url
    return None


def _fallback_laureate_url(laureate_id: str) -> str | None:
    if not _SAFE_LAUREATE_ID_RE.fullmatch(laureate_id):
        return None
    url = LAUREATE_FALLBACK_URL.format(id=laureate_id)
    if not _is_official_nobel_html_url(url):
        return None
    return url


def _select_source_url(
    prize_links: object,
    laureate_links: object,
    laureate_id: str,
) -> str | None:
    for links in (prize_links, laureate_links):
        facts = _facts_href_from_links(links)
        if facts is not None:
            return facts
    return _fallback_laureate_url(laureate_id)


def _notes_for_status(status: str) -> str | None:
    key = status.casefold()
    if key == 'received':
        return None
    if key == 'declined':
        return 'Nobel Prize status: declined.'
    if key == 'restricted':
        return 'Nobel Prize status: restricted.'
    return f'Nobel Prize status: {status}.'


def _parse_award_year(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            year = int(text)
            return year if year > 0 else None
    return None


def _parse_literature_prize(
    prize: object,
    laureate_id: str,
    laureate_links: object,
) -> _LiteraturePrize | None:
    if not isinstance(prize, dict):
        return None
    category = _localized_en(prize.get('category'))
    if category is None or category.casefold() != CATEGORY_LITERATURE.casefold():
        return None
    year = _parse_award_year(prize.get('awardYear'))
    if year is None:
        return None
    status = prize.get('prizeStatus')
    if not isinstance(status, str) or not status.strip():
        return None
    prize_status = _collapse_ws(status)
    source_url = _select_source_url(
        prize.get('links'),
        laureate_links,
        laureate_id,
    )
    if source_url is None:
        return None
    return _LiteraturePrize(
        award_year=year,
        prize_status=prize_status,
        source_url=source_url,
        notes=_notes_for_status(prize_status),
    )


def _unique_names(*names: str | None) -> tuple[str, ...]:
    unique: list[str] = []
    for name in names:
        if name and name not in unique:
            unique.append(name)
    return tuple(unique)


def _parse_laureate(item: object) -> _Laureate:
    if not isinstance(item, dict):
        raise NobelSourceError(
            'Nobel laureates payload contained a non-object laureate record'
        )
    raw_id = item.get('id')
    if isinstance(raw_id, bool) or raw_id is None:
        raise NobelSourceError('Nobel laureate is missing a usable id')
    laureate_id = _collapse_ws(str(raw_id))
    if not laureate_id:
        raise NobelSourceError('Nobel laureate is missing a usable id')
    known_name = _localized_en(item.get('knownName'))
    if known_name is None:
        raise NobelSourceError(
            f'Nobel laureate {laureate_id} is missing knownName.en'
        )
    prizes = item.get('nobelPrizes')
    if not isinstance(prizes, list) or not prizes:
        raise NobelSourceError(
            f'Nobel laureate {laureate_id} is missing nobelPrizes'
        )
    literature = [
        parsed
        for parsed in (
            _parse_literature_prize(prize, laureate_id, item.get('links'))
            for prize in prizes
        )
        if parsed is not None
    ]
    if not literature:
        raise NobelSourceError(
            f'Nobel laureate {laureate_id} has no usable Literature prize'
        )
    match_names = _unique_names(
        known_name,
        _localized_en(item.get('fullName')),
        _pen_name_of_full(item.get('penNameOf')),
    )
    return _Laureate(
        laureate_id=laureate_id,
        known_name=known_name,
        match_names=match_names,
        prize=literature[0],
    )


def _parse_laureates_payload(status: int, body: str) -> tuple[_Laureate, ...]:
    if status != 200:
        raise NobelSourceError(
            f'Nobel laureates request failed with HTTP {status} for {LAUREATES_URL}'
        )
    if not body.strip():
        raise NobelSourceError('Nobel laureates response was empty')
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise NobelSourceError(
            f'Nobel laureates response was not valid JSON: {exc}'
        ) from exc
    if not isinstance(payload, dict):
        raise NobelSourceError('Nobel laureates response JSON was not an object')
    laureates = payload.get('laureates')
    if not isinstance(laureates, list):
        raise NobelSourceError(
            'Nobel laureates response is missing a laureates list'
        )
    meta = payload.get('meta')
    if not isinstance(meta, dict):
        raise NobelSourceError('Nobel laureates response is missing meta')
    count = meta.get('count')
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        raise NobelSourceError(
            'Nobel laureates meta.count is not a positive integer'
        )
    if len(laureates) != count:
        raise NobelSourceError(
            'Nobel laureates response length did not match meta.count: '
            f'{len(laureates)} != {count}'
        )
    parsed = tuple(_parse_laureate(item) for item in laureates)
    if not parsed:
        raise NobelSourceError('Nobel laureates response contained no laureates')
    return parsed


def _get_laureates() -> tuple[_Laureate, ...]:
    global _laureates_cache
    with _cache_lock:
        if _laureates_cache is not None:
            return _laureates_cache
        status, body = _request_json()
        parsed = _parse_laureates_payload(status, body)
        _laureates_cache = parsed
        return parsed


def _normalize_title_text(value: str) -> str:
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
    return _collapse_ws(text).casefold()


def _title_match_forms(title: str) -> frozenset[str]:
    forms: list[str] = []
    for candidate in (title, _ascii_fold(title)):
        normalized = _normalize_title_text(candidate)
        if normalized and normalized not in forms:
            forms.append(normalized)
    return frozenset(forms)


def _title_matches_aliases(query_title: str, aliases: tuple[str, ...]) -> bool:
    query_forms = _title_match_forms(query_title)
    if not query_forms:
        return False
    return any(
        bool(query_forms & _title_match_forms(alias)) for alias in aliases
    )


def _cited_work_for(
    laureate: _Laureate, query_title: str
) -> _CitedWorkMapping | None:
    mapping = _CITED_WORKS_BY_ID.get(laureate.laureate_id)
    if mapping is None:
        return None
    if mapping.award_year != laureate.prize.award_year:
        return None
    if not _title_matches_aliases(query_title, mapping.title_aliases):
        return None
    return mapping


def _person_matches_laureate(person: str, laureate: _Laureate) -> bool:
    query_forms = _author_match_forms(person)
    if not query_forms:
        return False
    return any(
        bool(query_forms & _author_match_forms(name))
        for name in laureate.match_names
    )


def _to_award_result(laureate: _Laureate) -> AwardResult:
    prize = laureate.prize
    return AwardResult(
        work_title=laureate.known_name,
        work_author=laureate.known_name,
        award_name=AWARD_NAME,
        award_year=prize.award_year,
        category=CATEGORY_LITERATURE,
        status='Winner',
        rank=None,
        source_name=SOURCE_NAME,
        source_url=prize.source_url,
        notes=prize.notes,
        identity_kind='author',
    )


def _to_cited_work_result(
    laureate: _Laureate, mapping: _CitedWorkMapping
) -> AwardResult:
    prize = laureate.prize
    return AwardResult(
        work_title=mapping.canonical_title,
        work_author=laureate.known_name,
        award_name=AWARD_NAME,
        award_year=prize.award_year,
        category=CATEGORY_LITERATURE,
        status='Winner',
        rank=None,
        source_name=SOURCE_NAME,
        source_url=prize.source_url,
        notes=CITED_WORK_SCOPE_NOTE,
        identity_kind='work',
    )


def lookup(
    title: str,
    author: str,
    series: str | None = None,
) -> list[AwardResult]:
    """Look up Nobel Prize in Literature results."""
    cleaned_title = title.strip()
    cleaned_author = author.strip()
    if not cleaned_title:
        raise ValueError('title must be a non-empty string')
    if not cleaned_author:
        raise ValueError('author must be a non-empty string')

    people = _split_calibre_author_query(cleaned_author)
    if not people:
        return []

    matches: list[AwardResult] = []
    seen: set[str] = set()
    for person in people:
        for laureate in _get_laureates():
            if laureate.laureate_id in seen:
                continue
            if not _person_matches_laureate(person, laureate):
                continue
            seen.add(laureate.laureate_id)
            cited = _cited_work_for(laureate, cleaned_title)
            if cited is not None:
                matches.append(_to_cited_work_result(laureate, cited))
            else:
                matches.append(_to_award_result(laureate))
    matches.sort(
        key=lambda result: (
            result.award_year or 0,
            (result.work_author or '').casefold(),
        )
    )
    return matches
