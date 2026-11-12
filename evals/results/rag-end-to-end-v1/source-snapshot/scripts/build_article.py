"""Publish the reviewed technical narrative as a static personal-blog article."""

import html
import re
from pathlib import Path


def build():
    text = Path("docs/TECHNICAL_WRITEUP.md").read_text(encoding="utf-8")
    words = len(
        re.findall(r"\S+", "\n".join(s for s in text.splitlines() if not s.startswith("#")))
    )  # noqa: E501
    if not 1200 <= words <= 1800:
        raise ValueError("Technical article must have 1,200–1,800 narrative words")
    blocks = []
    for paragraph in text.strip().split("\n\n"):
        content = html.escape(paragraph.strip())
        if content.startswith("# "):
            blocks.append("<h1>" + content[2:] + "</h1>")
        elif content.startswith("## "):
            blocks.append("<h2>" + content[3:] + "</h2>")
        else:
            blocks.append("<p>" + content.replace("\n", " ") + "</p>")
    body = "\n".join(blocks)
    document = (
        """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description"
content="What 150 GigBid runs revealed about correctness, completion, and approval boundaries.">
<title>GigBid: correct decisions, incomplete proposals — Raahim Ibrar</title>
<style>
:root{color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:#101014;color:#e9e7ef;font:18px/1.85 system-ui,sans-serif}
a{color:#bc9aff;text-underline-offset:4px}
header,main,footer{max-width:800px;margin:auto;padding:28px}
header{border-bottom:1px solid #30303a;display:flex;justify-content:space-between;font-size:14px}
header a{color:#d0b6ff}
article{padding:40px 0 64px}
h1{font-size:clamp(34px,5vw,52px);line-height:1.16;letter-spacing:-1.6px;margin:14px 0 40px}
h2{font-size:26px;line-height:1.35;color:#c7a8ff;margin:48px 0 18px}
p{margin:0 0 24px;color:#ceccd6}
.eyebrow{font:13px/1.5 system-ui;color:#a5a0b3;letter-spacing:.08em;text-transform:uppercase}
.sources{border:1px solid #363041;background:#19151f;padding:24px;border-radius:12px;font-size:15px}
footer{border-top:1px solid #30303a;font-size:13px;color:#aaa3b6;padding-bottom:60px}
.skip{position:absolute;left:-9999px}
.skip:focus{left:20px;top:10px;background:#171321;padding:12px}
</style>
</head>
<body>
<a class="skip" href="#article">Skip to article</a>
<header>
<a href="https://github.com/raahim-ibrar">Raahim Ibrar · Engineering notes</a>
<a href="https://github.com/raahim-ibrar/GigBidA2">Project source ↗</a>
</header>
<main id="article">
<article>
<div class="eyebrow">12 November 2026 · Agent systems · """
        + str(words)
        + """ words</div>
"""
        + body
        + """
<aside class="sources">
<strong>Inspect the evidence</strong>
<p>All reported experiments use declared cohorts. Simulator outcomes are synthetic,
and failures remain in the results.</p>
<a href="https://github.com/raahim-ibrar/GigBidA2/tree/main/evals/results">
Results and raw records</a> ·
<a href="https://github.com/raahim-ibrar/GigBidA2/blob/main/docs/AI_USAGE.md">
AI assistance disclosure</a> ·
<a href="https://github.com/raahim-ibrar/GigBidA2/blob/main/output/pdf/GigBid_RnD_Report.pdf">
Engineering report</a>
</aside>
</article>
</main>
<footer>Written by Raahim Ibrar with disclosed AI assistance. Built for AI-4016.
Research findings are distinguished from deterministic control tests.</footer>
</body>
</html>"""
    )
    Path("docs/index.html").write_text(document, encoding="utf-8")
    Path("docs/.nojekyll").touch()
    print("Static article generated:", words, "narrative words")


if __name__ == "__main__":
    build()
