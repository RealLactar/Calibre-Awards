"""Official Akutagawa winners and explicitly documented nomination rounds.

English matching uses reviewed title/author mappings, never automatic translation.
"""
from __future__ import annotations
import json
import re
import threading
import unicodedata
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from .. import cache
from ..model import AwardResult

SOURCE_KEY = 'akutagawa'
AWARD_NAME = 'Akutagawa Prize'
SOURCE_NAME = 'Society for the Promotion of Japanese Literature / Bungeishunju'
SOURCE_HOME_URL = 'https://bungakushinko.or.jp/award/akutagawa/index.html'
WINNERS_URL = 'https://bungakushinko.or.jp/award/akutagawa/list.html'
CATEGORIES = ('Literary fiction',)
CACHE_VERSION = 1
CACHE_TTL_SECONDS = 7 * 86400 + 22 * 3600
TIMEOUT_SECONDS = 20
NOMINATION_PAGES = (
    (162, 2019, 'second half', 'https://books.bunshun.jp/articles/-/5210', 5),
    (175, 2026, 'first half', 'https://books.bunshun.jp/articles/-/11012', 5),
)
SOURCE_URLS = [WINNERS_URL] + [p[3] for p in NOMINATION_PAGES]
_VOID = frozenset('area base br col embed hr img input link meta param source track wbr'.split())
_records = None
_reference = None
_lock = threading.RLock()

class AkutagawaSourceError(RuntimeError):
    """The official source is unavailable, incomplete, or changed structure."""


def _text(value):
    return re.sub(r'\s+', ' ', value).strip()


def _key(value):
    return _text(unicodedata.normalize('NFKC', value).casefold().replace('’', "'"))

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
    round_number: int
    year: int
    half: str
    title: str
    source_title: str
    author: str
    magazine: str
    status: str
    source_url: str


def _one(nodes, description):
    values = list(nodes)
    if len(values) != 1:
        raise AkutagawaSourceError(f'Missing or ambiguous Akutagawa {description}')
    return values[0]


def _canonical(root, expected):
    node = _one((n for n in root.walk() if n.tag == 'link' and n.attrs.get('rel') == 'canonical'), 'canonical URL')
    if node.attrs.get('href') != expected:
        raise AkutagawaSourceError('Wrong Akutagawa source page')


def _parse_winners(html):
    root = _tree(html)
    # The organizer archive has no canonical link; identify its actual page heading.
    if not any(n.tag == 'h2' and n.text().startswith('芥川賞受賞者一覧') for n in root.walk()):
        raise AkutagawaSourceError('Missing Akutagawa winner archive heading')
    rows = []
    for listing in (n for n in root.walk() if n.tag == 'dl'):
        previous = None
        for n in listing.children:
            if not isinstance(n, _Node):
                continue
            if n.tag == 'dt':
                numbers = [a.text() for a in n.walk() if a.has('no')]
                dates = [a.text() for a in n.walk() if a.has('year')]
                if numbers == ['回']:
                    previous = None
                    continue
                if len(numbers) != 1 or len(dates) != 1 or not numbers[0].isdigit():
                    raise AkutagawaSourceError('Unreadable Akutagawa round')
                match = re.fullmatch(r'(\d{4})([上下])', dates[0])
                if not match:
                    raise AkutagawaSourceError('Unreadable Akutagawa award year')
                previous = (int(numbers[0]), int(match[1]), 'first half' if match[2] == '上' else 'second half')
            elif n.tag == 'dd' and previous:
                author = _one((a for a in n.walk() if a.has('name')), 'author').text()
                titles = [a for a in n.walk() if a.has('title')]
                magazines = [a.text() for a in n.walk() if a.has('magazine')]
                if author == 'なし' and not titles:
                    title = source_title = magazine = ''
                    status = 'No award'
                else:
                    title_node = _one(titles, 'work title')
                    source_title = title_node.text()
                    # Only explicitly marked pronunciation spans are omitted from the matching title.
                    def content(node):
                        return ''.join(content(a) if isinstance(a, _Node) else a for a in node.children
                                       if not isinstance(a, _Node) or not a.has('small'))
                    title = _text(content(title_node))
                    magazine = _one(magazines, 'publication')
                    if not title or not author or author == 'なし':
                        raise AkutagawaSourceError('Missing Akutagawa work identity')
                    status = 'Winner'
                rows.append(_Row(*previous, title, source_title, author, magazine, status, WINNERS_URL))
                previous = None
            elif n.tag == 'dd' and any(a.has('title') and not a.has('head') for a in n.walk()):
                raise AkutagawaSourceError('Akutagawa work has no round')
        if previous:
            raise AkutagawaSourceError('Akutagawa round has no result')
    _validate_winners(rows)
    return tuple(rows)


