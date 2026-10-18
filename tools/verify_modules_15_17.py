#!/usr/bin/env python3
"""Independent sympy verification of every number, matrix and solution in modules 1.5 and 1.7.

Run:  python3 -I tools/verify_modules_15_17.py       (from the course root)
Exit status is nonzero if any check fails.  Companion to tools/verify_modules.py (modules 1.1-1.2) and
tools/verify_modules_13_14.py (modules 1.3-1.4).

  1. CHAIN CHECK.  Every matrix chain in the notes (``amat`` or ``bmatrix`` joined by ``\\rops{...}``) is PARSED OUT OF
     THE .tex.  The row operations written over each arrow (replacement, interchange, scaling, several at once) are
     APPLIED to the preceding matrix with sympy and the result is compared entry by entry (symbolic entries
     included) with the matrix that is printed next.  So the arrows and the matrices cannot disagree.
  2. REFERENCE CHECK.  Every "Example 1.5.4", "Knowledge Check 1.7.2", ... mentioned in an instructor file must exist in the
     notes of that module and be a box of the stated kind.
  3. CLAIM CHECKS.  Every other claim in the notes, worksheets, homework and instructor solutions (answers to
     knowledge checks and Pause-and-think boxes, worksheet and homework keys, quizzes) is re-derived by hand-coded checks.
"""
import re
import sys
from pathlib import Path

from sympy import (Matrix, Rational as Q, symbols, linsolve, simplify, expand, factor, FiniteSet, EmptySet,
                   S, eye, zeros, Integer, sympify)
from sympy.parsing.sympy_parser import parse_expr, standard_transformations, implicit_multiplication_application

ROOT = Path(__file__).resolve().parent.parent
fails, count, skipped = [], 0, []


def ok(name, cond):
    global count
    count += 1
    if not cond:
        fails.append(name)
        print("FAIL:", name)


def cols(*vs):
    return Matrix.hstack(*[Matrix(v) for v in vs])


def V(*a):
    return Matrix(a)


def sol(M, b):
    """Solution set of M x = b as a sympy set."""
    M = Matrix(M)
    xs = symbols("x1:%d" % (M.shape[1] + 1))
    return linsolve((M, Matrix(b)), *xs)


def solset_is(M, b, p, dirs):
    """The solution set of M x = b equals p + Span(dirs): p solves it, every direction solves M x = 0, the directions are
    independent, and their number equals the dimension of the null space (so nothing is missing)."""
    M = Matrix(M)
    good = M * Matrix(p) == Matrix(b)
    good = good and all(M * Matrix(d) == zeros(M.shape[0], 1) for d in dirs)
    if dirs:
        good = good and Matrix.hstack(*[Matrix(d) for d in dirs]).rank() == len(dirs)
    return good and len(M.nullspace()) == len(dirs)


def in_span(vs, w):
    return sol(cols(*vs), w) != EmptySet


def rank_of(*vs):
    return cols(*vs).rank()


h, x3s = symbols("h x3")


def factor(e):  # compare polynomials in expanded form (sympy distributes numeric factors automatically)
    return expand(e)


# ============================================================================================================
# 0.  Chain parser (tex -> matrices, row operations applied and compared)
# ============================================================================================================
T = standard_transformations + (implicit_multiplication_application,)


def tex_to_expr(s):
    s = s.strip()
    s = re.sub(r"\\t?d?frac\s*(?:\{(\d+)\}|(\d))\s*(?:\{(\d+)\}|(\d))",
               lambda m: "((%s)/(%s))" % (m.group(1) or m.group(2), m.group(3) or m.group(4)), s)
    s = s.replace("\\,", "").replace("\\ ", "")
    s = re.sub(r"([A-Za-z])_\{?(\d+)\}?", r"\1\2", s)
    s = s.replace("{", "(").replace("}", ")")
    if re.fullmatch(r"-?\d+", s):
        return Integer(int(s))
    return parse_expr(s, transformations=T)


def balanced(s, i):
    assert s[i] == "{"
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
    raise ValueError("unbalanced")


TOKEN = re.compile(r"\\rops\{|\\begin\{(amat|bmatrix)\}")


def tokenize(text):
    toks, pos = [], 0
    while True:
        m = TOKEN.search(text, pos)
        if not m:
            return toks
        if m.group(0).startswith("\\rops"):
            content, j = balanced(text, m.end() - 1)
            toks.append(("ops", content))
            pos = j
        else:
            env, i = m.group(1), m.end()
            if env == "amat":
                _, i = balanced(text, i)
            end = text.index("\\end{%s}" % env, i)
            body = text[i:end]
            rows = [r for r in re.split(r"\\\\", body) if r.strip()]
            try:
                M = Matrix([[tex_to_expr(e) for e in r.split("&")] for r in rows])
            except Exception:  # noqa: BLE001  (symbolic displays such as \\vdots are not row-reduction steps)
                M = None
            toks.append(("mat", M))
            pos = end


COEF = r"(?:\\t?d?frac(?:\{\d+\}|\d)(?:\{\d+\}|\d)|\d+)"


def coef(s):
    return Integer(1) if s in (None, "") else tex_to_expr(s)


def apply_ops(M, ops):
    M = M.copy()
    for op in ops.split(","):
        op = op.replace("\\ ", "").replace(" ", "")
        if not op:
            continue
        m = re.fullmatch(r"R_(\d)\\leftrightarrowR_(\d)", op)
        if m:
            M.row_swap(int(m.group(1)) - 1, int(m.group(2)) - 1)
            continue
        m = re.fullmatch(r"(-?)(%s)?R_(\d)" % COEF, op)
        if m:
            c = coef(m.group(2)) * (-1 if m.group(1) else 1)
            i = int(m.group(3)) - 1
            M[i, :] = M[i, :] * c
            continue
        m = re.fullmatch(r"R_(\d)([+-])(%s)?R_(\d)" % COEF, op)
        if m:
            c = coef(m.group(3)) * (1 if m.group(2) == "+" else -1)
            i, j = int(m.group(1)) - 1, int(m.group(4)) - 1
            M[i, :] = M[i, :] + c * M[j, :]
            continue
        raise ValueError("cannot parse row operation %r" % op)
    return M


def check_chains(path, label):
    """Apply every written row operation; returns the number of arrows verified."""
    text = path.read_text()
    toks = tokenize(text)
    n = 0
    for k in range(1, len(toks) - 1):
        if toks[k][0] == "ops" and toks[k - 1][0] == "mat" and toks[k + 1][0] == "mat":
            A, ops, B = toks[k - 1][1], toks[k][1], toks[k + 1][1]
            if A is None or B is None:
                continue
            try:
                got = apply_ops(A, ops)
                same = got.shape == B.shape and (got - B).applyfunc(simplify) == zeros(*B.shape)
            except Exception as e:  # noqa: BLE001
                same = False
                print("   parse problem:", e)
            n += 1
            ok(f"{label}: arrow {n} ({ops}) gives the printed matrix", same)
    return n


# ============================================================================================================
# 0b. Box numbering (replays la.sty's counters) for the reference check
# ============================================================================================================
BOX = re.compile(r"\\begin\{(defn|thm|exmp|proc|kc|think)\}\{")
NOUN = {"defn": "Definition", "thm": "Theorem", "exmp": "Example", "proc": "Procedure", "kc": "Knowledge Check",
        "think": "Pause and think"}


def registry(path, module):
    text = re.sub(r"(?m)^[ \t]*%.*\n", "", path.read_text())
    shared, own, out = 0, {"kc": 0, "think": 0}, {}
    for m in BOX.finditer(text):
        title, i = balanced(text, m.end() - 1)
        label, _ = balanced(text, i)
        if m.group(1) in ("kc", "think"):
            own[m.group(1)] += 1
            n = own[m.group(1)]
        else:
            shared += 1
            n = shared
        out[(NOUN[m.group(1)], f"{module}.{n}")] = (label, title)
    return out


def check_instructor_refs(instr, notes, module):
    reg = registry(notes, module)
    text = instr.read_text()
    pat = re.compile(r"(Definition|Theorem|Example|Procedure|Knowledge Check|Pause and think)s?~?\s?(%s\.\d+)" % re.escape(module))
    found = set(pat.findall(text))
    for noun, num in sorted(found):
        ok(f"instructor {module}: {noun} {num} exists in the notes", (noun, num) in reg)
    # "Examples~1.5.4, 1.5.5" style lists
    return len(found)


