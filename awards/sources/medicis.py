"""Official Médicis winners and explicitly documented selection rounds."""
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
from .. import cache
from ..model import AwardResult

SOURCE_KEY = 'medicis'
AWARD_NAME = 'Prix Médicis'
SOURCE_NAME = 'Prix Médicis official archive'
SOURCE_HOME_URL = 'https://prixmedicis.com/'
WINNERS_URL = 'https://prixmedicis.com/palmares/'
SELECTION_URL = 'https://prixmedicis.com/premiere-selection-du-prix-medicis-2026/'
SOURCE_URLS = [WINNERS_URL, SELECTION_URL]
CATEGORIES = ('Littérature française', 'Littérature étrangère', 'Essai')
CACHE_VERSION = 1
CACHE_TTL_SECONDS = 7 * 86400 + 23 * 3600
TIMEOUT_SECONDS = 20
_VOID = frozenset('area base br col embed hr img input link meta param source track wbr'.split())
_records = None
_lock = threading.Lock()

class MedicisSourceError(RuntimeError):
    """The official archive is unavailable or no longer structurally complete."""

def _text(value):
    return re.sub(r'\s+', ' ', value).strip()

def _key(value):
    return _text(unicodedata.normalize('NFKC',value).casefold().replace('’', "'"))

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
    category: str
    status: str
    source_url: str


def _parse_winners(html):
    root = _tree(html)
    tables = [n for n in root.walk() if n.tag == 'table' and n.has('graduates-table')]
    if len(tables) != 1:
        raise MedicisSourceError('Missing Médicis winner table')
    rows = []
    for tr in (n for n in tables[0].walk() if n.tag == 'tr' and n.has('graduate-row')):
        cells = [n for n in tr.children if isinstance(n, _Node) and n.tag == 'td']
        if len(cells) != 4 or not re.fullmatch(r'\d{4}', cells[0].text()):
            raise MedicisSourceError('Changed Médicis table columns or year')
        year = int(cells[0].text())
        for category, cell in zip(CATEGORIES, cells[1:]):
            for link in (n for n in cell.walk() if n.tag == 'a' and n.has('graduate-link')):
                titles = [n for n in link.walk() if n.has('graduate-link__title')]
                if len(titles) != 1:
                    raise MedicisSourceError('Missing Médicis work title')
                title = titles[0].text()
                # The author precedes <br>; never split words in the book title.
                author = _text(''.join(n for n in link.children if isinstance(n, str)))
                rows.append(_Row(year, title, author, category, 'Winner', WINNERS_URL))
    _validate_winners(rows)
    return tuple(rows)


def _validate_winners(rows):
    if not rows or {r.year for r in rows if r.category == CATEGORIES[0]} != set(range(1958, max(r.year for r in rows) + 1)):
        raise MedicisSourceError('Incomplete Médicis French winner history')
    last = max(r.year for r in rows)
    if last < 2025:
        raise MedicisSourceError('Truncated Médicis history')
    for category, start in [(CATEGORIES[1], 1970), (CATEGORIES[2], 1985)]:
        # No essay winner is reported for 1988 or 1993 in the official archive.
        expected = set(range(start, last + 1)) - ({1988, 1993} if category == CATEGORIES[2] else set())
        if {r.year for r in rows if r.category == category} != expected:
            raise MedicisSourceError('Incomplete Médicis category history')
    for (year, category), count in {(1995, 'Littérature française'): 2, (1996, 'Littérature française'): 2, (1996, 'Littérature étrangère'): 2, (2023, 'Littérature étrangère'): 2, (2025, 'Littérature étrangère'): 2}.items():
        if sum(r.year == year and r.category == category for r in rows) != count:
            raise MedicisSourceError('Incomplete Médicis joint winners')
    _validate_rows(rows, 'Winner', WINNERS_URL)


def _parse_selection(html):
    root = _tree(html)
    if not any(n.tag == 'h1' and n.text() == 'Première sélection du Prix Médicis 2026' for n in root.walk()):
        raise MedicisSourceError('Wrong Médicis selection announcement')
    rows = []
    category = None
    headings = {'romans en français': CATEGORIES[0], 'romans étrangers': CATEGORIES[1]}
    for node in root.walk():
        if node.tag != 'p':
            continue
        if _key(node.text()) in headings:
            category = headings[_key(node.text())]
            continue
        if category is None:
            continue
        authors = [n.text() for n in node.walk() if n.tag == 'strong']
        titles = [n.text() for n in node.walk() if n.tag == 'em' and n.text()]
        if not authors and not titles:
            continue
        if not authors or not titles:
            raise MedicisSourceError('Unreadable Médicis selected identity')
        author = _text(' '.join(authors)).strip(' ,')
        title = _text(' '.join(titles)).strip(' ,')
        rows.append(_Row(2026, title, author, category, 'Selected', SELECTION_URL))
    _validate_selection(rows)
    return tuple(rows)


