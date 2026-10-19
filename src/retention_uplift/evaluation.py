"""Final evaluation only: oracle data cannot reach model training or selection."""

import numpy as np
from scipy.stats import spearmanr
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    roc_auc_score,
)

from retention_uplift.modelling_data import read_frame
from retention_uplift.policy import ranking


def load_test_truth(spark, root, ids):
    frame = read_frame(spark, root, "truth").select("customer_id", "p0", "p1", "tau")
    keys = spark.createDataFrame([(str(i),) for i in ids], "customer_id string")
    rows = frame.join(keys, "customer_id").collect()
    lookup = {r.customer_id: r for r in rows}
    if len(rows) != len(ids) or set(lookup) != set(ids):
        raise ValueError("Oracle test keys must match exactly")
    truth = {k: np.array([lookup[i][k] for i in ids]) for k in ("p0", "p1", "tau")}
    if any(not np.isfinite(v).all() for v in truth.values()):
        raise ValueError("Invalid oracle values")
    if not np.allclose(truth["tau"], truth["p1"] - truth["p0"], atol=1e-12):
        raise ValueError("Invalid oracle effect")
    return truth


def oracle_metrics(ids, prediction, tau):
    groups = np.array_split(ranking(ids, prediction), min(10, len(ids)))
    return {
        "mae": float(np.mean(abs(prediction - tau))),
        "rmse": float(np.sqrt(np.mean((prediction - tau) ** 2))),
        "mean_predicted": float(prediction.mean()),
        "mean_true": float(tau.mean()),
        "spearman": float(spearmanr(prediction, tau).statistic)
        if np.ptp(prediction) and np.ptp(tau)
        else None,
        "rank_groups": [
            {"n": len(g), "predicted": float(prediction[g].mean()), "true": float(tau[g].mean())}
            for g in groups
        ],
    }


def churn_metrics(data, risk):
    control = data.treatment == 0
    y, p = 1 - data.outcome[control], risk[control]
    groups = np.array_split(np.argsort(p), min(10, len(p)))
    return {
        "n_control": len(y),
        "churn_prevalence": float(y.mean()),
        "roc_auc": float(roc_auc_score(y, p)) if len(np.unique(y)) == 2 else None,
        "average_precision": float(average_precision_score(y, p)) if y.sum() else None,
        "brier": float(brier_score_loss(y, p)),
        "threshold": 0.5,
        "confusion_matrix": confusion_matrix(y, p >= 0.5, labels=[0, 1]).tolist(),
        "calibration": [
            {"n": len(g), "predicted": float(p[g].mean()), "observed": float(y[g].mean())}
            for g in groups
        ],
    }
