import gzip
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from analyzer import core

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "audit_sample.jsonl")


def ev(name="LaunchInstance", principal="a@x.com", ip="1.1.1.1",
       action="POST", status="200", when=1793059200000):
    return {"datetime": when, "data": {
        "eventName": name,
        "identity": {"principalName": principal, "ipAddress": ip},
        "request": {"action": action},
        "response": {"status": status}}}


class ParseTimeTests(unittest.TestCase):
    def test_ms_epoch(self):
        self.assertEqual(core.parse_time(1793059200000).isoformat(),
                         "2026-10-27T00:00:00+00:00")

    def test_iso_string(self):
        self.assertEqual(core.parse_time("2026-10-27T00:00:00Z").isoformat(),
                         "2026-10-27T00:00:00+00:00")

    def test_garbage_returns_none(self):
        self.assertIsNone(core.parse_time("not a time"))
        self.assertIsNone(core.parse_time(None))
        self.assertIsNone(core.parse_time(2**80))


class IterEventsTests(unittest.TestCase):
    def test_reads_fixture_and_counts_bad(self):
        from collections import Counter
        stats = Counter()
        events = list(core.iter_events([FIX], stats))
        self.assertEqual(len(events), 3)
        self.assertEqual(stats["bad_lines"], 1)
        self.assertEqual(stats["skipped"], 1)

    def test_reads_gzip(self):
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, "a.jsonl.gz")
            with gzip.open(p, "wt", encoding="utf-8") as fh:
                fh.write(json.dumps(ev()) + "\n")
            self.assertEqual(len(list(core.iter_events([p]))), 1)

    def test_reads_directory(self):
        with tempfile.TemporaryDirectory() as t:
            for i in range(2):
                with open(os.path.join(t, f"p{i}.jsonl"), "w") as fh:
                    fh.write(json.dumps(ev()) + "\n")
            self.assertEqual(len(list(core.iter_events([t]))), 2)

    def test_json_array_lines_tolerated(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            fh.write(json.dumps([ev(), ev()]) + "\n")
            path = fh.name
        self.assertEqual(len(list(core.iter_events([path]))), 2)
        os.unlink(path)

    def test_empty_and_missing_inputs(self):
        with self.assertRaises(core.InputError):
            list(core.iter_events([]))
        with self.assertRaises(core.InputError):
            list(core.iter_events(["/no/such/file.jsonl"]))


class SummarizeTests(unittest.TestCase):
    def test_counts_and_ranges(self):
        rep = core.summarize([
            ev(when=1793059200000),
            ev(name="GetInstance", action="GET", when=1793062800000),
            ev(name="DeleteBucket", action="DELETE", status="403", when=1793152800000),
        ])
        self.assertEqual(rep["total_events"], 3)
        self.assertEqual(rep["write_operations"], 2)
        self.assertEqual(rep["denied_count"], 1)
        self.assertEqual(rep["denials"][0]["status"], "403")
        self.assertEqual(rep["response_statuses"], {"200": 2, "403": 1})
        self.assertEqual(rep["first_event"], "2026-10-27T00:00:00+00:00")
        self.assertEqual(rep["last_event"], "2026-10-28T02:00:00+00:00")
        self.assertEqual(rep["events_per_day"],
                         {"2026-10-27": 2, "2026-10-28": 1})

    def test_top_lists(self):
        rep = core.summarize([ev(principal="a@x.com"), ev(principal="a@x.com"),
                              ev(principal="b@x.com", ip="2.2.2.2")], top=1)
        self.assertEqual(rep["top_principals"], [("a@x.com", 2)])
        self.assertEqual(rep["top_source_ips"], [("1.1.1.1", 2)])

    def test_missing_fields_get_placeholders(self):
        rep = core.summarize([{"data": {}}])
        self.assertEqual(rep["top_principals"], [("<unknown>", 1)])
        self.assertIsNone(rep["first_event"])

    def test_render_mentions_key_numbers(self):
        text = core.render(core.summarize([ev(), ev(status="403", when=1793062800000)]))
        self.assertIn("events analyzed: 2", text)
        self.assertIn("denied responses (4xx): 1", text)
        self.assertIn("top principals:", text)


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "analyzer", *args],
            cwd=os.path.join(os.path.dirname(__file__), ".."),
            capture_output=True, text=True)

    def test_report_on_fixture(self):
        r = self.run_cli(FIX)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("events analyzed: 3", r.stdout)
        self.assertIn("alice@example.com", r.stdout)
        self.assertIn("note: skipped 1 malformed line(s), 1 non-audit record(s)", r.stderr)

    def test_json_output(self):
        r = self.run_cli(FIX, "--json")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(json.loads(r.stdout)["total_events"], 3)

    def test_bad_input_exit_1(self):
        r = self.run_cli("/no/such/file")
        self.assertEqual(r.returncode, 1)

    def test_no_valid_events_exit_2(self):
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
            fh.write('{"unrelated": 1}\n')
            path = fh.name
        r = self.run_cli(path)
        self.assertEqual(r.returncode, 2)
        os.unlink(path)


if __name__ == "__main__":
    unittest.main()
