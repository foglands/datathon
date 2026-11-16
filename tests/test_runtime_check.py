"""The diagnosis must not call AWS or disclose credential values."""
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from datathon import runtime_check


def session(*providers):
    return SimpleNamespace(_session=SimpleNamespace(get_component=lambda _: SimpleNamespace(providers=providers)))


class RuntimeCheckTests(unittest.TestCase):
    def test_only_local_provider_is_loaded_and_credentials_are_never_serialized(self):
        remote = SimpleNamespace(METHOD="iam-role", load=Mock(side_effect=AssertionError("remote lookup")))
        credentials = object()
        local = SimpleNamespace(METHOD="env", load=Mock(return_value=credentials))
        result = runtime_check.credential_status(session(remote, local))
        self.assertEqual(result["status"], "present_unverified")
        self.assertEqual(result["provider"], "env")
        self.assertEqual(result["validity"], "not_checked")
        remote.load.assert_not_called()
        self.assertNotIn(str(credentials), json.dumps(result))

    def test_errors_do_not_echo_provider_exception_or_tokens(self):
        provider = SimpleNamespace(METHOD="env", load=Mock(side_effect=ValueError("secret=sentinel")))
        result = runtime_check.credential_status(session(provider))
        self.assertEqual(result["status"], "local_provider_error")
        self.assertNotIn("sentinel", json.dumps(result))

    def test_default_diagnosis_never_resolves_endpoint(self):
        with patch.object(runtime_check.socket, "getaddrinfo") as dns, patch.dict("os.environ", {}, clear=True):
            result = runtime_check.check_runtime(session=session())
        dns.assert_not_called()
        self.assertEqual(result["aws"]["network"], "not_checked")
        self.assertEqual(result["aws"]["bedrock_call"], "not_attempted")

    def test_archive_hash_and_optional_dns_failure_are_precise(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "starter.zip"
            source.write_bytes(b"abc")
            with patch.object(runtime_check.socket, "getaddrinfo", side_effect=OSError("secret=sentinel")):
                result = runtime_check.check_runtime(source, check_dns=True, session=session())
        self.assertEqual(result["data"]["source_sha256"]["archive"],
                         "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
        self.assertEqual(result["aws"]["network"], "dns_unavailable")
        self.assertNotIn("sentinel", json.dumps(result))

    def test_nonstandard_model_values_and_arns_are_not_echoed(self):
        for value in ("ASIAABCDEFGHIJKLMNOP", "arn:aws:bedrock:us-east-1:123456789012:custom-model/test", "secret=sentinel"):
            with self.subTest(value=value), patch.dict("os.environ", {"DATATHON_PROFILE_MODEL_ID": value}):
                result = runtime_check.check_runtime(session=session())
                self.assertNotIn(value, json.dumps(result))
                self.assertEqual(result["aws"]["profile_model"], "configured_value_not_displayed")
