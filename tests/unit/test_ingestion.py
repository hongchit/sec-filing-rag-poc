from __future__ import annotations

import uuid
from types import SimpleNamespace

from sec_filing_rag.core.config import Settings
from sec_filing_rag.services.ingestion import IngestionPipeline


class ReadyStore:
    def __init__(self) -> None:
        self.skipped = False

    def start_run(self, *args):  # type: ignore[no-untyped-def]
        del args
        return uuid.UUID(int=1), uuid.UUID(int=2)

    def stage(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        del args, kwargs

    def update_run_key(self, *args):  # type: ignore[no-untyped-def]
        del args

    def ready_corpus(self, *args):  # type: ignore[no-untyped-def]
        del args
        return {
            "is_active": True,
            "corpus_version_id": uuid.UUID(int=3),
            "coverage": {"1": "present"},
            "section_count": 6,
            "chunk_count": 12,
            "search_document_count": 12,
            "embedding_usage_status": "reported",
        }

    def skip_run(self, *args):  # type: ignore[no-untyped-def]
        del args
        self.skipped = True


class NoOpenAI:
    @property
    def embeddings(self):  # type: ignore[no-untyped-def]
        raise AssertionError("compatible unchanged ingestion must not access OpenAI")


def test_compatible_ready_corpus_skips_before_openai_request() -> None:
    settings = Settings(
        ingestion_api_token="0123456789abcdef",
        edgar_identity="Test test@example.com",
        openai_api_key="key",
    )
    store = ReadyStore()
    document = SimpleNamespace(media_type="text/html", content=b"<html>same</html>")
    import hashlib

    document.sha256 = hashlib.sha256(document.content).hexdigest()
    acquired = SimpleNamespace(
        filing=SimpleNamespace(accession="0000000001-26-000001"), document=document
    )

    result = IngestionPipeline(settings, store, NoOpenAI()).process_acquisition(  # type: ignore[arg-type]
        item_id=uuid.uuid4(),
        ticker="EX",
        acquired=acquired,
        mode="latest",
        kestra_execution_id="execution-1",
    )

    assert result.outcome == "skipped"
    assert result.corpus_disposition == "unchanged"
    assert store.skipped is True
