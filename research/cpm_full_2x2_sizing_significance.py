"""FULL 2x2 (selection objective x sizing) significance on the min-var 3-of-4 trio.

Completes the 2x2 INCLUDING the incoherent cells to settle whether sizing AND
objective AND coherence are uniformly statistical noise on the min-var trio.
A prior test (research/cpm_coherent_iv_vs_ew_significance) showed coherent-IV vs
coherent-EW indistinguishable; this ADDS the incoherent cells (esp. ivobj+EW) and
the cross-contrasts.

Four cells via research/cpm_minvar_coherence.make_weight_fn (m=3 of top-4,
both-252, full-risk-on-drop, else byte-identical to prod):
  1. COHERENT-EW   = ewobj + EW  (clean ~1.2711)  [matched]
  2. INCOHERENT-IV = ewobj + IV  (clean ~1.2622)  [= current prod min-var anchor; mismatch]
  3. COHERENT-IV   = ivobj + IV  (clean ~1.2501)  [matched]
  4. INCOHERENT-EW = ivobj + EW  (clean ~1.2509)  [mismatch -- min-var TARGETING inv-vol
                                                     weighting, then sized EQUAL-WEIGHT]

Pairwise contrasts (paired block bootstrap, B=2000 seed=42, block=21 + block=42),
path-independent metrics dSharpe + dSortino + dCVaR, 95% CI + p:
  C1 coherent-IV vs coherent-EW          (reproduce prior check)
  C2 INCOHERENT-EW vs COHERENT-EW        (objective effect under EW sizing)
  C3 INCOHERENT-IV(prod) vs COHERENT-IV  (objective effect under IV sizing)
  C4 EW vs IV WITHIN ewobj               (pure sizing at ewobj)
  C5 EW vs IV WITHIN ivobj               (pure sizing at ivobj)

Path-dependent context (Calmar/Martin/MaxDD) reported as POINT-EST only, both windows.

Throwaway research. Read-only re production; no prod/memo/cpm_live edits; no commit.

Run: .venv/bin/python -m research.cpm_full_2x2_sizing_significance
Out: research/cpm_full_2x2_sizing_significance_findings.md
"""

from __future__ import annotations

from pathlib import Path

from research import cpm_harness as H
from research.cpm_minvar_coherence import make_weight_fn
from research.cpm_bootstrap_multimetric import paired_block_bootstrap_mm

OUT_MD = Path(__file__).resolve().parent / "cpm_full_2x2_sizing_significance_findings.md"


def _fmt(x, nd=4):
    if x is None or (isinstance(x, float) and x != x):
        return "n/a"
    return f"{x:.{nd}f}"


def _ci_excl(s):
    return (s["ci_lo"] > 0) or (s["ci_hi"] < 0)


# 4 cells: (objective, sizing)
CELLS = {
    "COHERENT_EW":   ("minvar_ewobj", "ew"),     # matched
    "INCOHERENT_IV": ("minvar_ewobj", "invvol"),  # prod min-var anchor; mismatch
    "COHERENT_IV":   ("minvar_ivobj", "invvol"),  # matched
    "INCOHERENT_EW": ("minvar_ivobj", "ew"),      # mismatch
}
LABEL = {
    "COHERENT_EW":   "COHERENT-EW (ewobj + EW) [matched]",
    "INCOHERENT_IV": "INCOHERENT-IV (ewobj + IV) [= prod min-var; mismatch]",
    "COHERENT_IV":   "COHERENT-IV (ivobj + IV) [matched]",
    "INCOHERENT_EW": "INCOHERENT-EW (ivobj + EW) [mismatch]",
}

# pairwise contrasts: (ra_key, rb_key, description, "p(A>B)" label)
CONTRASTS = [
    ("C1", "COHERENT_IV", "COHERENT_EW",
     "C1 coherent-IV vs coherent-EW (prior check)", "p(cohIV>cohEW)"),
    ("C2", "INCOHERENT_EW", "COHERENT_EW",
     "C2 INCOHERENT-EW (ivobj+EW) vs COHERENT-EW (ewobj+EW): objective effect under EW sizing",
     "p(incEW>cohEW)"),
    ("C3", "INCOHERENT_IV", "COHERENT_IV",
     "C3 INCOHERENT-IV (ewobj+IV=prod) vs COHERENT-IV (ivobj+IV): objective effect under IV sizing",
     "p(incIV>cohIV)"),
    ("C4", "COHERENT_EW", "INCOHERENT_IV",
     "C4 EW vs IV WITHIN ewobj (pure sizing at ewobj): ewobj+EW - ewobj+IV",
     "p(EW>IV)"),
    ("C5", "INCOHERENT_EW", "COHERENT_IV",
     "C5 EW vs IV WITHIN ivobj (pure sizing at ivobj): ivobj+EW - ivobj+IV",
     "p(EW>IV)"),
]


