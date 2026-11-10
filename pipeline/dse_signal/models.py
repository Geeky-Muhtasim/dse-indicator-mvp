"""Two models: a transparent rules-based scorecard and a gradient-boosted ranker."""
from __future__ import annotations

import lightgbm as lgb
import numpy as np
import pandas as pd

from .config import Config
from .features import FEATURES

# Scorecard: equal-weighted, sign set by economic prior, no fitting at all.
# It is the benchmark the learned model has to beat to justify its complexity.
SCORECARD = {
    "rs_rank_10": +1,    # leaders keep leading over short horizons
    "ma_slope_10": +1,   # rising trend
    "ma_gap_20": +1,     # trading above trend
    "obv_slope_10": +1,  # volume confirms price
    "atr_pct_14": -1,    # prefer calmer names, penalise erratic ones
}


def _xs_zscore(df: pd.DataFrame, col: str) -> pd.Series:
    g = df.groupby("Date")[col]
    z = (df[col] - g.transform("mean")) / g.transform("std").replace(0, np.nan)
    return z.clip(-3, 3).fillna(0)


def scorecard_contributions(df: pd.DataFrame) -> pd.DataFrame:
    """Per-feature contribution to the scorecard. The score is their sum."""
    out = pd.DataFrame(index=df.index)
    for f, sign in SCORECARD.items():
        out[f] = sign * _xs_zscore(df, f) / len(SCORECARD)
    return out


def scorecard_score(df: pd.DataFrame) -> pd.Series:
    return scorecard_contributions(df).sum(axis=1)


class GBMRanker:
    """LightGBM regressor on the cross-sectional rank of excess return."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.model: lgb.LGBMRegressor | None = None

    def fit(self, df: pd.DataFrame) -> "GBMRanker":
        self.model = lgb.LGBMRegressor(random_state=self.cfg.seed, **self.cfg.lgbm_params)
        self.model.fit(df[FEATURES], df["target"])
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        return self.model.predict(df[FEATURES])

    def save(self, path) -> None:
        self.model.booster_.save_model(str(path))

    @classmethod
    def load(cls, path, cfg: Config) -> "GBMRanker":
        """Wrap a saved booster so daily scoring needs no retraining."""
        m = cls(cfg)
        booster = lgb.Booster(model_file=str(path))
        m.model = _BoosterAdapter(booster)
        return m


class _BoosterAdapter:
    """Gives a raw Booster the predict(X, pred_contrib=...) shape of LGBMRegressor."""

    def __init__(self, booster: lgb.Booster):
        self.booster_ = booster

    def predict(self, X, pred_contrib: bool = False):
        return self.booster_.predict(X, pred_contrib=pred_contrib)
