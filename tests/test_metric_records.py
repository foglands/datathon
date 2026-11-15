"""Exercise metric references at the checked publication boundary."""

import json
import os
import unittest
from copy import deepcopy
from dataclasses import replace

from datathon.counterfactual import run_counterfactual
from datathon.data import load_market_data
from datathon.metric_records import metric_id, resolve_metric
from datathon.publication import publish_check, publish_report
from datathon.workflow import examples, run_case


def numeric_paths(value, path):
    """Enumerate scalar number paths without accepting policy booleans."""
    if isinstance(value, dict):
        for key, child in value.items():
            yield from numeric_paths(child, (*path, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from numeric_paths(child, (*path, index))
    elif type(value) in (int, float):
        yield path


@unittest.skipUnless(os.getenv("DATATHON_STARTER_PATH"), "Requires the official starter dataset.")
class MetricRecordTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_market_data()

    def assert_indexed(self, publication, *paths):
        indexed = {tuple(row["value_ref"]) for row in publication["metric_records"].values()}
        for root in paths:
            source = publication
            for key in root:
                source = source[key]
            self.assertFalse(set(numeric_paths(source, root)) - indexed)

    async def test_historical_funding_and_rule_numbers_use_reviewed_reference_paths(self):
        report = publish_report(await run_case(self.data, examples("robert")[0]))
        self.assert_indexed(report, ("audit", "verified"), ("audit", "findings"), ("audit", "rule_margins"))
        verified = report["audit"]["verified"]
        prefix = ("audit", "verified", "proposal", "windows", "2022")
        drawdown_id = metric_id(*prefix, "max_drawdown")
        contribution_id = metric_id(*prefix, "drawdown_attribution", "ZST.TO")
        record = report["metric_records"][drawdown_id]
        self.assertEqual(record["formula_id"], "max_drawdown")
        self.assertEqual(record["formula_version"], "terminal-loss-and-drawdown-v1")
        self.assertEqual(record["unit"], "percent")
        self.assertEqual(record["denominator"], "portfolio_nav_at_drawdown_peak")
        self.assertEqual(record["review_id"], report["publication"]["review_id"])
        self.assertEqual(record["windows"], [{"id": "2022", "start": "2021-12-31", "end": "2022-12-30"}])
        self.assertEqual(set(record["source_ids"]), set(report["evidence"]["evidence_ids"]))
        self.assertEqual(len(record["input_hash"]), 64)
        self.assertNotIn("value", record)
        self.assertEqual(resolve_metric(report, drawdown_id), verified["proposal"]["windows"]["2022"]["max_drawdown"])
        self.assertEqual(report["metric_records"][contribution_id]["unit"], "percentage_points")
        self.assertEqual(resolve_metric(report, contribution_id),
                         verified["proposal"]["windows"]["2022"]["drawdown_attribution"]["ZST.TO"])
        breach_id = metric_id("audit", "rule_margins", "proposal.terminal_loss.policy", "breach")
        self.assertAlmostEqual(resolve_metric(report, breach_id), verified["proposal"]["terminal_loss"] - .14)
        self.assertEqual(report["scope_notes"]["calculation_verification"], "verified")
        self.assertTrue(report["scope_notes"]["future_risk_questions"])
        coverage = metric_id("publication", "versions", "inputs", "market_data", "windows", "2022",
                             "coverage", "expected_observations")
        self.assertEqual(resolve_metric(report, coverage), 244)
        self.assertEqual(report["metric_records"][coverage]["unit"], "observations")
        self.assertIsNone(resolve_metric(report, "model.claim.risk_is_zero"))
        self.assertEqual(resolve_metric(json.loads(json.dumps(report)), drawdown_id),
                         resolve_metric(report, drawdown_id))

    async def test_exposure_index_is_removed_when_only_optional_section_changes(self):
        case = replace(examples("amira")[0], include_sector=True)
        report = publish_report(await run_case(self.data, case))
        self.assert_indexed(report, ("sector_analysis", "sectors"), ("sector_analysis", "unmapped"),
                            ("exposure",), ("exposure_change",))
        sector = metric_id("sector_analysis", "sectors", "Information Technology", "after", "lower")
        change = metric_id("exposure_change", "upper")
        record = report["metric_records"][sector]
        self.assertEqual(record["as_of"], report["sector_analysis"]["reference_date"])
        self.assertTrue(all(source.startswith("sector:") for source in record["source_ids"]))
        self.assertTrue(all(source.startswith("issuer:") for source in report["metric_records"][change]["source_ids"]))
        changed = deepcopy(report)
        changed["sector_analysis"]["sectors"]["Information Technology"]["after"]["lower"] = .99
        published = publish_report(changed)
        self.assertIsNone(resolve_metric(published, sector))
        self.assertIsNotNone(resolve_metric(published, change))
        drawdown = metric_id("audit", "verified", "proposal", "max_drawdown")
        self.assertEqual(resolve_metric(published, drawdown), resolve_metric(report, drawdown))

    async def test_metric_references_cannot_be_injected_or_survive_core_tampering(self):
        raw = await run_case(self.data, examples("robert")[0])
        raw["metric_records"] = {"invented": {"metric_id": "invented", "value_ref": ["policy", "target"]}}
        report = publish_report(raw)
        self.assertIsNone(resolve_metric(report, "invented"))
        report["audit"]["verified"]["proposal"]["max_drawdown"] = .99
        blocked = publish_report(report)
        self.assertEqual(blocked["metric_records"], {})
        self.assertEqual(blocked["scope_notes"]["calculation_verification"], "invalid")

    async def test_published_replay_comparisons_and_issuer_thresholds_are_indexed(self):
        case = examples("robert")[0]
        raw = await run_case(self.data, case)
        check = publish_check(await run_counterfactual(self.data, case, raw, option_id="toggle_loss_metric"))
        self.assertTrue(check["verified"])
        self.assert_indexed(check, ("comparison",))
        identifier = metric_id("comparison", "replay", "proposal_loss_headroom")
        self.assertEqual(check["metric_records"][identifier]["review_id"], check["replay"]["publication"]["review_id"])
        self.assertEqual(resolve_metric(check, identifier), check["comparison"]["replay"]["proposal_loss_headroom"])

        case = examples("amira")[0]
        raw = await run_case(self.data, case)
        check = publish_check(await run_counterfactual(self.data, case, raw, option_id="request_issuer_evidence"))
        self.assertTrue(check["verified"])
        self.assert_indexed(check, ("action", "thresholds"))
        identifier = metric_id("action", "thresholds", "qqq_only", "maximum_combined_additional_exposure")
        self.assertEqual(check["metric_records"][identifier]["unit"], "percentage_points")
        self.assertAlmostEqual(resolve_metric(check, identifier), .14 - .13390629804835452)
