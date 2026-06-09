from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
OPEN_CACHE = ROOT / "data" / "macro_opens"
OPEN_CACHE_INTRADAY_SANITY_MAX = 0.50
OHLC_TICKERS = ["SPY", "QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC", "SHV", "IEF", "HYG", "TIP"]


def _assert_open_cache_adjusted(opens_df, closes_df, threshold=OPEN_CACHE_INTRADAY_SANITY_MAX):
    intraday_abs = (closes_df / opens_df - 1.0).abs().replace([np.inf, -np.inf], np.nan)
    bad_mask = intraday_abs > threshold
    if not bool(bad_mask.to_numpy().any()):
        return
    bad = intraday_abs.where(bad_mask).stack(dropna=True)
    dt, ticker = bad.idxmax()
    val = float(bad.max())
    raise ValueError(
        "Open-cache contamination detected: "
        f"{ticker} {pd.Timestamp(dt).date()} has |close/open - 1|={val:.2%} "
        f"(>{threshold:.0%}) in {OPEN_CACHE}. "
        "Regenerate cache with yfinance auto_adjust=True for BOTH Open and Close."
    )


from data_loader import load_open_close  # noqa: F401  re-export: consumed via engine.load_open_close() in dashboard_engine; do NOT autoflake/ruff --fix away

_VALID_CONVENTIONS = frozenset({"moo", "mooex", "moc", "moc1"})


def _segment_returns_conv(
    close,
    daily_ret,
    weight_fn,
    start,
    end,
    convention,
    cost_bps,
    intraday_ret=None,
    overnight_ret=None,
):
    if convention not in _VALID_CONVENTIONS:
        raise ValueError(
            f"_segment_returns_conv: unknown convention {convention!r}; "
            f"valid: {sorted(_VALID_CONVENTIONS)}"
        )
    exec_lag = 1 if convention == "moc1" else 0
    monthly_idx = pd.DataFrame({"x": 1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    sigs = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()

    def apply_from_of(sig_d):
        fut = close.index[close.index > sig_d]
        if len(fut) <= exec_lag:
            return None
        return fut[exec_lag]

    hist = []
    prev_w = {}
    for i, sig_d in enumerate(sigs):
        w = weight_fn(sig_d)
        af = apply_from_of(sig_d)
        if af is None:
            continue
        if i + 1 < len(sigs):
            naf = apply_from_of(sigs[i + 1])
            end_apply = naf if naf is not None else end
        else:
            end_apply = end
        hist.append({"apply_from": af, "end_apply": end_apply, "weights": w, "prev_weights": prev_w})
        prev_w = w

    all_assets = sorted({a for h in hist for a in h["weights"]})
    cols = [a for a in all_assets if a in daily_ret.columns]
    df_w = pd.DataFrame(0.0, index=close.index, columns=cols)
    for h in hist:
        mask = (close.index >= h["apply_from"]) & (close.index < h["end_apply"])
        for a, ww in h["weights"].items():
            if a in df_w.columns:
                df_w.loc[mask, a] = ww
    ret = (df_w[cols] * daily_ret[cols]).sum(axis=1, min_count=1).fillna(0.0)

    # MOO conventions: override rebal-day (apply_from) return.
    #   moo   : conservative -> new basket earns intraday only (overnight gap dropped).
    #   mooex : exact realistic -> old basket earns overnight close[T]->open[af],
    #           then new basket earns intraday open[af]->close[af] (compounded).
    n_real, n_fallback = 0, 0
    if convention in ("moo", "mooex"):
        for h in hist:
            af = h["apply_from"]
            if af not in ret.index:
                continue
            ok = True

            def cc(a):
                return (
                    daily_ret.at[af, a]
                    if a in daily_ret.columns and pd.notna(daily_ret.at[af, a])
                    else 0.0
                )

            def intra(a):
                nonlocal ok
                if (
                    intraday_ret is not None
                    and a in intraday_ret.columns
                    and af in intraday_ret.index
                    and pd.notna(intraday_ret.at[af, a])
                ):
                    return intraday_ret.at[af, a]
                ok = False
                return None

            def on(a):
                nonlocal ok
                if (
                    overnight_ret is not None
                    and a in overnight_ret.columns
                    and af in overnight_ret.index
                    and pd.notna(overnight_ret.at[af, a])
                ):
                    return overnight_ret.at[af, a]
                ok = False
                return None

            if convention == "moo":
                val = 0.0
                for a, ww in h["weights"].items():
                    if a not in cols:
                        continue
                    iv = intra(a)
                    val += ww * (iv if iv is not None else cc(a))
                ret.loc[af] = val
            else:  # mooex
                on_c = 0.0
                for a, ww in h["prev_weights"].items():
                    if a not in cols:
                        continue
                    ov = on(a)
                    on_c += ww * (ov if ov is not None else 0.0)
                id_c = 0.0
                for a, ww in h["weights"].items():
                    if a not in cols:
                        continue
                    iv = intra(a)
                    id_c += ww * (iv if iv is not None else cc(a))
                ret.loc[af] = (1.0 + on_c) * (1.0 + id_c) - 1.0
            if ok:
                n_real += 1
            else:
                n_fallback += 1

    # turnover costs at each apply_from
    for i, h in enumerate(hist):
        prev_w = hist[i - 1]["weights"] if i > 0 else {}
        curr_w = h["weights"]
        keys = set(curr_w) | set(prev_w)
        turnover = sum(abs(curr_w.get(k, 0.0) - prev_w.get(k, 0.0)) for k in keys)
        cost = turnover * cost_bps / 10000.0
        af = h["apply_from"]
        if af in ret.index:
            ret.loc[af] -= cost
    return ret.loc[(ret.index >= start) & (ret.index <= end)], (n_real, n_fallback)
