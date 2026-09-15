from jason_options_engine_v1 import build_debit_spreads, underlying_gate_ok


def _call(strike, bid, ask, delta, dte='2026-10-02T20:00:00Z'):
    return {
        'symbol': 'SPY', 'timestamp': '2026-09-15T15:00:00Z', 'expiration': dte,
        'option_type': 'call', 'strike': strike, 'bid': bid, 'ask': ask,
        'delta': delta, 'open_interest': 1000, 'volume': 150, 'underlying_price': 660.0,
    }


def test_bull_call_is_defined_risk_and_under_100_dollars():
    chain = [_call(660, 2.40, 2.50, 0.60), _call(665, 1.60, 1.70, 0.35)]
    plans = build_debit_spreads(chain, 'bull')
    assert len(plans) == 1
    p = plans[0]
    assert p['strategy'] == 'BULL_CALL_DEBIT_SPREAD'
    assert p['quantity'] == 1
    assert p['max_loss_usd'] == 90.0
    assert p['reward_risk'] >= 1.8
    assert p['live_order'] is False


def test_zero_dte_is_rejected():
    chain = [
        _call(660, 2.40, 2.50, 0.60, '2026-09-15T20:00:00Z'),
        _call(665, 1.60, 1.70, 0.35, '2026-09-15T20:00:00Z'),
    ]
    assert build_debit_spreads(chain, 'bull') == []


def test_wide_quote_is_rejected():
    chain = [_call(660, 1.00, 2.00, 0.60), _call(665, 1.60, 1.70, 0.35)]
    assert build_debit_spreads(chain, 'bull') == []


def test_upstream_must_be_real_pit_pass():
    ok, why = underlying_gate_ok({'qualification': 'REJECT', 'data_mode': 'point_in_time_real', 'synthetic_allowed': False})
    assert not ok and why == 'UPSTREAM_MULTI_ENGINE_NOT_PASS'
    ok, why = underlying_gate_ok({'qualification': 'PASS', 'hard_gates_passed': True, 'data_mode': 'synthetic', 'synthetic_allowed': True})
    assert not ok and why == 'UPSTREAM_REAL_PIT_NOT_VERIFIED'
