"""FastAPI daemon server for DMM."""

import asyncio
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from dmm.core.config import DMMConfig
from dmm.core.constants import (
    DEFAULT_BASELINE_BUDGET,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_TOTAL_BUDGET,
    Scope,
    get_memory_root,
)
from dmm.daemon.health import HealthChecker
from dmm.daemon.routes.review import router as review_router
from dmm.daemon.routes.usage import router as usage_router
from dmm.daemon.routes.write import router as write_router
from dmm.indexer.indexer import Indexer
from dmm.retrieval.assembler import ContextAssembler
from dmm.retrieval.baseline import BaselineManager
from dmm.retrieval.router import RetrievalConfig, RetrievalRouter


# Pydantic models for API
class QueryRequestModel(BaseModel):
    """API request model for query endpoint."""

    query: str = Field(..., min_length=1, description="Search query")
    budget: int = Field(DEFAULT_TOTAL_BUDGET, ge=100, le=10000)
    baseline_budget: int = Field(DEFAULT_BASELINE_BUDGET, ge=0, le=2000)
    scope_filter: str | None = Field(None, description="Filter by scope")
    exclude_ephemeral: bool = Field(False)
    include_deprecated: bool = Field(False)
    verbose: bool = Field(False)


class ReindexRequestModel(BaseModel):
    """API request model for reindex endpoint."""

    full: bool = Field(True, description="Perform full reindex")


# Global state
class DaemonState:
    """Global daemon state container."""

    def __init__(self) -> None:
        self.config: DMMConfig | None = None
        self.indexer: Indexer | None = None
        self.baseline_manager: BaselineManager | None = None
        self.router: RetrievalRouter | None = None
        self.assembler: ContextAssembler | None = None
        self.health: HealthChecker = HealthChecker()
        self.base_path: Path = Path.cwd()
        self.start_time: datetime | None = None


