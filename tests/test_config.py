import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")


def load(name):
    with open(os.path.join(ROOT, "config", name), encoding="utf-8") as fh:
        return json.load(fh)


class ConfigShapeTests(unittest.TestCase):
    def test_connector_shape(self):
        c = load("service-connector.json")
        self.assertEqual(c["source"]["kind"], "logging")
        self.assertEqual(c["target"]["kind"], "objectStorage")
        self.assertEqual(c["target"]["bucket"], "audit-archive")

    def test_bucket_private(self):
        self.assertEqual(load("bucket.json")["publicAccessType"], "NoPublicAccess")

    def test_placeholders_unfilled(self):
        self.assertIn("<compartment-ocid>", load("service-connector.json")["compartmentId"])
        self.assertIn("<audit-log-group-ocid>", load("service-connector.json")["source"]["logGroupId"])


class ValidatorTests(unittest.TestCase):
    def test_validator_flags_placeholders(self):
        r = subprocess.run([sys.executable, "scripts/validate.py"],
                           cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("still needs the real OCID", r.stdout)


class DocShapeTests(unittest.TestCase):
    def test_setup_doc_mentions_prerequisites(self):
        with open(os.path.join(ROOT, "docs", "setup.md"), encoding="utf-8") as fh:
            s = fh.read()
        for needle in ("Audit", "Connector Hub", "not been executed", "placeholder"):
            self.assertIn(needle, s)


if __name__ == "__main__":
    unittest.main()
