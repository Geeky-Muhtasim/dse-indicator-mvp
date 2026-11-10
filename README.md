# DSE Signal

Explainable **Buy / Hold / Avoid** signals for Dhaka Stock Exchange equities. The signals
update automatically after every trading session, and the model judges itself on purged
walk-forward, out-of-sample results with trading costs included.

- **Frontend:** Next.js 15 (App Router), Foundry finance theme, English or bilingual (Bangla + English)
- **Backend:** FastAPI as a Vercel Python function, with live scoring and pure-Python TreeSHAP
- **Pipeline:** pandas + LightGBM, run by GitHub Actions on a schedule
- **Data:** DSE end-of-day prices (history from an adjusted StockNow export, daily updates from dsebd.org via [bdshare](https://pypi.org/project/bdshare/))

## How it fits together

```
           GitHub Actions (cron)                          Vercel
  ┌────────────────────────────────────┐      ┌───────────────────────────────┐
  │ daily 15:30 & 17:30 Dhaka, Sun-Thu │      │ Next.js pages (/, /stock/…,   │
  │   fetch new DSE sessions (bdshare) │      │   /evidence, /regime, /method)│
  │   back-adjust corporate actions    │ push │            │ fetch /api/*      │
  │   rebuild features, score, explain ├─────►│ FastAPI  api/index.py         │
  │   write data/app/*.json            │      │   reads data/app/*.json       │
  │ weekly Fri: walk-forward retrain   │      │   POST /api/score: live       │
  │   promote only if OOS rank IC > 0  │      │   TreeSHAP over exported trees│
  └────────────────────────────────────┘      └───────────────────────────────┘
```

Every data commit triggers a Vercel redeploy, so the site always shows the latest session.

## Deploy (one time)

1. **Vercel:** New Project → Import `Geeky-Muhtasim/dse-indicator-mvp`. The framework is
   detected as Next.js, and `api/index.py` plus the root `requirements.txt` become the Python function.
   No environment variables are needed. Click Deploy.
2. **GitHub Actions:** the workflows commit data back to the repo. If a run fails on `git push`,
   open Settings → Actions → General → Workflow permissions and select "Read and write permissions".
3. Optional: run **Actions → Daily DSE update → Run workflow** once to pull the sessions since the
   last stored date immediately instead of waiting for the next schedule.

## Run locally

```bash
npm install
pip install -r pipeline/requirements.txt
npm run dev            # Next.js on :3000 and FastAPI on :8000 together
```

On Windows PowerShell, create a venv first (`python -m venv .venv; .venv\Scripts\Activate.ps1`).

Pipeline commands:

```bash
python pipeline/cli.py update     # fetch new DSE sessions, rescore, write data/app
python pipeline/cli.py score      # rescore the latest stored session
python pipeline/cli.py retrain    # walk-forward validation, retrain, HTML report in reports/
python pipeline/cli.py backfill   # rebuild ~2 years of history from DSE, then retrain
python pipeline/cli.py readjust   # find missed bonus/rights adjustments, then retrain
python -m pytest -q               # leakage, alignment, TreeSHAP and API tests
```

API docs are served at `/api/docs`.

## API

| Route | What it returns |
|---|---|
| `GET /api/health` | Status, data date, model version |
| `GET /api/meta` | Counts, regime, thresholds, model info |
| `GET /api/signals?signal=BUY&q=BANK` | Ranked signals with precomputed drivers |
| `GET /api/stock/{symbol}` | Price history, features and a live SHAP explanation |
| `POST /api/score` | `{symbol, overrides}` → what-if score, explanation and placement |
| `GET /api/metrics` | Walk-forward evidence: IC, quintiles, calibration, backtest, folds |
| `GET /api/regime` | Market breadth and regime history |

## Method in brief

- **Universe:** ordinary shares only, without the least liquid 20% by 20-day median turnover (recomputed daily).
- **Features:** 19 point-in-time features in six families: momentum, trend, volatility, volume, relative strength, market regime.
- **Target:** return from the next open to the close 5 sessions later, minus the equal-weight market, ranked across stocks.
- **Models:** an unfitted five-factor scorecard as the baseline; LightGBM regression on the rank target.
- **Validation:** expanding walk-forward with purging; backtest with next-open entry, limit-lock fills skipped, 0.90% round-trip cost.
- **Signals:** top 10% Buy (top 5% when risk-off), bottom 20% Avoid. The odds shown are the out-of-sample hit rate of the stock's score decile.
- **Explanations:** SHAP values that add up exactly to the score. The API recomputes them in pure Python, and a test checks them against LightGBM to within 1e-9.
- **Corporate actions:** DSE's archive does not adjust prices for bonus or rights issues, so adjustments are detected three ways: exact factors from the adjusted StockNow export where it overlaps; DSE's YCP when it differs from the stored close; and an ex-date rule (a session whose high is more than 11% below the previous close while still trading in a range, which circuit breakers rule out for normal trading), snapped to standard bonus ratios. Locked limit-down days are left alone. Bonuses of 10% or less outside the StockNow window can be missed. Every adjustment is logged in `data/history/corporate_actions.csv`; `python pipeline/cli.py readjust` re-checks the stored history.
- **History depth:** DSE publishes about two years of day-end data, so the backfill starts at 11 Nov 2024. Older history needs a vendor export.

## Repository layout

```
app/, components/, lib/   Next.js frontend
api/index.py              FastAPI backend (Vercel Python function)
pipeline/                 dse_signal package and CLI
data/history/eod.csv      Adjusted EOD history (grows daily)
data/model/               Saved LightGBM model, validation metrics
data/app/                 JSON the API serves (written by the pipeline)
reports/report.html       Static research report from the last retrain
tests/                    pytest suite
.github/workflows/        daily update, weekly retrain, CI
```

## Limits

- Two years of history and under one year of out-of-sample testing: the edge is statistically clear in ranking (IC t-stat above 6) but thin after costs.
- Cost assumptions are estimates; edit `pipeline/dse_signal/config.py`.
- Prices are public DSE end-of-day data used for research. Live intraday data is licensed and not used. For a commercial product, switch to a licensed data vendor.
- Not investment advice.
