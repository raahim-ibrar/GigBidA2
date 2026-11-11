from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parent


class Budgets(BaseModel):
    model_config = ConfigDict(extra="ignore")
    max_steps: int = Field(default=40, ge=5, le=100)
    max_tokens_per_thread: int = Field(default=16000, ge=1000, le=100000)
    max_critic_revisions: int = Field(default=2, ge=0, le=2)


class AgentConfig:
    def __init__(self, path: Path | None = None):
        self.data = yaml.safe_load((path or ROOT / "config.yaml").read_text(encoding="utf-8"))
        self.profile = self.data["profiles"][self.data["active_profile"]]
        if self.profile.get("provider") != "ollama":
            raise ValueError("Configure the supported local open profile before running agents")
        self.budgets = Budgets.model_validate(self.data["budgets"])
        self.models = self.profile["models"]
        self.fallback = self.profile.get("fallback_model")
        self.timeout = self.profile.get("timeout_seconds", 90)
        self.context_size = self.profile.get("context_size", 8192)
        self.output_tokens = self.profile.get("output_tokens", 1500)
        self.retrieval = self.data["retrieval"]
        self.policy = self.data["policy"]
        self.prompts = {
            role: (ROOT / "prompts" / f"{role}.md").read_text(encoding="utf-8")
            for role in self.models
        }

    def prompt(self, role: str) -> str:
        if role not in self.models:
            raise ValueError("Unknown agent role")
        return self.prompts[role]
