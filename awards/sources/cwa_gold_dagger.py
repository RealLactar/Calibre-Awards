"""Main CWA Gold Dagger and its officially continuous predecessor only."""
from __future__ import annotations

import json
import re
import threading
import unicodedata
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

from .. import cache
from ..matching import normalize_title_conjunctions
from ..model import AwardResult

SOURCE_KEY = 'cwa_gold_dagger'
AWARD_NAME = 'CWA Gold Dagger'
SOURCE_NAME = 'Crime Writers’ Association official archive'
SOURCE_HOME_URL = 'https://thecwa.co.uk/awards-and-competitions/the-daggers/gold-dagger/'
ARCHIVE_URL = 'https://thecwa.co.uk/past-winners/?past_winners_awards%5B0%5D=gold'
PREDECESSOR_URL = 'https://thecwa.co.uk/past-winners/?past_winners_awards%5B0%5D=gold-crossed-herrings'
SUPPLEMENT_URL = 'https://thecwa.co.uk/past-winners/we-begin-at-the-end/'
SOURCE_URLS = [ARCHIVE_URL, PREDECESSOR_URL, SUPPLEMENT_URL, SOURCE_HOME_URL]
CATEGORIES = ('Crime novel',)
CACHE_VERSION = 1
CACHE_TTL_SECONDS = 7 * 86400 + 23 * 3600
TIMEOUT_SECONDS = 20
MAX_PAGES = 100
REVIEWED_LAST_YEAR = 2026
_LABELS = frozenset({'Gold Dagger', 'Crossed Herrings Dagger'})
_STATUSES = {'Winner': 4, 'Highly Commended': 3, 'Shortlisted': 2, 'Longlisted': 1}
_UNDATED_URL = 'https://thecwa.co.uk/past-winners/bluebird-bluebird/'
_VOID = frozenset('area base br col embed hr img input link meta param source track wbr'.split())
_records = None
_lock = threading.RLock()


class CWAGoldDaggerSourceError(RuntimeError):
    """Unavailable, truncated, inconsistent or changed official records."""


def _text(value):
    return re.sub(r'\s+', ' ', value).strip()


def _key(value):
    value = unicodedata.normalize('NFKC', value).casefold()
    for a, b in [('’', "'"), ('‘', "'"), ('“', '"'), ('”', '"')]:
        value = value.replace(a, b)
    return re.sub(r'\b([a-z])\.\s+', r'\1.', _text(value))


def _author_key(value):
    # CWA itself uses both SA Cosby and S. A. Cosby for the same 2026 work.
    # Normalize only an initial group, never surnames or arbitrary punctuation.
    value = _key(value)
    return re.sub(r'^([a-z])\.([a-z])\.?(?:\s+|(?=[a-z]))', r'\1\2 ', value)


@dataclass
class _Node:
    tag: str
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, _Node):
                yield from child.walk()

    def text(self):
        def chunks(node):
            for child in node.children:
                if isinstance(child, _Node):
                    yield from chunks(child)
                else:
                    yield child
        return _text(''.join(chunks(self)))

    def has(self, name):
        return name in self.attrs.get('class', '').split()


class _Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node('root')
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, dict(attrs))
        self.stack[-1].children.append(node)
        if tag not in _VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def _tree(html):
    parser = _Tree()
    parser.feed(html)
    parser.close()
    return parser.root


@dataclass(frozen=True)
class _Row:
    year: int
    title: str
    author: str
    status: str
    source_url: str
    historical_name: str


def _page_url(page):
    return ARCHIVE_URL if page == 1 else f'https://thecwa.co.uk/past-winners/page/{page}/?past_winners_awards%5B0%5D=gold'


def _br_parts(node):
    parts, current = [], []
    for child in node.children:
        if isinstance(child, _Node) and child.tag == 'br':
            parts.append(_text(''.join(current)))
            current = []
        else:
            current.append(child.text() if isinstance(child, _Node) else child)
    if _text(''.join(current)):
        parts.append(_text(''.join(current)))
    return parts


