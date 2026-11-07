"""In-process background job runner with persistent state.

Competition progress is persisted cell-by-cell in SQLite, so the API can serve
live status while jobs run. On startup, anything left `running`/`queued` from a
previous process is explicitly marked `interrupted` and can be resumed.
"""
from __future__ import annotations

import asyncio
import logging

from app.agents import evaluation_agent, extraction_agent
from app.core.config import Settings
from app.core.errors import ConflictError
from app.core.utils import utcnow
from app.db.repository import Repository
from app.services.groq_client import LLMClient

log = logging.getLogger("n2.jobs")


class JobRunner:
    def __init__(self, repo: Repository, client: LLMClient, settings: Settings):
        self.repo = repo
        self.client = client
        self.settings = settings
        self.tasks: dict[str, asyncio.Task] = {}

    def is_running(self, competition_id: str) -> bool:
        t = self.tasks.get(competition_id)
        return t is not None and not t.done()

    def start(self, competition_id: str, *, only_unfinished: bool = False) -> asyncio.Task:
        if self.is_running(competition_id):
            raise ConflictError("Competition is already running")
        task = asyncio.create_task(self._run(competition_id, only_unfinished), name=f"competition:{competition_id}")
        self.tasks[competition_id] = task
        task.add_done_callback(lambda _t: self.tasks.pop(competition_id, None))
        return task

    async def _run(self, competition_id: str, only_unfinished: bool) -> None:
        await extraction_agent.run_competition(self.repo, self.client, self.settings, competition_id,
                                               only_unfinished=only_unfinished)
        try:
            evaluation_agent.run_evaluation(self.repo, competition_id)
        except Exception:  # noqa: BLE001
            log.exception("automatic evaluation failed for %s", competition_id)

    def recover_on_startup(self) -> int:
        recovered = 0
        for status in ("running", "queued"):
            for comp in self.repo.list("competitions", status=status, limit=1000):
                self.repo.update("competitions", comp["id"], {
                    "status": "interrupted", "finished_at": utcnow(),
                    "error": "The server stopped before this competition finished. Use Resume to run the remaining cells.",
                })
                for ex in self.repo.list("executions", parent_id=comp["id"], limit=50):
                    if ex["status"] == "running":
                        self.repo.update("executions", ex["id"], {"status": "interrupted",
                                                                  "error": "Interrupted by server restart"})
                recovered += 1
        if recovered:
            log.warning("marked %d unfinished competition(s) as interrupted", recovered)
        return recovered

    async def shutdown(self) -> None:
        tasks = [t for t in self.tasks.values() if not t.done()]
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