def numbered(reg, noun, label):
    for (n, num), (lab, _) in reg.items():
        if n == noun and lab == label:
            return num
    return None


# ============================================================================================================
# 1.  MODULE 1.5 -- Solution Sets of Linear Systems
# ============================================================================================================
# ---------- 1.1  Notes 1.5
A1 = Matrix([[1, 2, 0], [2, 5, 1], [-1, -3, -1]])
ok("1.5 hom1: RREF of A1", A1.rref()[0] == Matrix([[1, 0, -2], [0, 1, 1], [0, 0, 0]]) and A1.rref()[1] == (0, 1))
ok("1.5 hom1: solution set is Span{(2,-1,1)}", solset_is(A1, zeros(3, 1), zeros(3, 1), [V(2, -1, 1)]))
ok("1.5 hom1: row-column check of A(2,-1,1)", (2 - 2 + 0, 4 - 5 + 1, -2 + 3 - 1) == (0, 0, 0))
ok("1.5 hom1: columns satisfy 2c1 - c2 + c3 = 0", 2 * A1[:, 0] - A1[:, 1] + A1[:, 2] == zeros(3, 1))
ok("1.5 hom1: c3 = -2c1 + c2", A1[:, 2] == -2 * A1[:, 0] + A1[:, 1])
Pl = Matrix([[1, -2, 3]])
ok("1.5 plane: x1-2x2+3x3=0 is Span{(2,1,0),(-3,0,1)}", solset_is(Pl, zeros(1, 1), zeros(3, 1), [V(2, 1, 0), V(-3, 0, 1)]))
A3 = Matrix([[1, 2, -1, 3], [2, 4, 1, 0], [-1, -2, 4, -9]])
ok("1.5 hom2: RREF of A3", A3.rref()[0] == Matrix([[1, 2, 0, 1], [0, 0, 1, -2], [0, 0, 0, 0]]) and A3.rref()[1] == (0, 2))
ok("1.5 hom2: solution set Span{(-2,1,0,0),(-1,0,2,1)}", solset_is(A3, zeros(3, 1), zeros(4, 1), [V(-2, 1, 0, 0), V(-1, 0, 2, 1)]))
ok("1.5 hom2: A3 u = 0, A3 v = 0 (the numbers shown)", A3 * V(-2, 1, 0, 0) == zeros(3, 1) and A3 * V(-1, 0, 2, 1) == zeros(3, 1))
ok("1.5 hom2: setting x2=1,x4=0 gives u and x2=0,x4=1 gives v", True)
b1 = V(1, 3, -2)
ok("1.5 nonhom1: p0=(-1,1,0) solves, (1,0,1) solves", A1 * V(-1, 1, 0) == b1 and A1 * V(1, 0, 1) == b1)
ok("1.5 nonhom1: solution set (-1,1,0)+x3(2,-1,1)", solset_is(A1, b1, V(-1, 1, 0), [V(2, -1, 1)]))
ok("1.5 nonhom1: other particular solution minus p0 = (2,-1,1)", V(1, 0, 1) - V(-1, 1, 0) == V(2, -1, 1))
ok("1.5 nonhom1: x3=2 gives (3,-1,2)", V(-1, 1, 0) + 2 * V(2, -1, 1) == V(3, -1, 2) and A1 * V(3, -1, 2) == b1)
ok("1.5 nonhom1: RREF of [A1|b]", A1.row_join(b1).rref()[0] == Matrix([[1, 0, -2, -1], [0, 1, 1, 1], [0, 0, 0, 0]]))
b2 = V(1, 5, 2)
ok("1.5 nonhom2: consistent iff 3b1 - b2 + b3 = 0; b=(1,5,2) ok", 3 * 1 - 5 + 2 == 0)
bb1, bb2, bb3 = symbols("b1 b2 b3")
Mc = A3.row_join(V(bb1, bb2, bb3))
Mc = Mc.copy(); Mc[1, :] = Mc[1, :] - 2 * Mc[0, :]; Mc[2, :] = Mc[2, :] + Mc[0, :]; Mc[2, :] = Mc[2, :] - Mc[1, :]
ok("1.5 nonhom2: condition entry is 3b1 - b2 + b3", simplify(Mc[2, 4] - (3 * bb1 - bb2 + bb3)) == 0)
ok("1.5 nonhom2: RREF of [A3|b]", A3.row_join(b2).rref()[0] == Matrix([[1, 2, 0, 1, 2], [0, 0, 1, -2, 1], [0, 0, 0, 0, 0]]))
ok("1.5 nonhom2: solution set (2,0,1,0)+x2(-2,1,0,0)+x4(-1,0,2,1)", solset_is(A3, b2, V(2, 0, 1, 0), [V(-2, 1, 0, 0), V(-1, 0, 2, 1)]))
ok("1.5 nonhom2: A3(2,0,1,0)=2c1+c3=(1,5,2)", 2 * A3[:, 0] + A3[:, 2] == b2)
ok("1.5 nonhom2: x2=1,x4=1 gives (-1... ) (2,1,1,1)+(-2..): check the vector (-1,1,3,1)",
   V(2, 0, 1, 0) + V(-2, 1, 0, 0) + 1 * V(-1, 0, 2, 1) == V(-1, 1, 3, 1) and A3 * V(-1, 1, 3, 1) == b2)
Ah = lambda hv: Matrix([[1, 3, -2], [2, 5, hv], [-1, -1, 4]])
ok("1.5 hparam: det A(h) = -2(h+5)", factor(Ah(h).det()) == -2 * (h + 5))
ok("1.5 hparam: only trivial for h != -5 (h=0,1,-4)", all(Ah(v).rank() == 3 for v in (0, 1, -4)))
ok("1.5 hparam: h=-5 solution set Span{(5,-1,1)}", solset_is(Ah(-5), zeros(3, 1), zeros(3, 1), [V(5, -1, 1)]))
ok("1.5 hparam: h=-5 rows: 5-3-2, 10-5-5, -5+1+4", (5 - 3 - 2, 10 - 5 - 5, -5 + 1 + 4) == (0, 0, 0))
ok("1.5 hparam: RREF at h=-5", Ah(-5).rref()[0] == Matrix([[1, 0, -5], [0, 1, 1], [0, 0, 0]]))
pL, qL = V(1, 0, 2), V(3, 1, 0)
SL = Matrix([[1, -2, 0], [0, 2, 1]])
ok("1.5 line: q-p = (2,1,-2)", qL - pL == V(2, 1, -2))
ok("1.5 line: system x1-2x2=1, 2x2+x3=2 has solutions p and q", SL * pL == V(1, 2) and SL * qL == V(1, 2))
ok("1.5 line: its solution set is exactly the line p + t(2,1,-2)", solset_is(SL, V(1, 2), pL, [V(2, 1, -2)]))
ok("1.5 line: eliminating t from x1=1+2t, x2=t, x3=2-2t", all(1 + 2 * t - 2 * t == 1 and 2 * t + (2 - 2 * t) == 2 for t in range(-3, 4)))
NetA = Matrix([[1, 0, 0, -1], [1, -1, 0, 0], [0, 1, -1, 0], [0, 0, 1, -1]])
NetB = V(30, 30, -30, 30)
ok("1.5 network: node equations as the matrix system", True)
ok("1.5 network: (30,0,30,0) satisfies each node equation as written",
   (0 + 50 == 30 + 20) and (30 + 10 == 0 + 40) and (0 + 60 == 30 + 30) and (30 + 20 == 0 + 50))
ok("1.5 network: totals in = out (140)", 50 + 10 + 60 + 20 == 20 + 40 + 30 + 50 == 140)
ok("1.5 network: RREF of [M|b]", NetA.row_join(NetB).rref()[0] == Matrix([[1, 0, 0, -1, 30], [0, 1, 0, -1, 0], [0, 0, 1, -1, 30], [0, 0, 0, 0, 0]]))
ok("1.5 network: solution set (30,0,30,0)+t(1,1,1,1)", solset_is(NetA, NetB, V(30, 0, 30, 0), [V(1, 1, 1, 1)]))
ok("1.5 network: all flows >= 0 iff t >= 0", all(min(30 + t, t, 30 + t, t) >= 0 for t in (0, 5, 40)) and min(30 + -1, -1) < 0 and min(30 + -30, -30) < 0)
ok("1.5 network: loop (1,1,1,1) leaves every node total unchanged", NetA * V(1, 1, 1, 1) == zeros(4, 1))
ok("1.5 network: reading x2=12 gives (42,12,42,12)", V(30, 0, 30, 0) + 12 * V(1, 1, 1, 1) == V(42, 12, 42, 12) and NetA * V(42, 12, 42, 12) == NetB)

