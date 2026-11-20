# One-step-ahead forecast comparison (INR per litre)

Parameters frozen at the end of training; each month forecast from data up to the month before.
Negative 'ECM vs SARIMA' = ECM more accurate. DM = Diebold-Mariano test on squared errors.

| hold-out window                          | test months        | SARIMA order            | ECM lags (p,q)   |   RMSE no-change |   RMSE SARIMA |   RMSE ECM |   ECM vs SARIMA (%) |   DM p-value |   months price moved |
|:-----------------------------------------|:-------------------|:------------------------|:-----------------|-----------------:|--------------:|-----------:|--------------------:|-------------:|---------------------:|
| primary: last 24 months                  | 2024-11 to 2026-10 | (0, 1, 2)x(0, 0, 0, 12) | (2, 1)           |            1.087 |         0.977 |      2.377 |             143.345 |        0.068 |                    3 |
| robustness: last 24 market-linked months | 2020-05 to 2022-04 | (2, 1, 1)x(0, 0, 0, 12) | (1, 1)           |            3.47  |         3.403 |      3.688 |               8.357 |        0.447 |                   23 |
