"""Central configuration. Every assumption that affects results lives here."""
from dataclasses import dataclass, field


@dataclass
class Config:
    # Label horizon in trading days. Entry at next day's open, exit at close of day t+h.
    horizon: int = 5

    # Rows of history a stock needs before its features are trusted.
    warmup_days: int = 20

    # Universe: drop the least liquid fraction of equities by median 20-day turnover (Tk).
    liquidity_drop_quantile: float = 0.20

    # A daily move at or beyond this is treated as a likely circuit-breaker hit.
    limit_move_threshold: float = 0.095

    # Walk-forward validation.
    min_train_dates: int = 12          # label dates in the first training window
    test_block_dates: int = 5          # dates per out-of-sample block (= horizon by default)
    # With multi-year history: train on at least a year first, and widen the test blocks so
    # the walk-forward stays within max_folds refits (keeps CI runs to minutes).
    long_history_dates: int = 200
    long_min_train_dates: int = 240
    max_folds: int = 36

    # Costs, in basis points per side. DSE brokerage and levies are roughly 30 to 50 bps,
    # plus slippage. These are assumptions: edit them to match your broker.
    commission_bps_per_side: float = 35.0
    slippage_bps_per_side: float = 10.0

    # Signal buckets by cross-sectional score percentile.
    buy_top_pct: float = 0.10
    buy_top_pct_risk_off: float = 0.05
    avoid_bottom_pct: float = 0.20

    # Market regime: risk-off when fewer than this share of stocks sit above their 20-day MA
    # and the equal-weight market is down over 10 days.
    risk_off_breadth: float = 0.35

    seed: int = 7

    lgbm_params: dict = field(default_factory=lambda: dict(
        objective="regression",
        n_estimators=300,
        learning_rate=0.03,
        num_leaves=15,
        min_child_samples=80,
        subsample=0.8,
        subsample_freq=1,
        colsample_bytree=0.8,
        reg_lambda=2.0,
        verbose=-1,
    ))

    @property
    def round_trip_cost(self) -> float:
        return 2 * (self.commission_bps_per_side + self.slippage_bps_per_side) / 1e4
