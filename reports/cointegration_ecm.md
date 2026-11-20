# Cointegration, ECM and pass-through

## Engle-Granger cointegration test
MacKinnon critical values. H0: no cointegration (the levels residual has a unit root).

| sample               | long-run equation                |   EG tau |   5% critical |   p-value | cointegrated at 5%?   |
|:---------------------|:---------------------------------|---------:|--------------:|----------:|:----------------------|
| full, 176 months     | petrol ~ crude INR/litre         |    -1.71 |         -3.37 |     0.674 | no                    |
| full, 176 months     | petrol ~ crude INR/litre + trend |    -1.68 |         -3.84 |     0.881 | no                    |
| full, 176 months     | petrol ~ Brent + USD/INR         |    -2.26 |         -3.79 |     0.612 | no                    |
| training, 152 months | petrol ~ crude INR/litre         |    -1.51 |         -3.38 |     0.757 | no                    |
| training, 152 months | petrol ~ crude INR/litre + trend |    -3.47 |         -3.84 |     0.107 | no                    |
| training, 152 months | petrol ~ Brent + USD/INR         |    -3.02 |         -3.8  |     0.233 | no                    |

Static long-run fit on all 176 months: petrol = 52.10 + 0.820 x crude_INR_per_litre (R^2 = 0.46).
Because the residual is not stationary, this line is **not** a reliable long-run equilibrium.

## Error-correction model (Engle-Granger two-step, training window)
Long-run step on the training window: petrol = 50.65 + 0.833 x crude_INR_per_litre.
Lag orders chosen by BIC: p = 2 lags of d_petrol, q = 1 lags of d_crude. HAC standard errors.

|               |    coef |   HAC s.e. |   p-value |
|:--------------|--------:|-----------:|----------:|
| const         |  0.1958 |     0.1554 |    0.2078 |
| ect_lag1      |  0.0044 |     0.0202 |    0.8262 |
| d_petrol_lag1 |  0.1568 |     0.0691 |    0.0233 |
| d_petrol_lag2 | -0.2315 |     0.1029 |    0.0244 |
| d_crude_lag1  |  0.346  |     0.0632 |    0      |

Error-correction coefficient alpha = 0.0044 (p = 0.826).
Alpha is not significantly negative, so there is no measurable pull back to the long-run line (consistent with the Engle-Granger result).

## Short-run pass-through on changes, by pricing regime
Rupees of pump-price change per 1 rupee change in crude cost per litre, summed over months t, t-1, t-2.

|                                    | months             |   n |   cum_passthrough |    se |   p_value |    r2 |
|:-----------------------------------|:-------------------|----:|------------------:|------:|----------:|------:|
| whole window                       | 2012-06 to 2026-10 | 173 |             0.225 | 0.082 |    0.006  | 0.119 |
| market-linked (Mar-2012..Apr-2022) | 2012-06 to 2022-04 | 119 |             0.517 | 0.131 |    0.0001 | 0.414 |
| administered (May-2022..Oct-2026)  | 2022-05 to 2026-10 |  54 |            -0.009 | 0.054 |    0.8708 | 0.232 |

## Rockets and feathers (market-linked months)
Pass-through of crude increases = 0.778, of decreases = 0.546
(test of equality: p = 0.485, n = 120).
