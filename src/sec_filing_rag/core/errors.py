from __future__ import annotations


class UpstreamServiceError(RuntimeError):
    """A dependency or its returned data prevented an operation from completing."""

    def __init__(self, message: str, *, public_detail: str, code: str) -> None:
        super().__init__(message)
        self.public_detail = public_detail
        self.code = code
