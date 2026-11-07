#!/usr/bin/env python3
"""Render the constrained Markdown design document to PDF using Chromium."""
import html
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def inline(value):
    return re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html.escape(value))


def render(markdown):
    lines = markdown.splitlines()
    output = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
        elif line == '<!-- pagebreak -->':
            output.append('<div class="pagebreak"></div>'); i += 1
        elif line.startswith('```'):
            i += 1; block = []
            while i < len(lines) and not lines[i].startswith('```'):
                block.append(lines[i]); i += 1
            output.append('<pre>' + html.escape('\n'.join(block)) + '</pre>'); i += 1
        elif line.startswith('#'):
            level = len(line) - len(line.lstrip('#'))
            output.append(f'<h{level}>{inline(line[level:].strip())}</h{level}>'); i += 1
        elif line.startswith('|'):
            rows = []
            while i < len(lines) and lines[i].startswith('|'):
                cells = [c.strip() for c in lines[i].strip('|').split('|')]
                if not all(re.fullmatch(r'[-: ]+', c) for c in cells):
                    rows.append(cells)
                i += 1
            output.append('<table>' + ''.join('<tr>' + ''.join(f'<{ "th" if n == 0 else "td" }>{inline(c)}</{ "th" if n == 0 else "td" }>' for c in row) + '</tr>' for n, row in enumerate(rows)) + '</table>')
        else:
            paragraph = []
            while i < len(lines) and lines[i].strip() and not lines[i].startswith(('```', '#', '|', '<!--')):
                paragraph.append(lines[i]); i += 1
            output.append('<p>' + inline(' '.join(paragraph)) + '</p>')
    return '\n'.join(output)


def main():
    chromium = shutil.which('chromium') or shutil.which('chromium-browser')
    if not chromium:
        raise SystemExit('Install Chromium to render the design PDF')
    css = '''@page{size:A4;margin:16mm 17mm} body{font-family:Arial,sans-serif;color:#172337;font-size:10.2pt;line-height:1.35} h1{font-size:20pt;color:#102c45;margin:0 0 8pt} h2{font-size:13pt;color:#126078;border-bottom:1px solid #9fb9bf;padding-bottom:3pt;margin:12pt 0 6pt} p{margin:6pt 0} pre{font-family:monospace;font-size:8.3pt;line-height:1.35;background:#edf3f4;padding:8pt;border-radius:4pt;white-space:pre-wrap} table{border-collapse:collapse;width:100%;font-size:9.4pt;margin:7pt 0} td,th{padding:3pt 6pt;border-bottom:1px solid #cddadd;text-align:left} th{background:#e8f1f2} .pagebreak{break-after:page}'''
    body = render((ROOT / 'docs/design.md').read_text(encoding='utf-8'))
    with tempfile.TemporaryDirectory(prefix='scholargraph-design-') as directory:
        path = Path(directory) / 'design.html'
        path.write_text('<!doctype html><html><head><meta charset="utf-8"><style>' + css + '</style></head><body>' + body + '</body></html>', encoding='utf-8')
        subprocess.run([chromium, '--headless', '--no-sandbox', '--disable-gpu', '--no-pdf-header-footer', f'--user-data-dir={directory}/profile', f'--print-to-pdf={ROOT / "docs/design.pdf"}', path.as_uri()], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print('Wrote docs/design.pdf')


if __name__ == '__main__':
    main()
