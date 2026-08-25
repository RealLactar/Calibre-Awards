"""Curated Hugo Best Novel ordinal placements.

These records are transcribed from official Hugo final-ballot statistics.
They enrich an already-established live HTML Winner/Finalist result with
rank, an optional tie note, and the exact statistics document URL.

Absence of a row means rank is unknown, not that the work was not a
finalist. Ordinary Hugo history-page list order must never be converted
into rank. Shared ranks require tied=True on every sharing row.
source_url identifies the official statistics document that establishes
the rank.
"""

from __future__ import annotations

from dataclasses import dataclass

STATS_1972 = (
    'https://www.thehugoawards.org/content/pdf/1972HugoStatistics.pdf'
)
STATS_1980 = (
    'https://www.thehugoawards.org/wp-content/uploads/2024/02/'
    '1980-Hugo-Nominating-and-Voting-Statistics.pdf'
)
STATS_1996 = (
    'https://www.thehugoawards.org/content/pdf/1996HugoStatistics-Final.pdf'
)
STATS_2000 = (
    'https://www.thehugoawards.org/wp-content/uploads/2019/06/'
    '2000-Hugo-Statistics.pdf'
)
STATS_2006 = (
    'https://www.thehugoawards.org/content/pdf/2006HugoStatistics-Final.txt'
)
STATS_2015 = (
    'https://www.thehugoawards.org/content/pdf/2015HugoStatistics.pdf'
)
STATS_2017 = (
    'https://www.thehugoawards.org/wp-content/uploads/2017/08/'
    '2017-Hugo-report-1-voting-results.pdf'
)
STATS_2024 = (
    'https://www.thehugoawards.org/wp-content/uploads/2024/08/'
    '2024_hugo_statistics.pdf'
)
STATS_2025 = (
    'https://www.thehugoawards.org/wp-content/uploads/2025/09/'
    '2025-Hugo-Voting-Statistics-v3.pdf'
)

_NON_WORK_TITLES = frozenset({
    'no award',
    'no winner chosen',
})


@dataclass(frozen=True, slots=True)
class HugoRanking:
    """One official Best Novel ordinal placement for one work in one year."""

    award_year: int
    work_title: str
    work_author: str
    rank: int
    source_url: str
    tied: bool = False

    def __post_init__(self) -> None:
        if self.award_year <= 0:
            raise ValueError('award_year must be greater than zero')
        if not self.work_title or not self.work_title.strip():
            raise ValueError('work_title must be a non-empty string')
        if not self.work_author or not self.work_author.strip():
            raise ValueError('work_author must be a non-empty string')
        if self.rank <= 0:
            raise ValueError('rank must be greater than zero')
        if not self.source_url or not self.source_url.strip():
            raise ValueError('source_url must be a non-empty string')
        title_key = self.work_title.strip().casefold()
        author_key = self.work_author.strip().casefold()
        if title_key in _NON_WORK_TITLES or author_key in _NON_WORK_TITLES:
            raise ValueError('No Award is not a HugoRanking work entry')


def _ranking(
    award_year: int,
    work_title: str,
    work_author: str,
    rank: int,
    source_url: str,
    *,
    tied: bool = False,
) -> HugoRanking:
    return HugoRanking(
        award_year=award_year,
        work_title=work_title,
        work_author=work_author,
        rank=rank,
        source_url=source_url,
        tied=tied,
    )


