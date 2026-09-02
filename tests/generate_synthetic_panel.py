"""Generate deterministic, non-market panel data for local validation."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def main() -> int:
    dates = pd.bdate_range("2025-01-02", periods=140)
    rows: list[dict[str, object]] = []
    for symbol_no in range(8):
        symbol = f"SYNTH{symbol_no + 1:02d}"
        for day_no, date in enumerate(dates):
            base = 100 + symbol_no * 3 + day_no * 0.04
            cycle = np.sin((day_no + symbol_no) / 7) * 0.8
            close = base + cycle
            open_ = close * (1 + np.cos(day_no / 9) * 0.001)
            rows.append(
                {
                    "date": date.strftime("%Y%m%d"),
                    "symbol": symbol,
                    "open": round(open_, 4),
                    "high": round(max(open_, close) * 1.004, 4),
                    "low": round(min(open_, close) * 0.996, 4),
                    "close": round(close, 4),
                    "volume": int(1_000_000 + symbol_no * 20_000 + day_no * 1_000),
                    "amount": round(close * (1_000_000 + symbol_no * 20_000 + day_no * 1_000), 2),
                }
            )
    output = Path(__file__).with_name("synthetic_panel.csv")
    pd.DataFrame(rows).to_csv(output, index=False)
    print(f"Wrote {len(rows)} synthetic rows to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
