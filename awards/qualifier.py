from dataclasses import dataclass
from enum import Enum

from .model import AwardResult
from .policy import AwardPolicy

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


def qualify_award_result(
    result: AwardResult,
    policy: AwardPolicy | None = None,
) -> QualificationResult:
    """Decide inclusion for one AwardResult without modifying it or the policy."""
    if result.rank is not None:
        if 1 <= result.rank <= 5:
            return QualificationResult(
                QualificationDecision.QUALIFIES,
                'Source establishes an ordinal rank within the top five.',
            )
        if result.rank > 5:
            return QualificationResult(
                QualificationDecision.DOES_NOT_QUALIFY,
                'Source establishes an ordinal rank outside the top five.',
            )

    status = result.status.strip().casefold()
    if status in _WINNER_STATUSES:
        return QualificationResult(
            QualificationDecision.QUALIFIES,
            'Status indicates a win without an established ordinal rank.',
        )

    if policy is not None:
        policy_name = policy.award_name.strip().casefold()
        result_name = result.award_name.strip().casefold()
        if policy_name != result_name:
            raise ValueError(
                'AwardPolicy does not apply to this AwardResult: '
                f'policy.award_name={policy.award_name!r}, '
                f'result.award_name={result.award_name!r}'
            )
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
