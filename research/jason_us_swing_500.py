"""Jason US Swing $500 — research-only, no broker connectivity.

Profit-first 1-10 trading-day swing model with hard validation gates.
The module is deliberately broker-agnostic and cannot submit orders.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Iterable
import json, math, random

@dataclass(frozen=True)
class Config:
    capital: float = 500.0
    min_price: float = 5.0
    min_dollar_volume: float = 20_000_000.0
    max_spread_bps: float = 35.0
    max_positions: int = 3
    max_hold_days: int = 10
    preferred_hold_days: int = 5
    min_reward_risk: float = 1.8
    min_profit_factor: float = 1.2
    min_expectancy: float = 0.0
    min_test_trades: int = 30
    max_test_drawdown: float = 0.15
    correlation_penalty_start: float = 0.65
    event_cooldown_sessions: int = 2

CFG = Config()

def eligible(row: dict, existing_correlations: Iterable[float] = ()) -> tuple[bool, float, list[str]]:
    """Return (eligible, score, reasons). Inputs must be point-in-time data."""
    reasons=[]
    if row['price'] < CFG.min_price or row['dollar_volume'] < CFG.min_dollar_volume: reasons.append('liquidity')
    if row['spread_bps'] > CFG.max_spread_bps: reasons.append('spread')
    # Never chase the first impulse or first pullback after earnings/major news.
    if row.get('sessions_since_major_event', 99) < CFG.event_cooldown_sessions: reasons.append('event_chase_cooldown')
    if not row.get('second_confirmation', False): reasons.append('no_second_confirmation')
    if row.get('atr_upside_rr', 0.0) < CFG.min_reward_risk: reasons.append('insufficient_atr_room')
    score = (1.2*row.get('catalyst_score',0)+row.get('market_rs',0)+row.get('sector_rs',0)
             +row.get('volume_price_score',0)+row.get('vwap_score',0)+row.get('retest_score',0))
    corr=max(existing_correlations, default=0.0)
    if corr > CFG.correlation_penalty_start: score -= 2.0*(corr-CFG.correlation_penalty_start)
    return not reasons, score, reasons

def metrics(returns: list[float]) -> dict:
    wins=[x for x in returns if x>0]; losses=[x for x in returns if x<0]
    pf=sum(wins)/abs(sum(losses)) if losses else (float('inf') if wins else 0.0)
    exp=sum(returns)/len(returns) if returns else 0.0
    eq=1.0; peak=1.0; mdd=0.0
    for r in returns:
        eq*=1+r; peak=max(peak,eq); mdd=max(mdd,1-eq/peak)
    avg_win=sum(wins)/len(wins) if wins else 0.0; avg_loss=abs(sum(losses)/len(losses)) if losses else math.inf
    rr=avg_win/avg_loss if avg_loss not in (0,math.inf) else 0.0
    return {'trades':len(returns),'expectancy':exp,'profit_factor':pf,'realized_reward_risk':rr,'max_drawdown':mdd}

def monte_carlo(returns:list[float], runs:int=2000, seed:int=500)->dict:
    rng=random.Random(seed); dds=[]; exps=[]
    for _ in range(runs):
        sample=[rng.choice(returns) for _ in returns]
        m=metrics(sample); dds.append(m['max_drawdown']); exps.append(m['expectancy'])
    dds.sort(); exps.sort()
    return {'runs':runs,'drawdown_p95':dds[int(.95*(runs-1))] if dds else None,
            'expectancy_p05':exps[int(.05*(runs-1))] if exps else None}

def hard_gate(test:dict, stability_ok:bool, wf_ok:bool, engines_agree:bool)->tuple[bool,list[str]]:
    fail=[]
    if test['trades'] < CFG.min_test_trades: fail.append('insufficient_test_sample')
    if test['expectancy'] <= CFG.min_expectancy: fail.append('expectancy_not_positive')
    if test['profit_factor'] <= CFG.min_profit_factor: fail.append('profit_factor_le_1.2')
    if test['realized_reward_risk'] < CFG.min_reward_risk: fail.append('reward_risk_lt_1.8')
    if test['max_drawdown'] > CFG.max_test_drawdown: fail.append('drawdown_excessive')
    if not stability_ok: fail.append('stability_failed')
    if not wf_ok: fail.append('walk_forward_failed')
    if not engines_agree: fail.append('engine_disagreement')
    return not fail, fail

def write_result(path:str, payload:dict)->None:
    with open(path,'w',encoding='utf-8') as f: json.dump(payload,f,indent=2,ensure_ascii=False,allow_nan=False)

if __name__=='__main__':
    print(json.dumps({'strategy':'Jason US Swing $500','config':asdict(CFG),'broker_connectivity':False},indent=2))
