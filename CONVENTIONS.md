# Course build conventions (v0.2, 2026-10-17)

Read this first in every new conversation. It is the contract between the LaTeX sources, the PDFs and the site.

## 1. Source of truth
- **LaTeX is the source.** The compiled **PDF is the main deliverable** (notes, worksheet, homework).
- **The site is generated from the LaTeX** (pandoc + Lua filters), never from the PDF and never hand-edited.
- `course_map.yaml` is the single source for module order, tested/enrichment flags, prerequisites and status. The printed course map and the site navigation are generated from it.

## 2. Module = one Lay section
Folder `modules/<chapter>.<section>/` (e.g. `modules/1.3/`) with:
`notes.tex`, `worksheet.tex`, `homework.tex`, `instructor.tex` (+ compiled PDFs).
Each starts with `\documentclass[11pt]{article}`, `\usepackage[<kind>]{la}`, then `\lamodule{ch}{sec}{Title}` (in the preamble)
and uses exactly one `\section{Title}` (box numbers become `ch.sec.n`; use `\subsection*` for everything else). `<kind>` is `notes`, `worksheet`, `homework` or `instructor`.
- **Compile:** `python3 -I tools/build_pdfs.py` (all modules, in `course_map.yaml` order) or `python3 -I tools/build_pdfs.py 1.2`.
  By hand: `TEXINPUTS=$PWD/shared: latexmk -g -cd -pdf modules/1.2/notes.tex` (run from the course root; `-cd` is needed so `\laxdoc` paths work).
- **Cross-module references (notes only):** put `\laxdoc{1.1}` after `\lamodule` and cite with `\ref{1.1-thm:rowsol}`. This reads `modules/1.1/notes.aux`, so
  earlier modules must be built first (build_pdfs.py does this). Cite **backward only** (to prerequisites). For a forward pointer, name the section in words ("Section 1.2"), no number.
- **Numbering is per module.** Worksheet activities are "Activity 1, 2, ..." and homework problems are 1, 2, ... inside each module. No "Lecture N" wording anywhere: lecture slots are unassigned (`pacing: deferred`), so say "this section" / "Section 1.2".
  Pause-and-think and Knowledge Check boxes are numbered `ch.sec.n` automatically; refer to them by that number in instructor notes (e.g. "Pause and think 1.2.1").

## 3. Shared preamble `la.sty` (v0.2)
All boxes, macros and headers live there. Do not redefine them in a module. Macros: `\R \C \T \Span \Nul \Col \Row \rank \proj \bv{} \inner{}{} \amat \rops \lead \st`.
**Any new math macro must also be added to `site/macros.json`** (MathJax). `tools/build_site.py` fails with a clear message if one is missing. The `amat` environment is the one exception: the site pipeline expands it to `array` itself.

## 4. Box vocabulary (notes) and site mapping
| LaTeX box | Site rendering |
|---|---|
| `defn`, `thm`, `proc`, `exmp` | admonition (definition / theorem / procedure / example) |
| `kc` Knowledge Check | admonition "question" |
| `think` Pause and think | admonition with the numbered answer in a collapsible block |
| `warn`, `guide`, `remark` | admonition warning / tip / note |
Worksheet boxes: `activity`, `ext`, `roles` (site: abstract / success / info). Homework: `howto` (info), `\problem[Title.]` (bold numbered run-in heading). Instructor: `tip`, `sol` (never on the site).
- Each numbered box gets an anchor on the site (`def-lineq`, `thm-rowsol`, ...); `\ref` becomes a link, including links between modules.
- On the site the Pause-and-think answers are moved into the collapsible block under each question; the "Answers and discussion" section there keeps the Knowledge Check answers and the "Before the next section" answers. **In the PDF the answers stay in the "Answers and discussion" subsection, numbered to match.**
- Do not nest boxes. Do not use raw `tcolorbox`, `\fbox` or `\parbox` in module sources; use a vocabulary box (the "two fundamental questions" callout is a `remark`).

