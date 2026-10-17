#!/usr/bin/env python3
"""tex2md.py -- convert one module document (notes | worksheet | homework) from LaTeX to
MkDocs-Material Markdown.  Used by build_site.py; see CONVENTIONS.md section 4 for the box mapping.

The LaTeX is the single source of truth.  Numbering (boxes, equations) is recomputed here by
replaying the counters that la.sty uses, and \\ref/\\eqref are resolved from that registry, so the
site shows exactly the numbers the PDF shows.  Cross-module references (\\ref{1.1-thm:rowsol}) are
resolved from the registry of the other module and become links between pages.

Never converts instructor.tex (private).
"""
import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LUA = ROOT / "site" / "filters" / "la.lua"
PUBLIC_KINDS = ("notes", "worksheet", "homework")

# ---------------------------------------------------------------- box vocabulary (CONVENTIONS section 4)
SHARED = {"defn": "def", "thm": "thm", "exmp": "ex", "proc": "proc"}      # one shared counter
OWN = {"kc": "kc", "think": "think"}                                         # one counter each
NUMBERED = {**SHARED, **OWN}
PLAIN = {"warn": "Warning", "guide": "Guiding question", "remark": "Remark"}
TWO_ARGS = {"activity", "ext"}
NOUN = {"defn": "Definition", "thm": "Theorem", "exmp": "Example", "proc": "Procedure",
        "kc": "Knowledge Check", "think": "Pause and think"}
ADMONITION = {"defn": "definition", "thm": "theorem", "exmp": "example", "proc": "procedure",
              "kc": "question", "think": "think", "warn": "warning", "guide": "tip", "remark": "note",
              "activity": "abstract", "ext": "success", "roles": "info", "howto": "info"}
BOXES = {
    "notes": list(NUMBERED) + list(PLAIN),
    "worksheet": ["roles", "activity", "ext"],
    "homework": ["howto"],
}


class Box:
    def __init__(self, name, args, body, start, end):
        self.name, self.args, self.body, self.start, self.end = name, args, body, start, end


# ---------------------------------------------------------------- small TeX scanners
def read_group(s, i, opener="{", closer="}"):
    """s[i] == opener; return (content, index after the matching closer)."""
    assert s[i] == opener, f"expected {opener!r} at {s[i:i+30]!r}"
    depth, j = 0, i
    while j < len(s):
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
        j += 1
    raise ValueError("unbalanced group")


def find_boxes(body, names):
    pat = re.compile(r"\\begin\{(%s)\}" % "|".join(names))
    out, pos = [], 0
    while True:
        m = pat.search(body, pos)
        if not m:
            return out
        name, i, args = m.group(1), m.end(), []
        if name in NUMBERED or name in TWO_ARGS:
            for _ in range(2):
                g, i = read_group(body, i)
                args.append(g)
        elif name in PLAIN and body[i:i + 1] == "[":
            g, i = read_group(body, i, "[", "]")
            args.append(g)
        end = re.compile(r"\\end\{%s\}" % name).search(body, i)
        out.append(Box(name, args, body[i:end.start()], m.start(), end.end()))
        pos = end.end()


def strip_comments(s):
    return re.sub(r"(?m)^[ \t]*%.*\n", "", s)


def module_info(tex):
    m = re.search(r"\\lamodule\{(\d+)\}\{(\d+)\}\{([^}]*)\}", tex)
    return m.group(1), m.group(2), m.group(3)


def body_of(tex):
    return tex.split(r"\begin{document}", 1)[1].rsplit(r"\end{document}", 1)[0]