def _validate_winners(rows):
    rounds = {r.round_number for r in rows}
    if not rounds or max(rounds) < 175 or rounds != set(range(1, max(rounds) + 1)):
        raise AkutagawaSourceError('Incomplete Akutagawa winner history')
    identities = set()
    for r in rows:
        if (type(r.round_number) is not int or type(r.year) is not int
                or not 1935 <= r.year <= datetime.now(timezone.utc).year
                or r.half not in ('first half', 'second half')
                or r.status not in ('Winner', 'No award') or r.source_url != WINNERS_URL
                or any(not isinstance(x, str) for x in (r.title, r.source_title, r.author, r.magazine))
                or (r.status == 'Winner' and (not r.title.strip() or not r.author.strip() or not r.source_title.strip()))
                or (r.status == 'No award' and (r.title or r.source_title or r.author != 'なし' or r.magazine))):
            raise AkutagawaSourceError('Invalid Akutagawa archive record')
        identity = (r.round_number, _key(r.title), _key(r.author))
        if identity in identities:
            raise AkutagawaSourceError('Duplicate Akutagawa record')
        identities.add(identity)
    reviewed = _reference_data()['reviewed_rounds']
    for number in rounds:
        group = [r for r in rows if r.round_number == number]
        expected = reviewed.get(str(number))
        if expected and (len(group) < expected['minimum_rows'] or any(r.year != expected['year'] or r.half != expected['half'] for r in group)):
            raise AkutagawaSourceError('Incomplete or misdated reviewed Akutagawa round')
        if len({(r.year, r.half) for r in group}) != 1 or (len(group) > 1 and any(r.status == 'No award' for r in group)):
            raise AkutagawaSourceError('Conflicting Akutagawa round')
    if not any(r.round_number == 1 and r.year == 1935 and r.half == 'first half' for r in rows):
        raise AkutagawaSourceError('Wrong Akutagawa archive start')


def _parse_nominees(html, specification):
    number, year, half, url, count = specification
    root = _tree(html)
    _canonical(root, url)
    if not any(n.tag == 'h1' and f'第{number}回芥川' in n.text() for n in root.walk()):
        raise AkutagawaSourceError('Wrong Akutagawa nomination round')
    active = False
    rows = []
    for n in root.walk():
        if n.tag not in ('h3', 'h4'):
            continue
        text = n.text()
        if text in ('芥川龍之介賞 候補作', '候補作品（作者名：五十音順）'):
            active = True
            continue
        if '直木三十五賞' in text and '候補作' in text:
            active = False
        if not active:
            continue
        match = re.fullmatch(r'(.+?)（[^）]+）\s*「(.+?)」\s*(.+)', text)
        if match:
            author, title, publication = (_text(v) for v in match.groups())
            rows.append(_Row(number, year, half, title, title, author, publication, 'Nominated', url))
    if len(rows) != count or len({(r.title, r.author) for r in rows}) != count:
        raise AkutagawaSourceError(f'Incomplete Akutagawa round {number} nominations')
    return tuple(rows)


def _merge(winners, nominees):
    records = [r for r in winners if r.status == 'Winner']
    winner_keys = {(r.round_number, _key(t), _key(r.author)) for r in records for t in (r.title, r.source_title)}
    for r in nominees:
        if (r.round_number, _key(r.title), _key(r.author)) not in winner_keys:
            records.append(r)
    return tuple(records)


def _fetch_html(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'Calibre-Awards/0.3.0 (award lookup)', 'Accept-Encoding': 'identity'})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            if response.status != 200 or response.url != url:
                raise AkutagawaSourceError(f'Unexpected Akutagawa response: {url}')
            return response.read().decode('utf-8')
    except urllib.error.HTTPError as exc:
        exc.close()
        raise AkutagawaSourceError(f'Akutagawa request failed with HTTP {exc.code}: {url}') from exc
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeError) as exc:
        raise AkutagawaSourceError(f'Akutagawa source unavailable: {url}: {exc}') from exc


