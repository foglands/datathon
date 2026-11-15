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


def bedrock_failure_message(trace=(), *, stop_reason="") -> str:
    """Explain a failed AWS call using safe, structured exception metadata."""
    if not stop_reason:
        stop_reason = next((event.get("stop_reason") for event in reversed(trace) if event.get("event") == "agent_end"), "")
    failure = next((event for event in reversed(trace) if event.get("event") == "agent_exception"), {})
    error_type, code = failure.get("error_type"), failure.get("error_code")
    if error_type in {"NoCredentialsError", "PartialCredentialsError", "ProfileNotFound", "CredentialRetrievalError"}:
        return "No usable AWS credentials were found in the environment running the app."
    if code in {"ExpiredToken", "ExpiredTokenException", "InvalidClientTokenId", "UnrecognizedClientException"}:
        return "The AWS credentials could not be used. Refresh the AWS session before retrying."
    if code in {"AccessDenied", "AccessDeniedException", "UnauthorizedOperation", "NotAuthorizedException"}:
        return "The AWS session does not have access to the configured Bedrock model."
    if code in {"Throttling", "ThrottlingException", "TooManyRequestsException"}:
        return "Amazon Bedrock reached its request limit. Try again later or continue offline."
    if error_type in {"EndpointConnectionError", "ConnectTimeoutError", "ReadTimeoutError"} or stop_reason == "timeout":
        return "The Amazon Bedrock request did not complete in time."
    if error_type == "ProxyConnectionError":
        return "The environment running the app could not connect to AWS."
    if stop_reason == "unavailable":
        return "Amazon Bedrock is temporarily unavailable."
    if stop_reason == "runtime_unavailable":
        return "The Bedrock runtime is unavailable. Install the dependencies in requirements.txt."
    if stop_reason == "input_too_large":
        return "Shorten the fictional request or enter its supported inputs directly."
    return "Amazon Bedrock could not interpret the request."
