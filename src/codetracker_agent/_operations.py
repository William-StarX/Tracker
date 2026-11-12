"""Typed convenience methods shared by the local and HTTP clients."""
from os import PathLike
from typing import Any
from .models import AnalysisResult


class Operations:
    def call(self, operation: str, **arguments: Any) -> AnalysisResult:
        raise NotImplementedError

    def overview(self, repo: str | PathLike, **options: Any) -> AnalysisResult:
        return self.call("overview", repo=repo, **options)

    def trace(self, repo: str | PathLike, file: str, line: int, *, commit: str = "HEAD", name: str | None = None, **options: Any) -> AnalysisResult:
        if name is not None:
            options["name"] = name
        return self.call("trace", repo=repo, file=file, line=line, commit=commit, **options)
