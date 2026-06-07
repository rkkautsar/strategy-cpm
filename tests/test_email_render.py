import importlib.util
from pathlib import Path


def _load_markdown_to_html():
    module_path = Path(__file__).resolve().parents[1] / "deploy" / "cf-pages" / "send_email.py"
    spec = importlib.util.spec_from_file_location("send_email", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.markdown_to_html


markdown_to_html = _load_markdown_to_html()


def test_markdown_to_html_renders_telegram_format_with_literal_regimes():
    msg = "\n".join(
        [
            "📈 *Bold Header*",
            "Signal date: `2026-06-30`",
            "CPM: RISK_ON · NDX: NDX_ACTIVE · VAL: WEIGHTED_GUARDED · RPV: RISK_OFF",
            "_italic text_",
            "`AAPL` 10%",
            "`MSFT` 20%",
        ]
    )

    html = markdown_to_html(msg)

    assert "<strong>Bold Header</strong>" in html
    assert "<em>Bold Header</em>" not in html
    assert "<em>italic text</em>" in html
    assert "<code>AAPL</code>" in html
    assert "<code>MSFT</code>" in html

    regime_line = "CPM: RISK_ON · NDX: NDX_ACTIVE · VAL: WEIGHTED_GUARDED · RPV: RISK_OFF"
    assert regime_line in html
    assert "RISK<em>ON" not in html
    assert "NDX<em>ACTIVE" not in html
    assert "WEIGHTED<em>GUARDED" not in html

    assert "<br" in html
    assert "<code>AAPL</code> 10%<br" in html
