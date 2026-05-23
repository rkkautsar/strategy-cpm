"""Stitch QQQ with NDX index (^NDX) for pre-1999 warm-up.

NDX is the underlying index that QQQ tracks since QQQ inception (1999-03-10).
Pre-launch, the NDX index itself was published by NASDAQ from 1985-01-31.
Using NDX as a QQQ proxy pre-1999 is auditable: NDX existed and was
calculated and published by NASDAQ; QQQ tracks it with small drag
(expense ratio + dividends-not-reinvested).

This eliminates the synthetic QQQ pre-1999 dependency in the proxy file.
"""
import pandas as pd
import yfinance as yf
from pathlib import Path

OUT = Path(__file__).parent.parent.parent / 'data'

def dl(t, start='1985-01-01'):
    df = yf.download(t, start=start, end='2026-05-30', auto_adjust=True,
                      progress=False, threads=False)
    if isinstance(df.columns, pd.MultiIndex):
        df = df['Close']
    s = (df['Close'] if 'Close' in df.columns else df.iloc[:,0]).dropna()
    s.name = t
    return s

print('Downloading QQQ ...')
qqq = dl('QQQ', start='1999-03-01')
print(f'  QQQ: {qqq.index[0].date()} -> {qqq.index[-1].date()} ({len(qqq)} rows)')

print('Downloading NDX (^NDX) ...')
ndx = dl('^NDX')
print(f'  NDX: {ndx.index[0].date()} -> {ndx.index[-1].date()} ({len(ndx)} rows)')

splice = qqq.index[0]
ndx_anchor = ndx.index[ndx.index <= splice][-1]
scale = qqq.loc[splice] / ndx.loc[ndx_anchor]
print(f'  splice {splice.date()}: NDX {ndx.loc[ndx_anchor]:.2f} -> QQQ {qqq.loc[splice]:.4f} | scale {scale:.6f}')

ndx_scaled = ndx.loc[ndx.index < splice] * scale
stitched = pd.concat([ndx_scaled, qqq]).sort_index()
stitched = stitched[~stitched.index.duplicated(keep='last')]
stitched.name = 'QQQ'
print(f'  stitched: {stitched.index[0].date()} -> {stitched.index[-1].date()} ({len(stitched)} rows)')

# Sanity: check continuity around splice
pre = stitched.loc[stitched.index < splice].iloc[-1]
post = stitched.loc[splice]
print(f'  continuity: pre {pre:.4f} | post {post:.4f} | delta {(post-pre)/pre*100:+.2f}%')

out = OUT / 'qqq_stitched_daily.csv'
stitched.to_csv(out, header=True)
print(f'  Wrote {out}')
