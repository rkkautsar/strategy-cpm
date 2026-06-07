import re


def normalize_text(text: str) -> str:
    # Mask base64 PNGs
    text = re.sub(r"data:image/png;base64,[A-Za-z0-9+/=]+", "PNG", text)
    # Mask Git SHAs (7 to 40 hex chars)
    text = re.sub(r"\b[0-9a-f]{7,40}\b", "GITSHA", text)
    # Mask wall-clock timestamps
    text = re.sub(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]+", "TS", text)
    # Mask microsecond fractions
    text = re.sub(r"TS\.[0-9]+", "TS", text)
    # Mask built/on dates (volatile generation dates)
    text = re.sub(r"built \d{4}-\d{2}-\d{2}", "built DATE", text)
    text = re.sub(r"on \d{4}-\d{2}-\d{2}", "on DATE", text)
    # Mask volatile NDX snapshot date (changes every NDX refresh; not a behavior signal)
    text = re.sub(r"NDX snapshot \d{4}-\d{2}-\d{2}", "NDX snapshot DATE", text)

    # Mask Matplotlib random SVG IDs
    text = re.sub(r"\b[pm][0-9a-f]{10}\b", "MPLID", text)
    text = re.sub(r"#[pm][0-9a-f]{10}", "#MPLID", text)
    text = re.sub(r"\bC\d+_\d+_[0-9a-f]{10}\b", "MPLPATH", text)
    text = re.sub(r"#C\d+_\d+_[0-9a-f]{10}", "#MPLPATH", text)

    # Mask Matplotlib random image IDs
    text = re.sub(r"\bimage[0-9a-f]{10}\b", "MPLIMAGE", text)
    text = re.sub(r"#image[0-9a-f]{10}", "#MPLIMAGE", text)

    # Normalize stable sorting of table rows inside tbody to bypass python set-order randomization
    def sort_tbody(match: re.Match[str]) -> str:
        tbody_content = match.group(1)
        rows = re.findall(r"<tr>.*?</tr>", tbody_content, re.DOTALL)
        return "<tbody>" + "".join(sorted(rows)) + "</tbody>"

    text = re.sub(r"<tbody>(.*?)</tbody>", sort_tbody, text, flags=re.DOTALL)
    return text


def mask_html(text: str) -> str:
    """Backward-compatible alias for existing golden-master masking callsites."""
    return normalize_text(text)
