from dataclasses import replace
from datetime import date

import pytest

from retention_uplift.config import Config, Mechanism


@pytest.mark.parametrize(
    "kwargs",
    [
        {"customers": 0},
        {"customers": True},
        {"customers": 10.5},
        {"partitions": 0},
        {"outcome_days": 0},
        {"treatment_probability": 1.0},
        {"treatment_probability": float("nan")},
        {"history_start": "2025-01-02"},
        {"assignment_date": "2025-12-01"},
        {"assignment_date": "2027-01-01"},
        {"seed": "12"},
        {"master": ""},
    ],
)
def test_invalid_config(kwargs):
    with pytest.raises(ValueError):
        Config(**kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"monthly_rate": -1},
        {"monthly_rate": 0},
        {"mean_spend_gbp": 0},
        {"benefit_strength": float("inf")},
        {"latent_noise": -1},
        {"max_monthly_transactions": 0},
        {"max_monthly_transactions": 2.5},
    ],
)
def test_invalid_mechanism(kwargs):
    with pytest.raises(ValueError):
        Mechanism(**kwargs)


def test_config_profiles_and_dates():
    smoke, standard = Config.read("configs/smoke.toml"), Config.read("configs/standard.toml")
    assert smoke.customers == 1000 and standard.customers == 100000
    assert smoke.cutoff == date(2025, 12, 31)
    assert smoke.outcome_end == date(2026, 1, 31)
    assert smoke.history_days == 365
    assert (
        replace(smoke, history_start="2024-01-01", assignment_date="2025-01-01").history_days == 366
    )


def test_unknown_config_key_rejected(tmp_path):
    path = tmp_path / "bad.toml"
    path.write_text("custmers = 1000\n", encoding="utf-8")
    with pytest.raises(TypeError):
        Config.read(path)
