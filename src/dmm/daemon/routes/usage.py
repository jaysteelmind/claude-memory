"""Usage API endpoints for the daemon."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from dmm.writeback.usage import UsageTracker

router = APIRouter(prefix="/usage", tags=["usage"])


class MemoryStatsResponse(BaseModel):
    """Response for memory usage stats."""
    
    memory_id: str
    memory_path: str
    total_retrievals: int
    baseline_retrievals: int
    query_retrievals: int
    first_used: str | None
    last_used: str | None
    co_occurred_with: dict[str, int]


class MemoriesStatsResponse(BaseModel):
    """Response for multiple memory stats."""
    
    memories: list[dict[str, Any]]
    total: int


class UsageStatsResponse(BaseModel):
    """Response for aggregated usage stats."""
    
    period_start: str
    period_end: str
    total_queries: int
    avg_query_time_ms: float
    avg_tokens_per_query: float
    total_memories_retrieved: int
    unique_memories_retrieved: int
    most_retrieved: list[tuple[str, int]]
    least_retrieved: list[tuple[str, int]]


class HealthReportResponse(BaseModel):
    """Response for health report."""
    
    generated_at: str
    stale_memories: list[dict[str, Any]]
    stale_threshold_days: int
    hot_memories: list[dict[str, Any]]
    hot_threshold_retrievals: int
    deprecation_candidates: list[dict[str, Any]]


def get_tracker(base_path: Path | None = None) -> UsageTracker:
    """Get usage tracker."""
    base = base_path or Path.cwd()
    tracker = UsageTracker(base)
    tracker.initialize()
    return tracker


@router.get("/memory/{memory_id}", response_model=MemoryStatsResponse)
async def get_memory_stats(memory_id: str) -> MemoryStatsResponse:
    """Get usage stats for a specific memory."""
    tracker = get_tracker()
    
    record = tracker.get_memory_usage(memory_id)
    if not record:
        raise HTTPException(
            status_code=404,
            detail=f"No usage data for memory: {memory_id}",
        )
    
    return MemoryStatsResponse(
        memory_id=record.memory_id,
        memory_path=record.memory_path,
        total_retrievals=record.total_retrievals,
        baseline_retrievals=record.baseline_retrievals,
        query_retrievals=record.query_retrievals,
        first_used=record.first_used.isoformat() if record.first_used else None,
        last_used=record.last_used.isoformat() if record.last_used else None,
        co_occurred_with=record.co_occurred_with,
    )


@router.get("/memories", response_model=MemoriesStatsResponse)
async def get_memories_stats(
    sort_by: str = "total_retrievals",
    order: str = "desc",
    limit: int = 20,
) -> MemoriesStatsResponse:
    """Get usage stats for multiple memories."""
    tracker = get_tracker()
    
    if order == "desc":
        records = tracker.get_most_retrieved(limit)
    else:
        records = tracker.get_least_retrieved(limit)
    
    return MemoriesStatsResponse(
        memories=[r.to_dict() for r in records],
        total=len(records),
    )


@router.get("/stats", response_model=UsageStatsResponse)
async def get_usage_stats(days: int = 30) -> UsageStatsResponse:
    """Get aggregated usage statistics."""
    tracker = get_tracker()
    
    stats = tracker.get_stats(days)
    
    return UsageStatsResponse(
        period_start=stats.period_start.isoformat(),
        period_end=stats.period_end.isoformat(),
        total_queries=stats.total_queries,
        avg_query_time_ms=stats.avg_query_time_ms,
        avg_tokens_per_query=stats.avg_tokens_per_query,
        total_memories_retrieved=stats.total_memories_retrieved,
        unique_memories_retrieved=stats.unique_memories_retrieved,
        most_retrieved=stats.most_retrieved,
        least_retrieved=stats.least_retrieved,
    )


@router.get("/top", response_model=MemoriesStatsResponse)
async def get_top_memories(limit: int = 10) -> MemoriesStatsResponse:
    """Get most frequently retrieved memories."""
    tracker = get_tracker()
    
    records = tracker.get_most_retrieved(limit)
    
    return MemoriesStatsResponse(
        memories=[r.to_dict() for r in records],
        total=len(records),
    )


@router.get("/stale", response_model=MemoriesStatsResponse)
async def get_stale_memories(
    days: int = 30,
    limit: int = 20,
) -> MemoriesStatsResponse:
    """Get memories that haven't been retrieved recently."""
    tracker = get_tracker()
    
    records = tracker.get_stale_memories(days, limit)
    
    return MemoriesStatsResponse(
        memories=[r.to_dict() for r in records],
        total=len(records),
    )


@router.get("/health", response_model=HealthReportResponse)
async def get_health_report(
    stale_days: int = 30,
    hot_count: int = 10,
) -> HealthReportResponse:
    """Generate a health report for memory usage."""
    tracker = get_tracker()
    
    report = tracker.generate_health_report(stale_days, hot_count)
    
    return HealthReportResponse(
        generated_at=report.generated_at.isoformat(),
        stale_memories=report.stale_memories,
        stale_threshold_days=report.stale_threshold_days,
        hot_memories=report.hot_memories,
        hot_threshold_retrievals=report.hot_threshold_retrievals,
        deprecation_candidates=report.deprecation_candidates,
    )


@router.delete("/logs")
async def cleanup_logs(days: int = 90) -> dict[str, Any]:
    """Clean up old query logs."""
    tracker = get_tracker()
    
    deleted = tracker.clear_old_logs(days)
    
    return {
        "success": True,
        "deleted": deleted,
        "message": f"Deleted {deleted} log entries older than {days} days",
    }
