"""Fail-closed validation gate for Jason Options Engine v1.

Requires: (1) PASS from the stock $500 real-PIT multi-engine layer,
(2) real point-in-time option-chain snapshots, and (3) independent multi-engine
validation evidence. Missing evidence always means REJECT / NO_TRADE.
No broker connectivity or live-order path exists in this module.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'research'))
from jason_options_engine_v1 import CFG, build_debit_spreads, underlying_gate_ok  # noqa: E402

UPSTREAM = ROOT / 'QUANTDINGER_JASON_500_RESULT.json'
DATA = ROOT / 'data' / 'jason_options_pit'
EVIDENCE = ROOT / 'data' / 'jason_options_validation' / 'multi_engine_results.json'
RESULT = ROOT / 'QUANTDINGER_JASON_OPTIONS_500_RESULT.json'
REPORT = ROOT / 'QUANTDINGER_JASON_OPTIONS_500_REPORT.md'

REQUIRED_CHAIN = [
    'symbol', 'timestamp', 'expiration', 'option_type', 'strike', 'bid', 'ask',
    'delta', 'open_interest', 'volume', 'underlying_price', 'signal_direction'
]


def _write(payload: dict) -> dict:
    RESULT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    REPORT.write_text(
        '# QuantDinger — Jason Options Engine v1 ($500)\n\n'
        f"**{payload['qualification']} — {payload['today']}**\n\n"
        'Research only. No broker connectivity, margin, naked options, 0DTE, or live orders.\n\n'
        '```json\n' + json.dumps(payload, indent=2, ensure_ascii=False) + '\n```\n',
        encoding='utf-8',
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return payload


def fail_closed(reason: str, detail: str = '') -> dict:
    return _write({
        'strategy': 'Jason Options Engine v1',
        'capital_usd': 500,
        'mode': 'research_only',
        'margin': False,
        'leverage': False,
        'naked_options': False,
        'zero_dte': False,
        'broker_connected': False,
        'live_orders': False,
        'synthetic_allowed': False,
        'qualification': 'REJECT',
        'hard_gates_passed': False,
        'trade_decision': 'NO_TRADE',
        'today': '暂无A级交易机会',
        'multi_engine_status': '未完成多引擎验证',
        'reason': reason,
        'detail': detail,
    })


def load_upstream() -> dict:
    if not UPSTREAM.exists():
        raise RuntimeError('Missing QUANTDINGER_JASON_500_RESULT.json')
    payload = json.loads(UPSTREAM.read_text(encoding='utf-8'))
    ok, why = underlying_gate_ok(payload)
    if not ok:
        raise RuntimeError(why)
    return payload


def load_chain() -> pd.DataFrame:
    files = sorted(DATA.glob('*.parquet')) + sorted(DATA.glob('*.csv'))
    if not files:
        raise RuntimeError('No real point-in-time option chain data in data/jason_options_pit')
    parts = [pd.read_parquet(p) if p.suffix == '.parquet' else pd.read_csv(p) for p in files]
    d = pd.concat(parts, ignore_index=True)
    missing = [c for c in REQUIRED_CHAIN if c not in d.columns]
    if missing:
        raise RuntimeError('Missing option PIT fields: ' + ', '.join(missing))
    d['timestamp'] = pd.to_datetime(d['timestamp'], utc=True)
    d['expiration'] = pd.to_datetime(d['expiration'], utc=True)
    if (d['ask'] < d['bid']).any() or (d['bid'] <= 0).any() or (d['underlying_price'] <= 0).any():
        raise RuntimeError('Invalid option chain quote observations')
    if (~d['signal_direction'].astype(str).str.lower().isin(['bull', 'bear'])).any():
        raise RuntimeError('signal_direction must be bull or bear')
    return d.sort_values(['timestamp', 'symbol', 'expiration', 'strike'])


def load_evidence() -> dict:
    if not EVIDENCE.exists():
        raise RuntimeError('Missing independent multi-engine option validation evidence')
    e = json.loads(EVIDENCE.read_text(encoding='utf-8'))
    if e.get('data_mode') != 'point_in_time_real' or e.get('synthetic_allowed') is True:
        raise RuntimeError('Options validation evidence is not verified real PIT data')
    return e


def evidence_gates(e: dict) -> tuple[bool, dict]:
    event = e.get('event_driven', {})
    vectorized = e.get('vectorized', {})
    lean = e.get('lean_or_equivalent', {})
    wf = e.get('walk_forward', [])
    mc = e.get('monte_carlo', {})
    delta = abs(float(event.get('total_return', -999)) - float(vectorized.get('total_return', 999)))
    gates = {
        'sample_sufficient': int(event.get('trades', 0)) >= 30,
        'expectancy_gt_0': float(event.get('expectancy', -1)) > 0,
        'profit_factor_gt_1_2': float(event.get('profit_factor', 0)) > 1.2,
        'reward_risk_gte_1_8': float(event.get('reward_risk', 0)) >= CFG.min_reward_risk,
        'max_drawdown_ok': float(event.get('max_drawdown', -1)) >= -0.15,
        'vectorized_consistent': delta < 0.05,
        'lean_or_equivalent_verified': bool(lean.get('verified', False)),
        'walk_forward_stable': len(wf) >= 4 and sum(float(x.get('expectancy', -1)) > 0 for x in wf) >= 3,
        'monte_carlo_ok': int(mc.get('paths', 0)) >= 2000 and float(mc.get('p05_total_return', -1)) > -0.10,
    }
    return all(gates.values()), gates


def latest_candidates(d: pd.DataFrame) -> list[dict]:
    ts = d['timestamp'].max()
    snap = d[d['timestamp'] == ts]
    candidates: list[dict] = []
    for symbol, g in snap.groupby('symbol', sort=False):
        direction = str(g['signal_direction'].iloc[0]).lower()
        plans = build_debit_spreads(g.to_dict('records'), direction)
        candidates.extend(plans)
    candidates.sort(key=lambda x: x['reward_risk'], reverse=True)
    return candidates[:3]


def main() -> dict:
    try:
        load_upstream()
        chain = load_chain()
        evidence = load_evidence()
    except Exception as exc:
        return fail_closed('OPTIONS_REAL_VALIDATION_UNAVAILABLE_OR_INVALID', str(exc))

    ok, gates = evidence_gates(evidence)
    if not ok:
        return fail_closed('OPTIONS_MULTI_ENGINE_HARD_GATES_FAILED', json.dumps(gates, ensure_ascii=False))

    candidates = latest_candidates(chain)
    if not candidates:
        return _write({
            'strategy': 'Jason Options Engine v1', 'capital_usd': 500, 'mode': 'research_only',
            'margin': False, 'leverage': False, 'broker_connected': False, 'live_orders': False,
            'synthetic_allowed': False, 'qualification': 'PASS', 'hard_gates_passed': True,
            'trade_decision': 'NO_TRADE', 'today': '暂无A级交易机会',
            'multi_engine_status': 'PASS', 'gates': gates, 'candidates': [],
        })

    return _write({
        'strategy': 'Jason Options Engine v1', 'capital_usd': 500, 'mode': 'research_only',
        'margin': False, 'leverage': False, 'broker_connected': False, 'live_orders': False,
        'synthetic_allowed': False, 'qualification': 'PASS', 'hard_gates_passed': True,
        'trade_decision': 'RESEARCH_CANDIDATES_ONLY', 'today': '仅研究候选，不自动交易',
        'multi_engine_status': 'PASS', 'gates': gates, 'candidates': candidates,
    })


if __name__ == '__main__':
    main()
