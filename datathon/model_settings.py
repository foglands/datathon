"""Create Bedrock runtimes while keeping model choice outside policy logic."""

from os import environ

from .agents import DEFAULT_MODEL, DEFAULT_REGION, PROFILE_MODEL, StrandsAgents


def configured_bedrock_runtime(*, profile: bool = False) -> StrandsAgents:
    """Use the configured model for the requested role, or the competition default."""
    model_key = "DATATHON_PROFILE_MODEL_ID" if profile else "DATATHON_AUDIT_MODEL_ID"
    default_model = PROFILE_MODEL if profile else DEFAULT_MODEL
    model_id = environ.get(model_key, "").strip() or default_model
    region = environ.get("DATATHON_AWS_REGION", "").strip() or DEFAULT_REGION
    return StrandsAgents(model_id=model_id, region=region)
