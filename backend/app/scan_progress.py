"""In-memory scan progress tracking for SSE streaming."""

import time
from dataclasses import dataclass, field


class ScanCancelledError(Exception):
    """Raised inside a scan loop when the user requested cancellation.

    The service layer raises this from the cooperative cancel check points;
    the route runner catches it and marks the scan ``cancelled``.
    """


@dataclass
class ScanProgress:
    """Progress state for a single scan operation.

    ``phase`` gives the frontend a human label for what the scan is currently
    doing (discovering / importing / checking the NAS / committing / done) so
    the UI can explain a slow step instead of looking frozen. ``rate`` and
    ``eta`` are derived each time the store is updated.

    ``cancel_requested`` is a cooperative flag: long-running loops poll
    :meth:`is_cancelled` between files and raise :class:`ScanCancelled`, so a
    scan stops promptly without leaving the DB half-committed (each batch is
    committed before re-checking).
    """

    scan_id: str
    status: str = "running"  # running | completed | failed | cancelled
    phase: str = (
        "discovering"  # discovering | importing | checking_nas | scanning_nas | committing | done
    )
    total_found: int = 0
    processed: int = 0
    imported: int = 0
    skipped: int = 0
    errors: int = 0
    current_file: str = ""
    started_at: float = field(default_factory=time.time)
    message: str = ""
    rate: float = 0.0  # files per second (processed / elapsed)
    eta: float = 0.0  # estimated seconds remaining
    cancel_requested: bool = False

    def recompute(self) -> None:
        """Derive rate and ETA from the current counters and elapsed time."""
        elapsed = max(time.time() - self.started_at, 0.001)
        self.rate = round(self.processed / elapsed, 1)
        if self.total_found > self.processed and self.rate > 0:
            self.eta = round((self.total_found - self.processed) / self.rate, 0)
        else:
            self.eta = 0.0


class ScanProgressStore:
    """In-memory store for scan progress. Module-level singleton."""

    def __init__(self) -> None:
        self._scans: dict[str, ScanProgress] = {}

    def create(self, scan_id: str) -> ScanProgress:
        """Create a new progress tracker."""
        progress = ScanProgress(scan_id=scan_id)
        self._scans[scan_id] = progress
        return progress

    def get(self, scan_id: str) -> ScanProgress | None:
        """Get progress by scan ID."""
        return self._scans.get(scan_id)

    def update(self, scan_id: str, **kwargs: object) -> ScanProgress | None:
        """Update progress fields and recompute derived metrics."""
        progress = self._scans.get(scan_id)
        if progress:
            for k, v in kwargs.items():
                setattr(progress, k, v)
            progress.recompute()
        return progress

    def request_cancel(self, scan_id: str) -> bool:
        """Cooperatively request cancellation of a running scan.

        Returns True if the flag was set (the scan was running and will abort
        at its next check point), False if the scan was already finished.
        """
        progress = self._scans.get(scan_id)
        if progress and progress.status == "running":
            progress.cancel_requested = True
            return True
        return False

    @staticmethod
    def is_cancelled(scan_id: str | None) -> bool:
        """Check whether cancellation was requested for ``scan_id``.

        Safe to call with ``None`` (returns False). Used by the service-layer
        scan loops as a cooperative abort check point.
        """
        if not scan_id:
            return False
        progress = scan_store._scans.get(scan_id)  # noqa: SLF001
        return bool(progress and progress.cancel_requested)

    def to_dict(self, progress: ScanProgress) -> dict:
        """Serialize progress to dict for SSE events."""
        return {
            "scan_id": progress.scan_id,
            "status": progress.status,
            "phase": progress.phase,
            "total_found": progress.total_found,
            "processed": progress.processed,
            "imported": progress.imported,
            "skipped": progress.skipped,
            "errors": progress.errors,
            "current_file": progress.current_file,
            "message": progress.message,
            "rate": progress.rate,
            "eta": progress.eta,
            "elapsed": round(time.time() - progress.started_at, 1),
            "cancel_requested": progress.cancel_requested,
        }


# Module-level singleton
scan_store = ScanProgressStore()
