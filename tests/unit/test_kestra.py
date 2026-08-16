from __future__ import annotations

import httpx
import pytest
import respx

from sec_filing_rag.kestra import KestraGateway, KestraSubmissionError


def gateway() -> KestraGateway:
    return KestraGateway(
        api_url="http://kestra:8080/api/v1/main",
        namespace="sec_filings.ingestion",
        flow_id="prepare_historical_filing",
        username="server-user",
        password="server-password",
        timeout=1,
        retries=0,
    )


@respx.mock
def test_kestra_submission_uses_basic_auth_and_multipart_inputs() -> None:
    route = respx.post(
        "http://kestra:8080/api/v1/main/executions/sec_filings.ingestion/prepare_historical_filing"
    ).mock(return_value=httpx.Response(200, json={"id": "execution-1"}))
    result = gateway().submit_historical(
        request_id="request-1", ticker="XOM", requested_year=2024, accession="accession-1"
    )
    assert result.id == "execution-1"
    request = route.calls[0].request
    assert request.headers["authorization"].startswith("Basic ")
    assert b"request-1" in request.content
    assert b"selected_accession" in request.content


@respx.mock
def test_kestra_errors_are_sanitized() -> None:
    respx.post(
        "http://kestra:8080/api/v1/main/executions/sec_filings.ingestion/prepare_historical_filing"
    ).mock(side_effect=httpx.ConnectTimeout("server-password timed out"))
    with pytest.raises(KestraSubmissionError) as caught:
        gateway().submit_historical(
            request_id="request-1", ticker="XOM", requested_year=2024, accession="accession-1"
        )
    assert "server-password" not in str(caught.value)