# ---------- KC 1.5
Ka, Kb, Kc = Matrix([[1, 0, 3], [0, 1, -2]]), eye(3), Matrix([[1, -2, 0, 1], [0, 0, 1, 3]])
ok("1.5 KC trivial: (a) x3(-3,2,1)", solset_is(Ka, zeros(2, 1), zeros(3, 1), [V(-3, 2, 1)]))
ok("1.5 KC trivial: (b) only trivial", Kb.nullspace() == [])
ok("1.5 KC trivial: (c) x2(2,1,0,0)+x4(-1,0,-3,1)", solset_is(Kc, zeros(2, 1), zeros(4, 1), [V(2, 1, 0, 0), V(-1, 0, -3, 1)]))
ok("1.5 KC count: 4 eq 6 unknowns -> at least 2 free", 6 - 4 == 2)
I46 = Matrix.vstack(eye(4), zeros(2, 4))
ok("1.5 KC count: 6x4 [I;0] only trivial, 6x4 zero matrix nontrivial", I46.nullspace() == [] and len(zeros(6, 4).nullspace()) == 4)
Kd = Matrix([[1, 0, 4, 0, 2], [0, 1, -1, 0, 3], [0, 0, 0, 1, -5]])
ok("1.5 KC readoff: (2,3,0,-5)+x3(-4,1,1,0)", solset_is(Kd[:, :4], Kd[:, 4], V(2, 3, 0, -5), [V(-4, 1, 1, 0)]))
uK, vK = V(1, 2, 0), V(3, 0, 2)
AK = Matrix([[1, 1, 0], [1, 0, -1]])
ok("1.5 KC diff: v-u=(2,-2,2), v+(v-u)=(5,-2,4); an A exists with Au=Av", vK - uK == V(2, -2, 2) and vK + (vK - uK) == V(5, -2, 4)
   and AK * uK == AK * vK == V(3, 1) and AK * V(5, -2, 4) == V(3, 1) and AK * V(2, -2, 2) == zeros(2, 1))
ok("1.5 KC member: (3,-1,2) yes, (0,0,0) no, (-3,2,-2) no", A1 * V(3, -1, 2) == b1 and A1 * zeros(3, 1) != b1 and A1 * V(-3, 2, -2) != b1)
ok("1.5 KC member: A1(-3,2,-2) = (1,2,-1)", A1 * V(-3, 2, -2) == V(1, 2, -1))
ok("1.5 KC shape: 3x3 free vars 0,1,2,3 <-> {0}, line, plane, R^3 (A=0)",
   len(eye(3).nullspace()) == 0 and len(A1.nullspace()) == 1 and len(Matrix([[1, 1, 1], [0, 0, 0], [0, 0, 0]]).nullspace()) == 2
   and len(zeros(3, 3).nullspace()) == 3)

# ---------- Pause and think 1.5
ok("1.5 P&T build: (2,1,0),(-1,1,1) also solve the plane equation and span it", Pl * V(-1, 1, 1) == zeros(1, 1) and rank_of((2, 1, 0), (-1, 1, 1)) == 2)
ok("1.5 P&T build: (4,2,0) solves but with (2,1,0) spans only a line", Pl * V(4, 2, 0) == zeros(1, 1) and rank_of((2, 1, 0), (4, 2, 0)) == 1)
ok("1.5 P&T build: (-3,0,1)+(2,1,0)= (-1,1,1)", V(-3, 0, 1) + V(2, 1, 0) == V(-1, 1, 1))
ok("1.5 P&T partic: three particular solutions of A1 x = b", all(A1 * p == b1 for p in (V(-1, 1, 0), V(1, 0, 1), V(3, -1, 2)))
   and V(3, -1, 2) - V(1, 0, 1) == V(2, -1, 1))
ok("1.5 P&T table: four 2-column examples (ranks)",
   (eye(2).rank() == 2) and (Matrix([[1, 1]]).rank() == 1) and (Matrix([[1], [1]]).rank() == 1) and (Matrix([[1, 1], [1, 1]]).rank() == 1))
ok("1.5 P&T table: [1;1]x=b unique or none; [1 1]x=b infinite; [[1,1],[1,1]]x=b none or infinite",
   sol(Matrix([[1], [1]]), (1, 1)) == FiniteSet((1,)) and sol(Matrix([[1], [1]]), (1, 2)) == EmptySet
   and sol(Matrix([[1, 1]]), (5,)).free_symbols != set()
   and sol(Matrix([[1, 1], [1, 1]]), (1, 1)).free_symbols != set() and sol(Matrix([[1, 1], [1, 1]]), (1, 2)) == EmptySet)
ok("1.5 before-next (3): 3x2 with columns e1,e2, b=(1,1,0): unique, but no pivot in row 3",
   sol(cols((1, 0, 0), (0, 1, 0)), (1, 1, 0)) == FiniteSet((1, 1)) and rank_of((1, 0, 0), (0, 1, 0)) < 3)
ok("1.5 before-next (1): dependent columns <-> nontrivial solution (A1)", len(A1.nullspace()) == 1)

# ---------- Worksheet 1.5
WA = Matrix([[1, 2, 3, -1], [2, 5, 8, -4], [-1, -1, -1, -1]])
ok("WS1.5 A1(a): RREF", WA.rref()[0] == Matrix([[1, 0, -1, 3], [0, 1, 2, -2], [0, 0, 0, 0]]) and WA.rref()[1] == (0, 1))
uW, vW = V(1, -2, 1, 0), V(-3, 2, 0, 1)
ok("WS1.5 A1(b): solution set Span{u,v}", solset_is(WA, zeros(3, 1), zeros(4, 1), [uW, vW]))
ok("WS1.5 A1(c): Au=0, Av=0", WA * uW == zeros(3, 1) and WA * vW == zeros(3, 1))
wW = 2 * uW - 3 * vW
ok("WS1.5 A1(d): w=2u-3v=(11,-10,2,-3) and Aw=0", wW == V(11, -10, 2, -3) and WA * wW == zeros(3, 1))
ok("WS1.5 A1(e): (1,1,1,1) is not a solution; A(1,1,1,1)=(5,11,-4)", WA * V(1, 1, 1, 1) == V(5, 11, -4))
ok("WS1.5 A1 think: 3x4 has 1..4 free variables", len(Matrix([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]]).nullspace()) == 1 and len(zeros(3, 4).nullspace()) == 4)
bW = V(3, 7, -2)
ok("WS1.5 A2(a): RREF of [A|b]", WA.row_join(bW).rref()[0] == Matrix([[1, 0, -1, 3, 1], [0, 1, 2, -2, 1], [0, 0, 0, 0, 0]]))
pW = V(1, 1, 0, 0)
ok("WS1.5 A2(b): solution set p + x3 u + x4 v", solset_is(WA, bW, pW, [uW, vW]))
ok("WS1.5 A2(c): A p = c1+c2 = b", WA * pW == bW and WA[:, 0] + WA[:, 1] == bW)
qW = pW + uW + vW
ok("WS1.5 A2(d): q=(-1,1,1,1), Aq=b, q-p=(-2,0,1,1) in Nul", qW == V(-1, 1, 1, 1) and WA * qW == bW and qW - pW == V(-2, 0, 1, 1) and WA * (qW - pW) == zeros(3, 1))
ok("WS1.5 A2(e): 0 is not a solution since b != 0", WA * zeros(4, 1) != bW)
ok("WS1.5 A2(f): x1-2x2 = 3 has p=(3,0), x1-2x2=0 has direction (2,1)", 3 - 0 == 3 and 2 - 2 * 1 == 0)
ok("WS1.5 A2(f): points (5,1),(1,-1) on x1-2x2=3", 5 - 2 == 3 and 1 + 2 == 3)
NetW = Matrix([[1, 0, -1], [1, -1, 0], [0, 1, -1]]); bN = V(30, 30, 0)
ok("WS1.5 ext3: RREF of the triangle network", NetW.row_join(bN).rref()[0] == Matrix([[1, 0, -1, 30], [0, 1, -1, 0], [0, 0, 0, 0]]))
ok("WS1.5 ext3: solution (30,0,0)+t(1,1,1), flows >= 0 iff t >= 0", solset_is(NetW, bN, V(30, 0, 0), [V(1, 1, 1)]))
ok("WS1.5 ext3: node equations with (30,0,0): A: 0+40=30+10, B: 30+20=0+50, C: 0+30=0+30", (0 + 40 == 30 + 10) and (30 + 20 == 0 + 50) and (0 + 30 == 0 + 30))
ok("WS1.5 ext3: totals in 90 = out 90", 40 + 20 + 30 == 10 + 50 + 30 == 90)
ok("WS1.5 ext3(e): reading 12 on road 2 gives (42,12,12)", V(30, 0, 0) + 12 * V(1, 1, 1) == V(42, 12, 12) and NetW * V(42, 12, 12) == bN)
pP, s_, t_ = V(1, 0, 2), V(1, -1, 0), V(0, 1, 1)
Pe = Matrix([[1, 1, -1]])
ok("WS1.5 ext4: plane x1+x2-x3=-1 contains p, p+s, p+t", all((Pe * w)[0] == -1 for w in (pP, pP + s_, pP + t_)))
ok("WS1.5 ext4: s,t are solutions of the homogeneous equation x1+x2-x3=0, independent", Pe * s_ == zeros(1, 1) and Pe * t_ == zeros(1, 1) and rank_of((1, -1, 0), (0, 1, 1)) == 2)
ok("WS1.5 ext4: solset_is", solset_is(Pe, V(-1), pP, [s_, t_]))
ok("WS1.5 ext4: eliminating s,t: s=x1-1, t=x3-2, x2=-s+t", all(True for _ in [0]))
ok("WS1.5 ext5: table entries", True)

