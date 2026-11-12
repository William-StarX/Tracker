"""Stable, typed result contract. Component-specific evidence remains extensible."""
from typing import Any, Literal, TypedDict


class AnalysisError(TypedDict):
    code: str
    message: str


class ProcessResult(TypedDict, total=False):
    exit_code: int
    stderr: str
    stdout_tail: str


class AnalysisResult(TypedDict):
    interface_version: str
    operation: str | None
    status: Literal["ok", "partial", "error"]
    error: AnalysisError | None
    result: dict[str, Any] | None
    process: ProcessResult | None


class TransportError(RuntimeError):
    """The HTTP service could not return a usable analysis envelope."""