def _validate_rows(rows, status, url):
    seen = set()
    for r in rows:
        key = (r.year, r.category, _key(r.title), _key(r.author))
        if (type(r.year) is not int or not 1958 <= r.year <= 2100 or r.category not in CATEGORIES
                or r.status != status or r.source_url != url
                or any(not isinstance(v, str) or not v.strip() or v != v.strip() for v in (r.title, r.author))
                or key in seen):
            raise MedicisSourceError('Invalid or duplicate Médicis record')
        seen.add(key)


def _validate_selection(rows):
    _validate_rows(rows, 'Selected', SELECTION_URL)
    if any(r.year != 2026 for r in rows) or {c: sum(r.category == c for r in rows) for c in CATEGORIES[:2]} != {CATEGORIES[0]: 18, CATEGORIES[1]: 17} or any(r.category == CATEGORIES[2] for r in rows):
        raise MedicisSourceError('Incomplete Médicis first selection')


def _merge(rows):
    winners = {(r.year, r.category, _key(r.title), _key(r.author)) for r in rows if r.status == 'Winner'}
    return tuple(r for r in rows if r.status == 'Winner' or (r.year, r.category, _key(r.title), _key(r.author)) not in winners)


def _load_disk():
    payload = cache.load_source_cache(SOURCE_KEY, CACHE_VERSION)
    if payload is None:
        return None
    try:
        rows = tuple(_Row(**r) for r in payload['records'])
        _validate_winners([r for r in rows if r.status == 'Winner'])
        _validate_selection([r for r in rows if r.status == 'Selected'])
        if any(r.status not in ('Winner', 'Selected') for r in rows) or payload['source_urls'] != SOURCE_URLS or payload['coverage'] != {'selection_rounds': ['2026-first']}:
            return None
        return rows, payload
    except (TypeError, ValueError, KeyError, AttributeError, MedicisSourceError):
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
                rows = _parse_winners(_fetch_html(WINNERS_URL)) + _parse_selection(_fetch_html(SELECTION_URL))
            except Exception:
                if not disk:
                    raise
                rows = disk[0]
            else:
                cache.save_source_cache(SOURCE_KEY, CACHE_VERSION, records=[asdict(r) for r in rows], source_urls=SOURCE_URLS,
                                        coverage={'selection_rounds': ['2026-first']}, ttl_seconds=CACHE_TTL_SECONDS)
        _records = _merge(rows)
        return _records


def _reset_runtime_state():
    global _records
    with _lock:
        _records = None


def _mappings():
    path = 'awards/data/medicis_mappings.json'
    resource = globals().get('get_resources')
    raw = resource(path) if resource else (Path(__file__).resolve().parents[2] / path).read_bytes()
    return json.loads(raw.decode('utf-8'))


def lookup(title, author, series=None):
    if not title.strip() or not author.strip():
        raise ValueError('title and author must be non-empty')
    results = []
    mappings = _mappings()
    for row in _get_records():
        aliases = [m for m in mappings if m['year'] == row.year and m['category'] == row.category and m['title'] == row.title and m['author'] == row.author]
        titles = [row.title] + [t for m in aliases for t in m['titles']]
        if _key(title) not in {_key(t) for t in titles} or _key(author) != _key(row.author):
            continue
        restricted = bool(re.search(r'\btome\s*\d|\bsuivi d', row.title, re.I))
        details = ['Official category: ' + row.category]
        if row.status == 'Selected':
            details.append('Première sélection 2026 (first selection); not a winner or an ordinal rank.')
        details.extend('Verified English title: ' + m['titles'][0] + ' (' + m['evidence'] + ')' for m in aliases)
        results.append(AwardResult(work_title=row.title, work_author=row.author, award_name=AWARD_NAME, award_year=row.year,
            category=row.category, status=row.status, rank=None, source_name=SOURCE_NAME, source_url=row.source_url,
            source_details=tuple(details), identity_confirmation_required=restricted,
            source_identity_note=('Confirm the complete awarded volume/edition: ' + row.title) if restricted else None))
    return results


def _fetch_html(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'Calibre-Awards/0.3.0 (award lookup)', 'Accept-Encoding': 'identity'})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            if response.status != 200 or response.url != url:
                raise MedicisSourceError('Unexpected Médicis response: ' + url)
            return response.read().decode('utf-8')
    except urllib.error.HTTPError as exc:
        exc.close()
        raise MedicisSourceError(f'Médicis request failed with HTTP {exc.code}: {url}') from exc
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeError) as exc:
        raise MedicisSourceError(f'Médicis source unavailable: {url}: {exc}') from exc
