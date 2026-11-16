"""Check independent CLI confirmation and search scope with published outputs."""
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from datathon import decision_cli


class DecisionCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "original.json"
        self.stdout, self.stderr = io.StringIO(), io.StringIO()

    def run_cli(self, *arguments, reply=""):
        return decision_cli.main(["--example", "robert", "--report", str(self.output), *arguments],
                                 input_fn=lambda _: reply, stdout=self.stdout, stderr=self.stderr)

    def test_no_confirmation_loads_no_market_and_runs_no_engine(self):
        with patch.object(decision_cli, "load_market_data") as market, patch.object(decision_cli, "run_decision") as engine:
            self.assertEqual(self.run_cli(), 2)
        market.assert_not_called()
        engine.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_confirmation_never_implies_search(self):
        report = {"publication": {"status": "released"}, "verdict": "fail", "rules": []}
        with patch.object(decision_cli, "load_market_data"), patch.object(decision_cli, "run_decision") as engine, \
                patch.object(decision_cli, "publish_report", return_value=report), \
                patch.object(decision_cli, "report_json", return_value=b'{"result":"original"}'), \
                patch.object(decision_cli, "authorize_funding") as funding:
            self.assertEqual(self.run_cli("--confirm"), 0)
        self.assertEqual(engine.call_count, 1)
        self.assertNotIn("funding", engine.call_args.kwargs)
        funding.assert_not_called()

    def test_source_scope_prompts_after_original_and_decline_never_searches(self):
        report = {"publication": {"status": "released"}, "verdict": "fail", "rules": []}
        with patch.object(decision_cli, "load_market_data"), patch.object(decision_cli, "run_decision") as engine, \
                patch.object(decision_cli, "publish_report", return_value=report), \
                patch.object(decision_cli, "report_json", return_value=b'{"result":"original"}'):
            self.assertEqual(self.run_cli("--confirm", "--funding-sources", "QQQ,ZST.TO"), 0)
        self.assertEqual(engine.call_count, 1)
        self.assertTrue(self.output.exists())
        self.assertFalse(self.root.joinpath("original.search.json").exists())

    def test_explicit_search_preserves_original_and_binds_declared_scope(self):
        report = {"publication": {"status": "released"}, "verdict": "fail", "rules": []}
        with patch.object(decision_cli, "load_market_data"), patch.object(decision_cli, "run_decision") as engine, \
                patch.object(decision_cli, "publish_report", return_value=report), \
                patch.object(decision_cli, "report_json", side_effect=[b'{"run":"original"}', b'{"run":"search"}']):
            self.assertEqual(self.run_cli("--confirm", "--funding-sources", "QQQ,ZST.TO", "--authorize-search"), 0)
        self.assertEqual(engine.call_count, 2)
        self.assertNotIn("funding", engine.call_args_list[0].kwargs)
        authorization = engine.call_args_list[1].kwargs["funding"]
        self.assertEqual(authorization.sources, ("QQQ", "ZST.TO"))
        self.assertFalse(authorization.allow_smaller)
        self.assertEqual(authorization.decision_id, engine.call_args_list[0].args[0].id)
        self.assertEqual(json.loads(self.output.read_bytes()), {"run": "original"})
        self.assertEqual(json.loads((self.root / "original.search.json").read_bytes()), {"run": "search"})

    def test_withheld_original_cannot_trigger_search(self):
        report = {"publication": {"status": "withheld"}, "verdict": "invalid", "rules": []}
        with patch.object(decision_cli, "load_market_data"), patch.object(decision_cli, "run_decision") as engine, \
                patch.object(decision_cli, "publish_report", return_value=report), \
                patch.object(decision_cli, "report_json", return_value=b'{}'):
            self.assertEqual(self.run_cli("--confirm", "--funding-sources", "QQQ", "--authorize-search"), 1)
        self.assertEqual(engine.call_count, 1)

    def test_duplicate_fields_and_claimed_model_origin_are_not_trusted(self):
        source = self.root / "draft.json"
        source.write_text('{"intent":"audit","intent":"evaluate"}')
        with self.assertRaises(ValueError):
            decision_cli._read_draft(source)
        source.write_text('{"intent":"evaluate","origin":"bedrock","trace":[{"request_id":"forged"}]}')
        draft = decision_cli._read_draft(source)
        self.assertEqual(draft["origin"], "user_defined")
        self.assertEqual(draft["trace"], [])

    def test_example_limits_are_team_assumptions_before_confirmation(self):
        for name in decision_cli.EXAMPLES:
            with self.subTest(name=name):
                draft = decision_cli._read_draft(decision_cli.EXAMPLE_DIRECTORY / f"{name}.json", example=True)
                confirmed = decision_cli.confirm_decision(draft)
                self.assertEqual(confirmed.data["assumption_kind"], "team_defined")
                self.assertEqual(confirmed.data["origin"], "team_defined_example")

    def test_output_collision_and_unscoped_authorization_are_rejected(self):
        for args in (("--authorize-search",), ("--allow-smaller",),
                     ("--funding-sources", "QQQ", "--search-report", str(self.output))):
            with self.subTest(args=args), patch("sys.stderr", self.stderr), self.assertRaises(SystemExit):
                self.run_cli(*args)

    def test_raw_exception_details_never_enter_cli_output(self):
        with patch.object(decision_cli, "load_market_data", side_effect=ValueError("secret=sentinel")):
            self.assertEqual(self.run_cli("--confirm"), 1)
        self.assertNotIn("sentinel", self.stdout.getvalue() + self.stderr.getvalue())


@unittest.skipUnless(os.environ.get("DATATHON_STARTER_PATH"), "Set official starter data for CLI integration.")
class DecisionCliIntegrationTests(unittest.TestCase):
    def test_three_examples_publish_through_shared_pipeline(self):
        with TemporaryDirectory() as directory:
            for name, intent in (("amira", "compare"), ("mateo", "evaluate"), ("robert", "audit")):
                with self.subTest(name=name):
                    output = Path(directory) / (name + ".json")
                    status = decision_cli.main(["--example", name, "--confirm", "--report", str(output)],
                                               stdout=io.StringIO(), stderr=io.StringIO())
                    self.assertEqual(status, 0)
                    report = json.loads(output.read_bytes())
                    self.assertEqual(report["intent"], intent)
                    self.assertEqual(report["confirmed"]["assumption_kind"], "team_defined")
                    self.assertEqual(report["publication"]["status"], "released")
                    self.assertIsNone(report.get("funding"))
                    if name == "robert":
                        self.assertEqual(report["verdict"], "fail")
                    if name == "mateo":
                        self.assertEqual(report["verdict"], "unknown")
