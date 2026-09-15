"""Jason Options Engine v2.1 — research-only defined-risk option spreads.

Ranks bull-call or bear-put debit verticals for the $1,000 experiment.
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
    # v2.1 ranking gates: optional PIT fields become hard gates when supplied.
    max_days_to_earnings: int = 3
    max_iv_rank: float = 80.0
    max_abs_vega: float = 0.30
    max_abs_theta_to_debit: float = 0.12
    estimated_fee_per_contract_usd: float = 1.30
    slippage_fraction_of_leg_spread: float = 0.25

CFG = OptionsConfig()

def _as_utc(value) -> datetime:
    if isinstance(value, datetime): dt=value
    else: dt=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def _dte(timestamp, expiration)->int:
    return max(0,(_as_utc(expiration).date()-_as_utc(timestamp).date()).days)

def _leg_ok(row:dict,cfg:OptionsConfig=CFG)->tuple[bool,list[str]]:
    reasons=[]; bid,ask=float(row['bid']),float(row['ask'])
    if bid<=0 or ask<=0 or ask<bid: reasons.append('invalid_quote')
    else:
        mid=(bid+ask)/2
        if mid<=0 or (ask-bid)/mid>cfg.max_leg_spread_pct: reasons.append('wide_bid_ask')
    if int(row.get('open_interest',0))<cfg.min_open_interest: reasons.append('low_open_interest')
    if int(row.get('volume',0))<cfg.min_contract_volume: reasons.append('low_contract_volume')
    if not cfg.min_dte<=_dte(row['timestamp'],row['expiration'])<=cfg.max_dte: reasons.append('dte_out_of_range')
    if row.get('iv_rank') is not None and float(row['iv_rank'])>cfg.max_iv_rank: reasons.append('iv_rank_too_high')
    if row.get('vega') is not None and abs(float(row['vega']))>cfg.max_abs_vega: reasons.append('vega_too_high')
    return not reasons,reasons

def _delta_ok(row:dict,long_leg:bool,cfg:OptionsConfig=CFG)->bool:
    d=abs(float(row.get('delta',0))); lo=cfg.long_delta_min if long_leg else cfg.short_delta_min; hi=cfg.long_delta_max if long_leg else cfg.short_delta_max
    return lo<=d<=hi

def underlying_gate_ok(payload:dict|None)->tuple[bool,str]:
    if not payload:return False,'UPSTREAM_MULTI_ENGINE_RESULT_MISSING'
    if payload.get('qualification')!='PASS' or not payload.get('hard_gates_passed',True):return False,'UPSTREAM_MULTI_ENGINE_NOT_PASS'
    if payload.get('synthetic_allowed') is True or payload.get('data_mode') not in {'point_in_time_real','point_in_time_real_required'}:return False,'UPSTREAM_REAL_PIT_NOT_VERIFIED'
    return True,''

def _event_ok(row:dict,cfg:OptionsConfig)->bool:
    days=row.get('days_to_earnings')
    return days is None or int(days)<0 or int(days)>cfg.max_days_to_earnings

def _execution_cost(long_leg:dict,short_leg:dict,qty:int,cfg:OptionsConfig)->float:
    # Conservative estimated round-trip friction: partial quoted spread + fees.
    widths=(float(long_leg['ask'])-float(long_leg['bid']))+(float(short_leg['ask'])-float(short_leg['bid']))
    slip=widths*100*cfg.slippage_fraction_of_leg_spread*2*qty
    fees=cfg.estimated_fee_per_contract_usd*4*qty
    return slip+fees

def build_debit_spreads(chain:Iterable[dict],direction:str,cfg:OptionsConfig=CFG,current_open_risk_usd:float=0.0,risk_budget_usd:float|None=None)->list[dict]:
    if direction not in {'bull','bear'}: raise ValueError('direction must be bull or bear')
    if current_open_risk_usd<0: raise ValueError('current_open_risk_usd must be non-negative')
    remaining=max(0.0,cfg.portfolio_open_risk_cap_usd-current_open_risk_usd)
    requested=cfg.default_max_risk_per_trade_usd if risk_budget_usd is None else float(risk_budget_usd)
    cap=min(requested,cfg.absolute_max_risk_per_trade_usd,remaining,cfg.capital_usd)
    if cap<=0:return []
    typ='call' if direction=='bull' else 'put'; valid=[]
    for raw in chain:
        r=dict(raw)
        if str(r.get('option_type','')).lower()!=typ:continue
        ok,_=_leg_ok(r,cfg)
        if ok and _event_ok(r,cfg):valid.append(r)
    out=[]
    for long_leg in valid:
        if not _delta_ok(long_leg,True,cfg):continue
        for short_leg in valid:
            if not _delta_ok(short_leg,False,cfg):continue
            if long_leg.get('symbol')!=short_leg.get('symbol') or str(long_leg['expiration'])!=str(short_leg['expiration']):continue
            lk,sk=float(long_leg['strike']),float(short_leg['strike'])
            if direction=='bull' and not lk<sk:continue
            if direction=='bear' and not lk>sk:continue
            width=abs(sk-lk)
            if not cfg.min_width<=width<=cfg.max_width:continue
            debit=float(long_leg['ask'])-float(short_leg['bid'])
            if debit<=0 or debit>=width:continue
            unit_loss=debit*100; unit_profit=(width-debit)*100; rr=unit_profit/unit_loss
            if rr<cfg.min_reward_risk or unit_loss>cap:continue
            theta=abs(float(long_leg.get('theta',0))-float(short_leg.get('theta',0))) if long_leg.get('theta') is not None and short_leg.get('theta') is not None else 0.0
            if theta and theta/max(debit,0.01)>cfg.max_abs_theta_to_debit:continue
            qty=floor(cap/unit_loss)
            if qty<1:continue
            friction=_execution_cost(long_leg,short_leg,qty,cfg)
            net_profit=unit_profit*qty-friction; net_loss=unit_loss*qty+friction
            net_rr=net_profit/net_loss if net_loss>0 else 0
            if net_rr<cfg.min_reward_risk:continue
            # Prefer robust net economics, then liquidity; penalize expensive IV and theta/vega exposure.
            oi=min(int(long_leg['open_interest']),int(short_leg['open_interest']))
            vol=min(int(long_leg['volume']),int(short_leg['volume']))
            ivr=max(float(long_leg.get('iv_rank',50)),float(short_leg.get('iv_rank',50)))
            vega=abs(float(long_leg.get('vega',0))-float(short_leg.get('vega',0)))
            liquidity=min(1.0,oi/2000)+min(1.0,vol/500)
            score=2.5*net_rr+0.5*liquidity-0.006*ivr-0.5*vega-0.25*theta/max(debit,0.01)
            ts=max(_as_utc(long_leg['timestamp']),_as_utc(short_leg['timestamp']))
            total_loss=unit_loss*qty
            out.append({'symbol':long_leg['symbol'],'strategy':'BULL_CALL_DEBIT_SPREAD' if direction=='bull' else 'BEAR_PUT_DEBIT_SPREAD','direction':direction,'expiration':str(long_leg['expiration']),'dte':_dte(ts,long_leg['expiration']),'long_strike':lk,'short_strike':sk,'planned_debit':round(debit,4),'quantity':int(qty),'max_loss_usd':round(total_loss,2),'max_profit_usd':round(unit_profit*qty,2),'reward_risk':round(rr,3),'estimated_round_trip_cost_usd':round(friction,2),'net_reward_risk':round(net_rr,3),'iv_rank_used':round(ivr,2),'net_vega':round(vega,4),'net_theta':round(theta,4),'ranking_score':round(score,4),'risk_budget_usd':round(cap,2),'portfolio_open_risk_after_usd':round(current_open_risk_usd+total_loss,2),'quote_timestamp':ts.isoformat(),'live_order':False})
    out.sort(key=lambda x:(x['ranking_score'],x['net_reward_risk']),reverse=True)
    return out[:cfg.max_candidates]

def config_dict(cfg:OptionsConfig=CFG)->dict:return asdict(cfg)
