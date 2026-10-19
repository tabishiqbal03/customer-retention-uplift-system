"""Fixed-policy randomized financial evaluation with paired customer bootstrap."""

import numpy as np

from retention_uplift.economics import net_scores
from retention_uplift.policy import bootstrap_means, ipw_signal, summarize


def evaluate_financial(data, policies, values, cost, replications=1000, seed=20261104):
    z = ipw_signal(data.treatment, data.outcome, data.propensity)
    net_scores(z, values, cost)  # validates alignment, cost and values
    names = list(policies)
    for mask in policies.values():
        if np.shape(mask) != z.shape or not np.isin(mask, [0, 1]).all():
            raise ValueError("Aligned binary policy decisions required")
    retention = np.column_stack([policies[k] * z for k in names])
    money = np.column_stack([policies[k] * (values * z - cost) for k in names])
    n, k = len(z), len(names)
    contributions = np.column_stack((retention, money))
    boot = bootstrap_means(contributions, replications, seed)
    result = {"policies": {}, "paired_net_gbp": {}, "bootstrap": replications}
    for i, name in enumerate(names):
        result["policies"][name] = {
            "incremental_retained": summarize(retention[:, i] * n, boot[:, i] * n),
            "net_gbp": summarize(money[:, i] * n, boot[:, k + i] * n),
            "net_per_eligible_gbp": summarize(money[:, i], boot[:, k + i]),
        }
    a = names.index("profit")
    for b, name in enumerate(names):
        if name != "profit":
            result["paired_net_gbp"][f"profit - {name}"] = summarize(
                (money[:, a] - money[:, b]) * n,
                (boot[:, k + a] - boot[:, k + b]) * n,
            )
    return result
