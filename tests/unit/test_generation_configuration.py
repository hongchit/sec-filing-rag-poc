from pathlib import Path

from sec_filing_rag.generation.service import load_generation_configuration


def test_tracked_generation_prompts_resolve_under_config() -> None:
    config = load_generation_configuration(Path("config/generation.json"))
    expected_ids = {
        "basic-grounded-v1",
        "basic-grounded-v2",
        "guardrailed-10k-v3",
    }

    assert {entry.id for entry in config.prompts} == expected_ids
    assert all(entry.path.parent == Path("config/prompts") for entry in config.prompts)
    for prompt_id in expected_ids:
        template, prompt_sha256 = config.prompt(prompt_id)
        assert all(field in template for field in ("{goal_instruction}", "{question}", "{context}"))
        assert "in the citations field only" in template
        assert len(prompt_sha256) == 64


def test_generation_prompts_resolve_from_relocated_runtime(tmp_path: Path) -> None:
    import shutil

    original = load_generation_configuration(Path("config/generation.json"))
    runtime = tmp_path / "runtime"
    shutil.copytree(Path("config"), runtime / "config")
    relocated = load_generation_configuration(runtime / "config/generation.json")
    assert relocated.sha256() == original.sha256()
    for entry in relocated.prompts:
        expected = f"runtime prompt: {entry.id}"
        (runtime / entry.path).write_text(expected)
        assert relocated.prompt(entry.id)[0] == expected