def main():
    data = H.load_data()
    anchor = H.verify_anchor(data=data)
    print("ANCHOR OK:", {k: round(float(v), 4) for k, v in anchor.items()
                         if k in ("Sharpe", "MaxDD", "Calmar")})

    # build cells: clean + ext return streams + metrics
    clean_ret, ext_ret, m_clean, m_ext = {}, {}, {}, {}
    for key, (obj, sizing) in CELLS.items():
        wf = make_weight_fn(obj, sizing)
        clean_ret[key] = H.run_strategy(wf, window="clean", data=data)
        ext_ret[key] = H.run_strategy(wf, window="ext", data=data)
        m_clean[key] = H.metrics(clean_ret[key], data=data)
        m_ext[key] = H.metrics(ext_ret[key], data=data)
        print(f"cell {key}: clean Sharpe {m_clean[key]['Sharpe']:.4f} ext {m_ext[key]['Sharpe']:.4f}")

    cash = data.cash
    boots = {}  # contrast_id -> {21: bs, 42: bs}
    for cid, ra_key, rb_key, _desc, _plabel in CONTRASTS:
        ra, rb = clean_ret[ra_key], clean_ret[rb_key]
        boots[cid] = {
            21: paired_block_bootstrap_mm(ra, rb, cash, B=2000, block=21, seed=42),
            42: paired_block_bootstrap_mm(ra, rb, cash, B=2000, block=42, seed=42),
        }
        print(f"bootstrap done {cid} ({ra_key} - {rb_key})")

    write_md(anchor, m_clean, m_ext, boots)
    print("wrote", OUT_MD)


