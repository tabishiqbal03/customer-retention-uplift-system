"""Explicit illustrative GBP economics; only pre-treatment allowlisted inputs."""

import math
import tomllib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from retention_uplift.features import MODEL_FEATURES


@dataclass(frozen=True)
class Scenario:
    name: str
    value: float
    offer_cost: float
    contact_cost: float
    value_mode: str = "fixed"

    def __post_init__(self):
        if not self.name or self.value_mode not in ("fixed", "usage"):
            raise ValueError("Invalid scenario name or value mode")
        for v in (self.value, self.offer_cost, self.contact_cost):
            if (
                isinstance(v, bool)
                or not isinstance(v, (float, int))
                or not math.isfinite(v)
                or v < 0
            ):
                raise ValueError("Money must be finite and nonnegative")

    @property
    def cost(self):
        return self.offer_cost + self.contact_cost


def customer_values(x, scenario):
    x = np.asarray(x, dtype=float)
    if x.ndim != 2 or x.shape[1] != len(MODEL_FEATURES) or not np.isfinite(x).all():
        raise ValueError("Expected finite allowlisted pre-treatment features")
    if scenario.value_mode == "fixed":
        return np.full(len(x), scenario.value)
    # Hypothetical contribution multiplier [.5,1.5]; no spending-to-profit conversion.
    active = x[:, MODEL_FEATURES.index("active_months")]
    products = x[:, MODEL_FEATURES.index("products_used")]
    if ((active < 0) | (active > 12) | (products < 0) | (products > 3)).any():
        raise ValueError("Invalid historical usage")
    return scenario.value * (0.5 + 0.5 * active / 12 + 0.5 * products / 3)


def net_scores(uplift, values, cost):
    u, v = np.asarray(uplift, dtype=float), np.asarray(values, dtype=float)
    if u.ndim != 1 or u.shape != v.shape or not np.isfinite(u).all() or not np.isfinite(v).all():
        raise ValueError("Finite aligned vectors required")
    if (v < 0).any() or np.ndim(cost) != 0 or not math.isfinite(cost) or cost < 0:
        raise ValueError("Nonnegative values and uniform scalar cost required")
    return u * v - cost


def break_even(value, cost):
    net_scores(np.zeros(1), np.array([value]), cost)
    # At zero value no strictly profitable offer is possible, including free offers.
    return cost / value if value > 0 else None


def read_economics(path):
    with Path(path).open("rb") as f:
        config = tomllib.load(f)
    scenarios = [Scenario(**s) for s in config["scenarios"]]
    if len({s.name for s in scenarios}) != len(scenarios) or config["primary"] not in {
        s.name for s in scenarios
    }:
        raise ValueError("Unique scenarios and a valid primary required")
    if type(config["bootstrap"]) is not int or config["bootstrap"] < 1000:
        raise ValueError("Final evaluation requires >=1000 bootstrap replicates")
    return config, scenarios
