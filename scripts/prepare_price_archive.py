"""Validate and package a licensed daily-price export for the research app."""

import argparse
from datetime import date
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
from zipfile import ZIP_DEFLATED, ZipFile

from datathon.customer_data import PRICE_BASES, StarterResearch
from datathon.customer_report import analyze
from datathon.data import DATA_CSVS
from datathon.hosted_market import MAX_ARCHIVE_BYTES, load_approved_price_archive


EXAMPLE_GROUPS = (("SPY", "NVDA", "IBIT"), ("ESGU", "SPY"), ("TSLA",))


def prepare_archive(source, output, *, verify_examples=False):
    """Publish the output locally only after loading it through the app's reader."""
    source, output = Path(source), Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as temp:
        staged = Path(temp) / "prices.zip"
        with ZipFile(staged, "w", compression=ZIP_DEFLATED) as archive:
            for filename in DATA_CSVS:
                archive.write(source / filename, f"alphaforge_starter/{filename}")
        if staged.stat().st_size > MAX_ARCHIVE_BYTES:
            raise ValueError("The archive exceeds the hosted size limit of 32 MiB.")
        market = load_approved_price_archive(staged)
        metadata = {row["file"]: row for row in market.metadata}
        for filename in ("prices_daily.csv", "fx_usdcad_daily.csv"):
            row = metadata.get(filename, {})
            if not all(row.get(field) for field in ("source", "source_url", "retrieved_on", "terms_of_use", "processing", "limitations")):
                raise ValueError(f"{filename} needs source, source_url, retrieved_on, terms_of_use, processing and limitations.")
            url = urlsplit(row["source_url"])
            if url.scheme != "https" or not url.netloc:
                raise ValueError(f"{filename} needs a public HTTPS source reference.")
            date.fromisoformat(row["retrieved_on"])
        if metadata["prices_daily.csv"].get("price_basis") not in PRICE_BASES:
            raise ValueError("Record one supported adjustment basis for the entire price file: " + ", ".join(PRICE_BASES))
        provider = StarterResearch(market)
        if not provider.series or not market.fx:
            raise ValueError("The archive must include daily prices and Bank of Canada USD/CAD fixings.")
        if any(day["date"] > date.today().isoformat() for rows in provider.series.values() for day in rows):
            raise ValueError("The archive includes a future price observation.")
        coverage = []
        if verify_examples:
            for symbols in EXAMPLE_GROUPS:
                missing = [symbol for symbol in symbols if not provider.covers(symbol)]
                if missing:
                    raise ValueError("Missing example prices for " + ", ".join(missing))
                analyses = analyze([provider.asset(symbol) for symbol in symbols], None, provider.fx(),
                                   target_currency="USD")
                metrics = analyses[0]["metrics"]
                coverage.append((symbols, metrics["start"], metrics["end"], metrics["observations"]))
        digest = sha256(staged.read_bytes()).hexdigest()
        staged.replace(output)
    return digest, coverage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Directory containing the three prepared CSVs")
    parser.add_argument("output", type=Path, help="Path for the validated ZIP")
    parser.add_argument("--verify-examples", action="store_true", help="Require enough overlapping data for the three examples")
    args = parser.parse_args()
    try:
        digest, coverage = prepare_archive(args.source, args.output, verify_examples=args.verify_examples)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")
    for symbols, start, end, days in coverage:
        print(f"{', '.join(symbols)} | {start} to {end} | {days} common observations")
    print(f"SHA-256 {digest}")


if __name__ == "__main__":
    main()
