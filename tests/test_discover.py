import tempfile
import unittest
from pathlib import Path

from otto import config, db, discover


class TestCsvSource(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="otto-csv-"))
        self.cfg = config.load(self.root)
        self.con = db.connect(self.cfg.db_path)

    def write(self, text):
        path = self.root / "prospects.csv"
        path.write_text(text, encoding="utf-8")
        return path

    def test_with_header(self):
        path = self.write(
            "name,domain,email,city,category\n"
            "Harbor Dental,https://harbordental.test,,Karachi,dentist\n"
            "Highline Roofing,highlineroofing.test,o@highline.test,Karachi,roofer\n"
        )
        self.assertEqual(discover.from_csv(self.con, path), 2)
        rows = db.prospects(self.con)
        self.assertEqual(rows[0]["name"], "Harbor Dental")
        self.assertEqual(rows[0]["domain"], "harbordental.test")
        self.assertEqual(rows[1]["email"], "o@highline.test")

    def test_without_header(self):
        path = self.write("Phoenix HVAC,phoenixhvac.test,dispatch@phoenix.test,Karachi,hvac\n")
        self.assertEqual(discover.from_csv(self.con, path), 1)
        self.assertEqual(db.prospects(self.con)[0]["city"], "Karachi")

    def test_rows_without_a_domain_are_ignored(self):
        path = self.write("name,domain\nNo Site,\nFine,fine.test\n")
        self.assertEqual(discover.from_csv(self.con, path), 1)

    def test_duplicate_domains_do_not_multiply(self):
        path = self.write("name,domain\nA,alpha.test\nA again,www.alpha.test\n")
        self.assertEqual(discover.from_csv(self.con, path), 2)
        self.assertEqual(len(db.prospects(self.con)), 1)


class TestOverpassQuery(unittest.TestCase):
    def test_query_mentions_city_and_website_filter(self):
        query = discover.osm_query("Karachi", "dentist", 10)
        self.assertIn('area["name"="Karachi"]', query)
        self.assertIn('["website"]', query)
        self.assertIn('"amenity"="dentist"', query)


if __name__ == "__main__":
    unittest.main()
