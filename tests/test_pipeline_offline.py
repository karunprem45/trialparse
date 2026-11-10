"""End-to-end run with no network: fake trials, fake LLM client, real evaluator."""
import json
import os
import tempfile
import unittest
from types import SimpleNamespace

from trialparse import db as dbm
from trialparse import evaluate, fetch, gold, llm_extract, run_extract, tables
from trialparse.schema import Eligibility, LabThreshold

STUDY = {
    "protocolSection": {
        "identificationModule": {"nctId": "NCT00000001", "briefTitle": "Test trial"},
        "conditionsModule": {"conditions": ["Type 2 Diabetes"]},
        "eligibilityModule": {
            "eligibilityCriteria": "Inclusion Criteria:\n* Adults aged 18 to 75 years with type 2 diabetes\n"
                                   "* HbA1c ≥ 7%\nExclusion Criteria:\n* Pregnancy\n* Chronic kidney disease",
            "sex": "ALL", "minimumAge": "18 Years", "maximumAge": "75 Years",
        },
    }
}


class FakeClient:
    """Mimics anthropic.Anthropic().messages.create with a forced tool call."""
    def __init__(self, payload):
        self.messages = SimpleNamespace(create=lambda **kw: SimpleNamespace(
            content=[SimpleNamespace(type="tool_use", input=payload)],
            usage=SimpleNamespace(input_tokens=500, output_tokens=120)))


class PipelineTest(unittest.TestCase):
    def test_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            conn = dbm.connect(os.path.join(d, "t.db"))
            rec = fetch.parse_study(STUDY)
            self.assertEqual(rec["reg_min_age"], 18.0)
            self.assertEqual(fetch.upsert(conn, [rec], "type 2 diabetes"), (1, 0))
            self.assertEqual(fetch.upsert(conn, [rec], "type 2 diabetes"), (0, 0))

            print(run_extract.run(conn, "regex"))
            payload = {"min_age_years": 18, "max_age_years": 75, "sex": "ALL", "excludes_pregnancy": True,
                       "required_conditions": ["type 2 diabetes"], "excluded_conditions": ["chronic kidney disease"],
                       "lab_thresholds": [{"test": "HbA1c", "operator": ">=", "value": 7, "unit": "%",
                                           "section": "inclusion"}]}
            orig = llm_extract.make_client
            llm_extract.make_client = lambda: FakeClient(payload)
            try:
                self.assertEqual(run_extract.run(conn, "llm")["done"], 1)
                self.assertEqual(run_extract.run(conn, "llm")["skipped"], 1)  # cache hit
            finally:
                llm_extract.make_client = orig

            gpath = os.path.join(d, "gold.jsonl")
            gold.append(gpath, "NCT00000001", Eligibility(
                18, 75, "ALL", True, ["Type 2 Diabetes Mellitus"], ["CKD"],
                [LabThreshold("hba1c", ">=", 7, "inclusion", "%")]))
            rep = evaluate.run(conn, gpath, "all", 0.5, out_dir=os.path.join(d, "res"))
            llm = rep["gold_scores"]["llm"]
            self.assertEqual(llm["required_conditions"]["f1"], 1.0)
            self.assertEqual(llm["excluded_conditions"]["f1"], 1.0)
            self.assertEqual(llm["lab_thresholds"]["f1"], 1.0)
            self.assertIsNone(rep["gold_scores"]["regex"]["required_conditions"])
            self.assertEqual(rep["registry_agreement"]["llm"]["min_age_years"]["agreement"], 1.0)
            self.assertEqual(tables.build(conn)["condition_rows"], 2)


if __name__ == "__main__":
    unittest.main()
