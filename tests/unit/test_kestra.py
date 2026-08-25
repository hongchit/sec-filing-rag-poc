from __future__ import annotations

import httpx
import pytest
import respx

from sec_filing_rag.integrations.kestra import KestraGateway, KestraSubmissionError


def gateway() -> KestraGateway:
    return KestraGateway(
        api_url="http://kestra:8080/api/v1/main",
        namespace="sec_filings.ingestion",
        flow_id="filing_batch",
        username="server-user",
        password="server-password",
        timeout=1,
        retries=0,
        client=httpx.Client(),
    )


@respx.mock
def test_kestra_submission_uses_basic_auth_and_multipart_inputs() -> None:
    route = respx.post(
        "http://kestra:8080/api/v1/main/executions/sec_filings.ingestion/filing_batch"
    ).mock(return_value=httpx.Response(200, json={"id": "execution-1"}))
    result = gateway().submit_batch(batch_id="batch-1")
    assert result.id == "execution-1"
    request = route.calls[0].request
    assert request.headers["authorization"].startswith("Basic ")
    assert b"batch-1" in request.content
    assert b"batch_id" in request.content
    assert b"selected_accession" not in request.content


@respx.mock
def test_kestra_errors_are_sanitized() -> None:
    respx.post("http://kestra:8080/api/v1/main/executions/sec_filings.ingestion/filing_batch").mock(
        side_effect=httpx.ConnectTimeout("server-password timed out")
    )
    with pytest.raises(KestraSubmissionError) as caught:
        gateway().submit_batch(batch_id="batch-1")
    assert "server-password" not in str(caught.value)
