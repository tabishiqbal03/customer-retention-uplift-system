"""Validated, serializable experiment configuration."""

import math
import tomllib
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path


@dataclass(frozen=True)
class Mechanism:
    """Illustrative coefficients, not estimates from real financial customers."""

    baseline_intercept: float = -0.8
    engagement_weight: float = 2.3
    trend_weight: float = 1.0
    savings_weight: float = 0.25
    latent_noise: float = 0.6
    benefit_strength: float = 1.8
    harm_strength: float = 1.4
    engagement_noise: float = 0.22
    trend_noise: float = 0.28
    preference_noise: float = 0.22
    monthly_rate: float = 7.0
    max_monthly_transactions: int = 60
    mean_spend_gbp: float = 35.0
    spend_log_sigma: float = 0.85

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValueError(f"{name} must be finite numeric")
        for name in (
            "latent_noise",
            "benefit_strength",
            "harm_strength",
            "engagement_noise",
            "trend_noise",
            "preference_noise",
            "monthly_rate",
            "mean_spend_gbp",
            "spend_log_sigma",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be nonnegative")
        if self.monthly_rate <= 0 or self.mean_spend_gbp <= 0:
            raise ValueError("Rate and amount scale must be positive")
        if (
            type(self.max_monthly_transactions) is not int
            or not 1 <= self.max_monthly_transactions <= 500
        ):
            raise ValueError("max_monthly_transactions must be an integer in [1, 500]")


@dataclass(frozen=True)
class Config:
    customers: int = 1000
    seed: int = 20261019
    history_start: str = "2025-01-01"
    assignment_date: str = "2026-01-01"
    outcome_days: int = 30
    treatment_probability: float = 0.5
    partitions: int = 8
    master: str = "local[2]"
    mechanism: Mechanism = field(default_factory=Mechanism)

    def __post_init__(self) -> None:
        for key in ("customers", "seed", "outcome_days", "partitions"):
            if type(getattr(self, key)) is not int:
                raise ValueError(f"{key} must be an integer")
        if self.customers < 20 or self.partitions < 1 or self.outcome_days < 1:
            raise ValueError("Need >=20 customers, >=1 partition and >=1 outcome day")
        start, assignment = (
            date.fromisoformat(self.history_start),
            date.fromisoformat(self.assignment_date),
        )
        if start.day != 1 or assignment.day != 1:
            raise ValueError("History and assignment must begin on calendar-month boundaries")
        if self.months != 12:
            raise ValueError("Stage 1 requires exactly 12 calendar months of history")
        if not 0.05 <= self.treatment_probability <= 0.95:
            raise ValueError("treatment_probability must be in [0.05, 0.95]")
        if not self.master:
            raise ValueError("Spark master cannot be empty")

    @property
    def months(self) -> int:
        a, b = date.fromisoformat(self.history_start), date.fromisoformat(self.assignment_date)
        return (b.year - a.year) * 12 + b.month - a.month

    @property
    def cutoff(self) -> date:
        return date.fromisoformat(self.assignment_date) - timedelta(days=1)

    @property
    def outcome_end(self) -> date:
        return date.fromisoformat(self.assignment_date) + timedelta(days=self.outcome_days)

    @property
    def history_days(self) -> int:
        return (
            date.fromisoformat(self.assignment_date) - date.fromisoformat(self.history_start)
        ).days

    @classmethod
    def read(cls, path: str | Path) -> "Config":
        with Path(path).open("rb") as handle:
            values = tomllib.load(handle)
        values["mechanism"] = Mechanism(**values.get("mechanism", {}))
        return cls(**values)

    def as_dict(self) -> dict:
        return asdict(self)
