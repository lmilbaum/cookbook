"""Run a single bounded scraper process while the HTTP server stays responsive."""
from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

from .import_reasons import REASONS

# The job prints one line with this prefix when the scan is incomplete. Its text is
# a fixed message from our own code, so it is safe to show; other output is not.
REASON_PREFIX = "IMPORT-REASON: "
PROGRESS_PREFIX = "IMPORT-PROGRESS: "
RESULT_PREFIX = "IMPORT-RESULT: "
_RESULT_RE = re.compile(r"IMPORT-RESULT: ([A-Za-z0-9_-]{1,64})\n?\Z")
_PROGRESS_RE = re.compile(r"IMPORT-PROGRESS: ([0-9]{1,10})\n?\Z")
_LOG_TAIL = 4000
_JOB_TIMEOUT = 1800


def run_scraper(root: Path, progress: Callable[[int], None] | None = None) -> tuple[int, str, str]:
    """Stream safe numeric progress, retaining a bounded diagnostic tail."""
    with subprocess.Popen(
        [sys.executable, "-m", "cookbook.post_import_job", "--directory", str(root)],
        cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, errors="replace",
        start_new_session=True,
    ) as process:
        errors = ""
        reason = ""
        imported_recipe_id = ""

        def drain() -> None:
            nonlocal errors, reason, imported_recipe_id
            assert process.stderr is not None
            # Bound both retained diagnostics and individual reads even for noisy workers.
            continuation = False
            for line in iter(lambda: process.stderr.readline(_LOG_TAIL), ""):
                match = None if continuation else _PROGRESS_RE.fullmatch(line)
                result = None if continuation else _RESULT_RE.fullmatch(line)
                continuation = not line.endswith("\n") and len(line) == _LOG_TAIL
                if match is not None:
                    if progress is not None:
                        progress(int(match[1]))
                elif result is not None:
                    imported_recipe_id = result[1]
                else:
                    errors = (errors + line)[-_LOG_TAIL:]
                    if line.startswith(REASON_PREFIX) and _reason_code(line):
                        reason = line

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        deadline = time.monotonic() + _JOB_TIMEOUT
        try:
            process.wait(timeout=_JOB_TIMEOUT)
            reader.join(timeout=max(0, deadline - time.monotonic()))
            if reader.is_alive():
                raise subprocess.TimeoutExpired(process.args, _JOB_TIMEOUT)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            reader.join()
            raise
        return process.returncode, (errors + reason if reason and reason not in errors else errors), imported_recipe_id


def _reason_code(errors: str) -> str:
    """The job's own explanation of an incomplete scan, if it gave a known one."""
    for line in reversed(errors.splitlines()):
        if line.startswith(REASON_PREFIX):
            code = line.removeprefix(REASON_PREFIX).strip()
            return code if code in REASONS else ""
    return ""


def _status(status: str, code: str, message: str, reason_code: str = "") -> dict[str, str | int]:
    """A status for the page: ``code`` and ``reason_code`` let it show a translation,
    ``message`` is the English text for other API clients."""
    return {"status": status, "code": code, "message": message, "reason_code": reason_code, "reviewed_posts": 0, "imported_recipe_id": ""}


class ImportService:
    """Share import progress across requests and browser tabs."""

    def __init__(self, root: Path, refresh: Callable[[], None]) -> None:
        self.root = root
        self.refresh = refresh
        self._lock = threading.Lock()
        self._status = _status("idle", "", "")

    def status(self) -> dict[str, str | int]:
        with self._lock:
            return dict(self._status)

    def start(self) -> bool:
        with self._lock:
            if self._status["status"] == "running":
                return False
            self._status = _status(
                "running", "running",
                "Finding the oldest post not yet imported. This may take several minutes.",
            )
            threading.Thread(target=self._run, daemon=True).start()
            return True

    def _progress(self, count: int) -> None:
        with self._lock:
            self._status["reviewed_posts"] = max(int(self._status["reviewed_posts"]), count)

    def _run(self) -> None:
        try:
            code, errors, imported_recipe_id = run_scraper(self.root, self._progress)
            if code not in (0, 3):  # 3 means "nothing new", not a failure
                # Operator log only: the scraper's raw output may contain private details.
                print(f"Import job exited with code {code}:\n{errors[-_LOG_TAIL:]}", file=sys.stderr, flush=True)
            if code == 0:
                self.refresh()
                status = _status("succeeded", "succeeded", "Post imported. Refreshing the cookbook…")
                status["imported_recipe_id"] = imported_recipe_id
            elif code == 4:
                reason_code = _reason_code(errors)
                detail = f" Reason: {REASONS[reason_code]}" if reason_code else ""
                status = _status(
                    "failed", "incomplete",
                    f"Could not finish scanning for the oldest post. No post was imported.{detail} Please try again later.",
                    reason_code,
                )
            elif code == 3:
                status = _status("empty", "empty", "No unseen posts were found at the end of the loaded feed.")
            else:
                status = _status(
                    "failed", "failed",
                    "Import failed. Check Instagram credentials and session access, then try again.",
                )
        except subprocess.TimeoutExpired:
            status = _status("failed", "timeout", "Import timed out. Please try again later.")
        except Exception:  # noqa: BLE001 - the worker thread must always record a final status.
            status = _status(
                "failed", "error", "Unable to finish the import. Refresh the cookbook before retrying."
            )
        with self._lock:
            status["reviewed_posts"] = self._status["reviewed_posts"]
            self._status = status
