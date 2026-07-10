#!/usr/bin/env python3
"""
audit_dead_code.py — Reachability audit for Python / FastAPI backends.

Design philosophy
------------------
Dead-code detection in Python is formally undecidable, so every result here is a
*review candidate*, never an auto-delete instruction. This tool is READ-ONLY: it
runs analyzers in report mode only and never modifies the target codebase.

Two complementary passes:

1. Python pass (deterministic tools + AST safety net)
   - ruff   : fast, sound unused imports/vars/redefinitions (F401/F841/F811)
   - vulture: unused funcs/classes + UNREACHABLE code, with confidence scores
   - deadcode (optional): AST corroboration signal
   Framework false positives (route handlers, Pydantic fields, DI params,
   __all__ exports, dunder methods) are suppressed by our own AST analysis so we
   don't depend on each tool's inconsistent allowlist flags.

2. Cross-stack endpoint pass (LLM/tool can't be replaced by a Python linter)
   A route is "live" to every Python linter because a decorator registers it, yet
   it can still be dead if no client calls it. We extract FastAPI routes via AST
   and grep their path strings across client globs (Swift/TS/JS/any language).

Exit code is always 0 (this is an audit, not a gate) unless --fail-on is set,
or unless NO analyzer ran at all (exit 2) — a report from zero engines is
meaningless and must not look like a clean bill of health.
"""
from __future__ import annotations

import argparse
import ast
import fnmatch
import glob
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

# ----------------------------------------------------------------------------
# Defaults (FastAPI-aware, override via --config TOML)
# ----------------------------------------------------------------------------
DEFAULT_ROUTE_METHODS = {
    "get", "post", "put", "patch", "delete", "options", "head", "trace",
    "websocket",
}
# Decorators (as `<obj>.<attr>`) that mean "framework calls this, not your code".
DEFAULT_LIVE_DECORATORS = [
    "*.get", "*.post", "*.put", "*.patch", "*.delete", "*.options", "*.head",
    "*.websocket", "*.middleware", "*.exception_handler", "*.on_event",
    "*.route",                       # Flask/Starlette style
    "app.task", "*.task",            # Celery
    "*.timer", "*.scheduled",        # common scheduler decorators
]
# DI markers: an argument defaulting to one of these is framework-injected, so an
# "unused argument" finding on it is a false positive.
DEFAULT_DI_MARKERS = {
    "Depends", "Security", "Header", "Query", "Path", "Cookie", "Body", "Form",
    "File", "Provide",  # dependency-injector
}
# Base classes whose *fields* (class-level annotations) are schema, not dead vars.
DEFAULT_SCHEMA_BASES = [
    "BaseModel", "BaseSettings", "Base", "DeclarativeBase", "TypedDict",
    "Enum", "IntEnum", "StrEnum", "Struct",
]
DEFAULT_IGNORE_NAMES = [
    "__*__",            # dunder
    "test_*", "Test*",  # pytest discovery
    "conftest",
    "setUp", "tearDown", "setUpClass", "tearDownClass",  # unittest hooks
]
DEFAULT_INFRA_PATHS = [
    "/health", "/healthz", "/livez", "/readyz", "/ping", "/metrics",
    "/docs", "/redoc", "/openapi.json", "/", "/favicon.ico",
]
DEFAULT_EXCLUDE = [
    "*/.venv/*", "*/venv/*", "*/__pycache__/*", "*/migrations/*",
    "*/.git/*", "*/node_modules/*", "*/build/*", "*/dist/*",
]


# ----------------------------------------------------------------------------
# Data model
# ----------------------------------------------------------------------------
@dataclass
class Finding:
    file: str
    line: int
    name: str
    kind: str            # function | class | variable | import | unreachable
    message: str
    confidence: int      # 0-100
    tools: set = field(default_factory=set)

    def key(self):
        return (self.file, self.line, self.name)


@dataclass
class Route:
    method: str
    path: str
    func: str
    file: str
    line: int


@dataclass
class SymbolIndex:
    # (abspath, lineno) -> {"kind","name","decorators":[str]}
    defs: dict = field(default_factory=dict)
    # abspath -> list of (start_line, end_line, [base_names]) for classes
    class_spans: dict = field(default_factory=dict)
    # (abspath, lineno) -> True  for DI-injected argument names we should ignore
    di_arg_lines: set = field(default_factory=set)
    # names exported via __all__
    exported: set = field(default_factory=set)
    routes: list = field(default_factory=list)


# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
def load_config(path: str | None) -> dict:
    cfg = {
        "live_decorators": list(DEFAULT_LIVE_DECORATORS),
        "di_markers": set(DEFAULT_DI_MARKERS),
        "schema_bases": list(DEFAULT_SCHEMA_BASES),
        "ignore_names": list(DEFAULT_IGNORE_NAMES),
        "infra_paths": list(DEFAULT_INFRA_PATHS),
        "exclude": list(DEFAULT_EXCLUDE),
    }
    if not path:
        return cfg
    try:
        import tomllib
        with open(path, "rb") as f:
            user = tomllib.load(f).get("audit_dead_code", {})
    except Exception as e:  # noqa: BLE001
        print(f"! could not read config {path}: {e}", file=sys.stderr)
        return cfg
    for k in ("live_decorators", "schema_bases", "ignore_names", "infra_paths",
              "exclude"):
        if k in user:
            cfg[k] = list(user[k])
    if "di_markers" in user:
        cfg["di_markers"] = set(user["di_markers"])
    return cfg


# ----------------------------------------------------------------------------
# AST indexing
# ----------------------------------------------------------------------------
def _decorator_name(dec: ast.expr) -> str:
    """Render @a.b.c(...) -> 'a.b.c' (drop call args)."""
    node = dec.func if isinstance(dec, ast.Call) else dec
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _base_names(cls: ast.ClassDef) -> list[str]:
    out = []
    for b in cls.bases:
        n = _decorator_name(b)  # reuse dotted-name renderer
        if n:
            out.append(n.split(".")[-1])
    return out


def _iter_py_files(paths, exclude):
    for p in paths:
        p = Path(p)
        if p.is_file() and p.suffix == ".py":
            files = [p]
        elif p.is_dir():
            files = p.rglob("*.py")
        else:
            files = []
        for f in files:
            ap = str(f.resolve())
            if any(fnmatch.fnmatch(ap, pat) for pat in exclude):
                continue
            yield f


def build_index(paths, cfg) -> SymbolIndex:
    idx = SymbolIndex()
    di_markers = cfg["di_markers"]
    route_methods = DEFAULT_ROUTE_METHODS
    for f in _iter_py_files(paths, cfg["exclude"]):
        ap = str(f.resolve())
        try:
            src = f.read_text(encoding="utf-8")
            tree = ast.parse(src, filename=ap)
        except (SyntaxError, UnicodeDecodeError):
            continue
        idx.class_spans.setdefault(ap, [])

        for node in ast.walk(tree):
            # __all__ exports
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id == "__all__":
                        if isinstance(node.value, (ast.List, ast.Tuple)):
                            for el in node.value.elts:
                                if isinstance(el, ast.Constant) and isinstance(el.value, str):
                                    idx.exported.add(el.value)

            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                decs = [_decorator_name(d) for d in node.decorator_list]
                kind = "class" if isinstance(node, ast.ClassDef) else "function"
                idx.defs[(ap, node.lineno)] = {
                    "kind": kind, "name": node.name, "decorators": decs,
                }
                if isinstance(node, ast.ClassDef):
                    end = getattr(node, "end_lineno", node.lineno)
                    idx.class_spans[ap].append((node.lineno, end, _base_names(node)))

            # Routes + DI args on function defs
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for d in node.decorator_list:
                    if isinstance(d, ast.Call):
                        dn = _decorator_name(d)
                        method = dn.split(".")[-1].lower()
                        if method in route_methods and d.args:
                            first = d.args[0]
                            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                                idx.routes.append(Route(
                                    method=method.upper(), path=first.value,
                                    func=node.name, file=ap, line=node.lineno,
                                ))
                # DI-injected arguments -> ignore "unused arg" findings on them
                _mark_di_args(node, ap, di_markers, idx)
    return idx


