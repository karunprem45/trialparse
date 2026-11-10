import unittest

from trialparse.metrics import PRF, jaccard, match_labs, match_strings, scalar_equal
from trialparse.schema import Eligibility, LabThreshold, SchemaError


class MetricTests(unittest.TestCase):
    def test_jaccard_synonyms(self):
        self.assertEqual(jaccard("type 2 diabetes mellitus", "Type 2 Diabetes"), 1.0)
        self.assertEqual(jaccard("CKD", "chronic kidney disease"), 1.0)
        self.assertEqual(jaccard("heart failure", "pancreatitis"), 0.0)

    def test_one_to_one(self):
        m = match_strings(["type 2 diabetes", "type 2 diabetes mellitus"], ["type 2 diabetes"])
        self.assertEqual(len(m), 1)

    def test_labs_canonical(self):
        pred = [LabThreshold("Hemoglobin A1c", ">=", 7.0, "inclusion", "%")]
        gold = [LabThreshold("hba1c", ">=", 7, "inclusion")]
        self.assertEqual(match_labs(pred, gold), 1)
        self.assertEqual(match_labs([LabThreshold("hba1c", ">=", 7.0, "exclusion")], gold), 0)

    def test_prf(self):
        p = PRF()
        p.add(2, 4, 2)
        self.assertAlmostEqual(p.precision, 0.5)
        self.assertAlmostEqual(p.recall, 1.0)
        self.assertAlmostEqual(p.f1, 2 / 3)
        self.assertIsNone(PRF().precision)

    def test_scalar(self):
        self.assertTrue(scalar_equal(18, 18.0))
        self.assertTrue(scalar_equal(None, None))
        self.assertFalse(scalar_equal(None, 18))
        self.assertTrue(scalar_equal(True, True))


class SchemaTests(unittest.TestCase):
    def test_roundtrip(self):
        e = Eligibility(18, 75, "ALL", True, ["type 2 diabetes"], ["pancreatitis"],
                        [LabThreshold("hba1c", ">=", 7.0, "inclusion", "%")])
        self.assertEqual(Eligibility.from_dict(e.to_dict()), e)

    def test_rejects_bad_operator(self):
        with self.assertRaises(SchemaError):
            Eligibility.from_dict({"lab_thresholds": [{"test": "bmi", "operator": "=>", "value": 30, "section": "inclusion"}]})


if __name__ == "__main__":
    unittest.main()
