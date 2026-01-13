"""Conflict scan scheduling and triggers.

This module handles periodic scans, triggered scans, and scan history tracking.
"""

import asyncio
import logging
import secrets
from datetime import datetime
from typing import TYPE_CHECKING

from dmm.core.constants import (
    INCREMENTAL_SCAN_ON_COMMIT,
    PERIODIC_SCAN_ENABLED,
    PERIODIC_SCAN_INTERVAL_HOURS,
    SCAN_AT_STARTUP,
)
from dmm.core.exceptions import ScanError
from dmm.models.conflict import DetectionMethod, ScanRequest, ScanResult

if TYPE_CHECKING:
    from dmm.conflicts.detector import ConflictDetector


logger = logging.getLogger(__name__)


class ScanConfig:
    """Configuration for conflict scanning."""

    def __init__(
        self,
        periodic_enabled: bool = PERIODIC_SCAN_ENABLED,
        periodic_interval_hours: int = PERIODIC_SCAN_INTERVAL_HOURS,
        scan_at_startup: bool = SCAN_AT_STARTUP,
        incremental_on_commit: bool = INCREMENTAL_SCAN_ON_COMMIT,
    ) -> None:
        """Initialize scan configuration.
        
        Args:
            periodic_enabled: Whether periodic scans are enabled.
            periodic_interval_hours: Hours between periodic scans.
            scan_at_startup: Whether to scan at startup.
            incremental_on_commit: Whether to scan after commits.
        """
        self.periodic_enabled = periodic_enabled
        self.periodic_interval_hours = periodic_interval_hours
        self.scan_at_startup = scan_at_startup
        self.incremental_on_commit = incremental_on_commit


