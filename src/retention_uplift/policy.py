"""Outcome-free policy construction and paired held-out IPW evaluation."""

import numpy as np

from retention_uplift.modelling_data import hash_keys

FRACTIONS = (0.05, 0.10, 0.20, 0.30, 0.50)


def ranking(ids, scores, seed=20261022):
    scores = np.asarray(scores)
    if scores.shape != (len(ids),) or not np.isfinite(scores).all():
        raise ValueError("Need one finite score per customer")
    if len(set(ids)) != len(ids):
        raise ValueError("Unique customer IDs required")
    return np.lexsort((hash_keys(ids, seed, "policy-tie"), -scores))


def make_policies(ids, risk, uplift, fractions=FRACTIONS, seed=20261022):
    """All comparators receive the same actual budget, capped at positive uplift count."""
    orders = {
        "random": np.argsort(hash_keys(ids, seed, "random-policy")),
        "churn": ranking(ids, risk, seed),
        "uplift": ranking(ids, uplift, seed),
    }
    policies = {}
    for fraction in fractions:
        if not 0 <= fraction <= 1:
            raise ValueError("Outreach fraction must be in [0,1]")
        k = min(int(np.floor(fraction * len(ids))), int(np.sum(np.asarray(uplift) > 0)))
        for name, order in orders.items():
            mask = np.zeros(len(ids))
            mask[order[:k]] = 1
            policies[f"{name}@{fraction:g}"] = mask
    policies["no_offer"] = np.zeros(len(ids))
    return policies


def ipw_signal(treatment, outcome, propensity):
    t, y, e = map(np.asarray, (treatment, outcome, propensity))
    if t.ndim != 1 or t.shape != y.shape or t.shape != e.shape or not len(t):
        raise ValueError("Mismatched observation vectors")
    if not np.isin(t, [0, 1]).all() or not np.isin(y, [0, 1]).all():
        raise ValueError("Binary observations required")
    if not np.isfinite(e).all() or not ((e > 0) & (e < 1)).all():
        raise ValueError("Invalid propensity")
    return t * y / e - (1 - t) * y / (1 - e)


def bootstrap_means(contributions, replications=1000, seed=20261023):
    """Paired customer resampling, conditional on fitted rules and fixed test allocations.

    No refitting or reranking in bootstrap. One index vector is shared across all columns.
    Includes test sampling/assignment variation, not model-training uncertainty.
    """
    values = np.asarray(contributions, dtype=float)
    if values.ndim != 2 or len(values) < 2 or not np.isfinite(values).all() or replications < 100:
        raise ValueError("Need finite customer contributions and >=100 bootstrap replications")
    rng = np.random.default_rng(seed)
    samples = np.empty((replications, values.shape[1]))
    for b in range(replications):
        samples[b] = values[rng.integers(0, len(values), len(values))].mean(axis=0)
    return samples


def summarize(values, samples):
    return {
        "estimate": float(np.mean(values)),
        "ci95": np.quantile(samples, [0.025, 0.975]).tolist(),
    }


def evaluate_policies(data, policies, replications=1000, seed=20261023):
    z = ipw_signal(data.treatment, data.outcome, data.propensity)
    names = list(policies)
    for mask in policies.values():
        if mask.shape != z.shape or not np.isin(mask, [0, 1]).all():
            raise ValueError("Policy must contain one binary decision per customer")
    values = np.column_stack([z, *[policies[k] * z for k in names]])
    boot = bootstrap_means(values, replications, seed)
    results = {"ate": summarize(values[:, 0], boot[:, 0]), "policies": {}, "paired_differences": {}}
    for i, name in enumerate(names, 1):
        results["policies"][name] = {
            **summarize(values[:, i], boot[:, i]),
            "targeted": int(policies[name].sum()),
            "actual_fraction": float(policies[name].mean()),
        }
    for name in names:
        if name.startswith("uplift@"):
            for comparator in ("random", "churn"):
                other = name.replace("uplift", comparator)
                a, b = names.index(name) + 1, names.index(other) + 1
                results["paired_differences"][f"{name} - {other}"] = summarize(
                    values[:, a] - values[:, b], boot[:, a] - boot[:, b]
                )
    return results


def gain_curve(ids, scores, z):
    """G(q)=sum of IPW effects in top q / total N; Qini area above q*G(1)."""
    order = ranking(ids, scores)
    gains = np.r_[0, np.cumsum(z[order]) / len(z)]
    fraction = np.linspace(0, 1, len(z) + 1)
    area = float(np.trapezoid(gains - fraction * gains[-1], fraction))
    points = np.unique(np.linspace(0, len(z), min(101, len(z) + 1)).astype(int))
    return {
        "fraction": fraction[points].tolist(),
        "gain": gains[points].tolist(),
        "qini_area": area,
    }
