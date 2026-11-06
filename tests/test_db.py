import os
import tempfile
import unittest

os.environ.setdefault("OTTO_MODEL_PROVIDER", "none")

from otto import config, db  # noqa: E402


def fresh():
    tmp = tempfile.mkdtemp(prefix="otto-test-")
    cfg = config.load(tmp)
    return cfg, db.connect(cfg.db_path)


class TestProspects(unittest.TestCase):
    def test_normalize_domain(self):
        cases = {
            "https://HarborDental.test/about?x=1": "harbordental.test",
            "http://www.example.com/": "example.com",
            "hello@northline.test": "northline.test",
            "  Example.COM  ": "example.com",
            "": "",
        }
        for raw, expected in cases.items():
            self.assertEqual(db.normalize_domain(raw), expected)

    def test_add_is_idempotent(self):
        cfg, con = fresh()
        first = db.add_prospect(con, "Alpha", "alpha.test", email="a@alpha.test")
        second = db.add_prospect(con, "Alpha", "https://www.alpha.test/contact", city="Karachi")
        self.assertEqual(first, second)
        rows = db.prospects(con)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["city"], "Karachi")
        self.assertEqual(rows[0]["email"], "a@alpha.test")

    def test_status_and_counts(self):
        cfg, con = fresh()
        pid = db.add_prospect(con, "Beta", "beta.test")
        self.assertEqual(db.pipeline_counts(con)["unprofiled"], 1)
        db.save_profile(con, pid, {"title": "Beta"}, ok=True)
        db.set_status(con, pid, "profiled")
        self.assertEqual(db.pipeline_counts(con)["ready_to_write"], 1)
        self.assertEqual(db.pipeline_counts(con)["unprofiled"], 0)

    def test_draft_lifecycle_and_caps(self):
        cfg, con = fresh()
        pid = db.add_prospect(con, "Gamma", "gamma.test", email="g@gamma.test")
        did = db.add_draft(con, pid, "Hi", "Body")
        self.assertTrue(db.has_open_draft(con, pid))
        self.assertEqual(db.drafted_today(con), 1)
        self.assertEqual(db.sent_today(con), 0)
        db.set_draft_status(con, did, "sent", delivery="dry_run")
        self.assertEqual(db.sent_today(con), 1)
        self.assertFalse(db.has_open_draft(con, pid))


if __name__ == "__main__":
    unittest.main()
