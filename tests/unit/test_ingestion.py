from __future__ import annotations

import hashlib
import uuid
from array import array
from types import SimpleNamespace

import pytest

from sec_filing_rag.core.config import Settings
from sec_filing_rag.domain.filings import Chunk, ExtractedSection
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


def settings() -> Settings:
    return Settings(
        ingestion_api_token="0123456789abcdef",
        edgar_identity="Test test@example.com",
        openai_api_key="secret-key",
        openai_embedding_dimensions=3,
    )


def chunks(count: int) -> list[Chunk]:
    return [
        Chunk(str(index), index, f"chunk-{index}", index, index + 1, f"cite-{index}", "hash")
        for index in range(count)
    ]


class EmbeddingStore:
    def __init__(self) -> None:
        self.usage: list[dict[str, object]] = []

    def record_embedding_usage(self, run_id, model, **kwargs):  # type: ignore[no-untyped-def]
        self.usage.append({"run_id": run_id, "model": model, **kwargs})


class FakeEmbeddings:
    def __init__(self, *, fail_call: int | None = None, invalid: str | None = None) -> None:
        self.calls: list[list[str]] = []
        self.fail_call = fail_call
        self.invalid = invalid

    def create(self, *, model, input, dimensions):  # type: ignore[no-untyped-def]
        del model
        values = list(input)
        self.calls.append(values)
        if self.fail_call == len(self.calls):
            raise RuntimeError("provider secret-key rejected batch")
        entries = [
            SimpleNamespace(
                index=index, embedding=[float(value.removeprefix("chunk-"))] * dimensions
            )
            for index, value in enumerate(values)
        ]
        if self.invalid == "index":
            entries[0].index = len(entries)
        elif self.invalid == "dimension":
            entries[0].embedding.pop()
        elif self.invalid == "count":
            entries.pop()
        return SimpleNamespace(
            data=list(reversed(entries)),
            usage=SimpleNamespace(prompt_tokens=len(values) * 2, total_tokens=len(values) * 2),
        )


def test_embeddings_are_batched_compacted_ordered_and_usage_is_aggregated() -> None:
    store = EmbeddingStore()
    embeddings = FakeEmbeddings()
    pipeline = IngestionPipeline(settings(), store, SimpleNamespace(embeddings=embeddings))  # type: ignore[arg-type]

    vectors, usage_status = pipeline._embed(uuid.UUID(int=1), chunks(65))

    assert [len(call) for call in embeddings.calls] == [32, 32, 1]
    assert all(isinstance(vector, array) and vector.typecode == "f" for vector in vectors)
    assert [vector[0] for vector in vectors] == [float(index) for index in range(65)]
    assert usage_status == "reported"
    assert len(store.usage) == 1
    assert store.usage[0]["input_tokens"] == 130
    assert store.usage[0]["total_tokens"] == 130


@pytest.mark.parametrize("invalid", ["index", "dimension", "count"])
def test_embedding_response_indices_and_dimensions_are_validated(invalid: str) -> None:
    store = EmbeddingStore()
    embeddings = FakeEmbeddings(invalid=invalid)
    pipeline = IngestionPipeline(settings(), store, SimpleNamespace(embeddings=embeddings))  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="embedding response"):
        pipeline._embed(uuid.UUID(int=1), chunks(2))

    assert len(store.usage) == 1
    assert store.usage[0]["error"]


class FailingPipelineStore(EmbeddingStore):
    def __init__(self) -> None:
        super().__init__()
        self.failed_stage: str | None = None
        self.persisted = False

    def start_run(self, *args):  # type: ignore[no-untyped-def]
        del args
        return uuid.UUID(int=1), uuid.UUID(int=2)

    def stage(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        del args, kwargs

    def update_run_key(self, *args):  # type: ignore[no-untyped-def]
        del args

    def ready_corpus(self, *args):  # type: ignore[no-untyped-def]
        del args
        return None

    def fail_run(self, run_id, stage, error):  # type: ignore[no-untyped-def]
        del run_id, error
        self.failed_stage = stage

    def persist(self, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        self.persisted = True
        raise AssertionError("partial embeddings must never be persisted")


def test_later_embedding_batch_failure_preserves_previous_corpus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sec_filing_rag.services.ingestion as ingestion

    all_chunks = chunks(33)
    monkeypatch.setattr(ingestion, "REQUIRED_ITEMS", ("1",))
    monkeypatch.setattr(ingestion, "sanitize_filing_html", lambda *args, **kwargs: "narrative")
    monkeypatch.setattr(
        ingestion,
        "extract_sections",
        lambda narrative: {"1": ExtractedSection("present", narrative, 0, len(narrative))},
    )
    monkeypatch.setattr(ingestion, "make_chunks", lambda *args, **kwargs: all_chunks)
    store = FailingPipelineStore()
    embeddings = FakeEmbeddings(fail_call=2)
    pipeline = IngestionPipeline(settings(), store, SimpleNamespace(embeddings=embeddings))  # type: ignore[arg-type]
    content = b"<html>filing</html>"
    acquired = SimpleNamespace(
        filing=SimpleNamespace(accession="0000000001-26-000001"),
        document=SimpleNamespace(
            media_type="text/html", content=content, sha256=hashlib.sha256(content).hexdigest()
        ),
    )

    result = pipeline.process_acquisition(  # type: ignore[arg-type]
        item_id=uuid.uuid4(),
        ticker="EX",
        acquired=acquired,
        mode="latest",
        kestra_execution_id="execution-1",
    )

    assert result.outcome == "failed"
    assert result.corpus_disposition == "previous_preserved"
    assert store.failed_stage == "embedding"
    assert store.persisted is False
    assert len(store.usage) == 1
    assert store.usage[0]["input_tokens"] == 64
    assert "secret-key" not in str(store.usage[0]["error"])
