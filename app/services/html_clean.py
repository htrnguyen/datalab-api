from __future__ import annotations

import re

from bs4 import BeautifulSoup


def html_to_text(html: str) -> str:
    if not html or not html.strip():
        return ""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()
