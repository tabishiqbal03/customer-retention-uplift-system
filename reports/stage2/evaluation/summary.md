# Stage 2 measured results

Synthetic; N=25,000; held-out test n=5,001

Selected estimator: **t**, using validation observed transformed-outcome loss only.

Churn targeting ranks untreated churn risk; uplift targeting ranks predicted treatment benefit.

Control test ROC-AUC: 0.6823429519995232; Brier: 0.21818937593161492.

| Model | Oracle MAE | Oracle RMSE | Observed Qini area |
|---|---:|---:|---:|
| constant | 0.105570 | 0.134480 | -0.000687 |
| t | 0.102323 | 0.133085 | 0.013813 |
| s | 0.095338 | 0.126930 | 0.016505 |

All policy estimates below are percentage points over the entire test population relative to no offer.

| Policy / requested fraction | Actual count | IPW pp | 95% CI pp | Oracle pp |
|---|---:|---:|---|---:|
| random@0.05 | 250 | 0.640 | [-0.320, 1.601] | 0.093 |
| churn@0.05 | 250 | -0.080 | [-0.800, 0.641] | -0.113 |
| uplift@0.05 | 250 | 0.480 | [-0.401, 1.361] | 0.502 |
| random@0.1 | 500 | 0.520 | [-0.800, 1.920] | 0.150 |
| churn@0.1 | 500 | 0.000 | [-0.960, 1.000] | -0.113 |
| uplift@0.1 | 500 | 1.520 | [0.240, 2.720] | 0.730 |
| random@0.2 | 1000 | -0.680 | [-2.599, 1.200] | 0.285 |
| churn@0.2 | 1000 | 0.160 | [-1.201, 1.640] | 0.312 |
| uplift@0.2 | 1000 | 2.559 | [0.719, 4.319] | 1.206 |
| random@0.3 | 1500 | 0.200 | [-2.280, 2.519] | 0.425 |
| churn@0.3 | 1500 | 1.840 | [-0.161, 3.759] | 0.893 |
| uplift@0.3 | 1500 | 2.280 | [-0.081, 4.479] | 1.471 |
| random@0.5 | 2500 | 0.360 | [-2.560, 3.399] | 0.758 |
| churn@0.5 | 2500 | 2.200 | [-0.720, 4.759] | 1.867 |
| uplift@0.5 | 2500 | 1.880 | [-1.002, 4.879] | 1.850 |
| no_offer | 0 | 0.000 | [0.000, 0.000] | 0.000 |

Paired differences (uplift minus comparator), pointwise 95% bootstrap intervals:

- uplift@0.05 - random@0.05: -0.160 pp [-1.361, 1.081].
- uplift@0.05 - churn@0.05: 0.560 pp [-0.680, 1.680].
- uplift@0.1 - random@0.1: 1.000 pp [-0.800, 2.599].
- uplift@0.1 - churn@0.1: 1.520 pp [-0.160, 2.999].
- uplift@0.2 - random@0.2: 3.239 pp [1.080, 5.520].
- uplift@0.2 - churn@0.2: 2.400 pp [0.320, 4.480].
- uplift@0.3 - random@0.3: 2.080 pp [-0.601, 4.720].
- uplift@0.3 - churn@0.3: 0.440 pp [-1.760, 2.522].
- uplift@0.5 - random@0.5: 1.520 pp [-1.561, 4.639].
- uplift@0.5 - churn@0.5: -0.320 pp [-2.519, 1.800].

Intervals condition on fitted models and fixed test allocations; no training uncertainty or multiplicity correction. Test customers come from the same synthetic experiment. Oracle error includes inaccessible latent heterogeneity. No real retention improvement, profit, ROI or production validation has been demonstrated. Stage 3 is not implemented.