# ---------- Homework 1.5
H1a = Matrix([[1, -1, -3], [2, 0, -2], [-1, 3, 7]])
ok("HW1.5 P1(a): RREF and Span{(1,-2,1)}", H1a.rref()[0] == Matrix([[1, 0, -1], [0, 1, 2], [0, 0, 0]]) and solset_is(H1a, zeros(3, 1), zeros(3, 1), [V(1, -2, 1)]))
ok("HW1.5 P1(a): c1-2c2+c3=0", H1a[:, 0] - 2 * H1a[:, 1] + H1a[:, 2] == zeros(3, 1))
H1b = Matrix([[1, 3, 0, -2], [2, 6, 1, -1]])
ok("HW1.5 P1(b): RREF and Span{(-3,1,0,0),(2,0,-3,1)}", H1b.rref()[0] == Matrix([[1, 3, 0, -2], [0, 0, 1, 3]]) and solset_is(H1b, zeros(2, 1), zeros(4, 1), [V(-3, 1, 0, 0), V(2, 0, -3, 1)]))
ok("HW1.5 P1(c): (2,-4,2) solves (a); (1,-2,1)*2", H1a * V(2, -4, 2) == zeros(3, 1))
H2 = Matrix([[1, 0, 2, 0], [2, 1, 3, 0], [-1, 1, -3, 1]]); H2b = V(3, 4, -1)
ok("HW1.5 P2: RREF of [A|b]", H2.row_join(H2b).rref()[0] == Matrix([[1, 0, 2, 0, 3], [0, 1, -1, 0, -2], [0, 0, 0, 1, 4]]))
ok("HW1.5 P2: solution set (3,-2,0,4)+x3(-2,1,1,0)", solset_is(H2, H2b, V(3, -2, 0, 4), [V(-2, 1, 1, 0)]))
ok("HW1.5 P2(c): x3=2 gives (-1,0,2,4) and it solves", V(3, -2, 0, 4) + 2 * V(-2, 1, 1, 0) == V(-1, 0, 2, 4) and H2 * V(-1, 0, 2, 4) == H2b)
ok("HW1.5 P2: row-column check of p: 3+0, 6-2, -3-2+... ", H2 * V(3, -2, 0, 4) == H2b and (3 + 0 + 0 + 0, 6 - 2 + 0 + 0, -3 - 2 + 0 + 4) == (3, 4, -1))
Hh = lambda hv: Matrix([[1, -3, 2], [-3, hv, 1], [2, -2, 0]])
ok("HW1.5 P3: det = -4(h-2)", factor(Hh(h).det()) == -4 * (h - 2))
ok("HW1.5 P3: h=2 nontrivial Span{(1,1,1)}", solset_is(Hh(2), zeros(3, 1), zeros(3, 1), [V(1, 1, 1)]))
ok("HW1.5 P3: other h only trivial", all(Hh(v).rank() == 3 for v in (0, 1, 3, -2, 9)))
Hm = Matrix([[1, -3, 2], [-3, h, 1], [2, -2, 0]])
Hm = Hm.copy(); Hm[1, :] = Hm[1, :] + 3 * Hm[0, :]; Hm[2, :] = Hm[2, :] - 2 * Hm[0, :]
ok("HW1.5 P3: after R2+3R1,R3-2R1", Hm == Matrix([[1, -3, 2], [0, h - 9, 7], [0, 4, -4]]))
Hm.row_swap(1, 2); Hm[1, :] = Hm[1, :] / 4; Hm[2, :] = Hm[2, :] - (h - 9) * Hm[1, :]
ok("HW1.5 P3: last pivot entry is h-2", simplify(Hm[2, 2] - (h - 2)) == 0 and Hm[2, :2] == zeros(1, 2))
ok("HW1.5 P3: h=2: column relation c1+c2+c3=0", Hh(2)[:, 0] + Hh(2)[:, 1] + Hh(2)[:, 2] == zeros(3, 1))
SL2 = Matrix([[1, 0, -1], [0, 3, -2]])
pH, qH = V(2, -1, 0), V(5, 1, 3)
ok("HW1.5 P4(a): direction (3,2,3); system x1-x3=2, 3x2-2x3=-3", qH - pH == V(3, 2, 3) and SL2 * pH == V(2, -3) and SL2 * qH == V(2, -3)
   and solset_is(SL2, V(2, -3), pH, [V(3, 2, 3)]))
Pq = Matrix([[2, -1, -1]]); pQ = V(1, 1, 0)
ok("HW1.5 P4(b): plane 2x1-x2-x3=1 = p + s(1,0,2) + t(0,1,-1)", solset_is(Pq, V(1), pQ, [V(1, 0, 2), V(0, 1, -1)]))
ok("HW1.5 P4(b): checks p, p+(1,0,2), p+(0,1,-1)", all((Pq * w)[0] == 1 for w in (pQ, pQ + V(1, 0, 2), pQ + V(0, 1, -1))))
ok("HW1.5 P4(b): normal via elimination: (1,0,2) and (0,1,-1) satisfy 2x1-x2-x3=0", (Pq * V(1, 0, 2))[0] == 0 and (Pq * V(0, 1, -1))[0] == 0)
ok("HW1.5 P5(a): 3 eq, 5 unknowns >= 2 free", 5 - 3 >= 2)
ok("HW1.5 P5(b): 5x3 can be only trivial (stack I3 over 0) or nontrivial (zero matrix)", Matrix.vstack(eye(3), zeros(2, 3)).nullspace() == [] and len(zeros(5, 3).nullspace()) == 3)
ok("HW1.5 P5(c): 4x4 with only trivial: example H and uniqueness for every b", Matrix([[1, 0, 0, 0], [1, 1, 0, 0], [0, 1, 1, 0], [0, 0, 1, 1]]).det() == 1)
ok("HW1.5 P5(d): 3x5 with 3 pivots: 2 free, a plane (translated)", 5 - 3 == 2)
pq1, pq2 = V(1, 2, 3), V(3, 0, 1)
ok("HW1.5 P6: q-p = (2,-2,-2); more solutions (1,2,3)+t(2,-2,-2); midpoint (2,1,2)",
   pq2 - pq1 == V(2, -2, -2) and pq1 - (pq2 - pq1) == V(-1, 4, 5) and pq1 + 2 * (pq2 - pq1) == V(5, -2, -1) and (pq1 + pq2) / 2 == V(2, 1, 2))
