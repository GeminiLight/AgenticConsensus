from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from system.services.database import Database
from system.services.llm import EvidenceSummarizer, LLMConfig
from system.services.review_service import ReviewService


@dataclass
class AppContainer:
    database: Database
    reviews: ReviewService
    summarizer: EvidenceSummarizer

    @classmethod
    def build(cls, database_path: str | Path) -> "AppContainer":
        database = Database(database_path)
        return cls(database, ReviewService(database), EvidenceSummarizer(LLMConfig.from_env()))
