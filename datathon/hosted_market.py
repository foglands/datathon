"""Load an operator-approved snapshot from a private S3 object."""

from contextlib import closing
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
from zipfile import BadZipFile
import re

from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from .data import load_market_data


MAX_ARCHIVE_BYTES = 32 * 1024 * 1024


class HostedArchiveError(OSError):
    """An operator-safe error without object names, credentials or provider details."""


def load_hosted_market_data(uri, expected_digest, region, *, client=None):
    parsed = urlsplit(uri)
    if (parsed.scheme != "s3" or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", parsed.netloc)
            or not parsed.path.lstrip("/") or parsed.query or parsed.fragment
            or not re.fullmatch(r"[0-9a-f]{64}", expected_digest)):
        raise HostedArchiveError("The private price archive needs an S3 object and a valid SHA-256 digest.")
    try:
        if client is None:
            import boto3
            client = boto3.client("s3", region_name=region, config=Config(
                connect_timeout=3, read_timeout=8, retries={"total_max_attempts": 2, "mode": "standard"}))
        output = client.get_object(Bucket=parsed.netloc, Key=parsed.path[1:])
        with closing(output["Body"]) as stream:
            if output["ContentLength"] > MAX_ARCHIVE_BYTES:
                raise HostedArchiveError("The private price archive exceeds the 32 MiB limit.")
            data = stream.read(MAX_ARCHIVE_BYTES + 1)
        if len(data) > MAX_ARCHIVE_BYTES or sha256(data).hexdigest() != expected_digest:
            raise HostedArchiveError("The private price archive does not match its configured SHA-256 digest.")
        with TemporaryDirectory() as temp:
            path = Path(temp) / "market-snapshot.zip"
            path.write_bytes(data)
            result = load_market_data(path)
        price_metadata = next((row for row in result.metadata if row.get("file") == "prices_daily.csv"), {})
        source_url = urlsplit(price_metadata.get("source_url", ""))
        if (source_url.scheme != "https" or not source_url.netloc
                or not all(price_metadata.get(field) for field in ("source", "retrieved_on", "terms_of_use"))):
            raise HostedArchiveError("The private price archive lacks price source, date or terms metadata.")
        return replace(result, source_path="", source_name="Configured market snapshot", official_starter=False)
    except HostedArchiveError:
        raise
    except (BotoCoreError, ClientError, OSError, BadZipFile, ValueError, KeyError):
        raise HostedArchiveError("The app could not read or validate its private price archive.") from None
