"""Inclusion decisions for factual AwardResult records.

Rank is authoritative only when the source supplied it. Status words such as
finalist or nominee never become an inferred ordinal. A caller-supplied
policy must apply to the result before any of those rules run.
"""

from dataclasses import dataclass
from enum import Enum

from .model import AwardResult
from .policy import AwardPolicy
from .rank_cutoff import (
    DEFAULT_MAX_QUALIFYING_RANK,
    MAX_MAX_QUALIFYING_RANK,
    MIN_MAX_QUALIFYING_RANK,
)

_WINNER_STATUSES = frozenset({
    'winner',
    'win',
    'won',
})

_REVIEW_STATUSES = frozenset({
    'finalist',
    'shortlist',
    'shortlisted',
    'honor book',
    'honor',
    'runner-up',
    'runner up',
    'nominee',
    'nominated',
    'longlist',
    'longlisted',
})


class QualificationDecision(Enum):
    QUALIFIES = 'QUALIFIES'
    DOES_NOT_QUALIFY = 'DOES_NOT_QUALIFY'
    REVIEW = 'REVIEW'


@dataclass(frozen=True, slots=True)
class QualificationResult:
    decision: QualificationDecision
    reason: str


def _ensure_policy_applies(result: AwardResult, policy: AwardPolicy) -> None:
    policy_name = policy.award_name.strip().casefold()
    result_name = result.award_name.strip().casefold()
    if policy_name != result_name:
        raise ValueError(
            'AwardPolicy does not apply to this AwardResult: '
            f'policy.award_name={policy.award_name!r}, '
            f'result.award_name={result.award_name!r}'
        )

    if policy.category is not None:
        if result.category is None:
            raise ValueError(
                'AwardPolicy category does not apply to this AwardResult: '
                f'policy.category={policy.category!r}, result.category=None'
            )
        if policy.category.strip().casefold() != result.category.strip().casefold():
            raise ValueError(
                'AwardPolicy category does not apply to this AwardResult: '
                f'policy.category={policy.category!r}, '
                f'result.category={result.category!r}'
            )

    if policy.start_year is not None:
        if result.award_year is None or result.award_year < policy.start_year:
            raise ValueError(
                'AwardPolicy year range does not apply to this AwardResult: '
                f'policy.start_year={policy.start_year!r}, '
                f'result.award_year={result.award_year!r}'
            )

    if policy.end_year is not None:
        if result.award_year is None or result.award_year > policy.end_year:
            raise ValueError(
                'AwardPolicy year range does not apply to this AwardResult: '
                f'policy.end_year={policy.end_year!r}, '
                f'result.award_year={result.award_year!r}'
            )


def _require_max_qualifying_rank(max_qualifying_rank) -> int:
    if isinstance(max_qualifying_rank, bool) or not isinstance(
        max_qualifying_rank, int
    ):
        raise ValueError(
            'max_qualifying_rank must be an int from '
            f'{MIN_MAX_QUALIFYING_RANK} through {MAX_MAX_QUALIFYING_RANK}'
        )
    if not (
        MIN_MAX_QUALIFYING_RANK
        <= max_qualifying_rank
        <= MAX_MAX_QUALIFYING_RANK
    ):
        raise ValueError(
            'max_qualifying_rank must be an int from '
            f'{MIN_MAX_QUALIFYING_RANK} through {MAX_MAX_QUALIFYING_RANK}'
        )
    return max_qualifying_rank


def qualify_award_result(
    result: AwardResult,
    policy: AwardPolicy | None = None,
    *,
    max_qualifying_rank: int = DEFAULT_MAX_QUALIFYING_RANK,
) -> QualificationResult:
    """Decide inclusion for one AwardResult without modifying it or the policy.

    Order: apply the supplied policy if any, then explicit rank, then Winner,
    then policy status lists, then REVIEW. An explicit rank qualifies at or
    below max_qualifying_rank and does not otherwise. Winner qualifies without
    inventing a place. Policy status lists do not override an explicit rank.
    """
    if policy is not None:
        _ensure_policy_applies(result, policy)
    cutoff = _require_max_qualifying_rank(max_qualifying_rank)

    if result.rank is not None:
        if result.rank <= cutoff:
            return QualificationResult(
                QualificationDecision.QUALIFIES,
                'Source establishes an ordinal rank within the configured '
                f'cutoff ({cutoff}).',
            )
        return QualificationResult(
            QualificationDecision.DOES_NOT_QUALIFY,
            'Source establishes an ordinal rank outside the configured '
            f'cutoff ({cutoff}).',
        )

    status = result.status.strip().casefold()
    if status in _WINNER_STATUSES:
        return QualificationResult(
            QualificationDecision.QUALIFIES,
            'Status indicates a win without an established ordinal rank.',
        )

    if policy is not None:
        if status in policy.qualifying_statuses:
            return QualificationResult(
                QualificationDecision.QUALIFIES,
                'Award-specific policy identifies this status as satisfying '
                'the inclusion rule.',
            )
        if status in policy.nonqualifying_statuses:
            return QualificationResult(
                QualificationDecision.DOES_NOT_QUALIFY,
                'Award-specific policy identifies this status as outside '
                'the inclusion rule.',
            )

    if status in _REVIEW_STATUSES:
        return QualificationResult(
            QualificationDecision.REVIEW,
            'Status meaning depends on the structure of the specific award.',
        )
    return QualificationResult(
        QualificationDecision.REVIEW,
        'Status is unrecognized and requires review.',
    )
