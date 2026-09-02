"""Award-specific policies selected after lookup.

At most one policy may match a result. Overlaps are a configuration error,
not a merge. This registry is not the executable source list; that lives in
source_registry.AWARD_SOURCES.
"""

from .model import AwardResult
from .policy import AwardPolicy

PULITZER_FICTION_POLICY = AwardPolicy(
    award_name='Pulitzer Prize',
    category='Fiction',
    start_year=1980,
    qualifying_statuses=frozenset({'Finalist'}),
    notes=(
        'Pulitzer recognized finalists beginning in 1980. '
        'For Fiction, published finalists are included by this '
        'award-specific policy. Finalist does not imply an ordinal rank.'
    ),
)

NEWBERY_POLICY = AwardPolicy(
    award_name='Newbery Medal',
    category="Children's Literature",
    qualifying_statuses=frozenset({'Honor'}),
    notes=(
        'ALA Newbery Honor Books are an official award distinction. '
        'Historical runner-up terminology was made retroactive to Honor. '
        'Honor does not imply an ordinal rank.'
    ),
)

BOOKER_POLICY = AwardPolicy(
    award_name='Booker Prize',
    category='Fiction',
    qualifying_statuses=frozenset({'Shortlisted'}),
    notes=(
        'The Booker Prize Shortlist is an official published distinction. '
        'Shortlisted qualifies under this Booker-specific policy. '
        'Shortlisted does not imply an ordinal rank.'
    ),
)

GERMAN_BOOK_PRIZE_POLICY = AwardPolicy(
    award_name='Deutscher Buchpreis',
    category='Fiction',
    qualifying_statuses=frozenset({'Shortlisted'}),
    notes=(
        'The Deutscher Buchpreis Shortlist is an official finalist distinction. '
        'Shortlisted authors are formally recognized by the prize. '
        'Shortlisted qualifies under this award-specific policy. '
        'Shortlisted does not imply ordinal placement.'
    ),
)

PRIX_GONCOURT_POLICY = AwardPolicy(
    award_name='Prix Goncourt',
    category='Fiction',
    qualifying_statuses=frozenset({'Finalist'}),
    notes=(
        'The Académie Goncourt publishes three successive selections. '
        'The 3ème sélection is the final official selection from which '
        'the prize is awarded. Finalist qualifies under this '
        'award-specific policy. Finalist does not imply an ordinal rank.'
    ),
)

MILES_FRANKLIN_POLICY = AwardPolicy(
    award_name='Miles Franklin Literary Award',
    category='Fiction',
    qualifying_statuses=frozenset({'Finalist'}),
    notes=(
        'The Miles Franklin Literary Award publishes an official shortlist. '
        'Finalist represents an official published shortlist member. '
        'Shortlisted authors are formally recognized by the award. '
        'Qualification does not imply an ordinal rank.'
    ),
)

NBCC_FINALIST_POLICY = AwardPolicy(
    award_name='National Book Critics Circle Award',
    category=None,
    start_year=1976,
    qualifying_statuses=frozenset({'Finalist'}),
    notes=(
        'National Book Critics Circle Finalists are an official '
        'published distinction in the year archive. Finalist qualifies '
        'under this award-specific policy. Finalist does not imply an '
        'ordinal rank. Longlisted-only works are not returned. '
        'The 1975 archive lists Winners only.'
    ),
)

PEN_FAULKNER_FINALIST_POLICY = AwardPolicy(
    award_name='PEN/Faulkner Award for Fiction',
    category='Fiction',
    start_year=1981,
    qualifying_statuses=frozenset({'Finalist'}),
    notes=(
        'PEN/Faulkner Award for Fiction Finalists are an official '
        'published distinction. Finalist qualifies under this '
        'award-specific policy. Finalist does not imply an ordinal '
        'rank. Longlisted-only works are not returned. The Winner '
        'is selected from among the Finalists.'
    ),
)

PEN_HEMINGWAY_FINALIST_POLICY = AwardPolicy(
    award_name='PEN/Hemingway Award for Debut Novel',
    category='Fiction',
    start_year=2026,
    qualifying_statuses=frozenset({'Finalist'}),
    notes=(
        'PEN/Hemingway Award for Debut Novel Finalists are an '
        'official published distinction under the PEN/Faulkner '
        'administration. Finalist qualifies under this award-specific '
        'policy. Finalist does not imply an ordinal rank. Historical '
        'secondary distinctions from prior administrators are not '
        'returned in this phase. Longlisted-only works are not returned.'
    ),
)