class ConflictScanner:
    """Schedules and triggers conflict scans.
    
    This class manages:
    - Periodic background scans
    - Triggered scans on commit
    - Manual full scans
    - Scan history tracking
    """

    def __init__(
        self,
        detector: "ConflictDetector",
        config: ScanConfig | None = None,
    ) -> None:
        """Initialize the scanner.
        
        Args:
            detector: The conflict detector to use.
            config: Optional scan configuration.
        """
        self._detector = detector
        self._config = config or ScanConfig()
        self._periodic_task: asyncio.Task | None = None
        self._running = False
        self._last_scan_at: datetime | None = None

    @property
    def is_running(self) -> bool:
        """Check if periodic scanning is running."""
        return self._running

    @property
    def last_scan_at(self) -> datetime | None:
        """Get the time of the last scan."""
        return self._last_scan_at

    async def start(self) -> None:
        """Start the scanner (including periodic scans if enabled)."""
        if self._running:
            logger.warning("Scanner already running")
            return
        
        self._running = True
        logger.info("Conflict scanner started")
        
        if self._config.scan_at_startup:
            logger.info("Running startup scan")
            try:
                await self.trigger_full_scan()
            except Exception as e:
                logger.error(f"Startup scan failed: {e}")
        
        if self._config.periodic_enabled:
            self._periodic_task = asyncio.create_task(self._periodic_scan_loop())
            logger.info(
                f"Periodic scanning enabled (every {self._config.periodic_interval_hours} hours)"
            )

    async def stop(self) -> None:
        """Stop the scanner."""
        self._running = False
        
        if self._periodic_task is not None:
            self._periodic_task.cancel()
            try:
                await self._periodic_task
            except asyncio.CancelledError:
                pass
            self._periodic_task = None
        
        logger.info("Conflict scanner stopped")

    async def trigger_full_scan(
        self,
        methods: list[DetectionMethod] | None = None,
        include_rule_extraction: bool = False,
    ) -> ScanResult:
        """Manually trigger a full conflict scan.
        
        Args:
            methods: Optional list of detection methods to use.
            include_rule_extraction: Whether to include LLM rule extraction.
            
        Returns:
            Scan result.
        """
        request = ScanRequest(
            scan_type="full",
            methods=methods or [
                DetectionMethod.TAG_OVERLAP,
                DetectionMethod.SEMANTIC_SIMILARITY,
                DetectionMethod.SUPERSESSION_CHAIN,
            ],
            include_rule_extraction=include_rule_extraction,
        )
        
        logger.info("Starting full conflict scan")
        result = await self._detector.scan(request)
        self._last_scan_at = result.completed_at
        
        logger.info(
            f"Full scan completed: {result.conflicts_new} new conflicts, "
            f"{result.conflicts_existing} existing ({result.duration_ms}ms)"
        )
        
        return result

    async def trigger_incremental_scan(
        self,
        memory_id: str,
    ) -> ScanResult:
        """Trigger an incremental scan for a specific memory.
        
        Called after a memory is committed to check for new conflicts.
        
        Args:
            memory_id: The memory ID to scan.
            
        Returns:
            Scan result.
        """
        if not self._config.incremental_on_commit:
            return self._empty_scan_result("incremental", memory_id)
        
        logger.debug(f"Starting incremental scan for memory: {memory_id}")
        result = await self._detector.scan_new_memory(memory_id)
        self._last_scan_at = result.completed_at
        
        if result.conflicts_new > 0:
            logger.info(
                f"Incremental scan found {result.conflicts_new} new conflicts "
                f"for memory {memory_id}"
            )
        
        return result

    async def trigger_targeted_scan(
        self,
        memory_ids: list[str],
        methods: list[DetectionMethod] | None = None,
    ) -> ScanResult:
        """Trigger a scan for specific memories.
        
        Args:
            memory_ids: List of memory IDs to scan.
            methods: Optional list of detection methods.
            
        Returns:
            Scan result.
        """
        if not memory_ids:
            return self._empty_scan_result("targeted", None)
        
        request = ScanRequest(
            scan_type="targeted",
            target_memory_id=memory_ids[0],
            methods=methods or [
                DetectionMethod.TAG_OVERLAP,
                DetectionMethod.SEMANTIC_SIMILARITY,
                DetectionMethod.SUPERSESSION_CHAIN,
            ],
        )
        
        logger.debug(f"Starting targeted scan for {len(memory_ids)} memories")
        
        all_candidates = []
        for memory_id in memory_ids:
            request.target_memory_id = memory_id
            candidates = await self._detector._analyze_single_memory(memory_id, request)
            all_candidates.extend(candidates)
        
        if all_candidates:
            memory_map = self._detector._get_memory_map()
            scan_id = self._generate_scan_id()
            merge_result = self._detector._merger.merge_and_persist(
                all_candidates, memory_map, scan_id
            )
            
            result = ScanResult(
                scan_id=scan_id,
                scan_type="targeted",
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                duration_ms=0,
                memories_scanned=len(memory_ids),
                methods_used=[m.value for m in request.methods],
                conflicts_detected=merge_result.new_conflicts + merge_result.existing_conflicts,
                conflicts_new=merge_result.new_conflicts,
                conflicts_existing=merge_result.existing_conflicts,
            )
        else:
            result = self._empty_scan_result("targeted", None)
            result.memories_scanned = len(memory_ids)
        
        self._last_scan_at = result.completed_at
        return result

    def trigger_full_scan_sync(
        self,
        methods: list[DetectionMethod] | None = None,
        include_rule_extraction: bool = False,
    ) -> ScanResult:
        """Synchronous wrapper for full scan.
        
        Args:
            methods: Optional list of detection methods.
            include_rule_extraction: Whether to include LLM rule extraction.
            
        Returns:
            Scan result.
        """
        return asyncio.get_event_loop().run_until_complete(
            self.trigger_full_scan(methods, include_rule_extraction)
        )

    def trigger_incremental_scan_sync(
        self,
        memory_id: str,
    ) -> ScanResult:
        """Synchronous wrapper for incremental scan.
        
        Args:
            memory_id: The memory ID to scan.
            
        Returns:
            Scan result.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self.trigger_incremental_scan(memory_id),
                    loop,
                )
                return future.result(timeout=30)
            else:
                return loop.run_until_complete(
                    self.trigger_incremental_scan(memory_id)
                )
        except RuntimeError:
            return asyncio.run(self.trigger_incremental_scan(memory_id))

    async def _periodic_scan_loop(self) -> None:
        """Background loop for periodic scans."""
        interval_seconds = self._config.periodic_interval_hours * 3600
        
        while self._running:
            try:
                await asyncio.sleep(interval_seconds)
                
                if not self._running:
                    break
                
                logger.info("Starting periodic conflict scan")
                await self.trigger_full_scan()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Periodic scan failed: {e}")
                await asyncio.sleep(300)

    def get_scan_history(self, limit: int = 20) -> list[dict]:
        """Get recent scan history.
        
        Args:
            limit: Maximum number of scans to return.
            
        Returns:
            List of scan records.
        """
        return self._detector._conflict_store.get_scan_history(limit)

    def _empty_scan_result(
        self,
        scan_type: str,
        target_id: str | None,
    ) -> ScanResult:
        """Create an empty scan result."""
        now = datetime.utcnow()
        return ScanResult(
            scan_id=self._generate_scan_id(),
            scan_type=scan_type,
            started_at=now,
            completed_at=now,
            duration_ms=0,
            memories_scanned=0,
            methods_used=[],
            conflicts_detected=0,
            conflicts_new=0,
            conflicts_existing=0,
        )

    def _generate_scan_id(self) -> str:
        """Generate a unique scan ID."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        random_suffix = secrets.token_hex(4)
        return f"scan_{timestamp}_{random_suffix}"

    def get_config(self) -> dict:
        """Get scanner configuration."""
        return {
            "periodic_enabled": self._config.periodic_enabled,
            "periodic_interval_hours": self._config.periodic_interval_hours,
            "scan_at_startup": self._config.scan_at_startup,
            "incremental_on_commit": self._config.incremental_on_commit,
            "is_running": self._running,
            "last_scan_at": self._last_scan_at.isoformat() if self._last_scan_at else None,
        }
