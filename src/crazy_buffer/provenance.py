"""Optional, in-memory processing records; never writes files implicitly."""

from copy import deepcopy
from dataclasses import dataclass, field


@dataclass
class RunReport:
    steps: list[dict] = field(default_factory=list)
    issues: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def add_step(self, name, parameters, counts):
        self.steps.append(deepcopy({
            "name": name, "parameters": parameters, "counts": counts,
        }))
