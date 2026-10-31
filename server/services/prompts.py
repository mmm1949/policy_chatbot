import re
from pathlib import Path

from langchain_core.prompts import PromptTemplate


class PromptManager:
    def __init__(
        self,
        version: str = "v1",
        prompt_directory: Path | None = None,
    ) -> None:
        if not re.fullmatch(r"v[0-9]+", version):
            raise ValueError(f"Invalid prompt version: {version}")
        self.version = version
        self.prompt_directory = prompt_directory or (
            Path(__file__).resolve().parents[1] / "prompts" / version
        )
        self._prompts = self._load_prompts()

    def _load_prompts(self) -> dict[str, PromptTemplate]:
        prompt_files = {
            "classifier": "classifier.txt",
            "follow_up_rewrite": "follow_up_rewrite.txt",
            "query_refinement": "query_refinement.txt",
            "answer": "answer.txt",
            "grounding": "grounding.txt",
            "social_response": "social_response.txt",
        }
        prompts = {}
        for name, filename in prompt_files.items():
            path = self.prompt_directory / filename
            if not path.is_file():
                raise FileNotFoundError(f"Required prompt file is missing: {path}")
            prompts[name] = PromptTemplate.from_template(
                path.read_text(encoding="utf-8")
            )
        return prompts

    def render(self, name: str, **variables: str) -> str:
        try:
            prompt = self._prompts[name]
        except KeyError as exc:
            raise KeyError(f"Unknown prompt name: {name}") from exc
        return prompt.format(**variables)
