from __future__ import annotations

import argparse
from pathlib import Path

from ..evaluation.generation import (
    artifact_markdown,
    load_generation_artifact,
    select_generation_winner,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate and render a completed live generation-evaluation artifact."
    )
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args()
    artifact = load_generation_artifact(args.artifact)
    if len(artifact.cases) != 96:
        raise SystemExit("generation evaluation must contain exactly 96 reviewed cases")
    try:
        winner = select_generation_winner(artifact.prompts)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    if winner.prompt_id != artifact.selected_prompt_id:
        raise SystemExit("selected prompt does not match the deterministic winner")
    if args.markdown:
        args.markdown.write_text(artifact_markdown(artifact), encoding="utf-8")


if __name__ == "__main__":
    main()