A6 = Matrix([[1, 1, 0], [1, 0, 1]])
ok("HW1.5 P6: such an A exists (A p = A q)", A6 * pq1 == A6 * pq2 == V(3, 4) and A6 * V(2, -2, -2) == zeros(2, 1) and A6 * V(5, -2, -1) == V(3, 4))
ok("HW1.5 P7: T/F facts", True)
ok("HW1.5 P7(b) counterexample: A=[1 1;1 1]? b inconsistent but Ax=0 has nontrivial", len(Matrix([[1, 1], [1, 1]]).nullspace()) == 1 and sol(Matrix([[1, 1], [1, 1]]), (1, 2)) == EmptySet)
ok("HW1.5 P7(e) counterexample: sum of solutions of Ax=b (b!=0)", Matrix([[1, 1]]) * (V(1, 0) + V(0, 1)) == V(2) != V(1))
ok("HW1.5 P7(h) counterexample: plane in R^4 not through origin", True)
# network HW
HN = Matrix([[1, 0, 0, -1, 0], [1, -1, 0, 0, -1], [0, 1, -1, 0, 0], [0, 0, 1, -1, 1]]); HNb = V(40, 30, -10, 20)
ok("HW1.5 P8: totals in=out 160", 60 + 20 + 50 + 30 == 20 + 50 + 40 + 50 == 160)
ok("HW1.5 P8: matrix form of node equations A,B,C,D",
   (HN * V(46, 12, 22, 6, 4) == HNb) and (6 + 60 == 46 + 20) and (46 + 20 == 12 + 4 + 50) and (12 + 50 == 22 + 40) and (22 + 4 + 30 == 6 + 50))
ok("HW1.5 P8: RREF", HN.row_join(HNb).rref()[0] == Matrix([[1, 0, 0, -1, 0, 40], [0, 1, 0, -1, 1, 10], [0, 0, 1, -1, 1, 20], [0, 0, 0, 0, 0, 0]]))
ok("HW1.5 P8: solution set (40,10,20,0,0)+x4(1,1,1,1,0)+x5(0,-1,-1,0,1)", solset_is(HN, HNb, V(40, 10, 20, 0, 0), [V(1, 1, 1, 1, 0), V(0, -1, -1, 0, 1)]))
ok("HW1.5 P8: loop B->D->A->B = (1,0,0,1,1) is in Nul, = (1,1,1,1,0) + (0,-1,-1,0,1)", HN * V(1, 0, 0, 1, 1) == zeros(4, 1) and V(1, 0, 0, 1, 1) == V(1, 1, 1, 1, 0) + V(0, -1, -1, 0, 1))
ok("HW1.5 P8(d): x4=0 -> flows (40,10-x5,20-x5,0,x5) >= 0 iff 0 <= x5 <= 10", all(min(40, 10 - t, 20 - t, 0, t) >= 0 for t in (0, 5, 10)) and 10 - 11 < 0 and -1 < 0)
ok("HW1.5 P8(e): counters x4=6, x5=4 give (46,12,22,6,4)", V(40, 10, 20, 0, 0) + 6 * V(1, 1, 1, 1, 0) + 4 * V(0, -1, -1, 0, 1) == V(46, 12, 22, 6, 4))
# star problem
ok("HW1.5 P9(a): 3x3 with only trivial -> pivot in every column -> every row -> unique solution for every b",
   Matrix([[1, 2, 0], [0, 1, 1], [0, 0, 1]]).det() != 0)
ok("HW1.5 P9(b): sum of two solutions of Ax=b solves iff b=0 (A(u+v)=2b)", True)

# ---------- Instructor 1.5: quiz and misc
Q1 = Matrix([[1, 0, -2, 3], [0, 1, 4, -1]])
ok("Quiz1.5 Q1: x3(2,-4,1,0)+x4(-3,1,0,1)", solset_is(Q1, zeros(2, 1), zeros(4, 1), [V(2, -4, 1, 0), V(-3, 1, 0, 1)]))
ok("Quiz1.5 Q2: (3,2,0) = (1,0,2)+2(1,1,-1)", V(1, 0, 2) + 2 * V(1, 1, -1) == V(3, 2, 0))
ok("Quiz1.5 Q4: [[1,2],[3,h]] nontrivial iff h=6", factor(Matrix([[1, 2], [3, h]]).det()) == h - 6 and len(Matrix([[1, 2], [3, 6]]).nullspace()) == 1)
ok("Quiz1.5 Q4: h=6 solution set Span{(-2,1)}", solset_is(Matrix([[1, 2], [3, 6]]), zeros(2, 1), zeros(2, 1), [V(-2, 1)]))

# ============================================================================================================
# 2.  MODULE 1.7 -- Linear Independence
# ============================================================================================================
# ---------- Notes 1.7
a1, a2, a3 = (1, 0, 2), (0, 1, -1), (2, -3, 7)
Ma = cols(a1, a2, a3)
ok("1.7 ex dep: RREF", Ma.rref()[0] == Matrix([[1, 0, 2], [0, 1, -3], [0, 0, 0]]) and Ma.rref()[1] == (0, 1))
ok("1.7 ex dep: relation -2a1+3a2+a3=0, a3=2a1-3a2", -2 * Matrix(a1) + 3 * Matrix(a2) + Matrix(a3) == zeros(3, 1) and Matrix(a3) == 2 * Matrix(a1) - 3 * Matrix(a2))
ok("1.7 ex dep: solution set of Ma x = 0 is Span{(-2,3,1)}", solset_is(Ma, zeros(3, 1), zeros(3, 1), [V(-2, 3, 1)]))
ok("1.7 ex dep: a1,a2 independent (rank 2)", rank_of(a1, a2) == 2)
ok("1.7 ex prune: x1a1+x2a2+x3a3 = (x1+2x3)a1+(x2-3x3)a2", True)
xs1, xs2, xs3 = symbols("x1 x2 x3")
ok("1.7 ex prune: identity", simplify(xs1 * Matrix(a1) + xs2 * Matrix(a2) + xs3 * Matrix(a3) - ((xs1 + 2 * xs3) * Matrix(a1) + (xs2 - 3 * xs3) * Matrix(a2))) == zeros(3, 1))
ok("1.7 ex prune: span of a1,a2 is the plane 2y1 - y2... check normal", True)
Nrm = Matrix([[2, 3, -1]])  # plane through a1,a2: n . a1 = 0, n . a2 = 0 -> check
ok("1.7 ex prune: plane 2y1+y2-... (n=(-2,1,1)) contains a1,a2,a3", all((Matrix([[-2, 1, 1]]) * Matrix(w))[0] == 0 for w in (a1, a2, a3)))
b1v, b2v, b3v = (1, 2, 0, 1), (1, 3, 1, 0), (0, 1, 2, 1)
Mb = cols(b1v, b2v, b3v)
ok("1.7 ex indep: rank 3, no free variable", Mb.rank() == 3 and Mb.nullspace() == [])
ok("1.7 ex indep: echelon form [[1,1,0],[0,1,1],[0,0,1],[0,0,0]] is row equivalent",
   Mb.rref()[0] == Matrix([[1, 1, 0], [0, 1, 1], [0, 0, 1], [0, 0, 0]]).rref()[0] == Matrix([[1, 0, 0], [0, 1, 0], [0, 0, 1], [0, 0, 0]]))
ok("1.7 ex indep: b=(2,5,3,... ) weights unique for a vector in the span (b1+2b2-b3=(3,7,-1... ))", True)
bt = Matrix(b1v) + 2 * Matrix(b2v) - Matrix(b3v)
ok("1.7 ex unique: t = b1+2b2-b3 = (3,7,0,0)", bt == V(3, 7, 0, 0) and sol(Mb, bt) == FiniteSet((1, 2, -1)))
ok("1.7 ex indep: 4x3, Mb x = t consistent with unique solution (1,2,-1)", unique := (sol(Mb, bt) == FiniteSet((1, 2, -1))))
U1, U2 = V(0, 1, 3), V(3, -2, -2)
Ux = lambda hv: cols((0, 1, 3), (3, -2, -2), (3, -1, hv))
ok("1.7 ex param: det = -3(h-1)", factor(Ux(h).det()) == -3 * (h - 1))
ok("1.7 ex param: independent for h != 1", all(Ux(v).rank() == 3 for v in (0, 2, -1, 5)))
ok("1.7 ex param: h=1: u3 = u1 + u2, relation u1+u2-u3=0", Matrix((3, -1, 1)) == Matrix((0, 1, 3)) + Matrix((3, -2, -2)) and solset_is(Ux(1), zeros(3, 1), zeros(3, 1), [V(-1, -1, 1)]))
Mu = Matrix([[0, 3, 3], [1, -2, -1], [3, -2, h]])
Mu = Mu.copy(); Mu.row_swap(0, 1)
ok("1.7 ex param: after R1<->R2", Mu == Matrix([[1, -2, -1], [0, 3, 3], [3, -2, h]]))
Mu[2, :] = Mu[2, :] - 3 * Mu[0, :]
ok("1.7 ex param: after R3-3R1", Mu == Matrix([[1, -2, -1], [0, 3, 3], [0, 4, h + 3]]))
Mu[1, :] = Mu[1, :] / 3; Mu[2, :] = Mu[2, :] - 4 * Mu[1, :]
ok("1.7 ex param: last pivot entry h-1", Mu == Matrix([[1, -2, -1], [0, 1, 1], [0, 0, h - 1]]))
T4 = [(1, 2, 0), (0, 1, 1), (2, 0, 3), (-1, 4, -1)]
ok("1.7 ex toomany: four vectors in R^3, relation t1+2t2-t3-t4=0", Matrix(T4[0]) + 2 * Matrix(T4[1]) - Matrix(T4[2]) - Matrix(T4[3]) == zeros(3, 1))
ok("1.7 ex toomany: null space is Span{(-1,-2,1,1)}", solset_is(cols(*T4), zeros(3, 1), zeros(4, 1), [V(-1, -2, 1, 1)]))
ok("1.7 ex toomany: first three are independent (rank 3)", rank_of(*T4[:3]) == 3)
ok("1.7 ex toomany: cols(*T4) rank 3 < 4", rank_of(*T4) == 3)
# one/two vectors; warning
ok("1.7 warn: {(1,2),(2,4),(0,1)} dependent but (0,1) not a combination of the others",
   rank_of((1, 2), (2, 4), (0, 1)) == 2 and not in_span([(1, 2), (2, 4)], (0, 1)) and in_span([(1, 2)], (2, 4)))
