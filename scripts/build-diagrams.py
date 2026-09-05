"""Bake the theme-neutral diagram sources into light and dark SVG files.

Mintlify's MDX compiler strips most SVG child tags (text, circle, marker,
title), so diagrams cannot be inlined. Each source in images/diagrams/src/
uses only dg-* classes; this script resolves those classes against the
tokens in style.css and writes <name>-light.svg and <name>-dark.svg next
to them, with the styles embedded. Pages embed both with Mintlify's
block/dark:hidden image pattern. Run after editing a source or style.css:

    python scripts/build-diagrams.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "images" / "diagrams" / "src"
OUT = ROOT / "images" / "diagrams"
CSS = re.sub(r"/\*.*?\*/", "", (ROOT / "style.css").read_text(encoding="utf-8"), flags=re.S)


def block(selector: str) -> str:
    m = re.search(re.escape(selector) + r"\s*\{(.*?)\}", CSS, re.S)
    if not m:
        raise SystemExit(f"style.css: no {selector} block")
    return m.group(1)


def tokens(selector: str) -> dict:
    return dict(re.findall(r"(--dg-[\w-]+)\s*:\s*([^;]+);", block(selector)))


def class_rules() -> list:
    rules = []
    for sel, body in re.findall(r"^([^@{}/][^{}]*?)\s*\{([^}]*)\}", CSS, re.M):
        sel = sel.strip()
        if not sel.startswith(".dg-") or sel.startswith(".dg-scroll"):
            continue
        rules.append((sel, " ".join(body.split())))
    rules.append(("text", " ".join(block(".dg-scroll text").split())))
    return rules


def stylesheet(theme_tokens: dict) -> str:
    def resolve(body: str) -> str:
        return re.sub(r"var\((--dg-[\w-]+)\)", lambda m: theme_tokens[m.group(1)], body)
    return "\n".join(f"    {sel} {{ {resolve(body)} }}" for sel, body in class_rules())


def bake(src: Path, theme: str, theme_tokens: dict) -> Path:
    svg = src.read_text(encoding="utf-8")
    vb = re.search(r'viewBox="0 0 (\d+) (\d+)"', svg)
    if not vb:
        raise SystemExit(f"{src.name}: viewBox must be 0 0 W H")
    w, h = vb.groups()
    open_tag = re.match(r"<svg[^>]*>", svg)
    head = open_tag.group(0)
    if "xmlns=" not in head:
        head = head.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"', 1)
    if "width=" not in head:
        head = head.replace(">", f' width="{w}" height="{h}">', 1)
    style = f"\n  <style>\n{stylesheet(theme_tokens)}\n  </style>"
    baked = head + style + svg[open_tag.end():]
    out = OUT / f"{src.stem}-{theme}.svg"
    out.write_text(baked, encoding="utf-8", newline="\n")
    return out


if __name__ == "__main__":
    light, dark = tokens(":root"), tokens(".dark")
    missing = set(light) ^ set(dark)
    if missing:
        raise SystemExit(f"style.css: tokens differ between :root and .dark: {missing}")
    for src in sorted(SRC.glob("*.svg")):
        for theme, t in (("light", light), ("dark", dark)):
            print(bake(src, theme, t).relative_to(ROOT))
