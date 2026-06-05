"""COHERENT-IV vs COHERENT-EW: apples-to-apples sizing significance.

ONE question: is COHERENT-IV (ivobj selection + IV sizing) SIGNIFICANTLY
different from COHERENT-EW (ewobj selection + EW sizing) on PATH-INDEPENDENT
metrics (Sharpe + Sortino + CVaR)? Each sizing paired with its OWN matched
variance objective = the fair sizing comparison. Prior coherence study only
bootstrapped Sharpe for this pair; Sortino/CVaR never tested.

Contrast d = COHERENT-IV - COHERENT-EW. Paired block bootstrap B=2000 seed=42,
block=21 (primary) and block=42 (robustness). Path-dependent metrics
(Calmar/Martin/MaxDD) reported as POINT-EST context only, both windows.

Throwaway research. Read-only re production; no prod/memo/cpm_live edits; no commit.

Run: .venv/bin/python -m research.cpm_coherent_iv_vs_ew_significance
Out: research/cpm_coherent_iv_vs_ew_significance_findings.md
"""

from __future__ import annotations

from pathlib import Path

from research import cpm_harness as H
from research.cpm_minvar_coherence import make_weight_fn
from research.cpm_bootstrap_multimetric import paired_block_bootstrap_mm

OUT_MD = Path(__file__).resolve().parent / "cpm_coherent_iv_vs_ew_significance_findings.md"


def _fmt(x, nd=4):
    if x is None or (isinstance(x, float) and x != x):
        return "n/a"
    return f"{x:.{nd}f}"


def main():
    data = H.load_data()
    anchor = H.verify_anchor(data=data)
    print("ANCHOR OK:", {k: round(float(v), 4) for k, v in anchor.items()
                         if k in ("Sharpe", "MaxDD", "Calmar")})

    wf_iv = make_weight_fn("minvar_ivobj", "invvol")  # COHERENT-IV
    wf_ew = make_weight_fn("minvar_ewobj", "ew")       # COHERENT-EW

    # return streams: clean (DECISION) + ext
    iv_clean = H.run_strategy(wf_iv, window="clean", data=data)
    ew_clean = H.run_strategy(wf_ew, window="clean", data=data)
    iv_ext = H.run_strategy(wf_iv, window="ext", data=data)
    ew_ext = H.run_strategy(wf_ew, window="ext", data=data)

    m_iv_clean = H.metrics(iv_clean, data=data)
    m_ew_clean = H.metrics(ew_clean, data=data)
    m_iv_ext = H.metrics(iv_ext, data=data)
    m_ew_ext = H.metrics(ew_ext, data=data)
    print("COHERENT-IV clean Sharpe", round(m_iv_clean["Sharpe"], 4),
          "COHERENT-EW clean Sharpe", round(m_ew_clean["Sharpe"], 4))

    cash = data.cash
    # contrast IV - EW; ra=IV, rb=EW => dMetric = IV - EW
    bs21 = paired_block_bootstrap_mm(iv_clean, ew_clean, cash, B=2000, block=21, seed=42)
    bs42 = paired_block_bootstrap_mm(iv_clean, ew_clean, cash, B=2000, block=42, seed=42)
    print("bootstrap done (block 21 + 42)")

    write_md(anchor, m_iv_clean, m_ew_clean, m_iv_ext, m_ew_ext, bs21, bs42)
    print("wrote", OUT_MD)


def _ci_excl(s):
    return (s["ci_lo"] > 0) or (s["ci_hi"] < 0)


