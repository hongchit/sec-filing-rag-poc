from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

DOCUMENTS = [
    Path("README.md"),
    *sorted(Path("docs").glob("**/*.md")),
    Path("evaluation/REVIEW.md"),
]


def markdown_anchors(text: str) -> set[str]:
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    for heading in re.findall(r"^#{1,6}\s+(.+?)\s*$", text, flags=re.MULTILINE):
        slug = re.sub(r"[^\w\- ]", "", heading.lower()).strip().replace(" ", "-")
        count = counts.get(slug, 0)
        anchors.add(slug if count == 0 else f"{slug}-{count}")
        counts[slug] = count + 1
    return anchors


REQUIRED_DOCUMENTS = {
    Path("docs/README.md"),
    Path("docs/api.md"),
    Path("docs/architecture.md"),
    Path("docs/configuration.md"),
    Path("docs/commands.md"),
    Path("docs/corpus-reader.md"),
    Path("docs/database-schema.md"),
    Path("docs/evaluation.md"),
    Path("docs/getting-started.md"),
    Path("docs/local-development.md"),
    Path("docs/operations.md"),
    Path("docs/orchestration.md"),
    Path("docs/pipeline.md"),
    Path("docs/research.md"),
    Path("docs/retrieval-evaluation-workflow.md"),
    Path("docs/rag-evaluation-workflow.md"),
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
            if target.startswith(("http://", "https://")):
                continue
            path_target, _, fragment = target.partition("#")
            local_target = unquote(path_target.strip("<>"))
            path = (
                (document.parent / local_target).resolve() if local_target else document.resolve()
            )
            assert path.exists(), f"broken link in {document}: {target}"
            if fragment and path.suffix == ".md":
                assert unquote(fragment) in markdown_anchors(path.read_text(encoding="utf-8")), (
                    f"broken section link in {document}: {target}"
                )


def test_all_mermaid_diagrams_have_titles() -> None:
    for document in DOCUMENTS:
        text = document.read_text(encoding="utf-8")
        for diagram in re.findall(r"```mermaid\n(.*?)\n```", text, flags=re.DOTALL):
            assert re.match(r"---\ntitle: .+\n---\n", diagram), (
                f"untitled Mermaid diagram in {document}"
            )


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


def test_getting_started_covers_the_complete_project_journey() -> None:
    text = Path("docs/getting-started.md").read_text(encoding="utf-8").lower()
    stages = (
        "## 1. prerequisites",
        "## 3. configure the environment",
        "## 4. start the application and import the workflow",
        "## 5. sign in and prepare the first corpora",
        "## 7. full path: prepare evaluation corpora and ground truth",
        "## 8. promote an accepted retrieval result",
        "## 9. evaluate and promote the complete rag path",
        "## 10. verify the completed system",
    )
    positions = [text.index(stage) for stage in stages]
    assert positions == sorted(positions)
    assert "curl " not in text
