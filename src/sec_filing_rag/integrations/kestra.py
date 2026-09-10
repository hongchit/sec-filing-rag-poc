from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from ..domain.filings import safe_error


class KestraSubmissionError(RuntimeError):
    def __init__(self, message: str, *, definitely_rejected: bool) -> None:
        super().__init__(message)
        self.definitely_rejected = definitely_rejected


@dataclass(frozen=True)
class KestraExecution:
    id: str


class KestraGateway:
    def __init__(
        self,
        *,
        api_url: str,
        namespace: str,
        flow_id: str,
        username: str,
        password: str,
        timeout: float,
        retries: int,
        client: httpx.Client,
    ) -> None:
        self.url = f"{api_url.rstrip('/')}/executions/{namespace}/{flow_id}"
        self.username = username
        self.password = password
        self.timeout = timeout
        self.retries = retries
        self.client = client

    def submit_batch(self, *, batch_id: str) -> KestraExecution:
        return self._submit({"batch_id": (None, batch_id)})

    def _submit(self, fields: dict[str, tuple[None, str]]) -> KestraExecution:
        last_error: BaseException | None = None
        for attempt in range(self.retries + 1):
            try:
                response = self.client.post(
                    self.url,
                    files=fields,
                    auth=(self.username, self.password),
                    timeout=self.timeout,
                )
                response.raise_for_status()
                execution_id = str(response.json().get("id", ""))
                if not execution_id:
                    raise ValueError("Kestra response did not contain an execution id")
                return KestraExecution(execution_id)
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                retryable = not isinstance(
                    exc, httpx.HTTPStatusError
                ) or exc.response.status_code in {
                    429,
                    500,
                    502,
                    503,
                    504,
                }
                if attempt >= self.retries or not retryable:
                    break
                time.sleep(min(2**attempt, 4))
        assert last_error is not None
        definitely_rejected = (
            isinstance(last_error, httpx.HTTPStatusError)
            and 400 <= last_error.response.status_code < 500
            and last_error.response.status_code != 429
        )
        raise KestraSubmissionError(
            safe_error(last_error, (self.username, self.password)),
            definitely_rejected=definitely_rejected,
        ) from None
