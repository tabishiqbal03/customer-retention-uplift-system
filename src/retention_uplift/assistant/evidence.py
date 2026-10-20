"""Allowlisted, immutable projection of aggregate facts; no arbitrary file or path queries."""

import hashlib
import json
from pathlib import Path

from pydantic import ValidationError

from .contracts import AssistantError, Fact, Report

REPORT_PATH = Path(__file__).resolve().parents[3] / "reports/stage3/metrics.json"


class EvidenceStore:
    def __init__(self, path=REPORT_PATH):
        try:
            raw = Path(path).read_bytes()
            if len(raw) > 1_000_000:
                raise ValueError("Report too large")
            self.report = Report.model_validate(json.loads(raw))
        except (OSError, ValueError, ValidationError) as exc:
            raise AssistantError(
                "invalid_report",
                (
                    "Approved aggregate report missing or incompatible; restore the "
                    "reviewed Stage 3 artifact."
                ),
                503,
            ) from exc
        self.digest = hashlib.sha256(raw).hexdigest()
        self._facts = {}

        def add(path, value, units, category, label, scenario=None):
            self._facts[path] = Fact(
                reference=path,
                artifact="stage3-metrics-v1",
                artifact_sha256=self.digest,
                field_path=path,
                scenario=scenario,
                value=value,
                units=units,
                category=category,
                label=label,
            )

        econ = self.report.protocol.economics
        add(
            "protocol.economics.budget", econ.budget, "GBP", "assumption", "Maximum campaign budget"
        )
        add(
            "protocol.economics.maximum_contacts",
            econ.maximum_contacts,
            "customers",
            "assumption",
            "Maximum outreach capacity",
        )
        for name, s in self.report.scenarios.items():
            prefix = f"scenarios.{name}"
            for key in ("value", "offer_cost", "contact_cost"):
                add(
                    f"{prefix}.assumptions.{key}",
                    getattr(s.assumptions, key),
                    "GBP",
                    "assumption",
                    key.replace("_", " "),
                    name,
                )
            fields = [
                ("selected", "customers"),
                ("predicted_incremental_retained", "incremental_customers"),
                ("predicted_gross_gbp", "GBP"),
                ("spend_gbp", "GBP"),
                ("predicted_net_gbp", "GBP"),
                ("unspent_gbp", "GBP"),
            ]
            for policy, p in s.planning.items():
                for key, unit in fields:
                    add(
                        f"{prefix}.planning.{policy}.{key}",
                        getattr(p, key),
                        unit,
                        "prediction",
                        f"{policy}: {key.replace('_', ' ')}",
                        name,
                    )
            for policy, o in s.observed.policies.items():
                for key, unit in [
                    ("net_gbp", "GBP"),
                    ("incremental_retained", "incremental_customers"),
                ]:
                    v = getattr(o, key)
                    add(
                        f"{prefix}.observed.policies.{policy}.{key}.estimate",
                        v.estimate,
                        unit,
                        "observed_estimate",
                        f"{policy}: observed-outcome {key}",
                        name,
                    )
                    add(
                        f"{prefix}.observed.policies.{policy}.{key}.ci95",
                        v.ci95,
                        unit,
                        "interval",
                        f"{policy}: pointwise 95% interval for {key}",
                        name,
                    )
            for key, v in s.observed.paired_net_gbp.items():
                for part in ("estimate", "ci95"):
                    add(
                        f"{prefix}.observed.paired_net_gbp.{key}.{part}",
                        getattr(v, part),
                        "GBP",
                        "interval" if part == "ci95" else "observed_estimate",
                        f"Paired {key}: {part}",
                        name,
                    )
            add(
                f"{prefix}.recommendation",
                s.recommendation,
                "recommendation",
                "recommendation",
                "Saved recommendation",
                name,
            )
        for key, unit in [
            ("control", "customers"),
            ("treatment", "customers"),
            ("total", "customers"),
            ("p0", "probability"),
            ("p1", "probability"),
            ("mde_pp", "percentage_points"),
            ("alpha", "probability"),
            ("target_power", "probability"),
            ("treatment_control_ratio", "ratio"),
        ]:
            add(
                f"pilot.{key}",
                getattr(self.report.pilot, key),
                unit,
                "pilot_design",
                f"Pilot {key}",
            )

    def fact(self, reference):
        if reference not in self._facts:
            raise AssistantError(
                "unknown_evidence", "Reference is not an approved public evidence field.", 404
            )
        return self._facts[reference].model_copy(deep=True)

    def summary(self):
        s = self.report.scenarios["base"]
        return {
            "schema_version": 1,
            "synthetic_data": True,
            "illustrative_economics": True,
            "primary": "base",
            "recommendation": s.recommendation,
            "scenarios": list(self.report.scenarios),
            "artifact": "stage3-metrics-v1",
            "artifact_sha256": self.digest,
        }
