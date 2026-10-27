#!/usr/bin/env python3
"""Offline consistency check for the deploy configs. Exit 0 ok, 1 bad input, 2 findings."""
import json
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")


def load(name):
    with open(os.path.join(ROOT, "config", name), encoding="utf-8") as fh:
        return json.load(fh)


def main():
    try:
        conn = load("service-connector.json")
        bucket = load("bucket.json")
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: cannot read config: {e}", file=sys.stderr)
        return 1
    findings = []
    if conn.get("source", {}).get("kind") != "logging":
        findings.append("connector source.kind must be 'logging' (audit logs)")
    tgt = conn.get("target", {})
    if tgt.get("kind") != "objectStorage":
        findings.append("connector target.kind must be 'objectStorage'")
    if tgt.get("bucket") != bucket.get("name"):
        findings.append(f"connector target bucket {tgt.get('bucket')!r} != bucket name {bucket.get('name')!r}")
    if conn.get("compartmentId") != bucket.get("compartmentId"):
        findings.append("connector and bucket must use the same compartmentId placeholder/value")
    if bucket.get("publicAccessType") != "NoPublicAccess":
        findings.append("archive bucket must be private (publicAccessType NoPublicAccess)")
    for obj, what in ((conn, "connector"), (bucket, "bucket")):
        if "<compartment-ocid>" in obj.get("compartmentId", ""):
            findings.append(f"{what}.compartmentId still needs the real OCID at deploy time")
    for f in findings:
        print(f"FINDING: {f}")
    print(f"{len(findings)} finding(s)")
    return 2 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
