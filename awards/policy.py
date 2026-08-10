from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AwardPolicy:
    """Award-specific qualification policy; separate from factual AwardResult data."""

    award_name: str
    category: str | None = None
    start_year: int | None = None
    end_year: int | None = None
    qualifying_statuses: frozenset[str] = frozenset()
    nonqualifying_statuses: frozenset[str] = frozenset()
    notes: str | None = None

    def __post_init__(self) -> None:
        if not self.award_name or not self.award_name.strip():
            raise ValueError('award_name must be a non-empty string')

        if self.category is not None:
            category = self.category.strip()
            if not category:
                raise ValueError('category must be a non-empty string when set')
            object.__setattr__(self, 'category', category)

        if self.start_year is not None and self.start_year <= 0:
            raise ValueError('start_year must be greater than zero when set')
        if self.end_year is not None and self.end_year <= 0:
            raise ValueError('end_year must be greater than zero when set')
        if (
            self.start_year is not None
            and self.end_year is not None
            and self.start_year > self.end_year
        ):
            raise ValueError('start_year must be less than or equal to end_year')

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
