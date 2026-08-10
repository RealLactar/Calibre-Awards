from .model import AwardResult
from .policy import AwardPolicy

PULITZER_FICTION_POLICY = AwardPolicy(
    award_name='Pulitzer Prize',
    category='Fiction',
    start_year=1980,
    qualifying_statuses=frozenset({'Finalist'}),
    notes=(
        'Pulitzer recognized finalists beginning in 1980. '
        'For Fiction, published finalists fall within the project top-five '
        'inclusion threshold. Finalist does not imply an ordinal rank.'
    ),
)

BOOKER_PRIZE_POLICY = AwardPolicy(
    award_name='Booker Prize',
    start_year=2026,
    nonqualifying_statuses=frozenset({'Longlist', 'Longlisted'}),
    notes=(
        'The Booker Prize 2026 rules specify a 12- or 13-book longlist and '
        'a six-book shortlist. Longlisted therefore does not qualify. '
        'Shortlisted remains REVIEW because a six-book shortlist does not '
        'establish top-five placement.'
    ),
)

AWARD_POLICIES: tuple[AwardPolicy, ...] = (
    PULITZER_FICTION_POLICY,
    BOOKER_PRIZE_POLICY,
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
    """Return the single registry policy matching result, if any."""
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
