"""Keep verified charts isolated across comparison reports."""

import os
import unittest

try:
    from streamlit.testing.v1 import AppTest
except ModuleNotFoundError as exc:
    if exc.name != "streamlit":
        raise
    AppTest = None


@unittest.skipIf(AppTest is None, "Install Streamlit to run the UI tests.")
@unittest.skipUnless(os.environ.get("DATATHON_STARTER_PATH"), "Set DATATHON_STARTER_PATH to run official-data UI tests.")
class ResultsWorkspaceTests(unittest.TestCase):
    def test_comparison_survives_independent_chart_selection_and_hides_tampered_results(self):
        app = AppTest.from_string(
            """
import asyncio
from dataclasses import replace
import streamlit as st
from datathon.data import load_market_data
from datathon.publication import publish_report
from datathon.streamlit_results import render_audit_workspace
from datathon.workflow import examples, run_case

market = load_market_data()
case = replace(examples("robert")[0], search_alternatives=False)
for panel, name in zip(st.tabs(("Original review", "Second review")), ("original", "second")):
    report = asyncio.run(run_case(market, replace(case, id=name), None))
    if name == "second" and st.session_state.get("tamper"):
        report["audit"]["verified"]["proposal"]["terminal_loss"] = .9832
    with panel:
        render_audit_workspace(publish_report(report))
""",
            default_timeout=20,
        ).run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.get("arrow_vega_lite_chart")), 2)
        app.radio(key="audit-window-metric-original").set_value("max_drawdown").run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["audit-window-metric-original"], "max_drawdown")
        self.assertEqual(app.session_state["audit-window-metric-second"], "terminal_loss")

        app.session_state["tamper"] = True
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.get("arrow_vega_lite_chart")), 1)
        self.assertTrue(any("withheld" in alert.value for alert in app.error))
        self.assertEqual(len(app.get("download_button")), 2)
