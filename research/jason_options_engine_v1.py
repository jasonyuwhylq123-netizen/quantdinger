"""Jason Options Engine v1 — research-only defined-risk option spreads.

Selects bull-call or bear-put debit verticals for the $500 experiment.
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
    capital_usd: float = 500.0
    max_risk_per_trade_usd: float = 100.0
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


def _mid(row: dict) -> float:
    return (float(row['bid']) + float(row['ask'])) / 2.0


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
    """Fail closed unless the stock/multi-engine layer is formally validated."""
    if not payload:
        return False, 'UPSTREAM_MULTI_ENGINE_RESULT_MISSING'
    if payload.get('qualification') != 'PASS' or not payload.get('hard_gates_passed', True):
        return False, 'UPSTREAM_MULTI_ENGINE_NOT_PASS'
    if payload.get('synthetic_allowed') is True or payload.get('data_mode') not in {'point_in_time_real', 'point_in_time_real_required'}:
        return False, 'UPSTREAM_REAL_PIT_NOT_VERIFIED'
    return True, ''


def build_debit_spreads(chain: Iterable[dict], direction: str, cfg: OptionsConfig = CFG) -> list[dict]:
    """Return ranked executable spread plans; never returns an order object.

    direction: 'bull' -> bull call debit spread, 'bear' -> bear put debit spread.
    Entry debit is conservatively estimated as long ask minus short bid.
    """
    if direction not in {'bull', 'bear'}:
        raise ValueError('direction must be bull or bear')
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
            max_loss = debit * 100.0
            max_profit = (width - debit) * 100.0
            rr = max_profit / max_loss
            if rr < cfg.min_reward_risk or max_loss > cfg.max_risk_per_trade_usd or max_loss > cfg.capital_usd:
                continue
            qty = min(floor(cfg.capital_usd / max_loss), floor(cfg.max_risk_per_trade_usd / max_loss))
            if qty < 1:
                continue
            quote_ts = max(_as_utc(long_leg['timestamp']), _as_utc(short_leg['timestamp']))
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
                'max_loss_usd': round(max_loss * qty, 2),
                'max_profit_usd': round(max_profit * qty, 2),
                'reward_risk': round(rr, 3),
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
