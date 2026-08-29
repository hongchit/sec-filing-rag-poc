from __future__ import annotations

import re
from pathlib import Path

DOCUMENTS = [
    Path("README.md"),
    *sorted(Path("docs").glob("**/*.md")),
    Path("evaluation/REVIEW.md"),
]

REQUIRED_DOCUMENTS = {
    Path("docs/README.md"),
    Path("docs/api.md"),
    Path("docs/architecture.md"),
    Path("docs/configuration.md"),
    Path("docs/corpus-reader.md"),
    Path("docs/database-schema.md"),
    Path("docs/evaluation.md"),
    Path("docs/local-development.md"),
    Path("docs/operations.md"),
    Path("docs/orchestration.md"),
    Path("docs/pipeline.md"),
    Path("docs/research.md"),
    Path("docs/testing.md"),
    Path("docs/troubleshooting.md"),
    Path("docs/decisions/README.md"),
}

RETIRED_DOCUMENTS = {
    Path("docs/api-orchestration-design.md"),
    Path("docs/corpus-learnings.md"),
    Path("docs/corpus-pipeline.md"),
}


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


def test_documentation_has_clear_current_structure() -> None:
    assert all(path.is_file() for path in REQUIRED_DOCUMENTS)
    assert not any(path.exists() for path in RETIRED_DOCUMENTS)


def test_current_documentation_does_not_depend_on_planning_files() -> None:
    text = "\n".join(document.read_text(encoding="utf-8") for document in DOCUMENTS)
    assert "capstone-mvp-" not in text
    assert "corpus-reader-ux-plan.md" not in text
