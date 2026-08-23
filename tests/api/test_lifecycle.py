from __future__ import annotations

import asyncio
from pathlib import Path
from typing import cast

from sec_filing_rag.core.config import Settings
from sec_filing_rag.core.resources import AppResources
from sec_filing_rag.main import create_app


class RecordingResources:
    def __init__(self) -> None:
        self.closed = 0

    def close(self) -> None:
        self.closed += 1


def test_lifespan_creates_and_closes_resources_once(tmp_path: Path) -> None:
    company_file = tmp_path / "companies.yaml"
    company_file.write_text("companies: []\n")
    config = Settings(
        ingestion_api_token="0123456789abcdef",
        edgar_identity="Test test@example.com",
        openai_api_key="key",
        company_config_path=company_file,
    )
    resources = RecordingResources()
    calls = 0

    def factory(selected: Settings) -> AppResources:
        nonlocal calls
        calls += 1
        assert selected is config
        return cast(AppResources, resources)

    app = create_app(config, resource_factory=factory)

    async def exercise() -> None:
        async with app.router.lifespan_context(app):
            assert app.state.resources is resources
            assert calls == 1
            assert resources.closed == 0

    asyncio.run(exercise())
    assert resources.closed == 1