state = DaemonState()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI lifespan handler for startup/shutdown."""
    # Startup
    await startup()
    yield
    # Shutdown
    await shutdown()


async def startup() -> None:
    """Initialize daemon components on startup."""
    state.start_time = datetime.now()
    state.health.mark_started(os.getpid())

    # Load configuration
    state.config = DMMConfig.load(state.base_path)

    # Initialize indexer
    state.indexer = Indexer(
        config=state.config,
        base_path=state.base_path,
    )
    await state.indexer.start(watch=True)

    # Initialize retrieval components
    state.baseline_manager = BaselineManager(
        store=state.indexer.store,
        base_path=state.base_path,
        token_budget=state.config.retrieval.baseline_budget,
    )

    state.router = RetrievalRouter(
        store=state.indexer.store,
        embedder=state.indexer.embedder,
        config=RetrievalConfig(
            top_k_directories=state.config.retrieval.top_k_directories,
            max_candidates=state.config.retrieval.max_candidates,
            diversity_threshold=state.config.retrieval.diversity_threshold,
        ),
    )

    state.assembler = ContextAssembler()

    # Update health stats
    memory_root = get_memory_root(state.base_path)
    state.health.update_stats(
        indexed_count=state.indexer.store.get_memory_count(),
        baseline_tokens=state.baseline_manager.get_baseline_tokens(),
        last_reindex=state.indexer.last_reindex,
        watcher_active=state.indexer.is_watching,
        memory_root=str(memory_root),
    )


async def shutdown() -> None:
    """Cleanup daemon components on shutdown."""
    if state.indexer:
        await state.indexer.stop()

    state.health.mark_stopped()


# Create FastAPI app
app = FastAPI(
    title="DMM Daemon",
    description="Dynamic Markdown Memory daemon API",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> JSONResponse:
    """Health check endpoint."""
    response = state.health.get_health_response()
    return JSONResponse(content=response.to_dict())


@app.get("/status")
async def status() -> JSONResponse:
    """Detailed status endpoint."""
    response = state.health.get_status_response()

    # Add baseline file count
    if state.baseline_manager:
        pack = state.baseline_manager.get_baseline_pack()
        response_dict = response.to_dict()
        response_dict["baseline_files"] = len(pack.entries)
        return JSONResponse(content=response_dict)

    return JSONResponse(content=response.to_dict())


@app.post("/query")
async def query(request: QueryRequestModel) -> JSONResponse:
    """Query endpoint for retrieving Memory Pack."""
    if not state.indexer or not state.baseline_manager or not state.router or not state.assembler:
        raise HTTPException(status_code=503, detail="Daemon not fully initialized")

    start_time = time.perf_counter()

    try:
        # Parse scope filter
        scope_filter = None
        if request.scope_filter:
            try:
                scope_filter = Scope(request.scope_filter)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid scope: {request.scope_filter}",
                )

        # Build search filters
        from dmm.models.query import SearchFilters

        filters = SearchFilters(
            scopes=[scope_filter] if scope_filter else None,
            exclude_deprecated=not request.include_deprecated,
            exclude_ephemeral=request.exclude_ephemeral,
        )

        # Get baseline
        embed_start = time.perf_counter()
        baseline_pack = state.baseline_manager.get_baseline_pack()
        embed_time = (time.perf_counter() - embed_start) * 1000

        # Calculate retrieval budget
        retrieval_budget = request.budget - baseline_pack.total_tokens

        # Retrieve
        retrieve_start = time.perf_counter()
        retrieval_result = state.router.retrieve(
            query=request.query,
            budget=max(0, retrieval_budget),
            filters=filters,
        )
        retrieve_time = (time.perf_counter() - retrieve_start) * 1000

        # Assemble
        assemble_start = time.perf_counter()
        pack = state.assembler.assemble(
            query=request.query,
            baseline=baseline_pack,
            retrieved=retrieval_result,
            budget=request.budget,
        )
        assemble_time = (time.perf_counter() - assemble_start) * 1000

        # Render markdown
        pack_markdown = state.assembler.render_markdown(pack, verbose=request.verbose)

        total_time = (time.perf_counter() - start_time) * 1000

        # Build response
        from dmm.models.query import QueryResponse, QueryStats

        stats = QueryStats(
            query_time_ms=total_time,
            embedding_time_ms=embed_time,
            retrieval_time_ms=retrieve_time,
            assembly_time_ms=assemble_time,
            directories_searched=retrieval_result.directories_searched,
            candidates_considered=retrieval_result.candidates_considered,
            baseline_files=len(baseline_pack.entries),
            retrieved_files=len(retrieval_result.entries),
            excluded_files=len(retrieval_result.excluded_for_budget),
        )

        response = QueryResponse(
            pack=pack,
            pack_markdown=pack_markdown,
            stats=stats,
            success=True,
        )

        return JSONResponse(content=response.to_dict())

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/reindex")
async def reindex(request: ReindexRequestModel) -> JSONResponse:
    """Trigger reindexing of memory files."""
    if not state.indexer:
        raise HTTPException(status_code=503, detail="Indexer not initialized")

    start_time = time.perf_counter()

    try:
        result = await state.indexer.reindex_all()
        duration_ms = (time.perf_counter() - start_time) * 1000

        # Update health stats
        state.health.update_stats(
            indexed_count=state.indexer.store.get_memory_count(),
            last_reindex=state.indexer.last_reindex,
        )

        if state.baseline_manager:
            state.baseline_manager.invalidate_cache()
            state.health.update_stats(
                baseline_tokens=state.baseline_manager.get_baseline_tokens(),
            )

        return JSONResponse(
            content={
                "reindexed": result.indexed,
                "errors": len(result.errors),
                "duration_ms": round(duration_ms, 2),
                "error_details": result.errors,
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/stats")
async def stats() -> JSONResponse:
    """Get detailed daemon statistics."""
    result: dict[str, Any] = {
        "health": state.health.to_dict(),
    }

    if state.indexer:
        result["indexer"] = state.indexer.get_stats()

    if state.router:
        result["router"] = state.router.get_stats()

    return JSONResponse(content=result)


def run_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    base_path: Path | None = None,
) -> None:
    """Run the daemon server."""
    import uvicorn

    if base_path:
        state.base_path = base_path

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
    )


def run_server_async(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    base_path: Path | None = None,
) -> None:
    """Run the daemon server with asyncio."""
    import uvicorn

    if base_path:
        state.base_path = base_path

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    asyncio.run(server.serve())