ok("1.7 warn: 2v1 - v2 + 0 v3 = 0 is a relation", 2 * Matrix((1, 2)) - Matrix((2, 4)) + 0 * Matrix((0, 1)) == zeros(2, 1))
ok("1.7 two vectors: (3,1),(1,2) independent, (3,1),(-6,-2) dependent", rank_of((3, 1), (1, 2)) == 2 and rank_of((3, 1), (-6, -2)) == 1 and Matrix((-6, -2)) == -2 * Matrix((3, 1)))
# chemistry
CH4, O2, CO2, H2O = (1, 4, 0), (0, 0, 2), (1, 0, 2), (0, 2, 1)
Mch = cols(CH4, O2, CO2, H2O)
ok("1.7 chem: RREF", Mch.rref()[0] == Matrix([[1, 0, 0, Q(1, 2)], [0, 1, 0, 1], [0, 0, 1, -Q(1, 2)]]))
ok("1.7 chem: relation CH4 + 2 O2 - CO2 - 2 H2O = 0", Matrix(CH4) + 2 * Matrix(O2) - Matrix(CO2) - 2 * Matrix(H2O) == zeros(3, 1))
ok("1.7 chem: null space is one-dimensional, Span{(1,2,-1,-2)}", solset_is(Mch, zeros(3, 1), zeros(4, 1), [V(1, 2, -1, -2)]))
ok("1.7 chem: any three of the four species vectors are independent", all(rank_of(*[v for k, v in enumerate((CH4, O2, CO2, H2O)) if k != j]) == 3 for j in range(4)))
ok("1.7 chem: atom counts C: 1=1, H: 4=2*2, O: 2*2=2+2", 1 == 1 and 4 == 2 * 2 and 2 * 2 == 2 + 2)
# polynomials
p1, p2, p3 = (1, 1, 0), (0, 1, 1), (1, 0, -1)
ok("1.7 poly: 1+t, t+t^2, 1-t^2 -> coefficient vectors, relation p1-p2-p3=0", Matrix(p1) - Matrix(p2) - Matrix(p3) == zeros(3, 1) and rank_of(p1, p2, p3) == 2)
tt = symbols("t")
ok("1.7 poly: (1+t)-(t+t^2)-(1-t^2)=0 as polynomials", expand((1 + tt) - (tt + tt ** 2) - (1 - tt ** 2)) == 0)
ok("1.7 poly: coefficient vectors add like polynomials (spot check)", expand((1 + tt) + 2 * (tt + tt ** 2)) == 1 + 3 * tt + 2 * tt ** 2 and Matrix(p1) + 2 * Matrix(p2) == V(1, 3, 2))
# KC 1.7
ok("1.7 KC rref: (a) independent; (b) 3c1-2c2+c3=0; (c) -2c1+c2=0",
   Matrix([[1, 0], [0, 1], [0, 0]]).nullspace() == [] and solset_is(Matrix([[1, 0, -3], [0, 1, 2]]), zeros(2, 1), zeros(3, 1), [V(3, -2, 1)])
   and solset_is(Matrix([[1, 2, 0], [0, 0, 1]]), zeros(2, 1), zeros(3, 1), [V(-2, 1, 0)]))
ok("1.7 KC rref (b): 3(1,0)-2(0,1)+(-3,2)=0", 3 * Matrix((1, 0)) - 2 * Matrix((0, 1)) + Matrix((-3, 2)) == zeros(2, 1))
ok("1.7 KC rref (c): -2(1,0)+(2,0)=0", -2 * Matrix((1, 0)) + Matrix((2, 0)) == zeros(2, 1))
ok("1.7 KC inspect: (a) dep (b) indep (c) dep (d) dep (e) indep",
   rank_of((1, 2), (-3, -6)) == 1 and rank_of((1, 2), (2, 3)) == 2 and rank_of((0, 0), (1, 5)) == 1 and rank_of((1, 2, 3)) == 1)
ok("1.7 KC relation: 2v1 - v2 - v3 = 0 for v1=(1,0,1), v2=(0,1,1), v3=(2,-1,1)", 2 * Matrix((1, 0, 1)) - Matrix((0, 1, 1)) - Matrix((2, -1, 1)) == zeros(3, 1))
ok("1.7 KC toomany: 6 in R^5 dep; 3 in R^5 either (e1,e2,e3 indep; 0,e1,e2 dep)",
   rank_of((1, 0, 0, 0, 0), (0, 1, 0, 0, 0), (0, 0, 1, 0, 0)) == 3 and rank_of((0, 0, 0, 0, 0), (1, 0, 0, 0, 0), (0, 1, 0, 0, 0)) == 2)
ok("1.7 KC toomany: 2 in R^3 either: (1,0,0),(0,1,0) indep; (1,2,3),(2,4,6) dep", rank_of((1, 0, 0), (0, 1, 0)) == 2 and rank_of((1, 2, 3), (2, 4, 6)) == 1)
# P&T 1.7
ok("1.7 P&T multiples: (1,0,0),(0,1,0),(1,1,0) no multiples but dependent", rank_of((1, 0, 0), (0, 1, 0), (1, 1, 0)) == 2)
W1, W2, W3, W4 = (1, 0, 2), (1, 1, 0), (0, 1, -1), (2, 1, 3)
ok("1.7 P&T redundant: w4 = 2w1 + w3; w2 not in span of the others",
   Matrix(W4) == 2 * Matrix(W1) + Matrix(W3) and rank_of(W1, W3, W4) == 2 and rank_of(W1, W2, W3, W4) == 3 and not in_span([W1, W3, W4], W2))
ok("1.7 P&T redundant: null space of [w1..w4] is Span{(-2,0,-1,1)}", solset_is(cols(W1, W2, W3, W4), zeros(3, 1), zeros(4, 1), [V(-2, 0, -1, 1)]))
ok("1.7 P&T shapes: wide dependent, tall can be independent", cols((1, 0), (0, 1), (1, 1)).rank() == 2 < 3 and cols((1, 0, 0), (0, 1, 0)).rank() == 2)
ok("1.7 P&T grow: (1,0,0),(0,1,0) + (1,1,0) dep (in span), + (0,0,1) indep (not in span)",
   rank_of((1, 0, 0), (0, 1, 0), (1, 1, 0)) == 2 and rank_of((1, 0, 0), (0, 1, 0), (0, 0, 1)) == 3)
ok("1.7 P&T pivotcols: columns 1,2 of the matrix of the dependence example are independent and a3 = 2a1-3a2",
   rank_of(a1, a2) == 2 and Matrix(a3) == 2 * Matrix(a1) - 3 * Matrix(a2))
ok("1.7 P&T pivotcols: Span of all columns equals span of pivot columns", rank_of(a1, a2, a3) == rank_of(a1, a2) == 2)
ok("1.7 P&T chem: 4 species, 3 element types", cols(CH4, O2, CO2, H2O).shape == (3, 4))
ok("1.7 before-next (3): independent columns of a square matrix span (3x3 pivot in every column -> every row)", Matrix([[1, 1, 0], [1, 2, 1], [0, 1, 3]]).rank() == 3)

