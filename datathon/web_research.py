"""On-demand public source discovery via Amazon Bedrock AgentCore."""

import asyncio
from datetime import date, datetime, timezone
from os import environ
import re
from urllib.parse import urlsplit

from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

from .customer_data import ResearchUnavailable, read_public_json


TOPICS = {
    "daily_prices": "daily historical adjusted close dates currency split and dividend data source",
    "fund_methods": "fund issuer prospectus fund holdings screening methodology",
    "issuer_filings": "official issuer filings historical market information and disclosures",
}
SEARCH_STATUS = {
    "success": "Returned source leads for follow-up",
    "no_results": "No suitable source references returned",
    "access_denied": "The deployment's AWS identity lacks bedrock-agentcore:InvokeWebSearch access",
    "credentials_unavailable": "The deployment needs valid AWS credentials for web search",
    "timeout": "The search timed out",
    "throttled": "The search exceeded the service request rate",
    "budget_exhausted": "The research reached its source lookup limit",
    "service_unavailable": "The search service was unavailable",
}
SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"
SEC_AGENT = "AlphaForge Research (+https://github.com/foglands/datathon)"


class AgentCoreSearch:
    """Use the application's AWS identity to query the managed search tool."""

    def __init__(self, region, client=None):
        self.region = region
        self.client = client

    def lookup(self, topic, instruments):
        query = " ".join((*instruments, TOPICS[topic]))
        response = {"topic": topic, "query": query, "region": self.region, "results": []}
        try:
            client = self.client
            if client is None:
                import boto3
                client = boto3.client("bedrock-agentcore", region_name=self.region,
                    config=Config(connect_timeout=3, read_timeout=7, retries={"total_max_attempts": 1}))
            raw = client.invoke_web_search(webSearchId="web-search.v1", searchQuery=query, maxResults=4)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            status = {"AccessDeniedException": "access_denied", "UnauthorizedException": "access_denied",
                      "ThrottlingException": "throttled", "ExpiredTokenException": "credentials_unavailable",
                      "ExpiredToken": "credentials_unavailable"}.get(code, "service_unavailable")
            return {**response, "status": status}
        except NoCredentialsError:
            return {**response, "status": "credentials_unavailable"}
        except BotoCoreError:
            return {**response, "status": "service_unavailable"}
        seen = set()
        for row in (raw.get("results") or [])[:4]:
            url = row.get("url") or ""
            try:
                parsed = urlsplit(url)
            except ValueError:
                continue
            if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                    or len(url) > 500 or re.search(r"[\s<>\[\]()]", url) or url in seen):
                continue
            seen.add(url)
            published = row.get("publishedAt")
            response["results"].append({
                "title": " ".join((row.get("title") or "").split())[:160] or parsed.hostname,
                "url": url, "excerpt": " ".join((row.get("text") or "").split())[:450],
                "published_at": published.isoformat() if isinstance(published, datetime) else None,
            })
        return {**response, "status": "success" if response["results"] else "no_results",
                "checked_at": datetime.now(timezone.utc).isoformat()}


def configured_search():
    if environ.get("DATATHON_WEB_SEARCH", "1").strip() == "0":
        return None
    return AgentCoreSearch(environ.get("DATATHON_AWS_REGION", "").strip() or "us-east-1")


def _read_sec(url):
    return read_public_json(url, user_agent=SEC_AGENT)


async def verified_issuer_filings(assets, budget, transport=_read_sec):
    """Confirm filing identifiers and dates directly in the SEC's submissions API."""
    symbols = tuple(dict.fromkeys(
        asset["query"].strip().removeprefix("$").upper() for asset in assets
        if asset["role"] in {"consider", "holding"}
        and re.fullmatch(r"\$?[A-Z][A-Z0-9-]{0,7}", asset["query"].strip(), re.IGNORECASE)
    ))[:2]
    if not symbols or not budget.take("source_calls"):
        return {}

    async def read(url):
        return await asyncio.wait_for(asyncio.to_thread(transport, url), timeout=min(10, budget.remaining()))

    try:
        index = await read(SEC_TICKERS)
        matches = {row["ticker"]: row["cik_str"] for row in index.values() if row["ticker"] in symbols}
    except (ResearchUnavailable, asyncio.TimeoutError, AttributeError, KeyError, TypeError):
        return {}
    blocks = {}
    for symbol in symbols:
        cik = matches.get(symbol)
        if type(cik) is not int or not 0 < cik < 10**10 or not budget.take("source_calls"):
            continue
        registry = f"https://data.sec.gov/submissions/CIK{cik:010}.json"
        try:
            record = await read(registry)
            if int(record["cik"]) != cik or symbol not in record["tickers"]:
                continue
            recent = record["filings"]["recent"]
            today = datetime.now(timezone.utc).date()
            for form, filed, accession in zip(recent["form"], recent["filingDate"], recent["accessionNumber"]):
                if form not in {"10-K", "10-Q", "20-F", "40-F"}:
                    continue
                if (not re.fullmatch(r"\d{4}-\d{2}-\d{2}", filed) or date.fromisoformat(filed) > today
                        or not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession)):
                    continue
                url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{accession}-index.htm"
                blocks[f"{symbol}.sec_filing"] = {
                    "title": f"{symbol} · SEC filing on record",
                    "text": f"The SEC submissions registry lists a Form {form} filing for {symbol}, filed {filed}. "
                            "This record confirms the filing and date. It contains no daily market price series.",
                    "sources": [url, registry],
                    "scope": {"level": "asset", "objects": [symbol], "as_of": filed,
                              "method": "ticker and filing metadata verified against SEC EDGAR"},
                }
                break
        except (ResearchUnavailable, asyncio.TimeoutError, KeyError, AttributeError, ValueError, TypeError):
            continue
    return blocks


async def discover_sources(search, topics, assets, budget):
    # Transmit public instrument identifiers and lookup topics. Client goals,
    # financial amounts, names and the conversation stay outside search queries.
    instruments = tuple(dict.fromkeys(
        row["query"].strip().removeprefix("$") for row in assets
        if row["role"] in {"consider", "holding"}
        and re.fullmatch(r"\$?[A-Za-z][A-Za-z0-9. -]{0,55}", row["query"].strip())
    ))[:4]
    if not instruments:
        return []

    async def lookup(topic):
        if not budget.take("source_calls"):
            return {"topic": topic, "status": "budget_exhausted", "results": []}
        try:
            return await asyncio.wait_for(asyncio.to_thread(search.lookup, topic, instruments),
                                          timeout=min(11, budget.remaining()))
        except asyncio.TimeoutError:
            return {"topic": topic, "status": "timeout", "results": []}

    return await asyncio.gather(*(lookup(topic) for topic in dict.fromkeys(topics)))


def discovery_blocks(searches):
    blocks = {}
    for search in searches:
        for index, hit in enumerate(search["results"], start=1):
            published = (f" Published {hit['published_at'][:10]}." if hit["published_at"] else "")
            blocks[f"web.{search['topic']}.{index}"] = {
                "title": hit["title"],
                "text": "Search excerpt for source discovery." + published + " " + hit["excerpt"],
                "sources": [hit["url"]],
                "scope": {"level": "source_lead", "method": "AgentCore search extract", "as_of": hit["published_at"]},
            }
    return blocks
