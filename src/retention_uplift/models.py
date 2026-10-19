"""Training and validation interfaces accept observations only, never oracle labels."""

from dataclasses import dataclass

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from retention_uplift.modelling_data import Observations


def effect_signal(data):
    return data.treatment * data.outcome / data.propensity - (
        (1 - data.treatment) * data.outcome / (1 - data.propensity)
    )


@dataclass
class UpliftModel:
    kind: str
    leaves: int = 7
    seed: int = 20261021
    iterations: int = 100

    def fit(self, data: Observations):
        for arm in (0, 1):
            if len(np.unique(data.outcome[data.treatment == arm])) != 2:
                raise ValueError("Training requires both outcomes in each arm")
        if self.kind == "constant":
            self.effect_ = float(effect_signal(data).mean())
        elif self.kind in ("t", "s"):

            def new_model():
                return HistGradientBoostingClassifier(
                    max_leaf_nodes=self.leaves,
                    max_iter=self.iterations,
                    min_samples_leaf=40,
                    l2_regularization=10,
                    learning_rate=0.05,
                    early_stopping=False,
                    random_state=self.seed,
                )

            with threadpool_limits(limits=2):
                if self.kind == "t":
                    self.arms_ = [
                        new_model().fit(
                            data.x[data.treatment == a], data.outcome[data.treatment == a]
                        )
                        for a in (0, 1)
                    ]
                else:
                    self.model_ = new_model().fit(
                        np.column_stack((data.x, data.treatment)), data.outcome
                    )
        else:
            raise ValueError("Unknown uplift learner")
        return self

    def potential_outcomes(self, x):
        with threadpool_limits(limits=2):
            if self.kind == "t":
                return tuple(m.predict_proba(x)[:, 1] for m in self.arms_)
            if self.kind == "s":
                return tuple(
                    self.model_.predict_proba(np.column_stack((x, np.full(len(x), a))))[:, 1]
                    for a in (0, 1)
                )
        raise ValueError("Constant effect does not estimate potential outcome probabilities")

    def predict(self, x):
        if self.kind == "constant":
            return np.full(len(x), self.effect_)
        p0, p1 = self.potential_outcomes(x)
        return p1 - p0


def select_models(train: Observations, validation: Observations, seed=20261021, iterations=100):
    """No refit on validation; select each family and overall by observed transformed loss."""
    if set(train.ids) & set(validation.ids):
        raise ValueError("Training and validation customer sets must be disjoint")
    records, models = [], {}
    z = effect_signal(validation)
    for kind in ("constant", "t", "s"):
        candidates = []
        for leaves in (7,) if kind == "constant" else (7, 15):
            model = UpliftModel(kind, leaves, seed, iterations).fit(train)
            pred = model.predict(validation.x)
            # Subtract z^2: identical minimizer as transformed-outcome MSE, less noise in display.
            loss = float(np.mean(pred**2 - 2 * pred * z))
            record = {"model": kind, "leaves": leaves, "validation_effect_loss": loss}
            records.append(record)
            candidates.append((loss, leaves, model))
        models[kind] = min(candidates, key=lambda v: (v[0], v[1]))[2]
    selected = min(
        models,
        key=lambda k: (
            float(
                np.mean(
                    models[k].predict(validation.x) ** 2 - 2 * models[k].predict(validation.x) * z
                )
            ),
            k,
        ),
    )
    control = train.treatment == 0
    vc = validation.treatment == 0
    risks = []
    for c in (0.1, 1.0):
        model = make_pipeline(
            StandardScaler(), LogisticRegression(C=c, max_iter=3000, random_state=seed)
        )
        with threadpool_limits(limits=2):
            model.fit(train.x[control], 1 - train.outcome[control])
        loss = float(
            brier_score_loss(
                1 - validation.outcome[vc], model.predict_proba(validation.x[vc])[:, 1]
            )
        )
        records.append({"model": "churn", "C": c, "validation_brier": loss})
        risks.append((loss, c, model))
    return models, min(risks, key=lambda v: (v[0], v[1]))[2], selected, records
