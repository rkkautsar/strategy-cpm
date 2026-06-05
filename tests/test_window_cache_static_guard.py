from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_g8_static_no_prod_reference_to_research_window_cache() -> None:
    targets = [
        ROOT / "dashboard_engine.py",
        ROOT / "build_dashboard.py",
        ROOT / "cpm_live.py",
        *sorted((ROOT / "tools" / "golden_master").glob("*.py")),
    ]

    banned = ("get_sleeve_window", "research.window_cache")
    hits: list[str] = []

    for path in targets:
        text = path.read_text(encoding="utf-8")
        for token in banned:
            if token in text:
                hits.append(f"{path.relative_to(ROOT)} contains {token}")

    assert not hits, "\n".join(hits)
