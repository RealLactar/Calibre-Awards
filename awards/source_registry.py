"""Executable award lookup sources, in user-visible order.

This is the set of sources the engine can run. SOURCE_INFOS describes the
same sources for help text; tests keep the two lists aligned. Source lookup
callables must not read Calibre preferences — the engine filters enabled
keys before scheduling.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .model import AwardResult
from .sources.booker import lookup as booker_lookup
from .sources.german_book_prize import lookup as german_book_prize_lookup
from .sources.hugo import lookup as hugo_lookup
from .sources.prix_goncourt import lookup as prix_goncourt_lookup
from .sources.locus import lookup as locus_lookup
from .sources.miles_franklin import lookup as miles_franklin_lookup
from .sources.nebula import lookup as nebula_lookup
from .sources.newbery import lookup as newbery_lookup
from .sources.nobel import lookup as nobel_lookup
from .sources.pulitzer import lookup as pulitzer_lookup
from .sources.world_fantasy import lookup as world_fantasy_lookup


class AwardSourceLookup(Protocol):
    """Lookup callable: title and author required; series optional."""

    def __call__(
        self,
        title: str,
        author: str,
        series: str | None = None,
    ) -> list[AwardResult]: ...


@dataclass(frozen=True, slots=True)
class AwardSource:
    """One award lookup source. Source-neutral; no qualification or GUI logic."""

    key: str
    display_name: str
    lookup: AwardSourceLookup


AWARD_SOURCES: tuple[AwardSource, ...] = (
    AwardSource(
        key='pulitzer',
        display_name='Pulitzer Prizes',
        lookup=pulitzer_lookup,
    ),
    AwardSource(
        key='nebula',
        display_name='Nebula Awards',
        lookup=nebula_lookup,
    ),
    AwardSource(
        key='hugo',
        display_name='Hugo Awards',
        lookup=hugo_lookup,
    ),
    AwardSource(
        key='locus',
        display_name='Locus Awards',
        lookup=locus_lookup,
    ),
    AwardSource(
        key='world_fantasy',
        display_name='World Fantasy Awards',
        lookup=world_fantasy_lookup,
    ),
    AwardSource(
        key='nobel',
        display_name='Nobel Award',
        lookup=nobel_lookup,
    ),
    AwardSource(
        key='booker',
        display_name='The Booker Prize',
        lookup=booker_lookup,
    ),
    AwardSource(
        key='german_book_prize',
        display_name='Deutscher Buchpreis',
        lookup=german_book_prize_lookup,
    ),
    AwardSource(
        key='prix_goncourt',
        display_name='Prix Goncourt',
        lookup=prix_goncourt_lookup,
    ),
    AwardSource(
        key='miles_franklin',
        display_name='Miles Franklin Literary Award',
        lookup=miles_franklin_lookup,
    ),
    AwardSource(
        key='newbery',
        display_name='John Newbery Medal',
        lookup=newbery_lookup,
    ),
)
