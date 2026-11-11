class Reschedule(Exception):
    """Put the job back in the queue after `delay` seconds WITHOUT counting
    it as a failed attempt — for waits that aren't the job's fault: a rate
    limit (Groq 429, our own token budget), per-domain crawl spacing, etc."""

    def __init__(self, delay: float, reason: str, *, pause_queue: bool = False):
        super().__init__(reason)
        self.delay = max(1.0, float(delay))
        self.reason = reason
        # True for limits that apply to every job of the queue (a model's
        # token budget): the worker thread then idles until `delay` passes
        # instead of claiming and re-queueing the next job straight away.
        self.pause_queue = pause_queue


class PermanentJobError(Exception):
    """Retrying cannot help (bad payload, misconfiguration): the job goes
    straight to `dead` without using its remaining attempts."""