HUGO_BEST_NOVEL_RANKINGS: tuple[HugoRanking, ...] = (
    _ranking(1972, 'To Your Scattered Bodies Go', 'Philip José Farmer', 1, STATS_1972),
    _ranking(1972, 'The Lathe of Heaven', 'Ursula K. Le Guin', 2, STATS_1972),
    _ranking(1972, 'Dragonquest', 'Anne McCaffrey', 3, STATS_1972),
    _ranking(1972, 'Jack of Shadows', 'Roger Zelazny', 4, STATS_1972),
    _ranking(1972, 'A Time of Changes', 'Robert Silverberg', 5, STATS_1972),
    _ranking(1980, 'The Fountains of Paradise', 'Arthur C. Clarke', 1, STATS_1980),
    _ranking(1980, 'Titan', 'John Varley', 2, STATS_1980),
    _ranking(1980, 'Jem', 'Frederik Pohl', 3, STATS_1980),
    _ranking(1980, 'Harpist in the Wind', 'Patricia A. McKillip', 4, STATS_1980),
    _ranking(1980, 'On Wings of Song', 'Thomas M. Disch', 5, STATS_1980),
    _ranking(1996, 'The Diamond Age', 'Neal Stephenson', 1, STATS_1996),
    _ranking(1996, 'The Time Ships', 'Stephen Baxter', 2, STATS_1996),
    _ranking(1996, 'Brightness Reef', 'David Brin', 3, STATS_1996),
    _ranking(1996, 'The Terminal Experiment', 'Robert J. Sawyer', 4, STATS_1996),
    _ranking(1996, 'Remake', 'Connie Willis', 5, STATS_1996),
    _ranking(2000, 'A Deepness in the Sky', 'Vernor Vinge', 1, STATS_2000),
    _ranking(2000, 'A Civil Campaign', 'Lois McMaster Bujold', 2, STATS_2000),
    _ranking(2000, 'Cryptonomicon', 'Neal Stephenson', 3, STATS_2000),
    _ranking(2000, "Darwin's Radio", 'Greg Bear', 4, STATS_2000),
    _ranking(
        2000,
        'Harry Potter and the Prisoner of Azkaban',
        'J. K. Rowling',
        5,
        STATS_2000,
    ),
    _ranking(2006, 'Spin', 'Robert Charles Wilson', 1, STATS_2006),
    _ranking(2006, 'Accelerando', 'Charles Stross', 2, STATS_2006),
    _ranking(2006, "Old Man's War", 'John Scalzi', 3, STATS_2006),
    _ranking(2006, 'Learning the World', 'Ken MacLeod', 4, STATS_2006),
    _ranking(2006, 'A Feast for Crows', 'George R. R. Martin', 5, STATS_2006),
    _ranking(2015, 'The Three Body Problem', 'Cixin Liu', 1, STATS_2015),
    _ranking(2015, 'The Goblin Emperor', 'Katherine Addison', 2, STATS_2015),
    _ranking(2015, 'Ancillary Sword', 'Ann Leckie', 3, STATS_2015),
    _ranking(2015, 'Skin Game', 'Jim Butcher', 5, STATS_2015),
    _ranking(2015, 'The Dark Between the Stars', 'Kevin J. Anderson', 6, STATS_2015),
    _ranking(2017, 'The Obelisk Gate', 'N. K. Jemisin', 1, STATS_2017),
    _ranking(2017, 'All the Birds in the Sky', 'Charlie Jane Anders', 2, STATS_2017),
    _ranking(2017, 'Ninefox Gambit', 'Yoon Ha Lee', 3, STATS_2017),
    _ranking(2017, 'A Closed and Common Orbit', 'Becky Chambers', 4, STATS_2017),
    _ranking(2017, 'Too Like the Lightning', 'Ada Palmer', 5, STATS_2017),
    _ranking(2017, "Death's End", 'Cixin Liu', 6, STATS_2017),
    _ranking(2024, 'Some Desperate Glory', 'Emily Tesh', 1, STATS_2024),
    _ranking(2024, 'Translation State', 'Ann Leckie', 2, STATS_2024),
    _ranking(2024, 'The Adventures of Amina al-Sirafi', 'Shannon Chakraborty', 3, STATS_2024),
    _ranking(2024, 'Witch King', 'Martha Wells', 4, STATS_2024),
    _ranking(2024, 'The Saint of Bright Doors', 'Vajra Chandrasekera', 5, STATS_2024),
    _ranking(2024, 'Starter Villain', 'John Scalzi', 6, STATS_2024),
    _ranking(2025, 'The Tainted Cup', 'Robert Jackson Bennett', 1, STATS_2025),
    _ranking(2025, 'A Sorceress Comes to Call', 'T. Kingfisher', 2, STATS_2025),
    _ranking(2025, 'Alien Clay', 'Adrian Tchaikovsky', 3, STATS_2025),
    _ranking(2025, 'Someone You Can Build a Nest In', 'John Wiswell', 4, STATS_2025),
    _ranking(2025, 'Service Model', 'Adrian Tchaikovsky', 5, STATS_2025),
    _ranking(2025, 'The Ministry of Time', 'Kaliane Bradley', 6, STATS_2025),
)


def validate_hugo_rankings(records: tuple[HugoRanking, ...] | None = None) -> None:
    """Raise ValueError if curated Best Novel ranking data is internally inconsistent."""
    payload = HUGO_BEST_NOVEL_RANKINGS if records is None else records
    seen_works: set[tuple[int, str, str]] = set()
    ranks_by_year: dict[int, dict[int, list[HugoRanking]]] = {}
    for record in payload:
        if record.award_year <= 0:
            raise ValueError('award_year must be greater than zero')
        title = record.work_title.strip()
        author = record.work_author.strip()
        url = record.source_url.strip()
        if not title:
            raise ValueError('work_title must be a non-empty string')
        if not author:
            raise ValueError('work_author must be a non-empty string')
        if record.rank <= 0:
            raise ValueError('rank must be greater than zero')
        if not url:
            raise ValueError('source_url must be a non-empty string')
        title_key = title.casefold()
        author_key = author.casefold()
        if title_key in _NON_WORK_TITLES or author_key in _NON_WORK_TITLES:
            raise ValueError('No Award is not a HugoRanking work entry')
        work_key = (record.award_year, title_key, author_key)
        if work_key in seen_works:
            raise ValueError(
                'duplicate HugoRanking for '
                f'{record.award_year} {record.work_title!r} / {record.work_author!r}'
            )
        seen_works.add(work_key)
        ranks_by_year.setdefault(record.award_year, {}).setdefault(
            record.rank, []
        ).append(record)

    for year, by_rank in ranks_by_year.items():
        for rank, grouped in by_rank.items():
            if len(grouped) < 2:
                continue
            if not all(item.tied for item in grouped):
                titles = ', '.join(item.work_title for item in grouped)
                raise ValueError(
                    f'{year} rank {rank} is shared by {titles} without tied=True'
                )
