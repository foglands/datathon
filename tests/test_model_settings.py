"""The same workflow can use different Bedrock model configurations."""

import os
import unittest
from unittest.mock import patch

from datathon.agents import DEFAULT_MODEL, DEFAULT_REGION, PROFILE_MODEL
from datathon.model_settings import configured_bedrock_runtime


class BedrockModelSettingsTests(unittest.TestCase):
    def test_competition_configuration_is_the_default(self):
        with patch.dict(os.environ, {}, clear=True):
            audit = configured_bedrock_runtime()
            intake = configured_bedrock_runtime(profile=True)
        self.assertEqual((audit.model_id, audit.region), (DEFAULT_MODEL, DEFAULT_REGION))
        self.assertEqual((intake.model_id, intake.region), (PROFILE_MODEL, DEFAULT_REGION))

    def test_model_choices_remain_independent_and_use_the_selected_region(self):
        with patch.dict(os.environ, {
            "DATATHON_PROFILE_MODEL_ID": "  example.profile-v2:0  ",
            "DATATHON_AUDIT_MODEL_ID": "example.audit-v2:0",
            "DATATHON_AWS_REGION": "ca-central-1",
        }, clear=True):
            audit = configured_bedrock_runtime()
            intake = configured_bedrock_runtime(profile=True)
        self.assertEqual((audit.model_id, audit.region), ("example.audit-v2:0", "ca-central-1"))
        self.assertEqual((intake.model_id, intake.region), ("example.profile-v2:0", "ca-central-1"))

    def test_empty_overrides_use_the_default_for_that_setting(self):
        with patch.dict(os.environ, {"DATATHON_AUDIT_MODEL_ID": "example.audit-v3:0",
                                    "DATATHON_PROFILE_MODEL_ID": " ", "DATATHON_AWS_REGION": ""},
                        clear=True):
            self.assertEqual(configured_bedrock_runtime().model_id, "example.audit-v3:0")
            self.assertEqual(configured_bedrock_runtime(profile=True).model_id, PROFILE_MODEL)
            self.assertEqual(configured_bedrock_runtime().region, DEFAULT_REGION)
