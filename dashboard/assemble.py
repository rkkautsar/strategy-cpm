from __future__ import annotations
import argparse
from types import SimpleNamespace
from dashboard import shell, sections

SECTIONS = [
    sections.allocation.render,
    sections.headline.render,
    sections.performance_detail.render,
    sections.spec.render_summary,
    sections.sleeve_breakdown.render,
    sections.alpha_beta.render,
    sections.charts_analysis.render,
    sections.spec.render_details,
    sections.caveats.render,
]

def build(args, ctx: SimpleNamespace) -> str:
    html = shell.render_head(ctx) + "\n\n".join(fn(ctx) for fn in SECTIONS) + shell.render_footer(ctx)
    return html
