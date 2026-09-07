"""Jason US Swing $500 short-horizon research strategy.

Research/backtest only. No broker integration, leverage, margin or live orders.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd

@dataclass(frozen=True)
class Jason500Config:
    capital: float = 500.0
    max_hold: int = 10
    preferred_hold: int = 5
    min_price: float = 5.0
    min_dollar_volume: float = 20_000_000.0
    max_spread_bps: float = 35.0
    min_atr_pct: float = 0.012
    max_atr_pct: float = 0.09
    min_reward_risk: float = 1.8
    correlation_penalty_start: float = 0.70
    news_cooldown_bars: int = 2


def features(df: pd.DataFrame, benchmark: pd.Series, sector: pd.Series) -> pd.DataFrame:
    x = df.copy()
    prev = x.close.shift(1)
    tr = pd.concat([(x.high-x.low), (x.high-prev).abs(), (x.low-prev).abs()], axis=1).max(axis=1)
    x['atr'] = tr.rolling(14).mean()
    x['atr_pct'] = x.atr / x.close
    x['dollar_volume'] = x.close * x.volume
    x['vwap20'] = (x.close*x.volume).rolling(20).sum() / x.volume.rolling(20).sum()
    x['vol_ratio'] = x.volume / x.volume.rolling(20).mean()
    x['breakout20'] = x.close > x.high.shift(1).rolling(20).max()
    x['retest'] = (x.low <= x.high.shift(1).rolling(20).max()*1.01) & (x.close > x.open)
    x['second_confirm'] = x.retest.shift(1).fillna(False) & (x.close > x.high.shift(1))
    x['rs_market'] = x.close.pct_change(10) - benchmark.pct_change(10)
    x['rs_sector'] = x.close.pct_change(10) - sector.pct_change(10)
    x['spread_ok'] = x.get('spread_bps', pd.Series(0.0, index=x.index)) <= Jason500Config.max_spread_bps
    x['catalyst'] = x.get('catalyst', pd.Series(False, index=x.index)).astype(bool)
    shock = x.get('major_news', pd.Series(False, index=x.index)).astype(bool) | x.get('earnings', pd.Series(False, index=x.index)).astype(bool)
    # Ban the first wave and first pullback after major news/earnings: cooldown bars are ineligible.
    x['post_event_ban'] = shock.rolling(Jason500Config.news_cooldown_bars + 1, min_periods=1).max().astype(bool)
    return x


def entry_mask(x: pd.DataFrame, cfg: Jason500Config = Jason500Config()) -> pd.Series:
    liquidity = (x.close >= cfg.min_price) & (x.dollar_volume >= cfg.min_dollar_volume) & x.spread_ok
    regime = (x.rs_market > 0) & (x.rs_sector > 0)
    tape = (x.close > x.vwap20) & (x.vol_ratio >= 1.15)
    setup = x.breakout20.shift(2).fillna(False) & x.second_confirm
    room = x.atr_pct.between(cfg.min_atr_pct, cfg.max_atr_pct)
    return (liquidity & x.catalyst & regime & tape & setup & room & ~x.post_event_ban).fillna(False)


def correlation_penalty(candidate_returns: pd.Series, held_returns: list[pd.Series], cfg: Jason500Config = Jason500Config()) -> float:
    if not held_returns:
        return 1.0
    correlations = [candidate_returns.corr(r) for r in held_returns]
    worst = np.nanmax(correlations) if correlations else 0.0
    return float(max(0.25, 1.0 - max(0.0, worst-cfg.correlation_penalty_start)))


def exits(x: pd.DataFrame, entries: pd.Series, cfg: Jason500Config = Jason500Config()) -> pd.Series:
    out = pd.Series(False, index=x.index)
    active = False; entry_i = -1; entry_px = 0.0; risk = 0.0
    for i in range(len(x)):
        if not active and bool(entries.iloc[i]):
            active=True; entry_i=i; entry_px=float(x.close.iloc[i]); risk=max(float(x.atr.iloc[i]), entry_px*0.005)
        elif active:
            held=i-entry_i; px=float(x.close.iloc[i])
            stop=entry_px-risk; target=entry_px+cfg.min_reward_risk*risk
            if px <= stop or px >= target or held >= cfg.max_hold or (held >= cfg.preferred_hold and px < float(x.vwap20.iloc[i])):
                out.iloc[i]=True; active=False
    if active: out.iloc[-1]=True
    return out
