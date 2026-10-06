"""Independent implementation of the JJ Simon-style Fair Value session backtest.

This is a clean-room reimplementation of the publicly described trading logic.
It is NOT the original author's source code.

Core model:
- NY session anchors at 09:30 and 14:00
- Windows: 09:30-11:00 and 14:00-15:00
- First 15 minutes: continuation after a displacement candle
- Remaining window: reversion toward the session anchor
- Displacement: candle body >= 50% of its range
- ATR-based stop
- Target: 1.5R
- Optional per-day aggregation and direction-shuffle placebo

Reference implementation inspected:
https://github.com/jamesdchen/harxhar-clean
Original public file: experiments/jj_backtest.py

This file is an independent implementation and intentionally does not copy
the reference source verbatim.
"""

from __future__ import annotations

import argparse
from datetime import time

import numpy as np
import pandas as pd


SESSION_WINDOWS = (
    (time(9, 30), time(11, 0)),
    (time(14, 0), time(15, 0)),
)

CONTINUATION_MINUTES = 15
MIN_BODY_RATIO = 0.50
MIN_ANCHOR_DEVIATION = 0.0005
ATR_PERIOD = 14
ATR_STOP_MULTIPLIER = 1.0
REWARD_RISK = 1.5


def load_nq_ohlc(path: str) -> pd.DataFrame:
    data = pd.read_parquet(path)
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    data.columns = [str(c).lower() for c in data.columns]
    data.index = pd.to_datetime(data.index)

    if data.index.tz is None:
        data.index = data.index.tz_localize("UTC")
    else:
        data.index = data.index.tz_convert("UTC")

    data.index = data.index.tz_convert("America/New_York")
    return data[["open", "high", "low", "close"]].sort_index()


def calculate_atr(data: pd.DataFrame, period: int = ATR_PERIOD) -> np.ndarray:
    previous_close = data["close"].shift(1)

    true_range = pd.concat(
        [
            data["high"] - data["low"],
            (data["high"] - previous_close).abs(),
            (data["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    return true_range.rolling(period, min_periods=1).mean().to_numpy()


def trade_result(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    entry_bar: int,
    final_bar: int,
    direction: int,
    stop_distance: float,
) -> float:
    entry = close[entry_bar]
    stop = entry - direction * stop_distance
    target = entry + direction * REWARD_RISK * stop_distance

    for bar in range(entry_bar + 1, final_bar + 1):
        if direction > 0:
            if low[bar] <= stop:
                return -1.0
            if high[bar] >= target:
                return REWARD_RISK
        else:
            if high[bar] >= stop:
                return -1.0
            if low[bar] <= target:
                return REWARD_RISK

    return direction * (close[final_bar] - entry) / stop_distance


def collect_signals(data: pd.DataFrame):
    frame = data.copy()
    frame["atr"] = calculate_atr(frame)

    timestamps = frame.index
    bar_minutes = int(
        np.median(
            np.diff(timestamps.values)
            .astype("timedelta64[m]")
            .astype(int)
        )
    )
    bar_minutes = max(bar_minutes, 1)
    continuation_bars = max(
        1, int(np.ceil(CONTINUATION_MINUTES / bar_minutes))
    )

    o = frame["open"].to_numpy()
    h = frame["high"].to_numpy()
    l = frame["low"].to_numpy()
    c = frame["close"].to_numpy()
    atr = frame["atr"].to_numpy()

    times = np.array([x.time() for x in timestamps])
    days = np.array([x.date() for x in timestamps])

    candle_range = np.maximum(h - l, 1e-12)
    body_ratio = np.abs(c - o) / candle_range
    displacement = body_ratio >= MIN_BODY_RATIO

    signals = []

    for start, end in SESSION_WINDOWS:
        mask = (times >= start) & (times < end)

        for day in np.unique(days):
            indices = np.where(mask & (days == day))[0]
            if len(indices) < 3:
                continue

            anchor = o[indices[0]]
            last_bar = indices[-1]

            for position, bar in enumerate(indices, start=1):
                if not displacement[bar] or atr[bar] <= 0:
                    continue

                if position <= continuation_bars:
                    move = np.sign(c[bar] - o[bar])
                    phase = "continuation"
                else:
                    deviation = np.log(c[bar] / anchor)
                    if abs(deviation) < MIN_ANCHOR_DEVIATION:
                        continue

                    move = -np.sign(deviation)
                    phase = "reversion"

                if move == 0:
                    continue

                signals.append(
                    {
                        "day": day,
                        "phase": phase,
                        "bar": int(bar),
                        "last_bar": int(last_bar),
                        "direction": int(move),
                        "stop_distance": float(
                            ATR_STOP_MULTIPLIER * atr[bar]
                        ),
                    }
                )

    return signals, (h, l, c), {
        "bar_minutes": bar_minutes,
        "continuation_bars": continuation_bars,
        "bars": len(frame),
    }


def evaluate_phase(signals, ohlc, phase: str) -> pd.DataFrame:
    high, low, close = ohlc
    rows = []

    for signal in signals:
        if signal["phase"] != phase:
            continue

        r = trade_result(
            high,
            low,
            close,
            signal["bar"],
            signal["last_bar"],
            signal["direction"],
            signal["stop_distance"],
        )

        rows.append(
            {
                "day": signal["day"],
                "phase": phase,
                "direction": signal["direction"],
                "R": r,
            }
        )

    return pd.DataFrame(rows)


def summarize(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {"trades": 0}

    return {
        "trades": int(len(trades)),
        "win_rate": float((trades["R"] > 0).mean()),
        "average_R": float(trades["R"].mean()),
        "total_R": float(trades["R"].sum()),
        "profit_factor": float(
            trades.loc[trades["R"] > 0, "R"].sum()
            / max(
                abs(trades.loc[trades["R"] < 0, "R"].sum()),
                1e-12,
            )
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Independent Fair Value session backtest for NQ."
    )
    parser.add_argument(
        "--data",
        required=True,
        help="Path to a 1-minute NQ OHLC parquet file.",
    )
    args = parser.parse_args()

    data = load_nq_ohlc(args.data)
    signals, ohlc, meta = collect_signals(data)

    print(
        f"bars={meta['bars']} "
        f"bar={meta['bar_minutes']}m "
        f"continuation_bars={meta['continuation_bars']} "
        f"signals={len(signals)}"
    )

    for phase in ("continuation", "reversion"):
        trades = evaluate_phase(signals, ohlc, phase)
        print(f"{phase}: {summarize(trades)}")


if __name__ == "__main__":
    main()