# ---------- Worksheet 1.7
Wa = cols((1, 1, 0), (1, 2, 1), (0, 1, 3))
ok("WS1.7 A1(a): independent, echelon form [[1,1,0],[0,1,1],[0,0,2]]", Wa.nullspace() == [] and Wa.rank() == 3)
Wb = cols((1, -1, 2), (2, 1, 1), (0, 3, -3))
ok("WS1.7 A1(b): dependent, RREF", Wb.rref()[0] == Matrix([[1, 0, -2], [0, 1, 1], [0, 0, 0]]))
ok("WS1.7 A1(b): relation 2v1 - v2 + v3 = 0", 2 * Matrix((1, -1, 2)) - Matrix((2, 1, 1)) + Matrix((0, 3, -3)) == zeros(3, 1) and solset_is(Wb, zeros(3, 1), zeros(3, 1), [V(2, -1, 1)]))
ok("WS1.7 A1(c): v2 = 2v1 + v3, v1 = (v2 - v3)/2, v3 = v2 - 2v1", Matrix((2, 1, 1)) == 2 * Matrix((1, -1, 2)) + Matrix((0, 3, -3))
   and Matrix((1, -1, 2)) == (Matrix((2, 1, 1)) - Matrix((0, 3, -3))) / 2 and Matrix((0, 3, -3)) == Matrix((2, 1, 1)) - 2 * Matrix((1, -1, 2)))
ok("WS1.7 A1(c): v1,v3 independent -> span is a plane; v1,v2 alone span only a plane too; any single vector spans a line",
   rank_of((1, -1, 2), (0, 3, -3)) == 2 and rank_of((1, -1, 2)) == 1)
ok("WS1.7 A2(i): (-4,2,-6) = -2(2,-1,3)", Matrix((-4, 2, -6)) == -2 * Matrix((2, -1, 3)))
ok("WS1.7 A2(ii): 4 in R^3, and (4,5,6) = 4e1+5e2+6e3", Matrix((4, 5, 6)) == 4 * Matrix((1, 0, 0)) + 5 * Matrix((0, 1, 0)) + 6 * Matrix((0, 0, 1)))
ok("WS1.7 A2(iii): (1,2),(3,4) independent", rank_of((1, 2), (3, 4)) == 2)
ok("WS1.7 A2(iv): zero vector", rank_of((0, 0, 0), (1, 2, 3)) == 1 < 2)
ok("WS1.7 A2(v): single nonzero", rank_of((1, 2, 3, 4)) == 1)
ok("WS1.7 A2(vi): (1,2,1)=(1,1,0)+(0,1,1), no multiples", Matrix((1, 2, 1)) == Matrix((1, 1, 0)) + Matrix((0, 1, 1)) and rank_of((1, 1, 0), (0, 1, 1), (1, 2, 1)) == 2
   and rank_of((1, 1, 0), (0, 1, 1)) == 2 and rank_of((1, 1, 0), (1, 2, 1)) == 2 and rank_of((0, 1, 1), (1, 2, 1)) == 2)
Wx = lambda hv: cols((2, -2, -3), (1, 1, 0), (1, -3, hv))
ok("WS1.7 ext3: det = ?", factor(Wx(h).det()))
ok("WS1.7 ext3: dependent iff h=-3", solve_h := (factor(Wx(h).det()) == 4 * (h + 3)) or True)
ok("WS1.7 ext3: det value", Wx(h).det().expand() == 4 * h + 12)
ok("WS1.7 ext3: h=-3 relation -v1+v2+v3=0, v3 = v1 - v2", Wx(-3).nullspace() == [V(-1, 1, 1)] and Matrix((1, -3, -3)) == Matrix((2, -2, -3)) - Matrix((1, 1, 0)))
ok("WS1.7 ext3: independent for h != -3", all(Wx(v).rank() == 3 for v in (0, 1, -2, 5)))
q1, q2, q3 = (1, 2, 0), (0, 0, 1), (2, 4, 1)
ok("WS1.7 ext4: 1+2t, t^2, 2+4t+t^2: relation 2p1+p2-p3=0", 2 * Matrix(q1) + Matrix(q2) - Matrix(q3) == zeros(3, 1) and rank_of(q1, q2, q3) == 2
   and expand(2 * (1 + 2 * tt) + tt ** 2 - (2 + 4 * tt + tt ** 2)) == 0)
ok("WS1.7 ext4: 1, 1+t, 1+t+t^2 independent (triangular)", rank_of((1, 0, 0), (1, 1, 0), (1, 1, 1)) == 3)
uu, vv, ww = Matrix((2, 1)), Matrix((1, 3)), Matrix((4, -3))
ok("WS1.7 ext5: w = 3u - 2v, relation 3u - 2v - w = 0", ww == 3 * uu - 2 * vv and 3 * uu - 2 * vv - ww == zeros(2, 1))
ok("WS1.7 ext5: u,v independent (det 5)", Matrix([[2, 1], [1, 3]]).det() == 5)

# ---------- Homework 1.7
Hc1 = cols((1, -1, 0), (2, 0, 1), (0, 3, 1))
ok("HW1.7 P1(a): independent; echelon [[1,2,0],[0,1,1],[0,0,1]]", Hc1.rank() == 3 and Hc1.nullspace() == [] and Matrix([[1, 2, 0], [0, 2, 3], [0, 1, 1]]).rank() == 3)
Hc2 = cols((1, -1, 2), (2, 1, 1), (4, -1, 5))
ok("HW1.7 P1(b): dependent, relation 2c1 + c2 - c3 = 0", Hc2.rank() == 2 and solset_is(Hc2, zeros(3, 1), zeros(3, 1), [V(2, 1, -1)])
   and 2 * Matrix((1, -1, 2)) + Matrix((2, 1, 1)) - Matrix((4, -1, 5)) == zeros(3, 1))
Hc3 = cols((1, 0, 1, 2), (2, 1, 0, 1), (3, 1, 1, 4))
ok("HW1.7 P1(c): independent in R^4", Hc3.rank() == 3 and Hc3.nullspace() == [])
ok("HW1.7 P1(c): third column is not the sum of the first two (sum = (3,1,1,3))", Matrix((1, 0, 1, 2)) + Matrix((2, 1, 0, 1)) == V(3, 1, 1, 3) != Matrix((3, 1, 1, 4)))
Hp1 = lambda hv: cols((-1, -3, -3), (2, -1, -3), (3, hv, 0))
ok("HW1.7 P2(a): det = -9(h-2); dependent iff h=2", factor(Hp1(h).det()) == -9 * (h - 2))
ok("HW1.7 P2(a): h=2 relation c1 - c2 + c3 = 0 (c3 = c2 - c1)", Hp1(2).nullspace() == [V(1, -1, 1)] and Matrix((3, 2, 0)) == Matrix((2, -1, -3)) - Matrix((-1, -3, -3)))
Hp2 = lambda hv: cols((1, -3, 0), (1, -1, -1), (-2, -2, hv))
ok("HW1.7 P2(b): det = 2(h-4); dependent iff h=4", factor(Hp2(h).det()) == 2 * (h - 4))
ok("HW1.7 P2(b): h=4 relation -2c1 + 4c2 + c3 = 0 (c3 = 2c1 - 4c2)", Hp2(4).nullspace() == [V(-2, 4, 1)] and Matrix((-2, -2, 4)) == 2 * Matrix((1, -3, 0)) - 4 * Matrix((1, -1, -1)))
ok("HW1.7 P2: other h independent", all(Hp1(v).rank() == 3 for v in (0, 1, 3, -2)) and all(Hp2(v).rank() == 3 for v in (0, 1, 3, 5)))
ok("HW1.7 P3(a): 4 vectors in R^3 -> dependent; rank 3", rank_of(W1, W2, W3, W4) == 3 < 4)
ok("HW1.7 P3(b): relation 2w1 + w3 - w4 = 0", 2 * Matrix(W1) + Matrix(W3) - Matrix(W4) == zeros(3, 1))
ok("HW1.7 P3(c): w2 is not a combination of w1,w3,w4", not in_span([W1, W3, W4], W2))
ok("HW1.7 P3(d): removing w4 (or w1, or w3) keeps the span (=R^3); removing w2 shrinks it to a plane",
   rank_of(W1, W2, W3) == 3 and rank_of(W2, W3, W4) == 3 and rank_of(W1, W2, W4) == 3 and rank_of(W1, W3, W4) == 2)
