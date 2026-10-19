"""Normal approximation to a two-sided pooled two-proportion score test."""

import math

import numpy as np
from scipy.stats import norm


def sample_size(p0, mde=None, alpha=0.05, power=0.8, ratio=1.0, p1=None):
    if (mde is None) == (p1 is None):
        raise ValueError("Specify exactly one of MDE or treated probability")
    p1 = p0 + mde if p1 is None else p1
    if not all(math.isfinite(x) for x in (p0, p1, alpha, power, ratio)):
        raise ValueError("Finite inputs required")
    if not (0 < p0 < p1 < 1 and 0 < alpha < power < 1 and ratio > 0):
        raise ValueError("Require 0<p0<p1<1, 0<alpha<power<1 and positive ratio")
    # ratio = n_treatment / n_control. Variances scaled by n_control.
    pooled = (p0 + ratio * p1) / (1 + ratio)
    v0 = pooled * (1 - pooled) * (1 + 1 / ratio)
    v1 = p0 * (1 - p0) + p1 * (1 - p1) / ratio
    raw = ((norm.isf(alpha / 2) * math.sqrt(v0) + norm.ppf(power) * math.sqrt(v1)) / (p1 - p0)) ** 2
    control = math.ceil(raw)
    treatment = math.ceil(ratio * control)
    return {
        "control": control,
        "treatment": treatment,
        "total": control + treatment,
        "p0": p0,
        "p1": p1,
        "mde_pp": 100 * (p1 - p0),
        "alpha": alpha,
        "target_power": power,
        "treatment_control_ratio": ratio,
        "raw_control": raw,
    }


def monte_carlo(plan, repetitions=20000, seed=20261106):
    if type(repetitions) is not int or repetitions < 100:
        raise ValueError("Need >=100 simulation repetitions")
    rng = np.random.default_rng(seed)
    nc, nt = plan["control"], plan["treatment"]
    results = {}
    for label, p1 in (("power", plan["p1"]), ("type1", plan["p0"])):
        c = rng.binomial(nc, plan["p0"], repetitions)
        t = rng.binomial(nt, p1, repetitions)
        pooled = (c + t) / (nc + nt)
        se = np.sqrt(pooled * (1 - pooled) * (1 / nc + 1 / nt))
        z = np.divide(t / nt - c / nc, se, out=np.zeros(repetitions), where=se > 0)
        rate = float(np.mean(abs(z) > norm.isf(plan["alpha"] / 2)))
        results[label] = {
            "estimate": rate,
            "monte_carlo_se": math.sqrt(rate * (1 - rate) / repetitions),
        }
    return {
        "repetitions": repetitions,
        "seed": seed,
        "test": "two-sided pooled z, no continuity correction",
        **results,
    }
