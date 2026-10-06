# JJ Fair Value Backtest - Provenance Report

## Status

An independent clean-room reimplementation has been added to:

`research/jj_fair_value_backtest.py`

Commit:
`cfcb11ab0fc9b1a2b8440332c34b09e17224b61c`

## Source inspected

Public GitHub repository:
https://github.com/jamesdchen/harxhar-clean

Reference file:
`experiments/jj_backtest.py`

## Important provenance note

The reference file was inspected because it is publicly accessible, but no clear software license granting unrestricted redistribution of its source was established during this check.

Therefore the original file was NOT copied verbatim into this repository.

Instead, the new file is an independent implementation of the publicly described behavior.

## Logic preserved at the behavioral level

- NQ 1-minute OHLC workflow
- 09:30 and 14:00 New York session anchors
- 09:30-11:00 and 14:00-15:00 session windows
- 15-minute continuation phase
- subsequent reversion phase toward the session anchor
- displacement based on candle body/range
- ATR-derived stop distance
- 1.5R target
- first-touch stop/target evaluation
- end-of-window exit when neither level is reached

## Known differences

This implementation is intentionally not a byte-for-byte copy.

It also does not claim to reproduce the original JJ Simon TradingView source. In particular, the public reference implementation inspected earlier does not implement the full BOS/MSB structure logic or the exact 16.5/25/50 ATR stop tiers associated with the TradingView fingerprint.

Those components should be implemented separately if the research objective is to reproduce the published JJ strategy more faithfully.

## Next research step

Use the independent implementation as a research baseline, then build a second version that explicitly models:

1. BOS/MSB
2. the exact displacement/counter-wick rule
3. ATR risk tiers 16.5 / 25 / 50
4. the first-3-minute exclusion
5. the stated session/reversion filters

That version can then be compared against the published 150-trade / 52% / 46R / PF 1.66 baseline without relying on proprietary source code.