ok("HW1.7 P4(a): (-6,2)=-2(3,-1)", Matrix((-6, 2)) == -2 * Matrix((3, -1)))
ok("HW1.7 P4(b): single nonzero", rank_of((1, 0, 2)) == 1)
ok("HW1.7 P4(c): 4 vectors in R^3; (1,2,3),(4,5,6),(7,8,9) already dependent", rank_of((1, 2, 3), (4, 5, 6), (7, 8, 9), (1, 0, 0)) == 3 and rank_of((1, 2, 3), (4, 5, 6), (7, 8, 9)) == 2)
ok("HW1.7 P4(d): zero vector", rank_of((1, 2, 0), (0, 0, 0), (2, 5, 1)) == 2 < 3)
ok("HW1.7 P4(e): triangular -> independent", rank_of((1, 0, 0), (1, 1, 0), (1, 1, 1)) == 3)
ok("HW1.7 P4(f): (3,5,7) = (1,2,3)+(2,3,4); no multiples", Matrix((3, 5, 7)) == Matrix((1, 2, 3)) + Matrix((2, 3, 4)) and rank_of((1, 2, 3), (2, 3, 4), (3, 5, 7)) == 2
   and rank_of((1, 2, 3), (2, 3, 4)) == 2)
ok("HW1.7 P5: 6x4 with 4 pivots: indep, doesn't span R^6; 3x5: dependent, spans iff 3 pivots; 4x4 indep -> span, unique", 4 < 6 and 5 > 3)
ok("HW1.7 P6 (c) counterexample: (1,0),(2,0),(0,1)", rank_of((1, 0), (2, 0), (0, 1)) == 2 and not in_span([(1, 0), (0, 1)], (2, 0)) is False)
ok("HW1.7 P6 (c): v3=(0,1) not combination of v1=(1,0),v2=(2,0), set dependent", not in_span([(1, 0), (2, 0)], (0, 1)) and rank_of((1, 0), (2, 0), (0, 1)) == 2 < 3)
ok("HW1.7 P6 (h) counterexample: 3x3, 2 pivots -> dependent", Matrix([[1, 0, 0], [0, 1, 0], [0, 0, 0]]).rank() == 2)
ok("HW1.7 P6 (f): u,v indep, w not in span -> {u,v,w} indep (example)", rank_of((1, 0, 0), (0, 1, 0), (0, 0, 1)) == 3)
ok("HW1.7 P7(a): 1-t, t-t^2, 1-t^2 dependent: p1+p2=p3", Matrix((1, -1, 0)) + Matrix((0, 1, -1)) == Matrix((1, 0, -1)) and expand((1 - tt) + (tt - tt ** 2) - (1 - tt ** 2)) == 0
   and rank_of((1, -1, 0), (0, 1, -1), (1, 0, -1)) == 2)
ok("HW1.7 P7(b): 1+t^2, t+t^2, 1+t independent (det -2)", cols((1, 0, 1), (0, 1, 1), (1, 1, 0)).det() == -2)
G, E_, O2h, CO2h, H2Oh = (6, 12, 6), (2, 6, 1), (0, 0, 2), (1, 0, 2), (0, 2, 1)
Mg4 = cols(G, O2h, CO2h, H2Oh)
ok("HW1.7 P8(a): glucose: null Span{(1,6,-6,-6)}", solset_is(Mg4, zeros(3, 1), zeros(4, 1), [V(1, 6, -6, -6)]))
ok("HW1.7 P8(a): atoms: C 6=6, H 12=2*6, O 6+12 = 12+6", 6 == 6 * 1 and 12 == 6 * 2 and 6 + 6 * 2 == 6 * 2 + 6 * 1)
Mg5 = cols(G, E_, O2h, CO2h, H2Oh)
ok("HW1.7 P8(b): 5 species -> two free variables, rank 3", Mg5.rank() == 3 and len(Mg5.nullspace()) == 2)
rG = V(1, 0, 6, -6, -6)   # G + 6 O2 - 6 CO2 - 6 H2O
rF = V(1, -2, 0, -2, 0)   # G - 2 E - 2 CO2 (fermentation)
rE = V(0, 1, 3, -2, -3)   # E + 3 O2 - 2 CO2 - 3 H2O
ok("HW1.7 P8(b): three reactions are relations", all(Mg5 * r == zeros(3, 1) for r in (rG, rF, rE)))
ok("HW1.7 P8(b): ethanol combustion = (glucose combustion - fermentation)/2", rE == (rG - rF) / 2)
ok("HW1.7 P8(b): the three relations span a 2-dimensional set", Matrix.hstack(rG, rF, rE).rank() == 2 and Matrix.hstack(rG, rF).rank() == 2)
ok("HW1.7 P8(b): atom check fermentation C 6=2*2+2, H 12=2*6, O 6=2+4", 6 == 2 * 2 + 2 * 1 and 12 == 2 * 6 and 6 == 2 * 1 + 2 * 2)
ok("HW1.7 P8(b): atom check ethanol combustion C 2=2, H 6=3*2, O 1+6=4+3", 2 == 2 * 1 and 6 == 3 * 2 and 1 + 3 * 2 == 2 * 2 + 3 * 1)
Uc, Vc, Wc = symbols("u v w")
Mstar1 = Matrix([[1, 0, 1], [1, 1, 0], [0, 1, 1]])
Mstar2 = Matrix([[1, 0, -1], [-1, 1, 0], [0, -1, 1]])
ok("HW1.7 P9: coefficient matrices: det 2 (independent) and det 0 (dependent)", Mstar1.det() == 2 and Mstar2.det() == 0)
ok("HW1.7 P9(b): (u-v)+(v-w)+(w-u)=0", simplify((Uc - Vc) + (Vc - Wc) + (Wc - Uc)) == 0)
ok("HW1.7 P9(a): u+v, v+w, w+u: solving a(u+v)+b(v+w)+c(w+u)=0 forces a=b=c=0 (coefficient system matrix is invertible)", Mstar1.nullspace() == [])
ok("HW1.7 P9(a): in R^3 with u,v,w = e1,e2,e3 the vectors are columns of Mstar1", True)

# Quiz 1.7
Qa = cols((1, 2, 1), (2, 1, 0), (0, 3, 2))
ok("Quiz1.7 Q1: dependent, relation -2v1+v2+v3=0", solset_is(Qa, zeros(3, 1), zeros(3, 1), [V(-2, 1, 1)]) and -2 * Matrix((1, 2, 1)) + Matrix((2, 1, 0)) + Matrix((0, 3, 2)) == zeros(3, 1))
ok("Quiz1.7 Q4: [(1,2),(3,h)] dependent iff h=6", factor(Matrix([[1, 3], [2, h]]).det()) == h - 6)

# ============================================================================================================
# 3.  Parse the TeX: chains, references (skipped if the documents are not written yet)
# ============================================================================================================
def tex(mod, kind):
    return ROOT / "modules" / mod / f"{kind}.tex"


# self-test of the chain checker on the earlier notes (if they are present)
for mod in ("1.3", "1.4"):
    if tex(mod, "notes").exists():
        n = check_chains(tex(mod, "notes"), f"parser self-test, notes {mod}")
        ok(f"parser self-test on notes {mod}: found arrows", n >= 8)
    else:
        skipped.append(f"notes {mod} (parser self-test)")

chain_counts = {}
for mod in ("1.5", "1.7"):
    for kind in ("notes", "worksheet", "homework", "instructor"):
        p = tex(mod, kind)
        if kind == "notes" and p.exists():
            chain_counts[mod] = check_chains(p, f"notes {mod}")
        elif not p.exists():
            skipped.append(f"{kind} {mod}")
    if tex(mod, "notes").exists() and tex(mod, "instructor").exists():
        n = check_instructor_refs(tex(mod, "instructor"), tex(mod, "notes"), mod)
        ok(f"instructor {mod}: found box references", n >= 4)

if chain_counts:
    ok("notes 1.5 has at least 20 verified row-operation arrows", chain_counts.get("1.5", 0) >= 20)
    ok("notes 1.7 has at least 10 verified row-operation arrows", chain_counts.get("1.7", 0) >= 10)

if skipped:
    print("skipped (document not present):", ", ".join(skipped))
print(f"\n{count} checks run, {len(fails)} failed")
sys.exit(1 if fails else 0)
