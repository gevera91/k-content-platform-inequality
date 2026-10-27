#!/usr/bin/env python3
"""Build the frozen Korean TeX report with locally discovered Un fonts.

The published sources and final PDF are kept unchanged. Only a temporary build
copy receives the local font directory, and output is written to build/.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FONTS = ('UnBatang.ttf', 'UnBatangBold.ttf', 'UnDotum.ttf', 'UnDotumBold.ttf')

def dependencies():
    found = set()
    todo = ['kakao_enter.tex', 'kakao_report_style.sty', 'latexmkrc']
    while todo:
        rel = todo.pop()
        if rel in found:
            continue
        path = ROOT / rel
        if not path.is_file():
            raise FileNotFoundError(f'Required report input is missing: {rel}')
        found.add(rel)
        if path.suffix in ('.tex', '.sty', '.cls'):
            text = path.read_text(encoding='utf-8')
            for kind, target in re.findall(r'\\(input|include|includegraphics)(?:\[[^\]]*\])?\{([^}]+)\}', text):
                if not Path(target).suffix:
                    suffixes = ('.pdf', '.png', '.jpg') if kind == 'includegraphics' else ('.tex',)
                    target = next((target+s for s in suffixes if (ROOT/(target+s)).is_file()), target)
                todo.append(target)
    return sorted(found)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font-dir', type=Path, help='Folder containing the four Un*.ttf fonts')
    parser.add_argument('--check-only', action='store_true', help='Check inputs, TeX tools and fonts without compiling')
    args = parser.parse_args()
    inputs = dependencies()
    for command in ('latexmk', 'xelatex', 'kpsewhich'):
        if not shutil.which(command):
            raise SystemExit(f'{command} is required. Install XeLaTeX/latexmk and Korean TeX packages first.')
    font_dir = args.font_dir
    if font_dir is None:
        result = subprocess.run(['kpsewhich', 'UnBatang.ttf'], capture_output=True, text=True)
        candidate = result.stdout.strip()
        if result.returncode != 0 or not candidate:
            raise SystemExit('Install the TeX Live unfonts-core package, or pass --font-dir with Un*.ttf files.')
        font_dir = Path(candidate).resolve().parent
    font_dir = font_dir.resolve()
    for font in FONTS:
        if not (font_dir/font).is_file():
            raise SystemExit(f'Missing font: {font_dir/font}')
    print(f'Validated {len(inputs)} report inputs and four Korean fonts.')
    if args.check_only:
        return
    output = ROOT/'build'
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='kakao-report-') as scratch:
        staged = Path(scratch)
        for rel in inputs:
            dest = staged/rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT/rel, dest)
            if dest.suffix in ('.tex', '.sty'):
                text = dest.read_text(encoding='utf-8')
                text = text.replace('/usr/local/texlive/2024/texmf-dist/fonts/truetype/public/unfonts-core/', font_dir.as_posix()+'/')
                dest.write_text(text, encoding='utf-8')
        subprocess.run(['latexmk', '-xelatex', '-interaction=nonstopmode', '-halt-on-error', '-file-line-error', '-outdir=build', 'kakao_enter.tex'], cwd=staged, check=True)
        for name in ('kakao_enter.pdf', 'kakao_enter.log'):
            shutil.copyfile(staged/'build'/name, output/name)
    print('Rebuilt report: build/kakao_enter.pdf')
    print('The release PDF in reports/ is unchanged; PDF bytes can vary with TeX versions.')

if __name__ == '__main__':
    main()

