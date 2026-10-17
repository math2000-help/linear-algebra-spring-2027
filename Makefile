# Linear Algebra course build.  Run from the course root.
#
#   make setup    one-time: install MathJax for the math check (needs npm)
#   make verify   sympy checks on every number in the modules
#   make pdfs     compile all modules (+ the printed course map)
#   make site     generate site/docs + mkdocs.yml from the LaTeX and build build/site
#   make check    MathJax-parse every equation in the built site
#   make all      verify, pdfs, site, check
#   make serve    live preview at http://127.0.0.1:8000
#
# Requires: TeX Live (latexmk, pdflatex), pandoc >= 3.1, pdftocairo, python3 with pyyaml and sympy,
# mkdocs-material.   Generated: site/docs/<module>/, site/mkdocs.yml, build/.

PY := python3 -I

.PHONY: all setup verify pdfs site check serve clean

all: verify pdfs site check

setup:
	npm install --silent --prefix tools/node mathjax-full

verify:
	$(PY) tools/verify_modules.py

pdfs:
	$(PY) tools/build_pdfs.py

site: pdfs
	$(PY) tools/build_site.py

check:
	MATHJAX_FROM=$(CURDIR)/tools/node node tools/check_math.mjs build/site site/macros.json

serve:
	$(PY) tools/build_site.py --no-build
	mkdocs serve -f site/mkdocs.yml

clean:
	rm -rf build
	find modules -name '*.aux' -o -name '*.log' -o -name '*.out' -o -name '*.fls' -o -name '*.fdb_latexmk' | xargs rm -f