def write_md(anchor, m_clean, m_ext, boots):
    L = []
    L.append("# FULL 2x2 (selection objective x sizing) significance on the min-var 3-of-4 trio\n")
    L.append("Throwaway research. Read-only re production; no prod/memo/cpm_live edits; no commit.\n")
    L.append(f"Anchor (clean, via harness): Sharpe {_fmt(anchor['Sharpe'])}, "
             f"MaxDD {_fmt(anchor['MaxDD'])}, Calmar {_fmt(anchor['Calmar'])}.\n")

    L.append("\n## Question\n")
    L.append("Across the FULL 2x2 (selection objective {ewobj, ivobj} x sizing {EW, IV}) on the "
             "min-var 3-of-4 trio -- INCLUDING the incoherent (mismatched) cells -- are ALL pairwise "
             "differences within noise on the PATH-INDEPENDENT metrics (Sharpe/Sortino/CVaR), i.e. is "
             "sizing AND objective AND coherence uniformly statistical noise? A prior test "
             "(cpm_coherent_iv_vs_ew_significance) found coherent-IV vs coherent-EW indistinguishable; "
             "this adds the incoherent cells (esp. ivobj+EW) and the cross-contrasts.\n")

    L.append("\n## Method\n")
    L.append("- Engine: research/cpm_harness.py (mooex T+1, both-252, 10 bps/side). Anchor verified first.\n")
    L.append("- Cells via research/cpm_minvar_coherence.make_weight_fn (m=3 of top-4, full-risk-on-drop, "
             "else byte-identical to prod). objective in {minvar_ewobj, minvar_ivobj} x sizing in {EW, IV}.\n")
    L.append("- Pairwise contrasts: paired block bootstrap (research/cpm_bootstrap_multimetric) "
             "B=2000 seed=42, block=21 (primary) + block=42 (robustness). Path-independent metrics: "
             "dSharpe, dSortino, dCVaR. Contrast d = A - B (A = first cell named in the contrast).\n")
    L.append("- Path-dependent metrics (Calmar/Martin/MaxDD): POINT-EST context only (CIs soft under block resampling).\n")

    # ---- point table all 4 cells, both windows ----
    L.append("\n## Point estimates: all 4 cells, both windows (context)\n")
    L.append("| cell | window | Sharpe | Calmar | Martin | MaxDD |")
    L.append("|---|---|---|---|---|---|")
    order = ["COHERENT_EW", "INCOHERENT_IV", "COHERENT_IV", "INCOHERENT_EW"]
    for key in order:
        c = m_clean[key]
        L.append(f"| {LABEL[key]} | clean | {_fmt(c['Sharpe'])} | {_fmt(c['Calmar'])} | "
                 f"{_fmt(c['Martin'])} | {_fmt(c['MaxDD'])} |")
    for key in order:
        e = m_ext[key]
        L.append(f"| {LABEL[key]} | ext | {_fmt(e['Sharpe'])} | {_fmt(e['Calmar'])} | "
                 f"{_fmt(e['Martin'])} | {_fmt(e['MaxDD'])} |")

    # ---- pairwise contrasts ----
    L.append("\n## Significance: pairwise contrasts on path-independent metrics (clean)\n")
    L.append("Contrast d = A - B (A = first cell in the contrast name). Positive d = A ahead.\n")
    for cid, ra_key, rb_key, desc, plabel in CONTRASTS:
        L.append(f"\n### {desc}\n")
        for blk in (21, 42):
            tag = "primary" if blk == 21 else "robustness"
            bs = boots[cid][blk]
            L.append(f"\n**block={blk} ({tag})**\n")
            L.append(f"| metric | mean | 95% CI | {plabel} | CI excludes 0? |")
            L.append("|---|---|---|---|---|")
            for mk in ("dSharpe", "dSortino", "dCVaR"):
                s = bs[mk]
                L.append(f"| {mk} | {_fmt(s['mean'])} | [{_fmt(s['ci_lo'])}, {_fmt(s['ci_hi'])}] | "
                         f"{_fmt(s['p_gt0'], 3)} | {'YES' if _ci_excl(s) else 'no'} |")

    # ---- path-dependent context per contrast ----
    L.append("\n## Path-dependent context blocks (soft CIs -- NOT used for significance)\n")
    for cid, ra_key, rb_key, desc, plabel in CONTRASTS:
        L.append(f"\n### {desc}\n")
        for blk in (21, 42):
            bs = boots[cid][blk]
            L.append(f"\n**block={blk}**\n")
            L.append("| metric | mean | 95% CI | p>0 |")
            L.append("|---|---|---|---|")
            for mk in ("dCalmar", "dMartin", "dMaxDD"):
                s = bs[mk]
                L.append(f"| {mk} | {_fmt(s['mean'])} | [{_fmt(s['ci_lo'])}, {_fmt(s['ci_hi'])}] | "
                         f"{_fmt(s['p_gt0'], 3)} |")

    # ---- verdict ----
    sig_hits = []  # (cid, metric, block)
    for cid, ra_key, rb_key, desc, plabel in CONTRASTS:
        for blk in (21, 42):
            for mk in ("dSharpe", "dSortino", "dCVaR"):
                if _ci_excl(boots[cid][blk][mk]):
                    sig_hits.append((cid, mk, blk))

    L.append("\n## Verdict\n")
    if not sig_hits:
        L.append("UNIFORM NOISE. Across the FULL 2x2 (all matched and mismatched cells), EVERY pairwise "
                 "contrast (C1-C5) on EVERY path-independent metric (dSharpe, dSortino, dCVaR) spans 0 at "
                 "BOTH block sizes (21 and 42). On the min-var 3-of-4 trio, SIZING (EW vs IV), OBJECTIVE "
                 "(ewobj vs ivobj), and COHERENCE (matched vs mismatched) are ALL statistical noise on the "
                 "path-independent metrics. The incoherent cells -- including ivobj+EW (min-var TARGETING "
                 "inv-vol, then sized equal-weight) -- are indistinguishable from the coherent ones.\n")
    else:
        names = ", ".join(f"{c}/{m}@blk{b}" for c, m, b in sig_hits)
        L.append(f"NOT uniform noise. At least one path-independent contrast excludes 0: {names}. "
                 "Per significant contrast (sign of mean indicates winner):\n")
        seen = set()
        for cid, mk, blk in sig_hits:
            if (cid, mk) in seen:
                continue
            seen.add((cid, mk))
            s = boots[cid][blk][mk]
            desc = next(d for c, _ra, _rb, d, _p in CONTRASTS if c == cid)
            direction = "A>B" if s["mean"] > 0 else "B>A"
            L.append(f"- {cid} {mk} (block {blk}): mean {_fmt(s['mean'])} CI [{_fmt(s['ci_lo'])}, "
                     f"{_fmt(s['ci_hi'])}] => {direction}. ({desc})\n")

    L.append("\nDISCIPLINE: single in-sample test; path-independent metrics drive significance; "
             "path-dependent point-est is context only. All CIs (signed) reported at BOTH block sizes. "
             "Wide CIs = LOW POWER: 'cannot distinguish' is NOT 'proven equal'. No recommendation.\n")

    OUT_MD.write_text("\n".join(L))


if __name__ == "__main__":
    main()
