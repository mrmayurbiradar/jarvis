#!/usr/bin/env python3
"""Serve the JARVIS docs directory as rendered HTML.

- `.md` files are rendered to styled HTML (tables, code highlighting).
- Directory listings are generated with links (index-style).
- All other files are served as-is.
- Only intended for local development preview; binds localhost by default.
"""
import argparse
import http.server
import io
import os
import posixpath
import re
import urllib.parse
from pathlib import Path

import markdown
from pygments.formatters import HtmlFormatter
from pygments.styles import get_style_by_name

ROOT = Path(__file__).resolve().parent.parent
STYLE = get_style_by_name("github-dark")

INDEX_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{css}</style>
</head>
<body>
<header><h1>{title}</h1></header>
<main>
{crumbs}
{content}
</main>
<footer>JARVIS docs preview &middot; served by <code>scripts/serve_docs.py</code></footer>
</body>
</html>
"""


def crumbs_for(path: str) -> str:
    parts = [p for p in path.split("/") if p]
    items = ['<a href="/">home</a>']
    acc = ""
    for p in parts:
        acc += "/" + p
        items.append(f'<a href="{acc}/">{p}</a>')
    return '<nav class="crumbs">' + " / ".join(items) + "</nav>"


def render_markdown(text: str, title: str) -> str:
    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "toc", "codehilite"],
        extension_configs={
            "codehilite": {"css_class": "highlight", "guess_lang": False},
        },
    )
    body = md.convert(text)
    css = BASE_CSS + HtmlFormatter(style=STYLE).get_style_defs(".highlight")
    return INDEX_TEMPLATE.format(title=title, css=css, crumbs="", content=body)


def render_index(path: str, entries: list[str]) -> str:
    rows = []
    for name in sorted(entries):
        href = name + ("/" if os.path.isdir(posixpath.join(ROOT, path, name)) else "")
        rows.append(f'<li><a href="{href}">{name}</a></li>')
    content = f"<ul class=\"listing\">{''.join(rows)}</ul>"
    css = BASE_CSS
    return INDEX_TEMPLATE.format(title=f"Index: /{path}", css=css, crumbs=crumbs_for(path), content=content)


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def send_head(self):
        path = urllib.parse.unquote(self.path)
        path = posixpath.normpath(path).lstrip("/")
        full = (ROOT / path).resolve()
        # keep requests inside ROOT
        if not str(full).startswith(str(ROOT)):
            self.send_error(403)
            return None
        if full.is_dir():
            if not self.path.endswith("/"):
                self.send_response(301)
                self.send_header("Location", self.path + "/")
                self.end_headers()
                return None
            entries = [p for p in full.iterdir() if not p.name.startswith(".")]
            body = render_index(path, [p.name for p in entries]).encode()
            return self._html(body)
        if full.suffix.lower() in (".md", ".markdown"):
            try:
                text = full.read_text(encoding="utf-8")
            except OSError:
                self.send_error(404)
                return None
            body = render_markdown(text, full.name).encode()
            return self._html(body)
        return super().send_head()

    def _html(self, body: bytes) -> io.BytesIO:
        """Send an HTML response; return a file-like object for copyfile()."""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        return io.BytesIO(body)

    def log_message(self, fmt, *args):
        pass  # quiet


BASE_CSS = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body {
  margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
  Helvetica, Arial, sans-serif; line-height: 1.6; color: #e6e6e6;
  background: #111418; padding-bottom: 4rem;
}
header { border-bottom: 1px solid #2a2f37; padding: 1.2rem 1.5rem;
  background: #161b22; }
header h1 { margin: 0; font-size: 1.35rem; font-weight: 600; }
main { max-width: 900px; margin: 0 auto; padding: 1.5rem; }
nav.crumbs { font-size: .9rem; margin-bottom: 1.2rem; color: #8b949e; }
nav.crumbs a { color: #58a6ff; text-decoration: none; }
nav.crumbs a:hover { text-decoration: underline; }
a { color: #58a6ff; }
h1, h2, h3, h4 { color: #f0f6fc; line-height: 1.3; margin-top: 1.8em; }
h1 { border-bottom: 1px solid #2a2f37; padding-bottom: .3em; }
h2 { border-bottom: 1px solid #262b33; padding-bottom: .3em; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: .92rem; }
th, td { border: 1px solid #2a2f37; padding: .45rem .6rem; text-align: left; }
th { background: #1c2128; }
tr:nth-child(even) td { background: #161b22; }
pre { padding: .9rem; border-radius: 6px; overflow-x: auto; background: #0d1117;
  border: 1px solid #262b33; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: .88em; }
:not(pre) > code { background: #1c2128; padding: .12em .35em; border-radius: 4px; }
blockquote { border-left: 3px solid #30363d; margin: 1em 0; padding: .2em 1em;
  color: #8b949e; }
ul.listing { list-style: none; padding: 0; }
ul.listing li { padding: .5rem .75rem; border-bottom: 1px solid #262b33; }
ul.listing a { text-decoration: none; font-weight: 500; }
ul.listing a:hover { text-decoration: underline; }
footer { text-align: center; color: #6e7681; font-size: .8rem; margin-top: 2rem; }
hr { border: 0; border-top: 1px solid #2a2f37; margin: 2rem 0; }
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    print(f"Serving {ROOT} at http://{args.host}:{args.port}/")
    http.server.ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()