def _mark_di_args(node, ap, di_markers, idx):
    args = node.args
    # align defaults to trailing positional args
    pos_defaults = args.defaults
    pos_args = args.args[len(args.args) - len(pos_defaults):] if pos_defaults else []
    pairs = list(zip(pos_args, pos_defaults))
    for a, kd in zip(args.kwonlyargs, args.kw_defaults):
        if kd is not None:
            pairs.append((a, kd))
    for a, dflt in pairs:
        if isinstance(dflt, ast.Call):
            callee = _decorator_name(dflt).split(".")[-1]
            if callee in di_markers:
                idx.di_arg_lines.add((ap, a.lineno))
        # annotation-based DI: Annotated[X, Depends(...)]
        if isinstance(a.annotation, ast.Subscript):
            src = ast.dump(a.annotation)
            if any(m in src for m in di_markers):
                idx.di_arg_lines.add((ap, a.lineno))


# ----------------------------------------------------------------------------
# Tool runners
# ----------------------------------------------------------------------------
def _which(tool):
    return shutil.which(tool) is not None


def _fail_status(proc) -> str:
    """Summarize a failed analyzer run: exit code + last stderr line."""
    err = (proc.stderr or "").strip().splitlines()
    detail = err[-1][:120] if err else ""
    return f"failed (exit {proc.returncode}{': ' + detail if detail else ''})"


def run_ruff(paths, cfg, engines) -> list[Finding]:
    if not _which("ruff"):
        engines["ruff"] = "not found"
        return []
    cmd = ["ruff", "check", *map(str, paths),
           "--select", "F401,F811,F841", "--output-format", "json",
           "--no-cache"]
    for pat in cfg["exclude"]:
        cmd += ["--exclude", pat]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        rows = json.loads(proc.stdout or "[]")
    except Exception as e:  # noqa: BLE001
        engines["ruff"] = f"failed ({e.__class__.__name__}: {e})"
        return []
    findings = []
    for r in rows:
        code = r.get("code") or ""
        kind = {"F401": "import", "F841": "variable", "F811": "function"}.get(code, "variable")
        name = ""
        m = re.search(r"`([^`]+)`", r.get("message", ""))
        if m:
            name = m.group(1)
        findings.append(Finding(
            file=str(Path(r["filename"]).resolve()),
            line=r["location"]["row"], name=name, kind=kind,
            message=f"[{code}] {r.get('message','')}", confidence=100,
            tools={"ruff"},
        ))
    # ruff exits 0 (clean) or 1 (violations found); anything else is an error
    if proc.returncode not in (0, 1) and not findings:
        engines["ruff"] = _fail_status(proc)
    else:
        engines["ruff"] = "ok"
    return findings


VULT_RE = re.compile(r"^(?P<file>.+?):(?P<line>\d+): (?P<msg>.+?) \((?P<conf>\d+)% confidence\)$")


def run_vulture(paths, cfg, engines) -> list[Finding]:
    if not _which("vulture"):
        engines["vulture"] = "not found"
        return []
    cmd = ["vulture", *map(str, paths), "--min-confidence", "60",
           "--ignore-decorators", ",".join("@" + d for d in cfg["live_decorators"]),
           "--ignore-names", ",".join(cfg["ignore_names"]),
           "--exclude", ",".join(cfg["exclude"])]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        lines = proc.stdout.splitlines()
    except Exception as e:  # noqa: BLE001
        engines["vulture"] = f"failed ({e.__class__.__name__}: {e})"
        return []
    findings = []
    for ln in lines:
        m = VULT_RE.match(ln.strip())
        if not m:
            continue
        msg = m.group("msg")
        conf = int(m.group("conf"))
        if msg.startswith("unreachable"):
            kind, name = "unreachable", ""
        else:
            nm = re.search(r"'([^']+)'", msg)
            name = nm.group(1) if nm else ""
            if "function" in msg or "method" in msg:
                kind = "function"
            elif "class" in msg:
                kind = "class"
            elif "import" in msg:
                kind = "import"
            elif "property" in msg or "attribute" in msg:
                kind = "attribute"
            else:
                kind = "variable"
        findings.append(Finding(
            file=str(Path(m.group("file")).resolve()),
            line=int(m.group("line")), name=name, kind=kind,
            message=msg, confidence=conf, tools={"vulture"},
        ))
    # vulture exits 0 (clean) or 3 (dead code found); a nonzero exit with no
    # parseable findings means it actually failed (bad args, unreadable input)
    if proc.returncode != 0 and not findings:
        engines["vulture"] = _fail_status(proc)
    else:
        engines["vulture"] = "ok"
    return findings