def _cards(root):
    rows = []
    sections = [n for n in root.walk() if n.tag == 'section' and n.has('books')]
    for section in sections:
        for card in (n for n in section.children if isinstance(n, _Node) and n.tag == 'article'):
            links = [n for n in card.children if isinstance(n, _Node) and n.tag == 'a']
            if len(links) != 1:
                raise CWAGoldDaggerSourceError('Changed CWA result link')
            link = links[0]
            titles = [n.text() for n in link.walk() if n.tag == 'h2']
            paras = [n for n in link.walk() if n.tag == 'p']
            if len(titles) != 1 or len(paras) != 1:
                raise CWAGoldDaggerSourceError('Missing CWA title/author fields')
            parts = _br_parts(paras[0])
            if len(parts) < 3:
                raise CWAGoldDaggerSourceError('Missing CWA award distinction')
            if parts[1] not in _LABELS:
                continue
            url = link.attrs.get('href', '')
            match = re.fullmatch(r'(\d{4})\s*\|\s*(.+)', parts[2])
            if not match:
                if url == _UNDATED_URL and parts[2] == 'Shortlisted':
                    continue  # The individual page also lacks a year: never guess.
                raise CWAGoldDaggerSourceError('Missing explicit CWA award year')
            rows.append(_Row(int(match[1]), titles[0], parts[0], match[2], url, parts[1]))
    return tuple(rows)


def _parse_listing(html, page=1, predecessor=False):
    root = _tree(html)
    rows = _cards(root)
    if not rows:
        raise CWAGoldDaggerSourceError('Missing main Gold Dagger archive cards')
    navs = [n for n in root.walk() if n.tag == 'nav' and n.has('pagination')]
    if predecessor:
        if navs or any(r.historical_name != 'Crossed Herrings Dagger' for r in rows):
            raise CWAGoldDaggerSourceError('Changed predecessor archive')
        return rows, 1
    if len(navs) != 1:
        raise CWAGoldDaggerSourceError('Missing CWA pagination')
    nav = navs[0]
    pages = []
    for n in nav.walk():
        if n.tag == 'a' and '/past-winners/page/' in n.attrs.get('href', ''):
            match = re.search(r'/page/(\d+)/', n.attrs['href'])
            target = int(match[1])
            if n.attrs['href'] != _page_url(target):
                raise CWAGoldDaggerSourceError('Changed/unfiltered CWA pagination URL')
            pages.append(target)
    # Last-page links disappear on the terminal page; the page counter remains.
    counters = [n.text() for n in nav.walk() if n.tag == 'span' and n.has('pages')]
    counter = re.fullmatch(r'Page\s+(\d+)\s+of\s+(\d+)', counters[0]) if len(counters) == 1 else None
    if not counter or int(counter[1]) != page:
        raise CWAGoldDaggerSourceError('Invalid CWA page counter')
    total = int(counter[2])
    if not page <= total <= MAX_PAGES or total < 16:
        raise CWAGoldDaggerSourceError('Truncated CWA pagination')
    next_links = [n for n in nav.walk() if n.tag == 'a' and n.has('nextpostslink')]
    if (page < total and (len(next_links) != 1 or next_links[0].attrs.get('href') != _page_url(page + 1))) or (page == total and next_links):
        raise CWAGoldDaggerSourceError('Incomplete CWA pagination chain')
    if any(r.historical_name != 'Gold Dagger' for r in rows):
        raise CWAGoldDaggerSourceError('Unexpected archive award')
    return rows, total


def _parse_detail(html, url):
    root = _tree(html)
    sections = [n for n in root.walk() if n.tag == 'section' and n.has('entries')]
    if len(sections) != 1:
        raise CWAGoldDaggerSourceError('Missing CWA individual result')
    heads = [(n.tag, n.text()) for n in sections[0].walk() if n.tag in ('h1', 'h2', 'h3')]
    if len(heads) != 4 or [h[0] for h in heads] != ['h1', 'h2', 'h2', 'h3']:
        raise CWAGoldDaggerSourceError('Changed CWA result fields')
    match = re.fullmatch(r'(Gold Dagger|Crossed Herrings Dagger) (\d{4})', heads[0][1])
    if not match:
        raise CWAGoldDaggerSourceError('Not a dated main Gold Dagger result')
    return _Row(int(match[2]), heads[3][1], heads[2][1], heads[1][1], url, match[1])


def _parse_current(html):
    root = _tree(html)
    rows = list(_cards(root))
    for section in (n for n in root.walk() if n.tag == 'section'):
        headings = [n.text() for n in section.children if isinstance(n, _Node) and n.tag == 'h2']
        if len(headings) != 1:
            continue
        match = re.fullmatch(r'(\d{4}) longlist', headings[0], re.I)
        if not match:
            continue
        tables = [n for n in section.walk() if n.tag == 'table']
        if len(tables) != 1:
            raise CWAGoldDaggerSourceError('Missing CWA current longlist table')
        for tr in (n for n in tables[0].walk() if n.tag == 'tr'):
            cells = [n.text() for n in tr.children if isinstance(n, _Node) and n.tag == 'td']
            if not cells:
                continue
            if len(cells) != 3:
                raise CWAGoldDaggerSourceError('Changed CWA longlist columns')
            rows.append(_Row(int(match[1]), cells[1], cells[0], 'Longlisted', SOURCE_HOME_URL, 'Gold Dagger'))
    if not any(n.tag == 'h1' and n.text() in ('KAA Gold Dagger', 'Gold Dagger') for n in root.walk()):
        raise CWAGoldDaggerSourceError('Wrong CWA current award page')
    return tuple(rows)


