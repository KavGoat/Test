"""Problem tracker for the document.

Collects errors, undefined names, unit mismatches during evaluation
and presents them with page/region context.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


class Severity(Enum):
    ERROR = auto()
    WARNING = auto()
    INFO = auto()


@dataclass
class Problem:
    message: str
    severity: Severity = Severity.ERROR
    page: int = 0
    region_id: Optional[str] = None
    line: int = 0
    source: str = ""

    @property
    def location(self) -> str:
        parts = [f"Page {self.page + 1}"]
        if self.source:
            parts.append(self.source)
        if self.line:
            parts.append(f"line {self.line}")
        return ", ".join(parts)


class ProblemCollector:
    def __init__(self):
        self._problems: list[Problem] = []

    def clear(self):
        self._problems.clear()

    def add(self, message: str, severity: Severity = Severity.ERROR,
            page: int = 0, region_id: str = None, line: int = 0, source: str = ""):
        self._problems.append(Problem(
            message=message, severity=severity,
            page=page, region_id=region_id, line=line, source=source,
        ))

    def error(self, message: str, **kwargs):
        self.add(message, Severity.ERROR, **kwargs)

    def warning(self, message: str, **kwargs):
        self.add(message, Severity.WARNING, **kwargs)

    @property
    def errors(self) -> list[Problem]:
        return [p for p in self._problems if p.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[Problem]:
        return [p for p in self._problems if p.severity == Severity.WARNING]

    @property
    def all(self) -> list[Problem]:
        return list(self._problems)

    @property
    def count(self) -> int:
        return len(self._problems)

    @property
    def error_count(self) -> int:
        return len(self.errors)