DC_RE = re.compile(r"^(?P<file>.+?):(?P<line>\d+):\d+: DC\d+ (?P<msg>.+)$")


def run_deadcode(paths, cfg, engines) -> list[Finding]:
    if not _which("deadcode"):
        engines["deadcode"] = "not found"
        return []
    cmd = ["deadcode", *map(str, paths), "--no-color"]
    for pat in cfg["exclude"]:
        cmd += ["--exclude", pat]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        lines = proc.stdout.splitlines()
    except Exception as e:  # noqa: BLE001
        engines["deadcode"] = f"failed ({e.__class__.__name__}: {e})"
        return []
    findings = []
    for ln in lines:
        m = DC_RE.match(ln.strip())
        if not m:
            continue
        msg = m.group("msg")
        nm = re.search(r"`([^`]+)`", msg)
        name = nm.group(1) if nm else ""
        low = msg.lower()
        kind = ("function" if "function" in low else
                "class" if "class" in low else
                "import" if "import" in low else
                "variable")
        findings.append(Finding(
            file=str(Path(m.group("file")).resolve()),
            line=int(m.group("line")), name=name, kind=kind,
            message=msg, confidence=80, tools={"deadcode"},
        ))
    # deadcode exits nonzero both for findings and for crashes; only a run with
    # no parseable findings and a nonzero exit counts as a failure
    if proc.returncode != 0 and not findings:
        engines["deadcode"] = _fail_status(proc)
    else:
        engines["deadcode"] = "ok"
    return findings


# ----------------------------------------------------------------------------
# AST-based false-positive suppression (the safety net)
# ----------------------------------------------------------------------------
def _enclosing_class_bases(idx, file, line):
    for start, end, bases in idx.class_spans.get(file, []):
        if start <= line <= end:
            return bases
    return None


def is_false_positive(fnd: Finding, idx: SymbolIndex, cfg) -> str | None:
    """Return a reason string if this finding is a framework false positive."""
    live = cfg["live_decorators"]
    schema_bases = set(cfg["schema_bases"])

    # 1) def decorated with a live decorator (route/task/handler)
    d = idx.defs.get((fnd.file, fnd.line))
    if d:
        for dec in d["decorators"]:
            if any(fnmatch.fnmatch(dec, pat) or dec.endswith(pat.lstrip("*."))
                   for pat in live):
                return f"registered via @{dec} (framework-invoked)"

    # 2) exported through __all__
    if fnd.name and fnd.name in idx.exported:
        return "re-exported via __all__"

    # 3) DI-injected argument reported as unused
    if (fnd.file, fnd.line) in idx.di_arg_lines and fnd.kind in ("variable", "attribute"):
        return "dependency-injected parameter"

    # 4) class-level field of a schema/ORM base (Pydantic/SQLAlchemy/Enum/TypedDict)
    if fnd.kind in ("variable", "attribute"):
        bases = _enclosing_class_bases(idx, fnd.file, fnd.line)
        if bases and (set(bases) & schema_bases):
            return f"field of {bases[0]} subclass (schema/model attribute)"

    # 5) ignore-name patterns (dunder/test/etc.)
    if fnd.name and any(fnmatch.fnmatch(fnd.name, pat) for pat in cfg["ignore_names"]):
        return "matches ignore-name pattern"

    return None


# ----------------------------------------------------------------------------
# Merge + tier
# ----------------------------------------------------------------------------
def merge(findings: list[Finding]) -> list[Finding]:
    merged: dict = {}
    for f in findings:
        k = f.key()
        if k in merged:
            merged[k].tools |= f.tools
            merged[k].confidence = max(merged[k].confidence, f.confidence)
        else:
            merged[k] = f
    return list(merged.values())


def tier(f: Finding) -> str:
    if f.kind == "unreachable":
        return "unreachable"
    if "ruff" in f.tools:
        return "high"                      # sound
    if len(f.tools) >= 2:
        return "high"                      # corroborated by 2+ analyzers
    if f.confidence >= 90:
        return "high"
    if f.confidence >= 60:
        return "medium"
    return "low"


