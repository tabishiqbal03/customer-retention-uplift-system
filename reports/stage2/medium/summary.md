# Stage 2 measured results

Synthetic; N=10,000; held-out test n=2,000

Selected estimator: **s**, using validation observed transformed-outcome loss only.

Churn targeting ranks untreated churn risk; uplift targeting ranks predicted treatment benefit.

Control test ROC-AUC: 0.662771604231107; Brier: 0.22092939759666658.

| Model | Oracle MAE | Oracle RMSE | Observed Qini area |
|---|---:|---:|---:|
| constant | 0.103870 | 0.133767 | -0.001748 |
| t | 0.112189 | 0.143068 | 0.006539 |
| s | 0.098433 | 0.131143 | -0.007245 |

All policy estimates below are percentage points over the entire test population relative to no offer.

| Policy / requested fraction | Actual count | IPW pp | 95% CI pp | Oracle pp |
|---|---:|---:|---|---:|
| random@0.05 | 100 | 1.300 | [-0.300, 3.000] | 0.152 |
| churn@0.05 | 100 | -0.100 | [-1.002, 1.000] | -0.126 |
| uplift@0.05 | 100 | 0.600 | [-0.802, 2.000] | 0.486 |
| random@0.1 | 200 | 1.100 | [-1.000, 3.200] | 0.285 |
| churn@0.1 | 200 | -0.200 | [-1.800, 1.300] | -0.089 |
| uplift@0.1 | 200 | -0.400 | [-2.500, 1.700] | 0.676 |
| random@0.2 | 400 | -1.200 | [-4.100, 1.800] | 0.531 |
| churn@0.2 | 400 | -0.300 | [-2.700, 2.100] | 0.371 |
| uplift@0.2 | 400 | -2.100 | [-5.200, 1.000] | 0.965 |
| random@0.3 | 600 | -1.600 | [-5.200, 2.000] | 0.642 |
| churn@0.3 | 600 | 1.000 | [-2.200, 4.000] | 0.999 |
| uplift@0.3 | 600 | -2.100 | [-5.900, 1.700] | 1.131 |
| random@0.5 | 1000 | -1.400 | [-5.900, 3.205] | 1.092 |
| churn@0.5 | 1000 | -0.500 | [-4.800, 3.800] | 1.854 |
| uplift@0.5 | 1000 | -2.800 | [-7.600, 2.000] | 1.825 |
| no_offer | 0 | 0.000 | [0.000, 0.000] | 0.000 |

Paired differences (uplift minus comparator), pointwise 95% bootstrap intervals:

- uplift@0.05 - random@0.05: -0.700 pp [-2.902, 1.300].
- uplift@0.05 - churn@0.05: 0.700 pp [-1.100, 2.300].
- uplift@0.1 - random@0.1: -1.500 pp [-4.200, 1.200].
- uplift@0.1 - churn@0.1: -0.200 pp [-2.700, 2.302].
- uplift@0.2 - random@0.2: -0.900 pp [-4.600, 2.702].
- uplift@0.2 - churn@0.2: -1.800 pp [-5.500, 1.902].
- uplift@0.3 - random@0.3: -0.500 pp [-4.700, 3.600].
- uplift@0.3 - churn@0.3: -3.100 pp [-7.000, 1.200].
- uplift@0.5 - random@0.5: -1.400 pp [-6.002, 2.902].
- uplift@0.5 - churn@0.5: -2.300 pp [-5.800, 1.400].

Intervals condition on fitted models and fixed test allocations; no training uncertainty or multiplicity correction. Test customers come from the same synthetic experiment. Oracle error includes inaccessible latent heterogeneity. No real retention improvement, profit, ROI or production validation has been demonstrated. Stage 3 is not implemented.
