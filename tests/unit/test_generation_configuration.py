from pathlib import Path

from sec_filing_rag.generation.service import load_generation_configuration


def test_tracked_generation_prompts_resolve_under_config() -> None:
    config = load_generation_configuration(Path("config/generation.json"))
    expected_ids = {
        "basic-grounded-v1",
        "structured-investor-v1",
        "basic-grounded-v2",
        "structured-investor-v2",
        "guardrailed-10k-v3",
    }

    assert {entry.id for entry in config.prompts} == expected_ids
    assert all(entry.path.parent == Path("config/prompts") for entry in config.prompts)
    for prompt_id in expected_ids:
        template, prompt_sha256 = config.prompt(prompt_id)
        assert all(field in template for field in ("{goal_instruction}", "{question}", "{context}"))
        assert len(prompt_sha256) == 64
