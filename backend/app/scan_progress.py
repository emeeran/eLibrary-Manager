"""In-memory scan progress tracking for SSE streaming."""

import time
from dataclasses import dataclass, field


@dataclass
class ScanProgress:
    """Progress state for a single scan operation."""

    scan_id: str
    status: str = "running"  # running | completed | failed
    total_found: int = 0
    processed: int = 0
    imported: int = 0
    skipped: int = 0
    errors: int = 0
    current_file: str = ""
    started_at: float = field(default_factory=time.time)
    message: str = ""


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
        """Update progress fields."""
        progress = self._scans.get(scan_id)
        if progress:
            for k, v in kwargs.items():
                setattr(progress, k, v)
        return progress

    def to_dict(self, progress: ScanProgress) -> dict:
        """Serialize progress to dict for SSE events."""
        return {
            "scan_id": progress.scan_id,
            "status": progress.status,
            "total_found": progress.total_found,
            "processed": progress.processed,
            "imported": progress.imported,
            "skipped": progress.skipped,
            "errors": progress.errors,
            "current_file": progress.current_file,
            "message": progress.message,
            "elapsed": round(time.time() - progress.started_at, 1),
        }


# Module-level singleton
scan_store = ScanProgressStore()
