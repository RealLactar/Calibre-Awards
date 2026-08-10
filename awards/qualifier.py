from dataclasses import dataclass
from enum import Enum

from .model import AwardResult

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


def qualify_award_result(result: AwardResult) -> QualificationResult:
    """Decide inclusion for one AwardResult without modifying it."""
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
    if status in _REVIEW_STATUSES:
        return QualificationResult(
            QualificationDecision.REVIEW,
            'Status meaning depends on the structure of the specific award.',
        )
    return QualificationResult(
        QualificationDecision.REVIEW,
        'Status is unrecognized and requires review.',
    )