## 5. Content rules
- Notes are complete and self-reliant: definitions, proved or explicitly deferred theorems, worked examples covering different problem types, knowledge checks, and thought-provoking Pause-and-think questions. Understanding over drilling.
- **Answers to Pause-and-think stay in the notes**, in an "Answers and discussion" subsection, numbered to match. Do not move them out.
- Every number, matrix and solution is **verified with sympy before it goes into a document**: add the checks for each new module to `tools/verify_modules.py` (it also parses the matrix chains in the notes' worked examples and tests every step for row equivalence). Instructor solutions are written from the actual problem text, never from memory.
- Enrichment modules (`tested: false`) get full notes; homework is labeled optional; the instructor notes say which later sections (if any) lean on them.
- Introduce ideas in a way that foreshadows the abstraction (vector-space viewpoint) even while working in R^n.

## 6. Visibility
- Public (repo + site): notes PDFs and sources. **The site publishes the notes only** (`PUBLIC` in `tools/build_site.py`); worksheets and homework are PDFs you hand out (e.g. through the LMS). To publish them later, add "worksheet"/"homework" to `PUBLIC`. If the GitHub repo is public, also gitignore `modules/*/worksheet.*` and `modules/*/homework.*`.
- **Private (never on the site or public repo): `instructor.tex`/PDF, all solutions.** `tools/build_site.py` never converts `instructor.*`, excludes `instructor*`/`solution*` in `mkdocs.yml`, and fails if any such file name or the marker text "Instructor Notes" / "not for students" appears in `site/docs` or `build/site`.

## 7. Known technical gotchas
- `microtype` font expansion crashes pdfTeX on the instructor notes: `la.sty` turns it off for `[instructor]`.
- TikZ figures are compiled stand-alone and converted to SVG at build time (`pdftocairo -svg`; dvisvgm is not installed). Alt text is taken from the figure's `\node` labels.
- Python for sympy checks: `pip install --break-system-packages sympy`; run scripts with `python3 -I`.
- pandoc 3.1 does **not** read enumitem's `label=(\alph*)`; `tex2md.py` rewrites it to the enumerate-package form `[(a)]` and carries `start=N` through a marker. Python-Markdown cannot number `(a)`/`(1)` lists, so `la.lua` writes those labels out as bold run-in text. Plain `1.` lists stay real lists. Homework `enumerate` lists default to `(a)` labels, as `la.sty` does.
- `align*` is rewritten to `aligned`, `equation`+`\label` to `\[...\tag{n}\]`, `\eqref` to `(n)`; display equations are split into paragraphs of their own (arithmatex needs that).
- Math in tables and in markdown paragraphs starting with "(a)" must survive pandoc's escaping: `tex2md.py` undoes `\(a\)` so arithmatex does not read it as math.
- MathJax loads from the unpkg CDN (`site/mkdocs.yml`), so the math appears only when online. To make the site work offline, vendor `mathjax@3/es5` into `site/docs/javascripts/` and point `extra_javascript` at it.

## 8. Working pattern
- One conversation per 2-3 modules, in the Linear Algebra Project. First message: "Build modules X, Y, Z per CONVENTIONS.md and course_map.yaml."
- For each new module: write the four `.tex` files, add its checks to `tools/verify_modules.py`, then `make all` (verify, PDFs, site, MathJax check). Update `status` in `course_map.yaml`, regenerate the course map (done by `make pdfs`), save sources + PDFs to the Project.
- `make setup` once (installs `mathjax-full` for the math check); `make serve` for a local preview.

## 9. Site pipeline (MkDocs Material)
```
modules/<id>/notes.tex  --tools/tex2md.py-->  site/docs/<id>/notes.md  --mkdocs-->  build/site   (kinds listed in PUBLIC; notes only for now)
course_map.yaml --tools/build_site.py--> site/mkdocs.yml (nav), site/docs/index.md
site/macros.json --tools/build_site.py--> site/docs/javascripts/mathjax.js
```
- Hand-written: `site/filters/la.lua`, `site/macros.json`, `site/docs/stylesheets/extra.css`, everything in `tools/`. **Generated (do not edit): everything else under `site/` and `build/`.**
- `tex2md.py` replays la.sty's counters to recompute box and equation numbers, resolves `\ref`/`\eqref` (including cross-module), converts each box body with pandoc, and wraps it in an admonition.
- Only modules that have a `notes.tex` appear in the nav; the home page lists every module from `course_map.yaml` ("coming soon" for the rest).
- Checks that must pass before publishing: `make verify`, `make pdfs`, `make site` (strict MkDocs build + privacy check), `make check` (every equation parsed by MathJax with the site macros).
- Not yet checked: visual appearance in a real browser (all structure, links and math were verified programmatically). Look at one page of each kind after the first deploy.

## 10. Week 1 conversion log (legacy_week1 -> modules 1.1 and 1.2)
`course/legacy_week1/` is superseded by `modules/1.1` and `modules/1.2` and can be archived. What changed in the conversion:
- Lecture 1 -> 1.1, Lecture 2 -> 1.2. "Lecture" wording became "section". Pause-and-think numbers are now `1.1.1`-`1.1.5` and `1.2.1`-`1.2.2`.
- Worksheet: Activities 1-2 -> 1.1; Activities 3-4 (+ exit ticket) -> 1.2 as Activities 1-2; extensions 5-7 -> 1.2 as Activities 3-5.
- Homework: old 1-6, 13(a)(b), 15 -> 1.1 as Problems 1-8; old 7-12, 13(c), 14 -> 1.2 as Problems 1-8 (old 8(b) is now 2(b)). Suggested point values were re-split to total 100 per module.
- Notes 1.1: the forward reference to the counting theorem became a pointer to Section 1.2; the "How to read" legend became a `remark`; the boxed "two fundamental questions" became a `remark`. Notes 1.2 cite Section 1.1 with `\laxdoc`.
- Corrections found while re-verifying: instructor key for old Homework 1(b) said the product was x1x2 (it is x2x3); instructor "Connections forward" said the forward phase costs *less* than the backward phase (it costs far *more*); the Knowledge Check answer for matrix (d) now lists all entries that should be zero.
- New content: three "Connections forward" bullets in the 1.1 instructor notes (vector form of solution sets, link to Chapter 4).