# ---------------------------------------------------------------- registry (numbers and anchors)
def build_registry(module):
    """Replay la.sty's counters over modules/<module>/notes.tex."""
    tex = strip_comments((ROOT / "modules" / module / "notes.tex").read_text())
    ch, sec, _ = module_info(tex)
    body = body_of(tex)
    labels, shared, own = {}, 0, {"kc": 0, "think": 0}
    for b in find_boxes(body, BOXES["notes"]):
        if b.name in SHARED:
            shared += 1
            n = shared
        elif b.name in OWN:
            own[b.name] += 1
            n = own[b.name]
        else:
            continue
        key = f"{SHARED.get(b.name) or OWN[b.name]}:{b.args[1]}"
        labels[key] = {"num": f"{ch}.{sec}.{n}", "id": key.replace(":", "-"), "noun": NOUN[b.name]}
    eqs = {}
    for k, m in enumerate(re.finditer(r"\\begin\{equation\}\\label\{([^}]*)\}", body), start=1):
        eqs[m.group(1)] = k
    return {"labels": labels, "equations": eqs}


# ---------------------------------------------------------------- pandoc
def pandoc_md(tex):
    if not tex.strip():
        return ""
    cmd = ["pandoc", "-f", "latex", "-t",
           "markdown-smart-header_attributes-fenced_divs-native_divs-native_spans-bracketed_spans-link_attributes-inline_code_attributes-simple_tables-multiline_tables-grid_tables-raw_attribute",
           "--wrap=none", "--lua-filter", str(LUA)]
    r = subprocess.run(cmd, input=tex, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("pandoc failed: " + r.stderr + "\n--- input ---\n" + tex[:600])
    return r.stdout.strip()


def inline_md(tex):
    return pandoc_md(tex).replace("\n", " ").replace('"', "'").strip()


# ---------------------------------------------------------------- preprocessing of the TeX source
LABEL_TOKENS = [("\\alph*", "a"), ("\\Alph*", "A"), ("\\arabic*", "1"), ("\\roman*", "i"), ("\\Roman*", "I")]


def fix_enumerates(b, default_label=None):
    """pandoc 3.1 only understands enumerate-package labels such as [(a)], not enumitem's label=(\\alph*).
    Translate the label, and carry start=N through a marker that la.lua turns back into a start number."""
    out, pos = [], 0
    for m in re.finditer(r"\\begin\{enumerate\}(?:\[([^\]]*)\])?", b):
        opts = m.group(1) or ""
        lab = re.search(r"label=(\([^)]*\)|[^,\]]*)", opts)
        start = re.search(r"start=(\d+)", opts)
        label = lab.group(1) if lab else default_label
        if label:
            for tok, rep in LABEL_TOKENS:
                label = label.replace(tok, rep)
        out.append(b[pos:m.start()])
        out.append(r"\begin{enumerate}" + (f"[{label}]" if label else ""))
        pos = m.end()
        if start:
            it = b.find(r"\item", pos)
            out.append(b[pos:it + 5] + f" ZZSTART{start.group(1)}ZZ")
            pos = it + 5
    out.append(b[pos:])
    return "".join(out)


def preprocess(body, kind, module, registries, figures):
    ch, sec = module.split(".")
    reg = registries[module]
    b = strip_comments(body)

    # headings such as "Part A \\quad Title" -> "Part A -- Title"
    b = re.sub(r"(\\subsection\*\{[^}]*?)\s*\\quad\s*", lambda m: m.group(1) + " \u2014 ", b)

    # worksheet / homework clutter that only makes sense on paper
    b = "\n".join(line for line in b.split("\n") if r"\rule" not in line)
    b = re.sub(r"\\(?:answerline|newpage|clearpage|medskip)\b", "", b)
    b = re.sub(r"\\workspace\{[^}]*\}", "", b)
    b = b.replace(r"\dotfill", r"\ldots\ldots\ldots")
    b = re.sub(r"\\hspace\*?\{[^}]*\}", "", b)
    b = re.sub(r"\\renewcommand\{\\arraystretch\}\{[^}]*\}", "", b)

    # la.sty environments that MathJax does not know
    b = re.sub(r"\\begin\{amat\}\{([^}]*)\}", r"\\left[\\begin{array}{\1}", b)
    b = b.replace(r"\end{amat}", r"\end{array}\right]")
    b = b.replace(r"\begin{align*}", r"\[\begin{aligned}").replace(r"\end{align*}", r"\end{aligned}\]")

    # numbered equations -> display math with an explicit \tag
    def eq(m):
        return r"\[" + m.group(2).strip() + r"\tag{%d}" % reg["equations"][m.group(1)] + r"\]"
    b = re.sub(r"\\begin\{equation\}\\label\{([^}]*)\}(.*?)\\end\{equation\}", eq, b, flags=re.S)
    b = re.sub(r"\\eqref\{([^}]*)\}", lambda m: "(%d)" % reg["equations"][m.group(1)], b)

    # TikZ -> SVG placeholders
    def fig(m):
        figures.append(m.group(0))
        return "\n\nZZFIG%dZZ\n\n" % len(figures)
    b = re.sub(r"\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}", fig, b, flags=re.S)

    # \ref{...} -> tokens, resolved after pandoc
    def ref(m):
        key = m.group(1)
        xm = re.match(r"^(\d+\.\d+)-(.+)$", key)
        mod, lab = (xm.group(1), xm.group(2)) if xm else (module, key)
        if mod not in registries or lab not in registries[mod]["labels"]:
            raise KeyError(f"unresolved \\ref{{{key}}} in module {module}")
        e = registries[mod]["labels"][lab]
        return "ZZREF%sQQ%sQQ%sZZ" % (e["id"], e["num"], mod)
    b = re.sub(r"\\ref\{([^}]*)\}", ref, b)

    # homework problems
    if kind == "homework":
        counter = [0]
        def prob(m):
            counter[0] += 1
            title = (m.group(1) or "").strip()
            return r"\par\textbf{%d.}\ \textbf{%s}\ " % (counter[0], title)
        b = re.sub(r"\\problem(?:\[([^\]]*)\])?", prob, b)

    # list options
    b = re.sub(r"\\begin\{(description|itemize)\}\[[^\]]*\]", r"\\begin{\1}", b)
    b = fix_enumerates(b, r"(\alph*)" if kind == "homework" else None)
    return b


# ---------------------------------------------------------------- rendering of boxes
def indent(text, n=4):
    return "\n".join((" " * n + ln) if ln.strip() else ln for ln in text.split("\n"))


def admonition(cls, title, body_md, anchor=None, extra=""):
    inner = (f'<span id="{anchor}"></span>\n\n' if anchor else "") + body_md
    if extra:
        inner += "\n\n" + extra
    return f'!!! {cls} "{title}"\n' + indent(inner)


def split_answers(seg):
    """Pull the 'Pause and think' answers out of the Answers description list."""
    m = re.search(r"\\begin\{description\}(.*?)\\end\{description\}", seg, re.S)
    if not m:
        return seg, {}
    items = re.split(r"(?=\\item\[)", m.group(1))
    keep, answers = [], {}
    for it in items:
        if not it.strip():
            continue
        lm = re.match(r"\\item\[(.*?)\]\s*(.*)$", it, re.S)
        label, rest = lm.group(1), lm.group(2)
        tm = re.search(r"Pause and think ZZREF(think-[\w-]+)QQ", label)
        if tm:
            answers[tm.group(1)] = rest.strip()
        else:
            keep.append(it)
    new = r"\begin{description}" + "".join(keep) + r"\end{description}"
    return seg[:m.start()] + new + seg[m.end():], answers


def convert(module, kind, registries, out_dir):
    assert kind in PUBLIC_KINDS, "refusing to convert " + kind
    src = ROOT / "modules" / module / f"{kind}.tex"
    tex = src.read_text()
    ch, sec, title = module_info(strip_comments(tex))
    figures = []
    body = preprocess(body_of(tex), kind, module, registries, figures)
    body = re.sub(r"\\section\{[^}]*\}", "", body, count=1)

    boxes = find_boxes(body, BOXES[kind])

    # think answers (notes only)
    answers = {}
    segments = []
    pos = 0
    for b in boxes:
        segments.append(("text", body[pos:b.start]))
        segments.append(("box", b))
        pos = b.end
    segments.append(("text", body[pos:]))
    if kind == "notes":
        for k, (typ, val) in enumerate(segments):
            if typ == "text" and "Answers and discussion" in val and r"\begin{description}" in val:
                new, ans = split_answers(val)
                segments[k] = (typ, new)
                answers.update(ans)

    parts = [f"# {ch}.{sec} {title}", ""]
    pdf = src.with_suffix(".pdf")
    if pdf.exists():
        parts += [f"[Download the PDF version]({kind}.pdf)", ""]
    for typ, val in segments:
        if typ == "text":
            md = pandoc_md(val)
            if md:
                parts += [md, ""]
            continue
        b = val
        if b.name in NUMBERED:
            key = f"{SHARED.get(b.name) or OWN[b.name]}:{b.args[1]}"
            e = registries[module]["labels"][key]
            head = f"{NOUN[b.name]} {e['num']}: {inline_md(b.args[0])}"
            body_md = pandoc_md(b.body)
            extra = ""
            if b.name == "think":
                a = answers.get(e["id"])
                if a is None:
                    raise KeyError(f"no answer found for {key}")
                extra = '??? success "Answer and discussion"\n' + indent(pandoc_md(a))
            parts += [admonition(ADMONITION[b.name], head, body_md, e["id"], extra), ""]
        elif b.name in PLAIN:
            t = inline_md(b.args[0]) if b.args else PLAIN[b.name]
            parts += [admonition(ADMONITION[b.name], t, pandoc_md(b.body)), ""]
        elif b.name in TWO_ARGS:
            t = f"{inline_md(b.args[0])} ({b.args[1].strip()})" if b.args[1].strip() else inline_md(b.args[0])
            parts += [admonition(ADMONITION[b.name], t, pandoc_md(b.body)), ""]
        else:  # roles, howto
            t = {"roles": "Group roles", "howto": "How to write up your work"}[b.name]
            parts += [admonition(ADMONITION[b.name], t, pandoc_md(b.body)), ""]
    md = "\n".join(parts).rstrip() + "\n"

    # resolve placeholders
    def refsub(m):
        anchor, num, mod = m.group(1), m.group(2), m.group(3)
        target = f"#{anchor}" if mod == module else f"../{mod}/notes.md#{anchor}"
        return f"[{num}]({target})"
    md = re.sub(r"ZZREF([\w-]+?)QQ([\d.]+)QQ([\d.]+)ZZ", refsub, md)
    # pandoc writes a paragraph starting "(a)" as \(a\); arithmatex would turn that into inline math
    md = re.sub(r"(?<!\\)\\\(([A-Za-z0-9]{1,4})\\\)", r"(\1)", md)

    fig_dir = out_dir / module / "figures"
    for k, fig_tex in enumerate(figures, start=1):
        name = f"{kind}-fig{k}"
        alt = "Diagram: " + "; ".join(re.findall(r"\\node[^{]*\{(?:\\small )?([^}]*)\}", fig_tex))
        make_svg(fig_tex, fig_dir / f"{name}.svg")
        md = md.replace(f"ZZFIG{k}ZZ", f"![{alt}](figures/{name}.svg){{ .la-figure }}")

    target = out_dir / module / f"{kind}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(md)
    return target


def make_svg(tikz, svg_path):
    work = ROOT / "build" / "figs"
    work.mkdir(parents=True, exist_ok=True)
    stem = svg_path.stem + "_" + svg_path.parent.parent.name.replace(".", "_")
    tex = work / f"{stem}.tex"
    tex.write_text("\\documentclass[border=4pt]{standalone}\n\\usepackage{amsmath,amssymb}\n"
                   "\\usepackage{tikz}\n\\begin{document}\n" + tikz + "\n\\end{document}\n")
    r = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", tex.name],
                       cwd=work, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("figure failed to compile:\n" + r.stdout[-1500:])
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["pdftocairo", "-svg", str(work / f"{stem}.pdf"), str(svg_path)], check=True)


if __name__ == "__main__":
    mod, kind = sys.argv[1], sys.argv[2]
    mods = sorted(p.name for p in (ROOT / "modules").iterdir() if (p / "notes.tex").exists())
    regs = {m: build_registry(m) for m in mods}
    print(convert(mod, kind, regs, ROOT / "site" / "docs"))
