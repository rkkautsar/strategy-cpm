"""Build audited stitches for SHV, IEF, TLT, GLD using public Vanguard mutual
funds and London Gold Fix. Replaces opaque pre-live data in
proxy_adjusted_close_daily.csv with documented sources.

Stitches:
  SHV (2007-01-05+) <- VFISX (Vanguard Short-Term Treasury, 1991-10-28+)
  IEF (2002-07-22+) <- VFITX (Vanguard Intermediate-Term Treasury, 1991-10-28+)
  TLT (2002-07-22+) <- VUSTX (Vanguard Long-Term Treasury, 1986-05-19+)
  GLD (2004-11-18+) <- GOLDAMGBD228NLBM (FRED London PM Gold Fix, 1968-04-01+)
                       or yfinance GC=F (gold futures, varies)

All Vanguard funds tracked daily via yfinance with auto_adjust=True
(total return adjustment). FRED gold data downloaded directly.
"""
import pandas as pd
import numpy as np
import yfinance as yf
from pathlib import Path

OUT_DIR = Path(__file__).parent.parent.parent / 'data'
OUT_DIR.mkdir(exist_ok=True)


def download_yf(ticker, start='1985-01-01', end='2026-05-30'):
    df = yf.download(ticker, start=start, end=end, auto_adjust=True,
                      progress=False, threads=False)
    if isinstance(df.columns, pd.MultiIndex):
        df = df['Close']
    if hasattr(df, 'columns') and 'Close' in df.columns:
        s = df['Close']
    else:
        s = df.iloc[:, 0] if hasattr(df, 'iloc') else df
    s = s.dropna()
    s.name = ticker
    return s


def stitch(live_ticker, proxy_ticker, splice_lookback_days=5):
    """Stitch proxy series into live ETF at the live inception date,
    rescaling proxy so it joins continuously."""
    print(f'  Live {live_ticker} ...')
    live = download_yf(live_ticker)
    print(f'    range: {live.index[0].date()} -> {live.index[-1].date()}')

    print(f'  Proxy {proxy_ticker} ...')
    proxy = download_yf(proxy_ticker)
    print(f'    range: {proxy.index[0].date()} -> {proxy.index[-1].date()}')

    splice = live.index[0]
    # Find proxy anchor just before splice
    proxy_anchor_date = proxy.index[proxy.index <= splice]
    if len(proxy_anchor_date) == 0:
        raise ValueError(f'Proxy {proxy_ticker} starts after live {live_ticker}')
    proxy_anchor_date = proxy_anchor_date[-1]
    scale = live.loc[splice] / proxy.loc[proxy_anchor_date]
    proxy_scaled = proxy.loc[proxy.index < splice] * scale
    stitched = pd.concat([proxy_scaled, live]).sort_index()
    stitched = stitched[~stitched.index.duplicated(keep='last')]
    print(f'    splice {splice.date()}: scale {scale:.6f}')
    print(f'    stitched: {stitched.index[0].date()} -> {stitched.index[-1].date()} '
          f'({len(stitched)} rows)')
    return stitched


def fetch_lbma_gold():
    """LBMA PM Gold Fix from FRED via pandas-datareader."""
    from pandas_datareader import data as pdr
    print('  Fetching FRED GOLDAMGBD228NLBM (LBMA PM Gold Fix) ...')
    df = pdr.DataReader('GOLDAMGBD228NLBM', 'fred', start='1968-01-01', end='2026-05-30')
    s = df['GOLDAMGBD228NLBM'].dropna()
    s.name = 'LBMA_GOLD'
    print(f'    LBMA Gold: {s.index[0].date()} -> {s.index[-1].date()} ({len(s)} rows)')
    return s


def stitch_gld_lbma():
    print('  Live GLD ...')
    gld = download_yf('GLD')
    print(f'    range: {gld.index[0].date()} -> {gld.index[-1].date()}')

    gold = fetch_lbma_gold()
    splice = gld.index[0]
    gold_anchor = gold.index[gold.index <= splice]
    if len(gold_anchor) == 0:
        raise ValueError('LBMA Gold ends before GLD inception')
    gold_anchor = gold_anchor[-1]
    scale = gld.loc[splice] / gold.loc[gold_anchor]
    gold_scaled = gold.loc[gold.index < splice] * scale
    # Forward-fill LBMA to trading days
    stitched = pd.concat([gold_scaled, gld]).sort_index()
    stitched = stitched[~stitched.index.duplicated(keep='last')]
    print(f'    splice {splice.date()}: scale {scale:.6f}')
    print(f'    stitched: {stitched.index[0].date()} -> {stitched.index[-1].date()} '
          f'({len(stitched)} rows)')
    return stitched


def save(s, col_name, fname):
    s.name = col_name
    out = OUT_DIR / fname
    s.to_csv(out, header=True)
    print(f'  Wrote {out}')


def main():
    print('=== SHV <- VFISX (Vanguard Short-Term Treasury) ===')
    save(stitch('SHV', 'VFISX'), 'SHV', 'shv_stitched_daily.csv')

    print('\n=== IEF <- VFITX (Vanguard Intermediate-Term Treasury) ===')
    save(stitch('IEF', 'VFITX'), 'IEF', 'ief_stitched_daily.csv')

    print('\n=== TLT <- VUSTX (Vanguard Long-Term Treasury) ===')
    save(stitch('TLT', 'VUSTX'), 'TLT', 'tlt_stitched_daily.csv')

    print('\n=== GLD <- LBMA London PM Gold Fix (FRED) ===')
    save(stitch_gld_lbma(), 'GLD', 'gld_stitched_lbma.csv')


if __name__ == '__main__':
    main()
