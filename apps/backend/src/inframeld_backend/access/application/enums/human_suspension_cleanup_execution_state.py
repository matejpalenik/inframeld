from enum import StrEnum


class HumanSuspensionCleanupExecutionState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    STOPPED = "stopped"
    EXHAUSTED = "exhausted"
    COMPLETED = "completed"
