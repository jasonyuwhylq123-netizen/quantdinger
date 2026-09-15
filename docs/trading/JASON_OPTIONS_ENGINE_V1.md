# Jason Options Engine v1 — $500 experiment

Research-only options layer for the existing Jason US Swing $500 workflow.

## Design

The implementation uses the mature defined-risk vertical-spread pattern used by institutional/open-source option engines such as QuantConnect LEAN, while keeping QuantDinger's existing fail-closed validation philosophy. Optopsy is a useful research reference for systematic spread studies; no third-party strategy source is vendored or copied here.

Initial structures:

- bullish signal: bull call debit spread
- bearish signal: bear put debit spread
- 7–30 DTE only
- no 0DTE
- no naked short options
- no margin/financing/leverage
- no broker connectivity or live-order path

## $500 risk rules

- total experiment capital: $500
- maximum defined loss per spread position: $100
- minimum planned reward/risk: 1.8
- conservative planned debit: long-leg ask minus short-leg bid
- minimum open interest per leg: 200
- minimum same-session contract volume per leg: 25
- maximum bid/ask width per leg: 15% of mid
- long-leg absolute delta: 0.45–0.70
- short-leg absolute delta: 0.20–0.45

## Validation contract

`backend_api_python/scripts/validate_jason_options_500.py` fails closed unless all three layers exist:

1. Existing Jason US Swing $500 upstream result is PASS on real point-in-time data.
2. Real timestamped option-chain snapshots exist under `data/jason_options_pit/`.
3. Independent option validation evidence exists at `data/jason_options_validation/multi_engine_results.json`.

The multi-engine evidence must show:

- at least 30 independent-test trades
- positive test expectancy
- Profit Factor > 1.2
- realized reward/risk >= 1.8
- test max drawdown <= 15%
- vectorized/event-driven total-return delta < 5 percentage points
- LEAN or equivalent event-driven verification explicitly marked verified
- at least 3 of 4 positive walk-forward OOS folds
- Monte Carlo >= 2,000 paths with 5th-percentile total return > -10%

If any layer is absent or invalid, output is `REJECT / NO_TRADE` and includes `未完成多引擎验证`. Synthetic data may be used for unit/plumbing tests only and can never authorize a candidate.

## Required option-chain fields

`symbol, timestamp, expiration, option_type, strike, bid, ask, delta, open_interest, volume, underlying_price, signal_direction`

`signal_direction` must be `bull` or `bear` and must originate from the already-validated upstream directional model. The validator selects at most three research candidates from the latest real snapshot.

## Safety boundary

The engine returns research plans only. It deliberately contains no IBKR order submission function and every candidate carries `live_order: false`.
