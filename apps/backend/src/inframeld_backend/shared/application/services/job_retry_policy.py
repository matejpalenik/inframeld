from inframeld_backend.shared.application.enums.job_status import JobStatus


class JobRetryPolicy:
    """Keep unknown effects distinct from bounded, proven-safe repetition."""

    @staticmethod
    def after_interruption(
        *, attempt: int, uncertain_effect: bool, deadline_expired: bool
    ) -> JobStatus:
        if uncertain_effect:
            return JobStatus.RECOVERY_REQUIRED
        if attempt >= 3 or deadline_expired:
            return JobStatus.FAILED
        return JobStatus.QUEUED