def _identity(row):
    return row.year, normalize_title_conjunctions(_key(row.title)), _author_key(row.author)


def _merge(rows):
    found = {}
    for row in rows:
        identity = _identity(row)
        old = found.get(identity)
        if old is None or _STATUSES.get(row.status, 0) > _STATUSES.get(old.status, 0):
            found[identity] = row
    return tuple(sorted(found.values(), key=lambda r: (-r.year, _key(r.title), _author_key(r.author))))


def _reviewed_manifest():
    path = 'awards/data/cwa_gold_dagger_coverage.json'
    resource = globals().get('get_resources')
    raw = resource(path) if resource else (Path(__file__).resolve().parents[2] / path).read_bytes()
    return json.loads(raw.decode('utf-8'))


def _reviewed_counts():
    return _reviewed_manifest()['minimum_counts']


def _reviewed_rows():
    return tuple(_Row(**r) for r in _reviewed_manifest()['required_records'])


def _coverage(rows):
    counts = {}
    for row in rows:
        k = f'{row.year}:{row.status}'
        counts[k] = counts.get(k, 0) + 1
    return {'counts': counts, 'reviewed_winners_through': REVIEWED_LAST_YEAR}


def _validate(rows, previous=()):
    if not rows or len({_identity(r) for r in rows}) != len(rows):
        raise CWAGoldDaggerSourceError('Empty or duplicate CWA archive')
    for r in rows:
        url = urlparse(r.source_url)
        if (type(r.year) is not int or r.year < 1955 or not r.title.strip() or not r.author.strip()
                or r.status not in _STATUSES or r.historical_name not in _LABELS
                or url.scheme != 'https' or url.netloc != 'thecwa.co.uk'
                or not (url.path.startswith('/past-winners/') or r.source_url == SOURCE_HOME_URL)
                or url.query or url.fragment
                or (r.year <= 1959) != (r.historical_name == 'Crossed Herrings Dagger')):
            raise CWAGoldDaggerSourceError('Invalid CWA award record or provenance')
    counts = _coverage(rows)['counts']
    if not set(range(1955, REVIEWED_LAST_YEAR + 1)).issubset({r.year for r in rows if r.status == 'Winner'}):
        raise CWAGoldDaggerSourceError('Incomplete reviewed CWA winner history')
    if any(counts.get(k, 0) < v for k, v in _reviewed_counts().items()):
        raise CWAGoldDaggerSourceError('Truncated reviewed CWA distinctions')
    current = {_identity(r): r for r in rows}
    if any(_identity(r) not in current or _STATUSES[current[_identity(r)].status] < _STATUSES[r.status] for r in _reviewed_rows()):
        raise CWAGoldDaggerSourceError('Missing reviewed CWA result identities')
    if any(_identity(r) not in current or _STATUSES[current[_identity(r)].status] < _STATUSES[r.status] for r in previous):
        raise CWAGoldDaggerSourceError('CWA update loses previously accepted records')


def _recover_missing(rows, previous=()):
    # The official date-sorted listing can shift equal-year books between pages.
    # Recover only known omissions from live, individually dated main-award
    # results. The manifest never supplies lookup records or an offline archive.
    found = {_identity(r): r for r in _merge(rows)}
    for required in _merge(_reviewed_rows() + tuple(previous)):
        current = found.get(_identity(required))
        if current is not None and _STATUSES[current.status] >= _STATUSES[required.status]:
            continue
        if required.source_url == SOURCE_HOME_URL:
            continue  # Announcement-only entries must remain in the live table.
        detail = _parse_detail(_fetch_html(required.source_url), required.source_url)
        if _identity(detail) != _identity(required) or _STATUSES.get(detail.status, 0) < _STATUSES[required.status]:
            raise CWAGoldDaggerSourceError('Changed CWA individual result identity/distinction')
        found[_identity(detail)] = detail
    return _merge(found.values())