def write_md(anchor, m_iv_c, m_ew_c, m_iv_e, m_ew_e, bs21, bs42):
    L = []
    L.append("# COHERENT-IV vs COHERENT-EW: apples-to-apples sizing significance\n")
    L.append("Throwaway research. Read-only re production; no prod/memo/cpm_live edits; no commit.\n")
    L.append(f"Anchor (clean, via harness): Sharpe {_fmt(anchor['Sharpe'])}, "
             f"MaxDD {_fmt(anchor['MaxDD'])}, Calmar {_fmt(anchor['Calmar'])}.\n")

    L.append("\n## Question\n")
    L.append("Is COHERENT-IV (ivobj selection + IV sizing) SIGNIFICANTLY different from "
             "COHERENT-EW (ewobj selection + EW sizing) on PATH-INDEPENDENT metrics "
             "(Sharpe + Sortino + CVaR)? Each sizing paired with its OWN matched variance "
             "objective = the fair apples-to-apples sizing comparison. Prior coherence study "
             "bootstrapped Sharpe ONLY for this pair (dSharpe +0.021 p0.71); Sortino/CVaR "
             "never tested.\n")

    L.append("\n## Method\n")
    L.append("- Engine: research/cpm_harness.py (mooex T+1, both-252, 10 bps/side). Anchor verified first.\n")
    L.append("- Cells (research/cpm_minvar_coherence.make_weight_fn): COHERENT-IV = minvar_ivobj + IV; "
             "COHERENT-EW = minvar_ewobj + EW. m=3 of top-4, full-risk-on-drop, else byte-identical to prod.\n")
    L.append("- Contrast d = COHERENT-IV - COHERENT-EW. Paired block bootstrap "
             "(research/cpm_bootstrap_multimetric) B=2000 seed=42, block=21 (primary) + block=42 (robustness). "
             "Path-independent metrics: Sharpe, Sortino, CVaR-ratio.\n")
    L.append("- Path-dependent metrics (Calmar/Martin/MaxDD): POINT-EST context only (CIs soft under block resampling).\n")

    L.append("\n## Point estimates (both windows)\n")
    L.append("| cell | window | Sharpe | Calmar | Martin | MaxDD |")
    L.append("|---|---|---|---|---|---|")
    L.append(f"| COHERENT-IV | clean | {_fmt(m_iv_c['Sharpe'])} | {_fmt(m_iv_c['Calmar'])} | "
             f"{_fmt(m_iv_c['Martin'])} | {_fmt(m_iv_c['MaxDD'])} |")
    L.append(f"| COHERENT-EW | clean | {_fmt(m_ew_c['Sharpe'])} | {_fmt(m_ew_c['Calmar'])} | "
             f"{_fmt(m_ew_c['Martin'])} | {_fmt(m_ew_c['MaxDD'])} |")
    L.append(f"| COHERENT-IV | ext | {_fmt(m_iv_e['Sharpe'])} | {_fmt(m_iv_e['Calmar'])} | "
             f"{_fmt(m_iv_e['Martin'])} | {_fmt(m_iv_e['MaxDD'])} |")
    L.append(f"| COHERENT-EW | ext | {_fmt(m_ew_e['Sharpe'])} | {_fmt(m_ew_e['Calmar'])} | "
             f"{_fmt(m_ew_e['Martin'])} | {_fmt(m_ew_e['MaxDD'])} |")

    L.append("\n## Significance: path-independent contrast d = COHERENT-IV - COHERENT-EW (clean)\n")
    L.append("Positive d = COHERENT-IV ahead. p>0 = bootstrap P(IV>EW).\n")
    for tag, bs in [("block=21 (primary)", bs21), ("block=42 (robustness)", bs42)]:
        L.append(f"\n### {tag}\n")
        L.append("| metric | mean | 95% CI | p(IV>EW) | CI excludes 0? |")
        L.append("|---|---|---|---|---|")
        for mk, name in [("dSharpe", "dSharpe"), ("dSortino", "dSortino"), ("dCVaR", "dCVaR")]:
            s = bs[mk]
            L.append(f"| {name} | {_fmt(s['mean'])} | [{_fmt(s['ci_lo'])}, {_fmt(s['ci_hi'])}] | "
                     f"{_fmt(s['p_gt0'], 3)} | {'YES' if _ci_excl(s) else 'no'} |")

    L.append("\n## Path-dependent context blocks (soft CIs -- NOT used for significance)\n")
    for tag, bs in [("block=21", bs21), ("block=42", bs42)]:
        L.append(f"\n### {tag}\n")
        L.append("| metric | mean | 95% CI | p(IV>EW) |")
        L.append("|---|---|---|---|")
        for mk in ("dCalmar", "dMartin", "dMaxDD"):
            s = bs[mk]
            L.append(f"| {mk} | {_fmt(s['mean'])} | [{_fmt(s['ci_lo'])}, {_fmt(s['ci_hi'])}] | "
                     f"{_fmt(s['p_gt0'], 3)} |")

    # verdict
    any_sig = []
    for mk in ("dSharpe", "dSortino", "dCVaR"):
        if _ci_excl(bs21[mk]) or _ci_excl(bs42[mk]):
            any_sig.append(mk)

    L.append("\n## Verdict\n")
    if not any_sig:
        L.append("INDISTINGUISHABLE. Every path-independent contrast (dSharpe, dSortino, dCVaR) "
                 "spans 0 at BOTH block sizes (21 and 42). COHERENT-IV is NOT significantly "
                 "different from COHERENT-EW on any path-independent metric. Even apples-to-apples "
                 "-- each sizing paired with its own matched variance objective -- the sizing/objective "
                 "choice is statistical noise.\n")
    else:
        names = ", ".join(any_sig)
        L.append(f"DIFFERENCE FOUND on: {names}. At least one path-independent contrast excludes 0. "
                 "See sign per metric below: positive mean => COHERENT-IV wins, negative => COHERENT-EW wins.\n")
        for mk in any_sig:
            s = bs21[mk]
            winner = "COHERENT-IV" if s["mean"] > 0 else "COHERENT-EW"
            L.append(f"- {mk}: mean {_fmt(s['mean'])} (block21 CI [{_fmt(s['ci_lo'])}, {_fmt(s['ci_hi'])}]) "
                     f"=> {winner} wins.\n")

    L.append("\nAll CIs (signed, both block sizes) tabulated above. Single in-sample test; "
             "path-independent metrics drive significance; path-dependent point-est is context only. "
             "No recommendation.\n")

    OUT_MD.write_text("\n".join(L))


if __name__ == "__main__":
    main()
