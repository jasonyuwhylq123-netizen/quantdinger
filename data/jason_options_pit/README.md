# Jason Options PIT data

Place real point-in-time option-chain CSV/Parquet snapshots here. Required fields:

`symbol,timestamp,expiration,option_type,strike,bid,ask,delta,open_interest,volume,underlying_price,signal_direction`

Synthetic datasets are not accepted by the formal validator. Missing data fails closed to `REJECT / NO_TRADE`.
