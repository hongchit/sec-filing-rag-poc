from sec_filing_rag.repositories.corpus_reader import highlight_for, paragraphs


def test_paragraphs_preserve_nonempty_lines_and_exact_offsets() -> None:
    text = "Alpha\n\nβeta 🙂\r\nx\nApple Inc. | 2025 Form 10-K | 7"

    result = paragraphs(text)

    assert [(row["index"], row["start"], row["end"], row["text"]) for row in result] == [
        (1, 0, 5, "Alpha"),
        (2, 7, 13, "βeta 🙂"),
        (3, 15, 16, "x"),
        (4, 17, len(text), "Apple Inc. | 2025 Form 10-K | 7"),
    ]
    assert [row["is_furniture"] for row in result] == [False, False, False, True]


def test_highlight_slices_single_and_multiple_paragraphs_at_boundaries() -> None:
    derived = paragraphs("first line\nsecond line\nthird")
    chunk = {
        "id": "a" * 64,
        "citation_handle": "citation",
        "source_start": 104,
        "source_end": 118,
    }

    result = highlight_for(chunk, 100, derived)

    assert result is not None
    assert result["char_start"] == 4 and result["char_end"] == 18
    assert result["paragraph_start"] == 1 and result["paragraph_end"] == 2
    assert result["ranges"] == [
        {"paragraph_index": 1, "start": 4, "end": 10},
        {"paragraph_index": 2, "start": 0, "end": 7},
    ]
    # A chunk ending exactly at a paragraph boundary must not touch the next paragraph.
    chunk["source_start"], chunk["source_end"] = 100, 110
    assert highlight_for(chunk, 100, derived)["ranges"] == [  # type: ignore[index]
        {"paragraph_index": 1, "start": 0, "end": 10}
    ]


def test_invalid_or_non_text_chunk_spans_do_not_resolve() -> None:
    derived = paragraphs("one\ntwo")
    base = {"id": "b" * 64, "citation_handle": "citation"}
    assert highlight_for({**base, "source_start": 9, "source_end": 10}, 10, derived) is None
    assert highlight_for({**base, "source_start": 20, "source_end": 22}, 10, derived) is None
