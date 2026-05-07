"""Remove boilerplate wrappers from Datalab HTML snippets."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup


def clean_html_fragment(html: str) -> str:
    """Drop img-description shells and normalize whitespace."""
    if not html or not html.strip():
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.select("div.img-description"):
        tag.unwrap()
    for tag in soup.find_all("div", class_=re.compile(r"\bimg-alt\b")):
        tag.unwrap()
    for tag in soup.find_all(
        "div",
        style=re.compile(r"border:\s*1px solid", re.I),
    ):
        tag.unwrap()
    inner = soup.decode_contents().strip()
    out = re.sub(r"\s+", " ", inner)
    out = re.sub(r">\s+<", "><", out)
    out = out.strip()
    return out if out else html.strip()


def html_to_text(html: str) -> str:
    """Convert HTML fragment to plain text."""
    if not html or not html.strip():
        return ""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()
