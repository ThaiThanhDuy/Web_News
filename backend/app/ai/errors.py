class LLMError(Exception):
    pass


class LLMConfigError(LLMError):
    """Misconfiguration (missing/invalid key, unknown model/provider). Not
    the item's fault: the job fails without marking the item failed."""


class LLMRateLimited(LLMError):
    """Provider said slow down (HTTP 429) or our own token budget is spent.
    The job is rescheduled without using up an attempt."""

    def __init__(self, message: str, retry_after: float):
        super().__init__(message)
        self.retry_after = retry_after


class LLMTransientError(LLMError):
    """Network error / 5xx: retried with backoff."""


class LLMInvalidOutput(LLMError):
    """The model's answer didn't match the schema/validation."""
