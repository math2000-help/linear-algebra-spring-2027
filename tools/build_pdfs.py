#!/usr/bin/env python3
"""build_pdfs.py -- compile every module document, in course_map.yaml order.

    python3 -I tools/build_pdfs.py            # all modules that have sources
    python3 -I tools/build_pdfs.py 1.2        # just one module (its prerequisites' notes.aux must exist)

Order matters: a module's notes may cite earlier modules with \\laxdoc, which reads the earlier
notes.aux.  Fails on any LaTeX error and on any undefined reference or citation.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
KINDS = ("notes", "worksheet", "homework", "instructor")


def build(tex):
    env = dict(os.environ, TEXINPUTS=f"{ROOT / 'shared'}:")
    cmd = ["latexmk", "-g", "-cd", "-pdf", "-interaction=nonstopmode", "-halt-on-error", str(tex)]
    r = subprocess.run(cmd, env=env, capture_output=True, text=True)
    log = tex.with_suffix(".log")
    text = log.read_text(errors="ignore") if log.exists() else r.stdout
    if r.returncode:
        err = "\n".join(l for l in text.splitlines() if l.startswith("!") or re.match(r"l\.\d+", l))
        raise SystemExit(f"LaTeX failed for {tex.relative_to(ROOT)}\n{err}")
    undefined = re.findall(r"LaTeX Warning: (?:Reference|Citation) `[^']*' .*undefined", text)
    missing = re.findall(r"No notes.aux for module [\d.]+", text)
    if undefined or missing:
        raise SystemExit(f"{tex.relative_to(ROOT)}: " + "; ".join(undefined + missing))
    pages = subprocess.run(["pdfinfo", str(tex.with_suffix('.pdf'))], capture_output=True, text=True).stdout
    n = re.search(r"Pages:\s+(\d+)", pages).group(1)
    print(f"ok  {tex.relative_to(ROOT)}  ({n} pp)")


def main(only=None):
    course = yaml.safe_load((ROOT / "course_map.yaml").read_text())
    for m in course["modules"]:
        if only and m["id"] != only:
            continue
        d = ROOT / "modules" / m["id"]
        if not (d / "notes.tex").exists():
            continue
        for kind in KINDS:
            if (d / f"{kind}.tex").exists():
                build(d / f"{kind}.tex")
    if not only:
        # the printed course map
        subprocess.run([sys.executable, "-I", str(ROOT / "build_course_map.py"),
                        str(ROOT / "course_map.yaml"), str(ROOT / "course_map.tex")], check=True)
        build(ROOT / "course_map.tex")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
