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

AWARD_POLICIES: tuple[AwardPolicy, ...] = (
    PULITZER_FICTION_POLICY,
    NEWBERY_POLICY,
    BOOKER_POLICY,
    GERMAN_BOOK_PRIZE_POLICY,
    PRIX_GONCOURT_POLICY,
    MILES_FRANKLIN_POLICY,
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
