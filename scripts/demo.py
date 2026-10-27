#!/usr/bin/env python3
"""Local demo: build a small synthetic OCI Audit archive, then analyze it.

No OCI needed. The synthetic events follow the documented audit event shape
(datetime ms epoch, data.eventName, data.identity, data.request,
data.response). This simulates files you would get from the archive pipeline;
it is not a live OCI run.
"""
import gzip
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from analyzer import core

DAY = 24 * 3600 * 1000
T0 = 1793059200000  # 2026-10-27T00:00:00Z in ms


def event(i, principal, ip, name, action, status, when):
    return {
        "datetime": when,
        "logType": "com.oraclecloud.audit",
        "data": {
            "eventName": name,
            "eventSource": name.split(" and ")[0].lower(),
            "identity": {"principalName": principal, "ipAddress": ip,
                         "authType": "natv", "userAgent": "Oracle-JavaSDK/2.x"},
            "request": {"action": action, "path": "/20160918/example"},
            "response": {"status": status, "message": "", "responseTime": 1},
        },
    }


SAMPLE = [
    event(1, "alice@example.com", "203.0.113.10", "LaunchInstance", "POST", "200", T0 + 3600e3),
    event(2, "alice@example.com", "203.0.113.10", "CreateVcn", "POST", "200", T0 + 3700e3),
    event(3, "bob@example.com", "198.51.100.7", "GetInstance", "GET", "200", T0 + 3800e3),
    event(4, "bob@example.com", "198.51.100.7", "DeleteBucket", "DELETE", "403", T0 + 3900e3),
    event(5, "carol@example.com", "192.0.2.55", "UpdateUser", "PUT", "401", T0 + DAY + 4000e3),
    event(6, "alice@example.com", "203.0.113.10", "TerminateInstance", "DELETE", "200", T0 + DAY + 4100e3),
    event(7, "carol@example.com", "192.0.2.55", "ListBuckets", "GET", "200", T0 + DAY + 4200e3),
]


def main():
    tmp = tempfile.mkdtemp(prefix="audit-demo-")
    plain = os.path.join(tmp, "audit-part1.jsonl")
    with open(plain, "w", encoding="utf-8") as fh:
        for e in SAMPLE[:4]:
            fh.write(json.dumps(e) + "\n")
    gz = os.path.join(tmp, "audit-part2.jsonl.gz")
    with gzip.open(gz, "wt", encoding="utf-8") as fh:
        for e in SAMPLE[4:]:
            fh.write(json.dumps(e) + "\n")
    print(f"synthetic archive written to {tmp} (2 files, one gzipped - like the")
    print("Object Storage batches the connector would produce)")
    print()
    rep = core.summarize(core.iter_events([tmp]))
    print(core.render(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
