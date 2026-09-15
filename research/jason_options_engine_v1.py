"""Jason Options Engine v2 — research-only defined-risk option spreads.

Selects bull-call or bear-put debit verticals for the $1,000 experiment.
No broker connectivity, margin, naked short options, 0DTE, or live-order path.
All market/option inputs must be point-in-time observations.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from math import floor
from typing import Iterable


@dataclass(frozen=True)
class OptionsConfig:
    capital_usd: float = 1000.0
    default_max_risk_per_trade_usd: float = 150.0
    absolute_max_risk_per_trade_usd: float = 200.0
    portfolio_open_risk_cap_usd: float = 350.0
    min_dte: int = 7
    max_dte: int = 30
    min_reward_risk: float = 1.8
    min_open_interest: int = 200
    min_contract_volume: int = 25
    max_leg_spread_pct: float = 0.15
    long_delta_min: float = 0.45
    long_delta_max: float = 0.70
    short_delta_min: float = 0.20
    short_delta_max: float = 0.45
    min_width: float = 1.0
    max_width: float = 10.0
    max_candidates: int = 3


CFG = OptionsConfig()


def _as_utc(value) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _dte(timestamp, expiration) -> int:
    return max(0, (_as_utc(expiration).date() - _as_utc(timestamp).date()).days)


def _leg_ok(row: dict, cfg: OptionsConfig = CFG) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    bid, ask = float(row['bid']), float(row['ask'])
    if bid <= 0 or ask <= 0 or ask < bid:
        reasons.append('invalid_quote')
    else:
        mid = (bid + ask) / 2.0
        if mid <= 0 or (ask - bid) / mid > cfg.max_leg_spread_pct:
            reasons.append('wide_bid_ask')
    if int(row.get('open_interest', 0)) < cfg.min_open_interest:
        reasons.append('low_open_interest')
    if int(row.get('volume', 0)) < cfg.min_contract_volume:
        reasons.append('low_contract_volume')
    dte = _dte(row['timestamp'], row['expiration'])
    if not cfg.min_dte <= dte <= cfg.max_dte:
        reasons.append('dte_out_of_range')
    return not reasons, reasons


def _delta_ok(row: dict, long_leg: bool, cfg: OptionsConfig = CFG) -> bool:
    d = abs(float(row.get('delta', 0.0)))
    lo = cfg.long_delta_min if long_leg else cfg.short_delta_min
    hi = cfg.long_delta_max if long_leg else cfg.short_delta_max
    return lo <= d <= hi


def underlying_gate_ok(payload: dict | None) -> tuple[bool, str]:
    if not payload:
        return False, 'UPSTREAM_MULTI_ENGINE_RESULT_MISSING'
    if payload.get('qualification') != 'PASS' or not payload.get('hard_gates_passed', True):
        return False, 'UPSTREAM_MULTI_ENGINE_NOT_PASS'
    if payload.get('synthetic_allowed') is True or payload.get('data_mode') not in {'point_in_time_real', 'point_in_time_real_required'}:
        return False, 'UPSTREAM_REAL_PIT_NOT_VERIFIED'
    return True, ''


def build_debit_spreads(
    chain: Iterable[dict],
    direction: str,
    cfg: OptionsConfig = CFG,
    current_open_risk_usd: float = 0.0,
    risk_budget_usd: float | None = None,
) -> list[dict]:
    """Return ranked research plans, never order objects.

    Default per-trade risk is $150. An explicit A+ risk budget may be supplied but
    is hard-capped at $200. Portfolio open risk is capped at $350.
    """
    if direction not in {'bull', 'bear'}:
        raise ValueError('direction must be bull or bear')
    if current_open_risk_usd < 0:
        raise ValueError('current_open_risk_usd must be non-negative')
    remaining_portfolio_risk = max(0.0, cfg.portfolio_open_risk_cap_usd - current_open_risk_usd)
    requested = cfg.default_max_risk_per_trade_usd if risk_budget_usd is None else float(risk_budget_usd)
    trade_risk_cap = min(requested, cfg.absolute_max_risk_per_trade_usd, remaining_portfolio_risk, cfg.capital_usd)
    if trade_risk_cap <= 0:
        return []

    option_type = 'call' if direction == 'bull' else 'put'
    rows = [dict(r) for r in chain if str(r.get('option_type', '')).lower() == option_type]
    valid = []
    for r in rows:
        ok, _ = _leg_ok(r, cfg)
        if ok:
            valid.append(r)

    out: list[dict] = []
    for long_leg in valid:
        if not _delta_ok(long_leg, True, cfg):
            continue
        for short_leg in valid:
            if not _delta_ok(short_leg, False, cfg):
                continue
            if long_leg.get('symbol') != short_leg.get('symbol') or str(long_leg['expiration']) != str(short_leg['expiration']):
                continue
            lk, sk = float(long_leg['strike']), float(short_leg['strike'])
            if direction == 'bull' and not lk < sk:
                continue
            if direction == 'bear' and not lk > sk:
                continue
            width = abs(sk - lk)
            if not cfg.min_width <= width <= cfg.max_width:
                continue
            debit = float(long_leg['ask']) - float(short_leg['bid'])
            if debit <= 0 or debit >= width:
                continue
            unit_loss = debit * 100.0
            unit_profit = (width - debit) * 100.0
            rr = unit_profit / unit_loss
            if rr < cfg.min_reward_risk or unit_loss > trade_risk_cap:
                continue
            qty = floor(trade_risk_cap / unit_loss)
            if qty < 1:
                continue
            quote_ts = max(_as_utc(long_leg['timestamp']), _as_utc(short_leg['timestamp']))
            total_loss = unit_loss * qty
            total_profit = unit_profit * qty
            score = rr + min(int(long_leg['open_interest']), int(short_leg['open_interest'])) / 10000.0
            out.append({
                'symbol': long_leg['symbol'],
                'strategy': 'BULL_CALL_DEBIT_SPREAD' if direction == 'bull' else 'BEAR_PUT_DEBIT_SPREAD',
                'direction': direction,
                'expiration': str(long_leg['expiration']),
                'dte': _dte(quote_ts, long_leg['expiration']),
                'long_strike': lk,
                'short_strike': sk,
                'planned_debit': round(debit, 4),
                'quantity': int(qty),
                'max_loss_usd': round(total_loss, 2),
                'max_profit_usd': round(total_profit, 2),
                'reward_risk': round(rr, 3),
                'risk_budget_usd': round(trade_risk_cap, 2),
                'portfolio_open_risk_after_usd': round(current_open_risk_usd + total_loss, 2),
                'quote_timestamp': quote_ts.isoformat(),
                'live_order': False,
                '_score': score,
            })
    out.sort(key=lambda x: (x['_score'], x['reward_risk']), reverse=True)
    for item in out:
        item.pop('_score', None)
    return out[:cfg.max_candidates]


def config_dict(cfg: OptionsConfig = CFG) -> dict:
    return asdict(cfg)