def _load_live_archive(previous=()):
    rows, total = _parse_listing(_fetch_html(ARCHIVE_URL))
    rows = list(rows)
    for page in range(2, total + 1):
        batch, advertised = _parse_listing(_fetch_html(_page_url(page)), page)
        if advertised != total:
            raise CWAGoldDaggerSourceError('CWA pagination changed during retrieval')
        rows.extend(batch)
    predecessor, _ = _parse_listing(_fetch_html(PREDECESSOR_URL), predecessor=True)
    rows.extend(predecessor)
    rows.append(_parse_detail(_fetch_html(SUPPLEMENT_URL), SUPPLEMENT_URL))
    rows.extend(_parse_current(_fetch_html(SOURCE_HOME_URL)))
    rows = _recover_missing(rows, previous)
    _validate(rows, previous)
    return rows


def _load_disk():
    payload = cache.load_source_cache(SOURCE_KEY, CACHE_VERSION)
    if payload is None:
        return None
    try:
        rows = tuple(_Row(**r) for r in payload['records'])
        _validate(rows)
        if payload['source_urls'] != SOURCE_URLS or payload['coverage'] != _coverage(rows):
            return None
        return rows, payload
    except (TypeError, ValueError, KeyError, AttributeError, CWAGoldDaggerSourceError):
        return None


def _get_records():
    global _records
    with _lock:
        if _records is not None:
            return _records
        disk = _load_disk()
        if disk and (cache.cache_is_fresh(disk[1]) or not cache.try_claim_stale_refresh(SOURCE_KEY)):
            rows = disk[0]
        else:
            try:
                rows = _load_live_archive(previous=disk[0] if disk else ())
                _validate(rows, disk[0] if disk else ())
            except Exception:
                if not disk:
                    raise
                rows = disk[0]
            else:
                cache.save_source_cache(SOURCE_KEY, CACHE_VERSION, records=[asdict(r) for r in rows],
                                        source_urls=SOURCE_URLS, coverage=_coverage(rows), ttl_seconds=CACHE_TTL_SECONDS)
        _records = rows
        return rows


def _reset_runtime_state():
    global _records
    with _lock:
        _records = None


_ALIAS_SOURCE_URL = 'https://thecwa.co.uk/past-winners/the-spy-who-came-in-from-the-cold/'
_ALIAS_EVIDENCE_URL = 'https://johnlecarre.com/books/the-spy-who-came-in-from-the-cold'


def _is_verified_1963_record(row):
    return (row.year == 1963 and row.status == 'Winner' and row.historical_name == 'Gold Dagger'
            and row.source_url == _ALIAS_SOURCE_URL and row.author == 'John le Carr'
            and _key(row.title) == _key('The Spy Who Came in from the Cold'))


def _author_matches(row, author):
    if _author_key(author) == _author_key(row.author):
        return True
    return _is_verified_1963_record(row) and _author_key(author) == _author_key('John le Carré')


def _alias_details(row, author):
    if _is_verified_1963_record(row) and _author_key(author) != _author_key(row.author):
        return ('Verified record-specific author alias: John le Carré; original CWA credit: John le Carr. '
                'Official author bibliography identifies this September 1963 novel: ' + _ALIAS_EVIDENCE_URL,)
    return ()


def lookup(title, author, series=None):
    if not title.strip() or not author.strip():
        raise ValueError('title and author must be non-empty')
    return [AwardResult(work_title=r.title, work_author=r.author, award_name=AWARD_NAME,
                       award_year=r.year, category=None, status=r.status, rank=None,
                       source_name=SOURCE_NAME, source_url=r.source_url,
                       source_details=('Official archive award label: ' + r.historical_name,
                                       'Crossed Red Herrings Award (1955–1959) is the documented Gold Dagger predecessor.'
                                       if r.year < 1960 else 'Main Gold Dagger only; other CWA Daggers are excluded.') + _alias_details(r, author))
            for r in _get_records() if normalize_title_conjunctions(_key(title)) == normalize_title_conjunctions(_key(r.title))
            and _author_matches(r, author)]


def _fetch_html(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'Calibre-Awards/0.3.0 (award lookup)', 'Accept-Encoding': 'identity'})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            if response.status != 200 or response.url != url:
                raise CWAGoldDaggerSourceError('Unexpected CWA response: ' + url)
            return response.read().decode('utf-8')
    except urllib.error.HTTPError as exc:
        exc.close()
        raise CWAGoldDaggerSourceError(f'CWA request failed with HTTP {exc.code}: {url}') from exc
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeError) as exc:
        raise CWAGoldDaggerSourceError(f'CWA source unavailable: {url}: {exc}') from exc


import sys as _runtime_sys
from ..cache import source_runtime_guard as _runtime_guard
lookup = _runtime_guard(_runtime_sys.modules[__name__], lookup)
_get_records = _runtime_guard(_runtime_sys.modules[__name__], _get_records)
