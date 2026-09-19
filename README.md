# Kalman TDEE

Estimating daily energy expenditure (TDEE) from a bathroom scale and a food log, **with confidence intervals
that actually mean what they say**.

I built this for my own nutrition tracking. The first version did what most apps and spreadsheets do:
regress smoothed weight on time and back out TDEE = mean intake − slope × 7700. Its "95%" intervals turned
out to be badly overconfident. This repository replaces it with a small state-space model, and uses synthetic
users with a known TDEE to show how far off the naive intervals are.

![walkthrough](figures/walkthrough.png)

## The problem

Scale weight = tissue + water + noise. Water (salt, carbs, digestion, travel) moves ±1 kg and **persists for
several days**. A regression treats each reading as independent, so it thinks it has far more information than
it does; smoothing the weight first (an EMA) makes it much worse, because each smoothed point re-uses the
previous ones.

## The model

Daily state `x = [W, T, H]`:

| state | meaning | dynamics |
|---|---|---|
| `W` | tissue mass (kg) | `W' = W + (I − T) / 7700` — moves only with the energy balance |
| `T` | TDEE (kcal/day) | slow random walk |
| `H` | water / gut content (kg) | AR(1), mean-reverting |

Observation: `y = W + H + v` (morning-equivalent reading). `I` is the *logged* intake, so `T` is expressed in
"logging units": a systematic logging bias is absorbed into `T`, which is what you want when the output is a
calorie target compared against logged intake.

- Kalman filter for the causal estimate, Rauch-Tung-Striebel smoother for the tissue-mass curve.
- Missing weigh-ins / unlogged days handled natively (prediction only; an unlogged day assumes I ≈ T ± 700).
- Innovations beyond 2.5 sd are down-weighted (travel water spikes).
- `regime_breaks`: re-inflate TDEE uncertainty at a known lifestyle change.
- Noise parameters (`phi`, `sigma_h`, `sigma_v`) fitted by maximum likelihood on ~3 months of my own
  weigh-ins (`tdee.calibrate`). The data itself is not in this repo.

## Results on synthetic users

500 simulated users with a known TDEE, including water spikes and missing days the filter does not model
(`notebooks/02_ci_coverage.ipynb`). How often the true TDEE falls inside the reported 95% interval:

| days of data | Kalman (prior off by ±300) | Kalman (uninformative prior) | OLS, raw weight | OLS, EMA weight |
|---|---|---|---|---|
| 14 | 95% | 92% | 64% | 38% |
| 28 | 93% | 91% | 62% | 28% |
| 56 | 93% | 92% | 55% | 32% |
| 83 | 93% | 92% | 49% | 26% |

![coverage](figures/coverage.png)

What this does **not** show: with an uninformative prior, the Kalman *point* estimate is about as accurate
as OLS after a few weeks (RMSE ~90 kcal at 12 weeks for all methods). The gain is honest uncertainty, plus
better early estimates when a reasonable prior exists.

Robustness checks in the same notebook:
- **Misspecified noise** (real water noisier and more persistent than assumed): Kalman coverage drops to
  77–92%, against 26–32% for OLS on EMA.
- **Unannounced TDEE step (+300 kcal)**: with a slow random walk the filter lags, and coverage falls to ~35–42%
  after the step. Declaring the change (`regime_breaks`) restores ~91%.
- **Calibration** (`notebooks/03_noise_calibration.ipynb`): `phi` and `sigma_h` are recovered well from 120
  days; `sigma_v` is poorly identified, and `sigma_t` (TDEE drift) tends to collapse to 0, so its default is a
  modelling choice rather than a fitted value.

## Limitations

- 7700 kcal/kg in both directions; the energy density of gained vs lost tissue actually differs.
- Gaussian model with a crude robust gate; heavy-tailed water events are handled approximately.
- The interval covers estimation noise, not a systematic logging bias (which is absorbed into `T` by design).

## Project structure

- `src/tdee/` — library: `model.py` (filter + smoother), `baselines.py` (OLS), `simulate.py`, `calibrate.py`
- `notebooks/` — 01 walkthrough on one user · 02 interval coverage · 03 noise calibration
- `tests/` — coverage and sanity tests
- `app/` — the personal tracker I use daily (NiceGUI, UI in French): food/weight/steps/training log, weekly
  check-in that freezes the calorie target, all weight/rate/TDEE figures from the same filter

## Getting started

```bash
git clone https://github.com/Alexandre-Reyob/kalman-tdee.git
cd kalman-tdee
pip install -r requirements.txt
pytest -q
jupyter notebook notebooks/
python app/main.py        # generates 70 days of demo data on first launch → http://localhost:8080
```

To use the app with your own data: `TRACKER_DATA=/path/to/folder python app/main.py`.

## About me

I'm Alexandre Boyer, a student at CentraleSupélec and ESSEC. I built this to answer a practical question
about my own training, and kept it because the statistics turned out to be the interesting part.

## License

MIT
