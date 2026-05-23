"""Extend GLD stitch back further using free monthly World Bank gold data
from freegoldapi.com. Eliminates the 1999-03 to 2000-08 EXT PP gap.

Pipeline:
  Live GLD (2004-11+) <- existing daily CSV stitch (2000-08-30+)
                      <- World Bank monthly gold (1960+ via freegoldapi.com)

Monthly granularity is fine because the strategy month-end rebalances.
"""
import pandas as pd
import numpy as np
from pathlib import Path

OUT = Path(__file__).parent.parent.parent / 'data'

print('Loading existing GLD stitch ...')
existing = pd.read_csv(OUT / 'gld_stitched_daily_clean.csv', parse_dates=['Date'],
                       index_col='Date').sort_index()
existing = existing['GLD']
print(f'  range: {existing.index[0].date()} -> {existing.index[-1].date()}')

print('Fetching freegoldapi.com (World Bank monthly + others) ...')
url = 'https://freegoldapi.com/data/latest.csv'
df = pd.read_csv(url, parse_dates=['date'])
df = df.sort_values('date').reset_index(drop=True)
# Only USD entries (World Bank is USD); some MeasuringWorth older are GBP
df['source_lower'] = df['source'].str.lower()
wb = df[df['source_lower'].str.contains('worldbank', na=False)].copy()
wb = wb[['date','price']].set_index('date').sort_index()
print(f'  WB monthly: {wb.index[0].date()} -> {wb.index[-1].date()} ({len(wb)} rows)')

# Pre-2000-08-30 portion
splice = existing.index[0]  # 2000-08-30
wb_pre = wb.loc[wb.index < splice]
print(f'  WB pre-splice: {wb_pre.index[0].date()} -> {wb_pre.index[-1].date()} ({len(wb_pre)} rows)')

# Anchor: scale WB so that WB at end-of-July 2000 matches existing GLD on 2000-08-30
# Use last WB point before splice
wb_anchor_date = wb_pre.index[-1]
wb_anchor_price = wb_pre.iloc[-1, 0]
existing_anchor = existing.iloc[0]  # 2000-08-30 value
scale = existing_anchor / wb_anchor_price
print(f'  anchor: WB {wb_anchor_date.date()} = {wb_anchor_price:.2f} | GLD {splice.date()} = {existing_anchor:.4f}')
print(f'  scale: {scale:.6f}')

# Forward-fill WB monthly to business days
business_days = pd.bdate_range(start='1995-01-01', end=splice - pd.Timedelta(days=1))
wb_scaled = (wb_pre['price'] * scale)
wb_daily = wb_scaled.reindex(business_days, method='ffill')
wb_daily = wb_daily.dropna()
wb_daily.name = 'GLD'
print(f'  WB ffilled to daily: {wb_daily.index[0].date()} -> {wb_daily.index[-1].date()} ({len(wb_daily)} rows)')

# Stitch
stitched = pd.concat([wb_daily, existing]).sort_index()
stitched = stitched[~stitched.index.duplicated(keep='last')]
print(f'  stitched: {stitched.index[0].date()} -> {stitched.index[-1].date()} ({len(stitched)} rows)')

# Sanity check: continuity at splice
pre_val = stitched.loc[stitched.index < splice].iloc[-1]
post_val = stitched.loc[splice]
print(f'  continuity check: pre-splice {pre_val:.4f} | at-splice {post_val:.4f} | delta {(post_val-pre_val)/pre_val*100:+.2f}%')

# Save
out_path = OUT / 'gld_stitched_extended_daily.csv'
stitched.to_csv(out_path, header=True)
print(f'  Wrote {out_path}')
print(f'\nNote: pre-2000-08 portion is forward-filled monthly World Bank data,')
print(f'so daily volatility pre-2000-08 understated. Monthly returns at signal')
print(f'dates are correct.')
