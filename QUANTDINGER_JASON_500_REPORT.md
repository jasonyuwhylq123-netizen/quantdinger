# QuantDinger — Jason US Swing $500 Profit-First

## Mandate
Research-only US equity swing strategy for an isolated **$500 cash account**, no margin, no leverage, no live orders. Holding horizon is 1–10 trading days with selection optimized for 1–5 day opportunity efficiency.

## Entry architecture
A candidate must pass minimum price/dollar-volume and maximum spread filters, then combine catalyst quality, broad-market and sector relative strength, price/volume confirmation, VWAP behavior, breakout-retest **second confirmation**, and sufficient ATR/volatility-derived upside room. Existing-position correlation reduces rank once correlation exceeds the configured threshold.

### Anti-chase rule
After earnings or other major news, the first impulse and first pullback are not eligible. `sessions_since_major_event < 2` is fail-closed, and a later entry still requires explicit second confirmation.

## Risk/selection gates
- Capital: $500 cash only.
- Maximum positions: 3.
- Hard holding limit: 10 sessions; preferred opportunity window: 1–5.
- Minimum modeled reward/risk: 1.8.
- Independent test set: Expectancy > 0 and Profit Factor > 1.2.
- Minimum independent-test sample: 30 trades.
- Maximum test drawdown gate: 15%.
- Walk-forward instability, engine disagreement, sample insufficiency, test deterioration, excessive drawdown, or unstable Monte Carlo behavior => reject.

## Required validation stack
The acceptance decision requires all of: **QuantDinger**, **VectorBT**, **LEAN or an equivalent event-driven engine**, **Walk-Forward**, and **Monte Carlo**. Point-in-time data and realistic transaction-cost assumptions are required; look-ahead leakage is prohibited.

## Current result
**REJECT_UNTIL_EMPIRICALLY_VALIDATED.** The repository now contains the strategy filters, scoring logic, Monte Carlo utility and fail-closed acceptance gates in `research/jason_us_swing_500.py`, plus unit coverage in `research/test_jason_us_swing_500.py`.

No performance statistics are claimed here because this connector session does not provide a trustworthy execution environment plus independent historical market dataset for actually running QuantDinger + VectorBT + an event-driven engine. Inventing passing metrics would violate the validation requirement. The strategy therefore remains rejected until empirical multi-engine validation produces the required evidence.

## Safety
This research module contains **no IBKR connection and no order-submission path**. It cannot place real-money trades.
