"""Exactly optimal positive-net selection for uniform costs; guarded comparators."""

import math
from decimal import Decimal

import numpy as np

from retention_uplift.economics import net_scores
from retention_uplift.modelling_data import hash_keys
from retention_uplift.policy import ranking


def build_policies(ids, risk, uplift, values, cost, budget, capacity, seed=20261105):
    net = net_scores(uplift, values, cost)
    if not math.isfinite(budget) or budget < 0 or type(capacity) is not int or capacity < 0:
        raise ValueError("Invalid budget or integer contact capacity")
    orders = {
        "no_offer": np.array([], dtype=int),
        "random": np.argsort(hash_keys(ids, seed, "financial-random")),
        "churn": ranking(ids, risk, seed),
        "uplift": ranking(ids, uplift, seed),
        "profit": ranking(ids, net, seed),
    }
    if len(net) != len(ids) or not len(ids):
        raise ValueError("Nonempty aligned customer vectors required")
    money_cost, money_budget = Decimal(str(cost)), Decimal(str(budget))
    limit = min(capacity, len(ids), int(money_budget // money_cost) if cost else len(ids))
    policies, planning = {}, {}
    for name, order in orders.items():
        eligible = order[net[order] > 0]
        mask = np.zeros(len(ids), dtype=bool)
        mask[eligible[:limit]] = True
        spend = float(int(mask.sum()) * money_cost)
        policies[name] = mask
        planning[name] = {
            "selected": int(mask.sum()),
            "predicted_incremental_retained": float(np.sum(np.asarray(uplift)[mask])),
            "predicted_gross_gbp": float(np.sum((np.asarray(uplift) * values)[mask])),
            "spend_gbp": spend,
            "predicted_net_gbp": float(net[mask].sum()),
            "unspent_gbp": float(budget - spend),
            "capacity_used": int(mask.sum()),
            "capacity_unused": capacity - int(mask.sum()),
            "excluded_nonpositive_net": int((net <= 0).sum()),
            "excluded_limit_or_no_offer": int(((net > 0) & ~mask).sum()),
        }
    return policies, planning
