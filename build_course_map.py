#!/usr/bin/env python3
"""Generate course_map.tex from course_map.yaml (edit the YAML, not the .tex)."""
import re, sys, yaml
src = sys.argv[1] if len(sys.argv) > 1 else "course_map.yaml"
out = sys.argv[2] if len(sys.argv) > 2 else "course_map.tex"
d = yaml.safe_load(open(src, encoding="utf-8"))
C, M = d["course"], d["modules"]

def tex(s):
    s = str(s)
    s = s.replace("Ax = b", "@@AXB@@").replace("R^n", "@@RN@@").replace("|det A|", "@@DET@@")
    for a, b in [("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"), ("$", r"\$"),
                 ("#", r"\#"), ("_", r"\_"), ("~", r"\textasciitilde{}")]:
        s = s.replace(a, b)
    return (s.replace("@@AXB@@", r"$A\bv{x}=\bv{b}$").replace("@@RN@@", r"$\R^n$")
             .replace("@@DET@@", r"$|\det A|$"))

n_tested = sum(m["tested"] for m in M)
rows = {}
for m in M:
    rows.setdefault(m["chapter"], []).append(m)
chap_name = {1: "Linear Equations in Linear Algebra", 2: "Matrix Algebra", 3: "Determinants",
             4: "Vector Spaces", 5: "Eigenvalues and Eigenvectors", 6: "Orthogonality and Least Squares"}

L = [r"\documentclass[11pt]{article}", r"\usepackage[instructor]{la}", r"\usepackage{longtable}",
     r"\lahead{Linear Algebra --- Course Map}{\textbf{(instructor)}}",
     r"\begin{document}",
     r"{\Large\textbf{%s}}\\[2pt]{\large Course map --- %s}\par" % (tex(C["title"]), tex(C["term"])),
     r"\bigskip",
     r"\textbf{Textbook:} %s.\\" % tex(C["textbook"]),
     r"\textbf{Calendar:} %s.\\" % tex(C["length"]),
     r"\textbf{Site launch:} first week of January 2027.\\",
     r"\textbf{Pacing:} not assigned yet (lecture slots intentionally left open).",
     r"\begin{tcolorbox}[nbox,colback=gray!6,colframe=gray!60!black,coltitle=white,title=Summary]",
     r"%d modules in total, %d tested, %d enrichment (full notes and site page, excluded from exams, "
     r"homework optional). Sections intentionally left out of the build: %s. "
     r"Sections 2.8 and 2.9 are omitted because Chapter 4 develops the same ideas in general form "
     r"(as Lay's own footnote suggests)." % (len(M), n_tested, len(M) - n_tested,
                                              ", ".join(tex(x) for x in C["dropped_on_purpose"])),
     r"\end{tcolorbox}",
     r"\textbf{Status key:} \texttt{legacy} = delivered in Week 1, awaiting conversion to a module; "
     r"\texttt{todo} = not yet built. \textbf{Tested:} Y = on exams; N = enrichment."]
for ch in sorted(rows):
    L += [r"\subsection*{Chapter %d --- %s}" % (ch, tex(chap_name[ch])),
          r"{\small\renewcommand{\arraystretch}{1.2}",
          r"\begin{longtable}{@{}p{0.45in}>{\raggedright\arraybackslash}p{2.0in}p{0.4in}p{0.75in}p{0.6in}>{\raggedright\arraybackslash}p{1.65in}@{}}",
          r"\toprule \textbf{\S} & \textbf{Title} & \textbf{Tested} & \textbf{Needs} & \textbf{Status} & \textbf{Notes}\\ \midrule \endhead"]
    for m in rows[ch]:
        note = m.get("note", "")
        if m.get("priority"):
            note = ("If time permits. " + note).strip()
        if m.get("legacy_source"):
            note = ("Source: " + m["legacy_source"] + ". " + note).strip()
        L.append(r"%s & %s & %s & %s & \texttt{%s} & %s\\" % (
            tex(m["id"]), tex(m["title"]), "Y" if m["tested"] else "N",
            tex(", ".join(m["prereqs"]) or "---"), m["status"], tex(note)))
    L += [r"\bottomrule", r"\end{longtable}}"]
L += [r"\end{document}"]
open(out, "w", encoding="utf-8").write("\n".join(L) + "\n")
print("wrote", out, "-", len(M), "modules,", n_tested, "tested")
