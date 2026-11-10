import unittest

from trialparse import regex_baseline
from trialparse.text import parse_registry_age, split_sections

SAMPLE = """Inclusion Criteria:

* Adults aged 18 to 75 years
* Diagnosed with type 2 diabetes for at least 6 months
* HbA1c between 7.0% and 10.5%
* BMI ≥ 25 kg/m2

Exclusion Criteria:

* Pregnant or breastfeeding women
* eGFR < 30 mL/min/1.73 m2
* History of pancreatitis
"""


class TextTests(unittest.TestCase):
    def test_split(self):
        incl, excl = split_sections(SAMPLE)
        self.assertIn("HbA1c", incl)
        self.assertIn("pancreatitis", excl)
        self.assertNotIn("pancreatitis", incl)

    def test_split_no_exclusion(self):
        incl, excl = split_sections("Inclusion Criteria:\n* age 18+")
        self.assertEqual(excl, "")
        self.assertIn("18", incl)

    def test_registry_age(self):
        self.assertEqual(parse_registry_age("18 Years"), 18.0)
        self.assertEqual(parse_registry_age("6 Months"), 0.5)
        self.assertIsNone(parse_registry_age("N/A"))
        self.assertIsNone(parse_registry_age(None))


class RegexTests(unittest.TestCase):
    def test_sample(self):
        e = regex_baseline.extract(SAMPLE)
        self.assertEqual((e.min_age_years, e.max_age_years), (18.0, 75.0))
        self.assertEqual(e.sex, "ALL")
        self.assertTrue(e.excludes_pregnancy)
        labs = {(t.test, t.operator, t.value, t.section) for t in e.lab_thresholds}
        self.assertIn(("hba1c", ">=", 7.0, "inclusion"), labs)
        self.assertIn(("hba1c", "<=", 10.5, "inclusion"), labs)
        self.assertIn(("bmi", ">=", 25.0, "inclusion"), labs)
        self.assertIn(("egfr", "<", 30.0, "exclusion"), labs)
        self.assertEqual(e.required_conditions, [])  # not attempted by design

    def test_min_only(self):
        e = regex_baseline.extract("Inclusion Criteria:\n* 18 years of age or older\nExclusion Criteria:\n* none")
        self.assertEqual(e.min_age_years, 18.0)
        self.assertIsNone(e.max_age_years)
        self.assertFalse(e.excludes_pregnancy)

    def test_female_only(self):
        e = regex_baseline.extract("Inclusion Criteria:\n* Postmenopausal women aged 50-80 years old")
        self.assertEqual(e.sex, "FEMALE")
        self.assertEqual((e.min_age_years, e.max_age_years), (50.0, 80.0))

    def test_word_operators(self):
        e = regex_baseline.extract("Exclusion Criteria:\n* HbA1c greater than 11%\n* alternative therapy use")
        labs = {(t.test, t.operator, t.value, t.section) for t in e.lab_thresholds}
        self.assertEqual(labs, {("hba1c", ">", 11.0, "exclusion")})  # 'alternative' must not match ALT


if __name__ == "__main__":
    unittest.main()