# ----------------------------------------------------------------------------
# Cross-stack endpoint audit
# ----------------------------------------------------------------------------
def _normalize_path(p: str) -> list[str]:
    """Return searchable fragments for a route path.

    /users/{user_id}/posts -> ['/users/', '/posts'] plus the literal.
    Clients often build paths dynamically, so we match on stable literal
    segments rather than the whole templated string.
    """
    literal = p
    segments = [s for s in re.split(r"\{[^}]+\}", p) if s and s != "/"]
    frags = [literal] + [s.rstrip("/") for s in segments if len(s.rstrip("/")) > 1]
    return sorted(set(frags), key=len, reverse=True)


def audit_endpoints(routes, client_globs, infra_paths):
    client_files = []
    for g in client_globs:
        client_files += glob.glob(g, recursive=True)
    corpus = ""
    for cf in client_files:
        try:
            corpus += Path(cf).read_text(encoding="utf-8", errors="ignore") + "\n"
        except OSError:
            continue

    results = {"used": [], "infra": [], "candidate": [], "client_files": len(client_files)}
    def _is_infra(path):
        for ip in infra_paths:
            if ip == "/":
                if path == "/":
                    return True
                continue
            if path == ip or path.startswith(ip.rstrip("/") + "/"):
                return True
        return False

    for r in routes:
        if _is_infra(r.path):
            results["infra"].append(r)
            continue
        frags = _normalize_path(r.path)
        hit = any(frag in corpus for frag in frags)
        (results["used"] if hit else results["candidate"]).append(r)
    return results


# ----------------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------------
def _engine_line(engines) -> str:
    parts = []
    for t in ("ruff", "vulture", "deadcode"):
        s = engines.get(t, "not run")
        if s == "ok":
            parts.append(f"{t} ✓")
        elif s == "disabled":
            parts.append(f"{t} – disabled")
        else:
            parts.append(f"{t} ✗ ({s})")
    return " · ".join(parts)


def render_markdown(kept, suppressed, ep, target, engines) -> str:
    tiers = {"high": [], "medium": [], "low": [], "unreachable": []}
    for f in kept:
        tiers[tier(f)].append(f)
    for lst in tiers.values():
        lst.sort(key=lambda x: (x.file, x.line))

    def short(p):
        try:
            return os.path.relpath(p)
        except ValueError:
            return p

    L = []
    L.append(f"# Dead Code Audit Report: {target}\n")
    L.append(f"**Engines:** {_engine_line(engines)}\n")
    degraded = [t for t, s in engines.items() if s not in ("ok", "disabled")]
    if degraded:
        L.append(f"> ⚠ {', '.join(degraded)} did not run — coverage is reduced "
                 "and cross-tool corroboration may be incomplete.\n")
    total = len(kept)
    L.append(f"**{total} review candidates** "
             f"(high: {len(tiers['high'])}, medium: {len(tiers['medium'])}, "
             f"unreachable: {len(tiers['unreachable'])}) · "
             f"{len(suppressed)} framework false positives suppressed\n")
    L.append("> Every item is a **review candidate**, not an auto-delete. "
             "Dead-code detection in Python is undecidable; confirm before removing.\n")

    def table(rows):
        if not rows:
            return ["_none_\n"]
        out = ["| Item | Kind | Location | Evidence | Tools |",
               "|------|------|----------|----------|-------|"]
        for f in rows:
            item = f"`{f.name}`" if f.name else "_(block)_"
            out.append(f"| {item} | {f.kind} | {short(f.file)}:{f.line} | "
                       f"{f.message} ({f.confidence}%) | {','.join(sorted(f.tools))} |")
        return out + [""]

    L.append("## High confidence — safe to remove (verify no dynamic use)\n")
    L += table(tiers["high"])
    L.append("## Unreachable code — after return/raise/break\n")
    L += table(tiers["unreachable"])
    L.append("## Medium confidence — review needed\n")
    L += table(tiers["medium"])
    if tiers["low"]:
        L.append("## Low confidence — hints only\n")
        L += table(tiers["low"])

    if ep is not None:
        L.append("## Endpoint reachability (vs client code)\n")
        L.append(f"Scanned {ep['client_files']} client file(s). "
                 "Routes are live to Python linters (decorator-registered) but "
                 "may be dead if no client calls them.\n")
        L.append("### Removal candidates — no client reference found\n")
        if ep["candidate"]:
            L.append("| Method | Path | Handler | Location |")
            L.append("|--------|------|---------|----------|")
            for r in ep["candidate"]:
                L.append(f"| {r.method} | `{r.path}` | `{r.func}` | {short(r.file)}:{r.line} |")
            L.append("")
        else:
            L.append("_none — every non-infra route is referenced by a client_\n")
        L.append(f"### Referenced by clients: {len(ep['used'])} · "
                 f"Infrastructure (health/docs/etc.): {len(ep['infra'])}\n")

    if suppressed:
        L.append("<details><summary>Suppressed framework false positives "
                 f"({len(suppressed)})</summary>\n")
        L.append("| Item | Location | Reason |")
        L.append("|------|----------|--------|")
        for f, reason in suppressed:
            item = f"`{f.name}`" if f.name else "_(block)_"
            L.append(f"| {item} | {short(f.file)}:{f.line} | {reason} |")
        L.append("\n</details>\n")

    return "\n".join(L)


