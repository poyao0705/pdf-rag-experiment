from agents import MaxTurnsExceeded
from openai import APIError, APITimeoutError, RateLimitError


def public_error(exc: Exception) -> tuple[int, str]:
    if isinstance(exc, APITimeoutError):
        return 504, "Model request timed out"
    if isinstance(exc, RateLimitError):
        return 503, "Model service temporarily unavailable"
    if isinstance(exc, MaxTurnsExceeded):
        return 502, "Agent exceeded the maximum number of turns"
    if isinstance(exc, APIError):
        return 502, "Model service request failed"
    return 500, "Internal server error"
