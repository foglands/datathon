"""Inspect local prerequisites without printing credentials or calling AWS services."""
from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import re
import socket
import sys


DEPENDENCIES = ("streamlit", "strands-agents", "boto3", "reportlab", "altair")
_LOCAL_PROVIDERS = {"env", "shared-credentials-file", "config-file", "boto-config"}
_REGION = re.compile(r"[a-z]{2}(?:-[a-z]+)+-\d\Z")
_MODEL = re.compile(r"(?:(?:us|eu|apac|global)\.)?(?:amazon|anthropic|meta|mistral|cohere|ai21|openai|deepseek)\.[a-z0-9_.:-]{1,100}\Z")


def _setting(name, default):
    value = os.environ.get(name, "").strip() or default
    allowed = _REGION if name == "DATATHON_AWS_REGION" else _MODEL
    return value if allowed.fullmatch(value) else "configured_value_not_displayed"


def credential_status(session=None):
    """Ask only SDK local providers; skip remote, SSO and process providers.

    No credential values are resolved, frozen, logged, returned or persisted.
    Finding a local provider does not establish that the session is valid.
    """
    try:
        if session is None:
            import boto3
            session = boto3.Session()
        providers = session._session.get_component("credential_provider").providers
        deferred = False
        for provider in providers:
            if provider.METHOD not in _LOCAL_PROVIDERS:
                deferred = True
                continue
            credentials = provider.load()
            if credentials is not None:
                return {"status": "present_unverified", "provider": provider.METHOD,
                        "validity": "not_checked"}
        return {"status": "not_found_in_local_providers", "provider": None,
                "remote_providers_not_checked": deferred, "validity": "not_checked"}
    except ImportError:
        return {"status": "sdk_unavailable", "provider": None, "validity": "not_checked"}
    except Exception:
        return {"status": "local_provider_error", "provider": None, "validity": "not_checked"}


def _file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def check_runtime(data=None, *, check_dns=False, session=None):
    dependencies = {}
    for package in DEPENDENCIES:
        try:
            dependencies[package] = {"installed": True, "version": metadata.version(package)}
        except metadata.PackageNotFoundError:
            dependencies[package] = {"installed": False}
    raw_path = data or os.environ.get("DATATHON_STARTER_PATH")
    market = {"configured": bool(raw_path), "exists": False, "source_sha256": {}}
    if raw_path:
        path = Path(raw_path).expanduser()
        market["exists"] = path.exists()
        try:
            if path.is_file():
                market["kind"] = "archive"
                market["source_sha256"] = {"archive": _file_hash(path)}
            elif path.is_dir():
                market["kind"] = "directory"
                files = ("prices_daily.csv", "fx_usdcad_daily.csv", "sources_metadata.csv",
                         "assets_universe.csv", "corporate_actions.csv", "macro_rates.csv")
                market["missing_tables"] = [name for name in files if not (path / name).is_file()]
                market["source_sha256"] = {name: _file_hash(path / name) for name in files if (path / name).is_file()}
        except OSError:
            market["read_status"] = "unreadable"
    region = _setting("DATATHON_AWS_REGION", "us-east-1")
    result = {
        "python": {"version": platform.python_version(), "supported": sys.version_info >= (3, 10)},
        "dependencies": dependencies, "data": market,
        "aws": {"region": region,
                "profile_model": _setting("DATATHON_PROFILE_MODEL_ID", "global.anthropic.claude-sonnet-4-5-20250929-v1:0"),
                "audit_model": _setting("DATATHON_AUDIT_MODEL_ID", "us.amazon.nova-2-lite-v1:0"),
                "credentials": credential_status(session), "bedrock_call": "not_attempted",
                "network": "not_checked"},
    }
    if check_dns:
        if not re.fullmatch(r"[a-z]{2}(?:-[a-z]+)+-\d", region):
            result["aws"]["network"] = "invalid_region"
        else:
            try:
                socket.getaddrinfo(f"bedrock-runtime.{region}.amazonaws.com", 443)
                result["aws"]["network"] = "dns_resolved_only"
            except OSError:
                result["aws"]["network"] = "dns_unavailable"
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, help="Organizer ZIP or starter directory")
    parser.add_argument("--check-dns", action="store_true", help="Resolve the Bedrock endpoint; does not invoke a model")
    args = parser.parse_args(argv)
    print(json.dumps(check_runtime(args.data, check_dns=args.check_dns), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
