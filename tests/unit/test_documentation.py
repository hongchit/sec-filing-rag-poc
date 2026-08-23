from __future__ import annotations

import re
from pathlib import Path

DOCUMENTS = [Path("README.md"), *sorted(Path("docs").glob("*.md")), Path("evaluation/REVIEW.md")]


def test_documentation_local_links_resolve() -> None:
    for document in DOCUMENTS:
        for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "#")):
                continue
            path = (document.parent / target.split("#", 1)[0]).resolve()
            assert path.exists(), f"broken link in {document}: {target}"


def test_current_documentation_excludes_retired_contracts() -> None:
    text = "\n".join(document.read_text(encoding="utf-8") for document in DOCUMENTS)
    forbidden = (
        "prepare_historical_filing",
        "ingest_corpus.yaml",
        "preparation_request",
        "/filings/discover",
        "/filings/prepare",
        "/internal/ingestions",
        "0002_filing_batches.sql",
    )
    assert not any(value in text for value in forbidden)
