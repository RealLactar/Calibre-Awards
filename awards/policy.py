from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AwardPolicy:
    """Award-specific qualification policy; separate from factual AwardResult data."""

    award_name: str
    qualifying_statuses: frozenset[str] = frozenset()
    nonqualifying_statuses: frozenset[str] = frozenset()
    notes: str | None = None

    def __post_init__(self) -> None:
        if not self.award_name or not self.award_name.strip():
            raise ValueError('award_name must be a non-empty string')

        qualifying = frozenset(
            status.strip().casefold() for status in self.qualifying_statuses
        )
        nonqualifying = frozenset(
            status.strip().casefold() for status in self.nonqualifying_statuses
        )

        if '' in qualifying:
            raise ValueError(
                'qualifying_statuses must not contain empty or whitespace-only values'
            )
        if '' in nonqualifying:
            raise ValueError(
                'nonqualifying_statuses must not contain empty or whitespace-only values'
            )

        overlap = qualifying & nonqualifying
        if overlap:
            raise ValueError(
                'status values must not appear in both qualifying_statuses and '
                f'nonqualifying_statuses: {sorted(overlap)}'
            )

        object.__setattr__(self, 'qualifying_statuses', qualifying)
        object.__setattr__(self, 'nonqualifying_statuses', nonqualifying)
