from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from .domain import safe_error


class KestraSubmissionError(RuntimeError):
    pass


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
    ) -> None:
        self.url = f"{api_url.rstrip('/')}/executions/{namespace}/{flow_id}"
        self.username = username
        self.password = password
        self.timeout = timeout
        self.retries = retries

    def submit_historical(
        self, *, request_id: str, ticker: str, requested_year: int, accession: str
    ) -> KestraExecution:
        fields = {
            "preparation_request_id": (None, request_id),
            "ticker": (None, ticker),
            "requested_year": (None, str(requested_year)),
            "selected_accession": (None, accession),
        }
        last_error: BaseException | None = None
        for attempt in range(self.retries + 1):
            try:
                response = httpx.post(
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
                retryable = not isinstance(exc, httpx.HTTPStatusError) or (
                    exc.response.status_code in {429, 500, 502, 503, 504}
                )
                if attempt >= self.retries or not retryable:
                    break
                time.sleep(min(2**attempt, 4))
        assert last_error is not None
        raise KestraSubmissionError(safe_error(last_error, (self.username, self.password))) from None
