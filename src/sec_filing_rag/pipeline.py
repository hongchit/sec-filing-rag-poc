from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass

from bs4 import BeautifulSoup
from openai import OpenAI

from .config import Settings, load_companies
from .domain import compatibility_key, extract_item_1a, make_chunks, safe_error
from .sec import SecClient
from .store import Store


@dataclass(frozen=True)
class Result:
    run_id: uuid.UUID
    ticker: str
    accession: str
    coverage_status: str
    chunk_count: int
    embedding_usage_status: str
    corpus_status: str


class IngestionPipeline:
    def __init__(self, settings: Settings, store: Store) -> None:
        self.settings = settings
        self.store = store

    def run(self, ticker: str, item: str, trigger: str = "api") -> Result:
        config = load_companies(self.settings.company_config_path)
        self.store.load_configuration(config, self.settings.company_config_path)
        key = compatibility_key(parser=self.settings.parser_version, chunker=self.settings.chunking_version,
                                model=self.settings.openai_embedding_model, dimensions=self.settings.openai_embedding_dimensions,
                                index=self.settings.index_version)
        run_id, company_id = self.store.start_run(ticker, item, trigger, key)
        stage = "resolve"
        try:
            sec = SecClient(identity=self.settings.sec_user_agent, timeout=self.settings.sec_timeout_seconds,
                            retries=self.settings.sec_max_retries, interval=self.settings.sec_request_interval_seconds)
            cik, name, ticker_fetch = sec.resolve(ticker)
            stage = "select-filing"
            filing, submission_fetch, submission = sec.latest_filing(cik)
            stage = "download"
            document = sec.document(cik, filing)
            stage = "extract"
            soup = BeautifulSoup(document.body, "html.parser")
            section = extract_item_1a(soup.get_text("\n", strip=True))
            chunks = make_chunks(section.text or "", accession=filing.accession, item=item,
                                 version=self.settings.chunking_version, size=self.settings.chunk_size_chars,
                                 overlap=self.settings.chunk_overlap_chars) if section.status == "present" else []
            if section.status != "present":
                raise ValueError(section.error or f"Item {item} is absent")
            stage = "embed"
            started = time.monotonic()
            response = OpenAI(api_key=self.settings.openai_api_key, timeout=self.settings.openai_timeout_seconds).embeddings.create(
                model=self.settings.openai_embedding_model, input=[chunk.text for chunk in chunks],
                dimensions=self.settings.openai_embedding_dimensions,
            )
            embeddings = [entry.embedding for entry in response.data]
            if len(embeddings) != len(chunks) or any(len(vector) != self.settings.openai_embedding_dimensions for vector in embeddings):
                raise ValueError("embedding response dimension or count mismatch")
            usage_object = getattr(response, "usage", None)
            prompt_tokens = getattr(usage_object, "prompt_tokens", None)
            total_tokens = getattr(usage_object, "total_tokens", None)
            usage = (prompt_tokens, None, total_tokens, "reported" if total_tokens is not None else "unavailable")
            stage = "persist-promote"
            user_agent_hash = hashlib.sha256(self.settings.sec_user_agent.encode()).hexdigest()
            self.store.persist(run_id=run_id, company_id=company_id, ticker=ticker, cik=cik, name=name,
                ticker_fetch=ticker_fetch, submission_fetch=submission_fetch, submission=submission, document=document,
                filing=filing, section=section, chunks=chunks, embeddings=embeddings, key=key,
                parser=self.settings.parser_version, chunker=self.settings.chunking_version,
                model=self.settings.openai_embedding_model, dimensions=self.settings.openai_embedding_dimensions,
                index=self.settings.index_version, usage=usage, user_agent_hash=user_agent_hash)
            _ = started
            return Result(run_id, ticker, filing.accession, section.status, len(chunks), usage[3], "active")
        except Exception as exc:
            error = safe_error(exc, (self.settings.openai_api_key, self.settings.ingestion_api_token, self.settings.sec_user_agent))
            self.store.fail_run(run_id, stage, error)
            raise RuntimeError(error) from None