def render_json(kept, suppressed, ep, target, engines):
    def dump(f):
        d = asdict(f)
        d["tools"] = sorted(f.tools)
        d["tier"] = tier(f)
        return d
    payload = {
        "target": target,
        "engines": engines,
        "candidates": [dump(f) for f in kept],
        "suppressed": [{**{k: v for k, v in asdict(f).items() if k != "tools"},
                        "reason": r} for f, r in suppressed],
    }
    if ep is not None:
        payload["endpoints"] = {
            "client_files": ep["client_files"],
            "candidate": [asdict(r) for r in ep["candidate"]],
            "used": [asdict(r) for r in ep["used"]],
            "infra": [asdict(r) for r in ep["infra"]],
        }
    return json.dumps(payload, indent=2)


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description="Read-only dead-code audit for Python/FastAPI backends.")
    ap.add_argument("paths", nargs="+", help="Files or directories to audit")
    ap.add_argument("--config", help="TOML config with [audit_dead_code] table")
    ap.add_argument("--client-glob", action="append", default=[],
                    help="Glob(s) of client files to check endpoints against (repeatable). Enables endpoint pass.")
    ap.add_argument("--infra-path", action="append", default=[],
                    help="Extra path prefixes treated as infrastructure (repeatable).")
    ap.add_argument("--format", choices=["md", "json"], default="md")
    ap.add_argument("--output", help="Write report to file instead of stdout")
    ap.add_argument("--no-ruff", action="store_true")
    ap.add_argument("--no-vulture", action="store_true")
    ap.add_argument("--no-deadcode", action="store_true")
    ap.add_argument("--fail-on", choices=["none", "high", "any"], default="none",
                    help="Exit non-zero if candidates at/above this tier remain (for CI).")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    idx = build_index(args.paths, cfg)

    engines: dict = {}
    raw: list[Finding] = []
    if args.no_ruff:
        engines["ruff"] = "disabled"
    else:
        raw += run_ruff(args.paths, cfg, engines)
    if args.no_vulture:
        engines["vulture"] = "disabled"
    else:
        raw += run_vulture(args.paths, cfg, engines)
    if args.no_deadcode:
        engines["deadcode"] = "disabled"
    else:
        raw += run_deadcode(args.paths, cfg, engines)

    if not any(s == "ok" for s in engines.values()):
        print("! no analyzer ran — refusing to emit a report that would look "
              "like a clean bill of health.", file=sys.stderr)
        for t, s in engines.items():
            print(f"!   {t}: {s}", file=sys.stderr)
        print("! install the engines with: pip install ruff vulture deadcode",
              file=sys.stderr)
        return 2

    kept, suppressed = [], []
    for f in raw:
        reason = is_false_positive(f, idx, cfg)
        (suppressed.append((f, reason)) if reason else kept.append(f))
    kept = merge(kept)

    ep = None
    if args.client_glob:
        ep = audit_endpoints(idx.routes, args.client_glob,
                             cfg["infra_paths"] + args.infra_path)

    target = ", ".join(args.paths)
    report = (render_json(kept, suppressed, ep, target, engines) if args.format == "json"
              else render_markdown(kept, suppressed, ep, target, engines))

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"Report written to {args.output}", file=sys.stderr)
    else:
        print(report)

    if args.fail_on != "none":
        hot = [f for f in kept if tier(f) in
               (("high", "unreachable") if args.fail_on == "high"
                else ("high", "medium", "low", "unreachable"))]
        if hot:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
