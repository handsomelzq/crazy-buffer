"""Structured, actionable failures at the spatial input boundary."""


class SpatialInputError(ValueError):
    def __init__(self, code: str, message: str, issues: list[dict]):
        super().__init__(message)
        self.code = code
        self.issues = issues
