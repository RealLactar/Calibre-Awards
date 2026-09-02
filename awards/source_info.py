"""User-facing award-source capability metadata. Calibre-free and Qt-free.

SOURCE_INFOS describes what each source can do. It does not select sources,
run lookups, or qualify results. Keep keys and order aligned with
AWARD_SOURCES; tests enforce that, not a runtime import cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from .sources import (
    booker,
    bram_stoker,
    edgar,
    german_book_prize,
    hugo,
    ipaf,
    locus,
    miles_franklin,
    national_book_critics_circle,
    nebula,
    newbery,
    nobel,
    pen_faulkner,
    pen_hemingway,
    prix_goncourt,
    pulitzer,
    womens_prize_fiction,
    world_fantasy,
)

_IDENTITY_SCOPES = frozenset({'work', 'series', 'author'})
_SCOPE_LABELS = {
    'work': 'Work awards',
    'series': 'Series awards',
    'author': 'Author awards',
}


@dataclass(frozen=True, slots=True)
class SourceInfo:
    """Static help metadata for one award source.

    Categories and identity scopes describe current lookup capabilities.
    They do not change lookup, matching, or qualification.
    """

    key: str
    display_name: str
    categories: tuple[str, ...]
    identity_scopes: tuple[str, ...]
    homepage_url: str
    description: str
    limitation: str | None = None

    def __post_init__(self) -> None:
        if not self.key or not self.key.strip() or self.key != self.key.strip():
            raise ValueError('key must be a non-empty string')
        if (
            not self.display_name
            or not self.display_name.strip()
            or self.display_name != self.display_name.strip()
        ):
            raise ValueError('display_name must be a non-empty string')
        if not self.categories:
            raise ValueError('categories must contain at least one label')
        if any(not label or not str(label).strip() for label in self.categories):
            raise ValueError('categories must contain non-empty labels')
        if not self.identity_scopes:
            raise ValueError('identity_scopes must contain at least one scope')
        if any(scope not in _IDENTITY_SCOPES for scope in self.identity_scopes):
            raise ValueError(
                "identity_scopes values must be 'work', 'series', or 'author'"
            )
        if not self.homepage_url or not self.homepage_url.strip():
            raise ValueError('homepage_url must be a non-empty string')
        parsed = urlparse(self.homepage_url.strip())
        if parsed.scheme != 'https' or not parsed.netloc:
            raise ValueError('homepage_url must be an https URL')
        if not self.description or not self.description.strip():
            raise ValueError('description must be a non-empty string')
        if self.limitation is not None and not self.limitation.strip():
            raise ValueError('limitation must be None or a non-empty string')


def _pulitzer_categories() -> tuple[str, ...]:
    return tuple(category for category, _url in pulitzer._CATEGORY_URLS)


def _nebula_categories() -> tuple[str, ...]:
    labels: list[str] = []
    for config in nebula._AWARD_CONFIGS:
        if config.award_name == nebula.AWARD_NAME_NEBULA:
            labels.append(config.category)
        else:
            labels.append(f'{config.award_name} — {config.category}')
    return tuple(labels)


def _hugo_categories() -> tuple[str, ...]:
    return hugo._PARSED_CATEGORIES


def _locus_categories() -> tuple[str, ...]:
    return tuple(locus._SUPPORTED_CATEGORY_LABELS)


def _world_fantasy_categories() -> tuple[str, ...]:
    return world_fantasy._CANONICAL_CATEGORIES


def _bram_stoker_categories() -> tuple[str, ...]:
    return bram_stoker.SOURCEINFO_CATEGORIES


def _edgar_categories() -> tuple[str, ...]:
    return edgar.SOURCEINFO_CATEGORIES


def _nobel_categories() -> tuple[str, ...]:
    return (nobel.CATEGORY_LITERATURE,)


def _booker_categories() -> tuple[str, ...]:
    return (booker.CATEGORY,)


def _german_book_prize_categories() -> tuple[str, ...]:
    return (german_book_prize.CATEGORY,)


def _prix_goncourt_categories() -> tuple[str, ...]:
    return (prix_goncourt.CATEGORY,)


def _miles_franklin_categories() -> tuple[str, ...]:
    return (miles_franklin.CATEGORY,)


def _womens_prize_fiction_categories() -> tuple[str, ...]:
    return (womens_prize_fiction.CATEGORY,)


def _nbcc_categories() -> tuple[str, ...]:
    return national_book_critics_circle._SOURCEINFO_CATEGORIES


def _pen_faulkner_categories() -> tuple[str, ...]:
    return (pen_faulkner.CATEGORY,)


def _pen_hemingway_categories() -> tuple[str, ...]:
    return (pen_hemingway.CATEGORY,)


def _ipaf_categories() -> tuple[str, ...]:
    return (ipaf.CATEGORY,)


def _newbery_categories() -> tuple[str, ...]:
    return (newbery.CATEGORY,)


def format_identity_scopes(scopes: tuple[str, ...]) -> str:
    """Return comma-separated user-facing labels for identity scopes."""
    return ', '.join(_SCOPE_LABELS[scope] for scope in scopes)


def format_source_info(info: SourceInfo) -> str:
    """Return a plain-text help block for one source."""
    lines = [
        info.display_name,
        f'Categories: {", ".join(info.categories)}',
        f'Scope: {format_identity_scopes(info.identity_scopes)}',
        info.description.strip(),
    ]
    if info.limitation is not None:
        lines.append(f'Note: {info.limitation.strip()}')
    return '\n'.join(lines)


SOURCE_INFOS: tuple[SourceInfo, ...] = (
    SourceInfo(
        key='pulitzer',
        display_name='Pulitzer Prizes',
        categories=_pulitzer_categories(),
        identity_scopes=('work',),
        homepage_url=pulitzer.SOURCE_HOME_URL,
        description='Fiction and Novel awards from Pulitzer.org.',
        limitation=(
            'Pulitzer.org sometimes blocks automated checks, so this source '
            'may be unavailable. Other award sources still run.'
        ),
    ),
    SourceInfo(
        key='nebula',
        display_name='Nebula Awards',
        categories=_nebula_categories(),
        identity_scopes=('work',),
        homepage_url=nebula.SOURCE_HOME_URL,
        description='Nebula and Andre Norton literary award results.',
    ),
    SourceInfo(
        key='hugo',
        display_name='Hugo Awards',
        categories=_hugo_categories(),
        identity_scopes=('work', 'series'),
        homepage_url=hugo.SOURCE_HOME_URL,
        description=(
            'Hugo work awards and supported series awards, including '
            'historical category names where applicable.'
        ),
    ),
    SourceInfo(
        key='locus',
        display_name='Locus Awards',
        categories=_locus_categories(),
        identity_scopes=('work',),
        homepage_url=locus.SFADB_ORIGIN,
        description=(
            'Ranked Locus literary awards from the Science Fiction Awards '
            'Database.'
        ),
    ),
    SourceInfo(
        key='world_fantasy',
        display_name='World Fantasy Awards',
        categories=_world_fantasy_categories(),
        identity_scopes=('work',),
        homepage_url=world_fantasy.SOURCE_HOME_URL,
        description=(
            'World Fantasy work awards in the supported literary categories.'
        ),
    ),
    SourceInfo(
        key='bram_stoker',
        display_name='Bram Stoker Awards',
        categories=_bram_stoker_categories(),
        identity_scopes=('work',),
        homepage_url=bram_stoker.SOURCE_HOME_URL,
        description=(
            'Horror Writers Association awards for superior achievement in '
            'horror and dark literature. Returns Winners and official Final '
            'Ballot works in bibliographic categories.'
        ),
        limitation=(
            'Coverage begins with the 1987 award cycle. Award year is the '
            'publication year, although Winners are announced the following '
            'year. Final Ballot works are returned as Finalists; Preliminary '
            'Ballot and recommendation list appearances are ignored. '
            'Screenplay, other-media, Lifetime Achievement, service, and '
            'press honors are excluded. Historical category names are '
            'preserved and ties may produce multiple Winners. No ordinal '
            'rank is inferred.'
        ),
    ),
    SourceInfo(
        key='edgar',
        display_name='Edgar Awards',
        categories=_edgar_categories(),
        identity_scopes=('work',),
        homepage_url=edgar.SOURCE_HOME_URL,
        description=(
            'Mystery Writers of America Edgar Awards for mystery and crime '
            'fiction and nonfiction. Returns official Winners and Nominees '
            'in bibliographic categories.'
        ),
        limitation=(
            'Coverage begins in 1946. Award year is the ceremony year and '
            'generally honors prior-year publication. Nominees are official '
            'announced nominee slates and do not imply rank. Early years are '
            'often winner-only. Robert L. Fish Nominees appear in the official '
            'database only from 2024. Media, screen, stage, person, service, '
            'design, and Special Edgar categories are excluded.'
        ),
    ),
    SourceInfo(
        key='nobel',
        display_name='Nobel Award',
        categories=_nobel_categories(),
        identity_scopes=('author', 'work'),
        homepage_url=nobel.SOURCE_HOME_URL,
        description=(
            'Nobel Prize in Literature results, normally awarded to the '
            'author and shown as [Author: Name]; a small set of specifically '
            'cited works is recognized separately as work awards.'
        ),
    ),
    SourceInfo(
        key='booker',
        display_name='The Booker Prize',
        categories=_booker_categories(),
        identity_scopes=('work',),
        homepage_url=booker.SOURCE_HOME_URL,
        description=(
            'Booker Prize winners and shortlisted works from the official '
            'Booker Prize archive.'
        ),
        limitation='Longlisted-only works are not returned.',
    ),
    SourceInfo(
        key='german_book_prize',
        display_name='Deutscher Buchpreis',
        categories=_german_book_prize_categories(),
        identity_scopes=('work',),
        homepage_url=german_book_prize.ARCHIVE_INDEX_URL,
        description=(
            'German Book Prize (Deutscher Buchpreis) winners and shortlisted '
            'novels from the official archive.'
        ),
        limitation='Longlisted-only works are not returned.',
    ),
    SourceInfo(
        key='prix_goncourt',
        display_name='Prix Goncourt',
        categories=_prix_goncourt_categories(),
        identity_scopes=('work',),
        homepage_url=prix_goncourt.SOURCE_HOME_URL,
        description=(
            'Prix Goncourt winners from the official Académie Goncourt '
            'archive; French-language fiction.'
        ),
        limitation=(
            'Winners are available from the complete official archive '
            'beginning in 1903. Finalists from the Académie Goncourt '
            '3ème sélection are included from 2018 onward. First- and '
            'second-selection-only works are not returned.'
        ),
    ),
    SourceInfo(
        key='miles_franklin',
        display_name='Miles Franklin Literary Award',
        categories=_miles_franklin_categories(),
        identity_scopes=('work',),
        homepage_url=miles_franklin.SOURCE_HOME_URL,
        description=(
            'Miles Franklin Literary Award winners and officially labeled '
            'shortlist/finalist novels from Perpetual\'s judges and history '
            'of recipients archive.'
        ),
        limitation=(
            'Official production coverage begins in 2007. Finalists are '
            'included only when the history page labels the work Finalist, '
            'Shortlist, or Shortlisted. The 2025 nonwinning shortlist is not '
            'returned because that page does not distinguish those works from '
            'longlist-only works. Longlist-only works are not returned. '
            'Pre-2007 winners are not available from this archive.'
        ),
    ),
    SourceInfo(
        key='womens_prize_fiction',
        display_name="Women's Prize for Fiction",
        categories=_womens_prize_fiction_categories(),
        identity_scopes=('work',),
        homepage_url=womens_prize_fiction.SOURCE_HOME_URL,
        description=(
            "Women's Prize for Fiction winners from the official "
            'previous-prizes archive and current prize page, plus official '
            'shortlisted works from first-party shortlist announcements.'
        ),
        limitation=(
            'Official Winner coverage begins in 1996. Historical Orange '
            'Prize for Fiction years are treated as the same prize under '
            'its current name. Shortlisted works are covered from 2017 '
            'onward. Longlisted-only works are not returned. The Women\'s '
            'Prize for Non-Fiction, Discoveries, and other Women\'s Prize '
            'programmes are excluded.'
        ),
    ),
    SourceInfo(
        key='national_book_critics_circle',
        display_name='National Book Critics Circle Awards',
        categories=_nbcc_categories(),
        identity_scopes=('work',),
        homepage_url=national_book_critics_circle.SOURCE_HOME_URL,
        description=(
            'Official National Book Critics Circle year archive: Winners and '
            'Finalists in the core book categories, plus the John Leonard '
            'Prize and Gregg Barrios Book in Translation Prize.'
        ),
        limitation=(
            "Award year is the book's publication/archive year, not the later "
            'ceremony date. Winner coverage begins in 1975; Finalists begin in '
            '1976. Historical category labels such as General Nonfiction, '
            'Biography/Autobiography, and Autobiography/Memoir are preserved. '
            'Longlisted-only works are not returned. Reviewing citations, '
            'lifetime/institution honors, and fellowships are excluded.'
        ),
    ),
    SourceInfo(
        key='pen_faulkner',
        display_name='PEN/Faulkner Award for Fiction',
        categories=_pen_faulkner_categories(),
        identity_scopes=('work',),
        homepage_url=pen_faulkner.SOURCE_HOME_URL,
        description=(
            'Official PEN/Faulkner Award for Fiction Winners and Finalists. '
            'Eligible works include novels, novellas, and short-story '
            'collections.'
        ),
        limitation=(
            'Winner and Finalist coverage begins in 1981. Award year is the '
            'ceremony/award year, not the eligibility publication year. '
            'Longlisted-only works are not returned. The PEN/Hemingway Award, '
            'PEN/Malamud Award, and PEN/Faulkner Literary Champion are '
            'excluded. Historical Finalist counts vary and no ordinal rank '
            'is inferred.'
        ),
    ),
    SourceInfo(
        key='pen_hemingway',
        display_name='PEN/Hemingway Award for Debut Novel',
        categories=_pen_hemingway_categories(),
        identity_scopes=('work',),
        homepage_url=pen_hemingway.SOURCE_HOME_URL,
        description=(
            'Official PEN/Hemingway Award for Debut Novel Winners, plus '
            'Finalists from the PEN/Faulkner administration. Historical '
            'winners include first books of fiction; current guidelines '
            'are for debut novels.'
        ),
        limitation=(
            'Winner coverage begins in 1976. Award year is the '
            'ceremony/award year, not the eligibility publication year. '
            'Finalists are included from 2026, when administration '
            'transferred to the PEN/Faulkner Foundation. Historical '
            'Finalists, Runners-up, and Honorable Mentions from prior '
            'administrators are not returned in this phase. '
            'Longlisted-only works are not returned. The PEN/Faulkner '
            'Award for Fiction, PEN/Malamud Award, and PEN/Faulkner '
            'Literary Champion are excluded. No ordinal rank is inferred.'
        ),
    ),
    SourceInfo(
        key='ipaf',
        display_name='International Prize for Arabic Fiction',
        categories=_ipaf_categories(),
        identity_scopes=('work',),
        homepage_url=ipaf.SOURCE_HOME_URL,
        description=(
            'Official Winners and Shortlisted novels originally written '
            'in Arabic for the International Prize for Arabic Fiction. '
            'IPAF also supports international translation of recognized '
            'novels.'
        ),
        limitation=(
            'Coverage currently follows populated official English '
            'prize-year pages from 2020 onward; IPAF\'s earlier 2008-2019 '
            'archive has not yet been migrated to the current site. '
            'Longlisted-only works are not returned. Titles and author '
            'names use IPAF\'s official English forms and may differ from '
            'earlier announcements or later published translations. No '
            'generated transliteration or ordinal rank is used.'
        ),
    ),
    SourceInfo(
        key='newbery',
        display_name='John Newbery Medal',
        categories=_newbery_categories(),
        identity_scopes=('work',),
        homepage_url=newbery.SOURCE_HOME_URL,
        description=(
            'Newbery Medal winners and Honor Books from the official ALA '
            'HTML archive.'
        ),
        limitation=(
            'Current plugin coverage begins in 1930 and ends in 2023.'
        ),
    ),
)