def _load_disk():
    payload = cache.load_source_cache(SOURCE_KEY, CACHE_VERSION)
    if payload is None:
        return None
    try:
        rows = tuple(_Row(**r) for r in payload['records'])
        winners = tuple(r for r in rows if r.source_url == WINNERS_URL)
        _validate_winners(winners)
        if payload['source_urls'] != SOURCE_URLS or payload['coverage'] != {'last_round': max(r.round_number for r in winners), 'nomination_rounds': [p[0] for p in NOMINATION_PAGES]}:
            return None
        for number, year, half, url, count in NOMINATION_PAGES:
            group = [r for r in rows if r.source_url == url]
            if (len(group) != count or len({(r.title, r.author) for r in group}) != count
                    or any(r.round_number != number or r.year != year or r.half != half or r.status != 'Nominated'
                           or not isinstance(r.title, str) or not r.title.strip() or r.title != r.source_title
                           or not isinstance(r.author, str) or not r.author.strip() or not isinstance(r.magazine, str) for r in group)):
                return None
        if len(winners) + sum(p[4] for p in NOMINATION_PAGES) != len(rows):
            return None
        return rows, payload
    except (TypeError, KeyError, ValueError, AttributeError, AkutagawaSourceError):
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
                winners = _parse_winners(_fetch_html(WINNERS_URL))
                nominees = tuple(r for p in NOMINATION_PAGES for r in _parse_nominees(_fetch_html(p[3]), p))
                rows = winners + nominees
            except Exception:
                if not disk:
                    raise
                rows = disk[0]
            else:
                cache.save_source_cache(SOURCE_KEY, CACHE_VERSION, records=[asdict(r) for r in rows],
                                        source_urls=SOURCE_URLS,
                                        coverage={'last_round': max(r.round_number for r in winners), 'nomination_rounds': [p[0] for p in NOMINATION_PAGES]},
                                        ttl_seconds=CACHE_TTL_SECONDS)
        _records = _merge([r for r in rows if r.source_url == WINNERS_URL], [r for r in rows if r.status == 'Nominated'])
        return _records


def _reset_runtime_state():
    global _records, _reference
    with _lock:
        _records = None
        _reference = None


def _reference_data():
    global _reference
    if _reference is None:
        path = 'awards/data/akutagawa_mappings.json'
        resource = globals().get('get_resources')
        try:
            raw = resource(path) if resource else (Path(__file__).resolve().parents[2] / path).read_bytes()
            _reference = json.loads(raw.decode('utf-8'))
        except (OSError, ValueError, AttributeError) as exc:
            raise AkutagawaSourceError('Reviewed Akutagawa mappings could not be read') from exc
    return _reference


def _mappings():
    return _reference_data()['mappings']


def lookup(title, author, series=None):
    if not title.strip() or not author.strip():
        raise ValueError('title and author must be non-empty')
    mappings = _mappings()
    results = []
    for row in _get_records():
        aliases = [m for m in mappings if m['round'] == row.round_number and m['title_ja'] == row.title and m['author_ja'] == row.author]
        titles = [row.title, row.source_title] + [t for m in aliases for t in m['titles']]
        authors = [row.author] + [a for m in aliases for a in m['authors']]
        if _key(title) not in {_key(t) for t in titles} or _key(author) not in {_key(a) for a in authors}:
            continue
        details = [f'Round {row.round_number}: {row.year}, {row.half}.', f'Original title: {row.source_title} | {row.author}']
        if row.magazine:
            details.append(f'Original publication: {row.magazine}')
        if aliases:
            details.extend(f"Verified title/name mapping: {m['titles'][0]} | {m['authors'][0]} ({m['evidence'][0]})" for m in aliases)
        results.append(AwardResult(work_title=row.title, work_author=row.author, award_name=AWARD_NAME,
                                   award_year=row.year, category=None, status=row.status, rank=None,
                                   source_name=SOURCE_NAME, source_url=row.source_url, source_details=tuple(details)))
    return results


# Coordinate RAM freshness and explicit refresh on retrieval workers.
import sys as _runtime_sys
from ..cache import source_runtime_guard as _runtime_guard
lookup = _runtime_guard(_runtime_sys.modules[__name__], lookup)
_get_records = _runtime_guard(_runtime_sys.modules[__name__], _get_records)
