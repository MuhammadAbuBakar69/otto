import unittest

from otto import profile

HTML = """
<!doctype html><html><head>
<title>Harbor Dental Studio | Family dentistry in Clifton</title>
<meta name="description" content="Same-week appointments and evening slots for families.">
</head><body>
<nav><a>Sign in</a><a>Skip to content</a></nav>
<h1>Evening appointments</h1>
<h2>Hygiene plans</h2>
<p>We keep two evening slots open every day for people who cannot take time off work.</p>
<p>Cookie policy. All rights reserved.</p>
<p>Short.</p>
<p>Email us at Hello@HarborDental.test or book@harbordental.test.</p>
<img src="logo.png">
</body></html>
"""


class TestExtraction(unittest.TestCase):
    def test_pulls_the_useful_fields(self):
        facts = profile.extract(HTML, "https://harbordental.test/about")
        self.assertIn("Harbor Dental Studio", facts["title"])
        self.assertIn("Same-week", facts["description"])
        self.assertIn("Evening appointments", facts["headings"])
        self.assertIn("hello@harbordental.test", facts["emails"])
        self.assertEqual(len(facts["emails"]), 2)

    def test_drops_boilerplate(self):
        facts = profile.extract(HTML)
        joined = " ".join(facts["headings"] + facts["paragraphs"])
        self.assertNotIn("Sign in", joined)
        self.assertNotIn("Cookie", facts["headings"])
        self.assertNotIn("Cookie", " ".join(facts["paragraphs"]))
        self.assertNotIn("Short.", facts["paragraphs"])

    def test_empty_input_is_not_an_error(self):
        facts = profile.extract("")
        self.assertEqual(facts["headings"], [])
        self.assertEqual(facts["emails"], [])

    def test_unreachable_domain_returns_not_ok(self):
        facts, ok, error = profile.profile_domain("no-such-host.invalid", timeout=2)
        self.assertFalse(ok)
        self.assertTrue(error)


if __name__ == "__main__":
    unittest.main()