BRAM_STOKER_FINALIST_POLICY = AwardPolicy(
    award_name='Bram Stoker Award',
    category=None,
    start_year=1987,
    qualifying_statuses=frozenset({'Finalist'}),
    notes=(
        'Horror Writers Association Final Ballot works are official '
        'Bram Stoker nominees/finalists. Finalist qualifies under this '
        'award-specific policy. Preliminary Ballot and recommendation '
        'list appearances are not returned. No ordinal rank is inferred.'
    ),
)

RONA_SHORTLIST_POLICY = AwardPolicy(
    award_name='Romantic Novel of the Year Award',
    category=None,
    start_year=2018,
    qualifying_statuses=frozenset({'Shortlisted'}),
    notes=(
        'The Romantic Novel of the Year Awards publish an official '
        'shortlist (also called finalists) from which the Winner is '
        'selected. Shortlisted qualifies under this award-specific '
        'policy. Shortlisted does not imply an ordinal rank. Ordinary '
        'submissions and entries are not returned.'
    ),
)

EDGAR_NOMINEE_POLICY = AwardPolicy(
    award_name='Edgar Award',
    category=None,
    start_year=1946,
    qualifying_statuses=frozenset({'Nominee'}),
    notes=(
        'Mystery Writers of America publishes official announced nominee '
        'slates from which the Winner is selected. Nominee qualifies under '
        'this Edgar-specific policy. Nomination does not imply an ordinal '
        'rank. Submissions are a separate earlier pool and are not returned.'
    ),
)

IPAF_SHORTLISTED_POLICY = AwardPolicy(
    award_name='International Prize for Arabic Fiction',
    category='Fiction',
    start_year=2020,
    qualifying_statuses=frozenset({'Shortlisted'}),
    notes=(
        'The International Prize for Arabic Fiction publishes a formal '
        'six-book shortlist from which the Winner is selected. '
        'Shortlisted qualifies under this award-specific policy. '
        'No ordinal rank is inferred. Longlisted-only works are not '
        'returned. Current production coverage begins in 2020 because '
        'earlier official English archive pages have not yet been '
        'migrated to the current site.'
    ),
)

WOMENS_PRIZE_FICTION_POLICY = AwardPolicy(
    award_name="Women's Prize for Fiction",
    category='Fiction',
    start_year=2017,
    qualifying_statuses=frozenset({'Shortlisted'}),
    notes=(
        "The Women's Prize for Fiction Shortlist is an official "
        'published distinction. Shortlisted qualifies under this '
        'award-specific policy. Shortlisted does not imply an '
        'ordinal rank. Longlisted-only works are not returned.'
    ),
)

AWARD_POLICIES: tuple[AwardPolicy, ...] = (
    PULITZER_FICTION_POLICY,
    NEWBERY_POLICY,
    BOOKER_POLICY,
    GERMAN_BOOK_PRIZE_POLICY,
    PRIX_GONCOURT_POLICY,
    MILES_FRANKLIN_POLICY,
    WOMENS_PRIZE_FICTION_POLICY,
    NBCC_FINALIST_POLICY,
    PEN_FAULKNER_FINALIST_POLICY,
    PEN_HEMINGWAY_FINALIST_POLICY,
    IPAF_SHORTLISTED_POLICY,
    BRAM_STOKER_FINALIST_POLICY,
    EDGAR_NOMINEE_POLICY,
    RONA_SHORTLIST_POLICY,
)


def _policy_matches(result: AwardResult, policy: AwardPolicy) -> bool:
    if policy.award_name.strip().casefold() != result.award_name.strip().casefold():
        return False

    if policy.category is not None:
        if result.category is None:
            return False
        if policy.category.strip().casefold() != result.category.strip().casefold():
            return False

    if policy.start_year is not None:
        if result.award_year is None or result.award_year < policy.start_year:
            return False

    if policy.end_year is not None:
        if result.award_year is None or result.award_year > policy.end_year:
            return False

    return True


def find_award_policy(result: AwardResult) -> AwardPolicy | None:
    """Return the single matching policy, or None.

    Two matches raise RuntimeError: overlapping policies are an architecture
    bug, not an invitation to pick one arbitrarily.
    """
    matches = [
        policy for policy in AWARD_POLICIES if _policy_matches(result, policy)
    ]
    if not matches:
        return None
    if len(matches) > 1:
        raise RuntimeError(
            'Overlapping award policies in registry for '
            f'award_name={result.award_name!r}, category={result.category!r}, '
            f'award_year={result.award_year!r}'
        )
    return matches[0]
