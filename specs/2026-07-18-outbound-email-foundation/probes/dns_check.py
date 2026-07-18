#!/usr/bin/env python3
"""Verify talktomytrip.com's live DNS matches the Phase 39 email plan.

Objective check for the manual Squarespace edits in ../dns-runbook.md:
the four planned records are live, the Email Security preset remnants are
gone, and the demo's A records are untouched. Stdlib + `dig` only (no new
dependency); nonzero exit on any deviation — the sweep.py precedent.

Usage:
    python3 dns_check.py [--domain talktomytrip.com]
                         [--dkim-selector resend] [--ns 8.8.8.8]

`--ns` queries a specific resolver (useful to dodge a stale local cache
while propagation settles).
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys

EXPECTED_SPF = "v=spf1 include:amazonses.com ~all"
EXPECTED_A = "35.192.205.215"

failures: list[str] = []


def check(label: str, ok: bool, detail: str) -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}: {detail}")
    if not ok:
        failures.append(label)


def dig(name: str, rtype: str, ns: str | None) -> list[str]:
    cmd = ["dig", "+short", name, rtype]
    if ns:
        cmd.insert(1, f"@{ns}")
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    if out.returncode != 0:
        check(f"dig {rtype} {name}", False, out.stderr.strip() or "dig failed")
        return []
    return [line.strip() for line in out.stdout.splitlines() if line.strip()]


def txt_records(name: str, ns: str | None) -> list[str]:
    """TXT answers with quotes stripped and multi-chunk strings joined."""
    records = []
    for line in dig(name, "TXT", ns):
        chunks = re.findall(r'"((?:[^"\\]|\\.)*)"', line)
        records.append("".join(chunks) if chunks else line)
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", default="talktomytrip.com")
    parser.add_argument("--dkim-selector", default="resend")
    parser.add_argument("--ns", default=None, help="resolver to query, e.g. 8.8.8.8")
    args = parser.parse_args()
    domain, ns = args.domain, args.ns

    # --- SPF: exactly one, the planned value, no hard-fail remnant ---
    apex_txt = txt_records(domain, ns)
    spf = [r for r in apex_txt if r.lower().startswith("v=spf1")]
    check("SPF count", len(spf) == 1, f"{len(spf)} SPF record(s) on @ (need exactly 1): {spf}")
    if len(spf) == 1:
        check("SPF value", spf[0] == EXPECTED_SPF, f"{spf[0]!r} (want {EXPECTED_SPF!r})")
    check(
        "SPF preset gone",
        not any(re.search(r"v=spf1\s+-all", r) for r in apex_txt),
        "no 'v=spf1 -all' hard-fail record remains",
    )

    # --- DMARC: p=none, preset p=reject gone ---
    dmarc = [r for r in txt_records(f"_dmarc.{domain}", ns) if r.lower().startswith("v=dmarc1")]
    check("DMARC count", len(dmarc) == 1, f"{len(dmarc)} DMARC record(s): {dmarc}")
    if len(dmarc) == 1:
        tags = dmarc[0].replace(" ", "").lower()
        check("DMARC policy", "p=none" in tags and "p=reject" not in tags, dmarc[0])

    # --- DKIM: Resend selector present with a non-empty key ---
    dkim_name = f"{args.dkim_selector}._domainkey.{domain}"
    dkim = txt_records(dkim_name, ns)
    key = ""
    for record in dkim:
        match = re.search(r"p=([A-Za-z0-9+/=]+)", record)
        if match:
            key = match.group(1)
    check("DKIM key", bool(key), f"{dkim_name}: {'non-empty p= key' if key else f'no key found in {dkim}'}")

    # --- Null MX: outbound-only ---
    mx = dig(domain, "MX", ns)
    check("Null MX", mx == ["0 ."], f"{mx} (want ['0 .'])")

    # --- A records untouched: the live demo rides on these ---
    for host in (domain, f"www.{domain}"):
        a = dig(host, "A", ns)
        check(f"A {host}", a == [EXPECTED_A], f"{a} (want ['{EXPECTED_A}'])")

    if failures:
        print(f"\nDEVIATION: {len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("\nAll DNS checks pass — safe to verify the domain in Resend.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
