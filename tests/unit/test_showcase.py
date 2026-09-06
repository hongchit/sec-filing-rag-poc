from __future__ import annotations

import json

from sec_filing_rag.showcase import load_showcase


def example(identifier: str) -> dict[str, object]:
    return {
        "id": identifier,
        "question": "What was reported?",
        "answer": "The filing reported a result.",
        "ticker": "MSFT",
        "filing_period": "Fiscal year 2024",
        "accession": "0000950170-24-087843",
        "items": ["7"],
        "citations": ["0000950170-24-087843:item-7:0000"],
        "goal": "management_analysis",
    }


def test_showcase_preserves_order_and_skips_invalid_entries(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "showcase.json"
    path.write_text(
        json.dumps(
            {
                "version": "showcase-v1",
                "examples": [
                    example("second"),
                    {**example("bad"), "ticker": "msft"},
                    example("first"),
                ],
            }
        ),
        encoding="utf-8",
    )

    result = load_showcase(path)

    assert [value.id for value in result.examples] == ["second", "first"]


def test_showcase_disables_missing_malformed_and_empty_configuration(tmp_path) -> None:  # type: ignore[no-untyped-def]
    missing = load_showcase(tmp_path / "missing.json")
    malformed_path = tmp_path / "malformed.json"
    malformed_path.write_text("not json", encoding="utf-8")
    malformed = load_showcase(malformed_path)
    empty_path = tmp_path / "empty.json"
    empty_path.write_text('{"version":"showcase-v1","examples":[]}', encoding="utf-8")
    empty = load_showcase(empty_path)

    assert missing.examples == []
    assert malformed.examples == []
    assert empty.examples == []


def test_showcase_skips_duplicate_ids(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "showcase.json"
    path.write_text(
        json.dumps({"version": "showcase-v1", "examples": [example("same"), example("same")]}),
        encoding="utf-8",
    )

    assert [value.id for value in load_showcase(path).examples] == ["same"]
