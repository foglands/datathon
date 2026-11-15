"""Exercise the command-line publication boundary on the official snapshot."""

import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from datathon.__main__ import main
from datathon.workflow import run_case


@unittest.skipUnless(os.environ.get("DATATHON_STARTER_PATH"), "Set DATATHON_STARTER_PATH to the official starter data.")
class NumericOutputTests(unittest.TestCase):
    def test_suite_console_and_export_read_the_published_audit(self):
        async def poison_raw_results(*args, **kwargs):
            result = await run_case(*args, **kwargs)
            result["agent_commentary"] = "Fabricated model claim: risk is 0%."
            result["explanation"] = result["agent_commentary"]
            if baseline := result.get("scenarios", {}).get("baseline"):
                baseline["windows"]["2022"]["terminal_loss"] = .9832
            return result

        output = io.StringIO()
        with TemporaryDirectory() as folder:
            report_path = Path(folder) / "report.json"
            argv = ["datathon", "--data", os.environ["DATATHON_STARTER_PATH"], "--case", "robert",
                    "--mode", "offline", "--stress", "--report", str(report_path)]
            with (patch("sys.argv", argv), patch("datathon.__main__.run_case", side_effect=poison_raw_results),
                  redirect_stdout(output)):
                self.assertEqual(main(), 0)
            serialized = report_path.read_text(encoding="utf-8")

        self.assertNotIn("Fabricated model claim", serialized)
        self.assertNotIn("Fabricated model claim", output.getvalue())
        self.assertNotIn("98.32%", output.getvalue())
        reports = {report["case"]: report for report in json.loads(serialized)}
        self.assertTrue(all(report["passed"] for report in reports.values()))
        first = reports["robert_terminal"]
        published_loss = first["scenarios"]["baseline"]["windows"]["2022"]["terminal_loss"]
        verified_loss = first["audit"]["verified"]["baseline"]["windows"]["2022"]["terminal_loss"]
        self.assertAlmostEqual(published_loss, .11342148)
        self.assertEqual(published_loss, verified_loss)
        self.assertFalse(reports["robert_tampered"]["audit"]["verified"])
