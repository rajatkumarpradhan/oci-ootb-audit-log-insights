"""CLI: python3 -m analyzer <file-or-dir>... [--top N] [--json]"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter

from . import core


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="analyzer",
        description="Offline insights from OCI Audit log files (jsonl/json/gz). No API calls.")
    ap.add_argument("paths", nargs="+", help="audit log files or directories")
    ap.add_argument("--top", type=int, default=5, help="rows per section (default 5)")
    ap.add_argument("--json", action="store_true", help="machine-readable report")
    a = ap.parse_args(argv)
    stats = Counter()
    try:
        rep = core.summarize(core.iter_events(a.paths, stats), top=a.top)
    except core.InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if rep["total_events"] == 0:
        print("error: no valid audit events found in the input", file=sys.stderr)
        return 2
    if stats["bad_lines"] or stats["skipped"]:
        print(f"note: skipped {stats['bad_lines']} malformed line(s), "
              f"{stats['skipped']} non-audit record(s)", file=sys.stderr)
    if a.json:
        print(json.dumps(rep, indent=1))
    else:
        print(core.render(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
