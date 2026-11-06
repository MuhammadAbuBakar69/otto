import unittest

from otto import replies


class TestClassification(unittest.TestCase):
    def test_labels(self):
        cases = [
            ("Re: hello", "Please take me off this list.", "unsubscribe"),
            ("Re: hello", "Not interested, thanks.", "unsubscribe"),
            ("Re: hello", "Sounds good, can we book a call?", "interested"),
            ("Re: hello", "How much does this cost?", "objection"),
            ("Re: hello", "What does onboarding look like?", "question"),
            ("Re: hello", "Thanks, noted.", "other"),
        ]
        for subject, body, expected in cases:
            self.assertEqual(replies.classify(subject, body), expected, body)

    def test_opt_out_wins_over_everything_else(self):
        body = "Interested, but please unsubscribe me for now."
        self.assertEqual(replies.classify("Re: x", body), "unsubscribe")


class TestSubjectHandling(unittest.TestCase):
    def test_no_duplicate_re_prefix(self):
        self.assertEqual(
            replies._re_subject({"subject": "Re: Bookwell"}, "Bookwell"), "Re: Bookwell"
        )
        self.assertEqual(
            replies._re_subject({"subject": "Bookwell"}, "Bookwell"), "Re: Bookwell"
        )
        self.assertEqual(replies._re_subject({"subject": ""}, "Bookwell"), "Re: Bookwell")


if __name__ == "__main__":
    unittest.main()
