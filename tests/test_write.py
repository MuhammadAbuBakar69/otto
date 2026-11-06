import tempfile
import unittest

from otto import config, write

PROSPECT = {
    "name": "Harbor Dental Studio",
    "domain": "harbordental.test",
    "city": "Karachi",
    "category": "dentist",
    "email": "hi@harbordental.test",
}

FACTS = {
    "title": "Harbor Dental Studio | Family dentistry",
    "description": "Same-week appointments, evening slots and a hygiene plan for families.",
    "headings": ["Evening appointments"],
    "paragraphs": [],
}


class TestDrafting(unittest.TestCase):
    def setUp(self):
        self.cfg = config.load(tempfile.mkdtemp(prefix="otto-write-"))

    def test_first_name_strips_legal_words(self):
        self.assertEqual(write.first_name("Harbor Dental Studio"), "Harbor")
        self.assertEqual(write.first_name("Cedar Lane Garage Ltd"), "Cedar")
        self.assertEqual(write.first_name("Phoenix HVAC"), "Phoenix")
        self.assertEqual(write.first_name(""), "there")

    def test_best_detail_prefers_description(self):
        self.assertIn("Same-week appointments", write.best_detail(FACTS))
        self.assertEqual(write.best_detail({}), "")

    def test_template_is_specific_and_short(self):
        subject, body = write.template(self.cfg, PROSPECT, FACTS)
        self.assertTrue(subject)
        self.assertIn("Same-week appointments", body)
        self.assertIn("Harbor", body)
        self.assertIn("Karachi", body)
        self.assertLess(len(body.split()), 160)
        self.assertEqual(body, write.template(self.cfg, PROSPECT, FACTS)[1])

    def test_draft_falls_back_to_template_without_model(self):
        subject, body, source = write.draft(self.cfg, PROSPECT, FACTS)
        self.assertEqual(source, "template")
        self.assertTrue(subject and body)

    def test_model_output_that_ignores_the_brief_is_rejected(self):
        self.cfg.set("model.provider", "ollama")
        original = write.model.generate
        write.model.generate = lambda *a, **k: "Sorry, here is an essay " + ("word " * 400)
        try:
            subject, body, source = write.draft(self.cfg, PROSPECT, FACTS)
        finally:
            write.model.generate = original
        self.assertEqual(source, "template")


class TestModelParsing(unittest.TestCase):
    def test_json_object_extraction(self):
        from otto import model

        self.assertEqual(model.json_object('{"a": 1}'), {"a": 1})
        self.assertEqual(model.json_object("text before {\"a\": 2} after"), {"a": 2})
        self.assertEqual(model.json_object("no json here"), {})
        self.assertEqual(model.json_object('{"broken": '), {})


if __name__ == "__main__":
    unittest.main()
