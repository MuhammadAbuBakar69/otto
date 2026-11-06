import tempfile
import unittest

from otto import config, db, pipeline, send


def fresh():
    tmp = tempfile.mkdtemp(prefix="otto-pipe-")
    cfg = config.load(tmp)
    return cfg, db.connect(cfg.db_path)


class TestDecisionOrder(unittest.TestCase):
    def test_priority(self):
        cases = [
            ({"unhandled_replies": 1, "approved": 3, "ready_to_write": 2, "unprofiled": 5}, "handle_replies"),
            ({"unhandled_replies": 0, "approved": 3, "ready_to_write": 2, "unprofiled": 5}, "send"),
            ({"unhandled_replies": 0, "approved": 0, "ready_to_write": 2, "unprofiled": 5}, "write"),
            ({"unhandled_replies": 0, "approved": 0, "ready_to_write": 0, "unprofiled": 5}, "profile"),
            ({"unhandled_replies": 0, "approved": 0, "ready_to_write": 0, "unprofiled": 0}, "idle"),
        ]
        for counts, expected in cases:
            self.assertEqual(pipeline.decide(counts), expected, counts)

    def test_write_respects_daily_cap(self):
        cfg, con = fresh()
        cfg.set("limits.max_daily_drafts", 1)
        for name in ("Alpha", "Beta", "Gamma"):
            pid = db.add_prospect(con, name, f"{name.lower()}.test")
            db.save_profile(con, pid, {"description": f"{name} does a very specific useful thing for locals."}, ok=True)
            db.set_status(con, pid, "profiled")
        self.assertEqual(pipeline.write_pending(cfg, con), 1)

    def test_write_skips_prospects_with_an_open_draft(self):
        cfg, con = fresh()
        pid = db.add_prospect(con, "Alpha", "alpha.test")
        db.save_profile(con, pid, {"description": "Alpha does a very specific useful thing."}, ok=True)
        db.set_status(con, pid, "profiled")
        self.assertEqual(pipeline.write_pending(cfg, con), 1)
        self.assertEqual(pipeline.write_pending(cfg, con), 0)

    def test_cycle_sends_approved_drafts_in_dry_run(self):
        cfg, con = fresh()
        pid = db.add_prospect(con, "Alpha", "alpha.test", email="a@alpha.test")
        db.save_profile(con, pid, {"description": "Alpha does a very specific useful thing."}, ok=True)
        db.set_status(con, pid, "profiled")
        pipeline.write_pending(cfg, con)
        draft = db.drafts(con, status="draft", limit=1)[0]
        db.set_draft_status(con, draft["id"], "approved")

        result = pipeline.cycle(cfg, con, out=lambda *a: None)
        self.assertEqual(result["action"], "send")
        self.assertEqual(result["sent"], 1)
        sent = db.drafts(con, status="sent", limit=1)[0]
        self.assertEqual(sent["delivery"], "dry_run")


class TestDelivery(unittest.TestCase):
    def setUp(self):
        self.cfg, self.con = fresh()

    def test_footer_is_idempotent(self):
        body = send.normalize_body(self.cfg, "Hello there")
        once = send.normalize_body(self.cfg, body)
        self.assertEqual(body, once)
        self.assertIn("unsubscribe", body.lower())

    def test_dry_run_never_needs_credentials(self):
        ok, detail = send.deliver(self.cfg, "someone@example.test", "Hi", "Body")
        self.assertTrue(ok)
        self.assertEqual(detail, "dry_run")

    def test_smtp_mode_blocks_until_configured(self):
        self.cfg.set("delivery.mode", "smtp")
        ok, detail = send.deliver(self.cfg, "someone@example.test", "Hi", "Body")
        self.assertFalse(ok)
        self.assertIn("postal_address", detail)

    def test_opted_out_prospects_are_never_sent(self):
        pid = db.add_prospect(self.con, "Alpha", "alpha.test", email="a@alpha.test")
        did = db.add_draft(self.con, pid, "Hi", "Body")
        db.set_draft_status(self.con, did, "approved")
        db.set_status(self.con, pid, "opted_out")
        result = send.send_approved(self.cfg, self.con)
        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["skipped"], 1)

    def test_drafts_without_an_address_are_skipped(self):
        pid = db.add_prospect(self.con, "Beta", "beta.test")
        did = db.add_draft(self.con, pid, "Hi", "Body")
        db.set_draft_status(self.con, did, "approved")
        result = send.send_approved(self.cfg, self.con)
        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["skipped"], 1)


if __name__ == "__main__":
    unittest.main()
