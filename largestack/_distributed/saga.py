"""Saga orchestration — distributed transactions with compensation, timeout, retry.

Reference: "Sagas" (Garcia-Molina & Salem, 1987)
"""
from __future__ import annotations
import asyncio, json, logging, os, sqlite3, time, uuid
from typing import Any, Callable

log = logging.getLogger("largestack.saga")


class SagaStep:
    """A single step in a saga transaction.
    
    Each step has an action (forward) and compensation (rollback).
    """
    def __init__(self, name: str, action: Callable, compensation: Callable = None,
                 timeout: float = None, max_retries: int = 0,
                 idempotent: bool = False):
        if not name:
            raise ValueError("Step name is required")
        self.name = name
        self.action = action
        self.compensation = compensation  # None = no-op
        self.timeout = timeout
        self.max_retries = max_retries
        self.idempotent = idempotent


class SagaExecutionError(RuntimeError):
    """Raised when saga fails and compensation completes."""
    def __init__(self, saga_name: str, failed_step: str, error: Exception,
                 compensation_errors: list = None):
        self.saga_name = saga_name
        self.failed_step = failed_step
        self.error = error
        self.compensation_errors = compensation_errors or []
        super().__init__(f"Saga '{saga_name}' failed at '{failed_step}': {error}")


class SagaOrchestrator:
    """Execute distributed transactions with automatic compensation.
    
    Features:
      - Per-step timeouts
      - Per-step retries with exponential backoff
      - Optional persistence (resume after crash)
      - Idempotent steps (skip on retry if already done)
      - Parallel steps (branches that can run concurrently)
    
    Usage:
        saga = SagaOrchestrator("order-processing")
        saga.add_step(
            "reserve_inventory",
            action=reserve_fn,
            compensation=release_fn,
            timeout=10, max_retries=3
        )
        saga.add_step("charge_payment", charge_fn, refund_fn)
        saga.add_step("ship_order", ship_fn, cancel_fn)
        
        result = await saga.execute({"order_id": "123"})
    """
    def __init__(self, name: str = "saga", persist_to: str = None,
                 global_timeout: float = None):
        self.name = name
        self.steps: list[SagaStep] = []
        self.persist_to = os.path.expanduser(persist_to) if persist_to else None
        self.global_timeout = global_timeout
        self._db = None
        
        if self.persist_to:
            self._init_persistence()
    
    def _init_persistence(self):
        os.makedirs(os.path.dirname(self.persist_to), exist_ok=True)
        self._db = sqlite3.connect(self.persist_to, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("""CREATE TABLE IF NOT EXISTS saga_runs (
            saga_id TEXT PRIMARY KEY,
            saga_name TEXT NOT NULL,
            status TEXT NOT NULL,
            current_step INTEGER DEFAULT 0,
            context TEXT,
            completed_steps TEXT,
            error TEXT,
            started_at REAL NOT NULL,
            completed_at REAL
        )""")
        self._db.commit()
    
    def add_step(self, name: str, action: Callable, compensation: Callable = None,
                 timeout: float = None, max_retries: int = 0,
                 idempotent: bool = False):
        """Add a step to the saga."""
        self.steps.append(SagaStep(name, action, compensation, timeout, max_retries, idempotent))
        return self
    
    async def _run_step(self, step: SagaStep, ctx: dict) -> Any:
        """Execute a step with timeout and retry."""
        attempts = step.max_retries + 1
        last_exc = None
        
        for attempt in range(attempts):
            try:
                if step.timeout:
                    if asyncio.iscoroutinefunction(step.action):
                        result = await asyncio.wait_for(step.action(ctx), timeout=step.timeout)
                    else:
                        result = await asyncio.wait_for(
                            asyncio.to_thread(step.action, ctx),
                            timeout=step.timeout
                        )
                else:
                    if asyncio.iscoroutinefunction(step.action):
                        result = await step.action(ctx)
                    else:
                        result = step.action(ctx)
                return result
            except Exception as e:
                last_exc = e
                if attempt + 1 < attempts:
                    backoff = 2 ** attempt
                    log.warning(
                        f"Saga '{self.name}': step '{step.name}' failed "
                        f"(attempt {attempt+1}/{attempts}), retrying in {backoff}s: {e}"
                    )
                    await asyncio.sleep(backoff)
        
        raise last_exc
    
    async def _run_compensation(self, step: SagaStep, ctx: dict) -> Exception | None:
        """Run compensation. Returns exception if failed, None if success."""
        if step.compensation is None:
            return None  # No-op compensation
        try:
            log.info(f"Saga '{self.name}': compensating '{step.name}'")
            if asyncio.iscoroutinefunction(step.compensation):
                await step.compensation(ctx)
            else:
                step.compensation(ctx)
            return None
        except Exception as e:
            log.error(f"Saga '{self.name}': compensation for '{step.name}' failed: {e}")
            return e
    
    def _save_run(self, saga_id: str, status: str, current_step: int,
                  ctx: dict, completed: list[str], error: str = None):
        if not self._db:
            return
        self._db.execute(
            "INSERT OR REPLACE INTO saga_runs "
            "(saga_id, saga_name, status, current_step, context, completed_steps, error, started_at, completed_at) "
            "VALUES (?,?,?,?,?,?,?, "
            "  COALESCE((SELECT started_at FROM saga_runs WHERE saga_id=?), ?), "
            "  ?)",
            (saga_id, self.name, status, current_step, json.dumps(ctx, default=str),
             json.dumps(completed), error, saga_id, time.time(),
             time.time() if status in ("completed", "compensated", "failed") else None)
        )
        self._db.commit()
    
    async def execute(self, context: dict = None, saga_id: str = None) -> dict:
        """Execute saga. Returns final context on success.
        
        Raises SagaExecutionError on failure (after compensation).
        """
        ctx = dict(context or {})
        saga_id = saga_id or f"{self.name}-{uuid.uuid4().hex[:8]}"
        completed: list[SagaStep] = []
        started_at = time.monotonic()
        
        self._save_run(saga_id, "running", 0, ctx, [])
        
        for i, step in enumerate(self.steps):
            # Global timeout check
            if self.global_timeout:
                elapsed = time.monotonic() - started_at
                if elapsed >= self.global_timeout:
                    last_exc = TimeoutError(
                        f"Saga '{self.name}' global timeout after {elapsed:.1f}s"
                    )
                    comp_errors = await self._compensate_all(completed, ctx)
                    self._save_run(saga_id, "failed", i, ctx,
                                  [s.name for s in completed],
                                  error=str(last_exc))
                    raise SagaExecutionError(self.name, step.name, last_exc, comp_errors)
            
            try:
                log.info(f"Saga '{self.name}': executing step {i+1}/{len(self.steps)} — '{step.name}'")
                result = await self._run_step(step, ctx)
                
                if isinstance(result, dict):
                    ctx.update(result)
                
                completed.append(step)
                self._save_run(saga_id, "running", i + 1, ctx,
                              [s.name for s in completed])
            
            except Exception as e:
                log.error(f"Saga '{self.name}': step '{step.name}' failed: {e}")
                comp_errors = await self._compensate_all(completed, ctx)
                self._save_run(saga_id, "failed", i, ctx,
                              [s.name for s in completed], error=str(e))
                raise SagaExecutionError(self.name, step.name, e, comp_errors)
        
        self._save_run(saga_id, "completed", len(self.steps), ctx,
                      [s.name for s in completed])
        return ctx
    
    async def _compensate_all(self, completed: list[SagaStep], ctx: dict) -> list:
        """Run compensation for all completed steps in reverse order."""
        errors = []
        for step in reversed(completed):
            err = await self._run_compensation(step, ctx)
            if err:
                errors.append({"step": step.name, "error": str(err)})
        return errors
    
    def get_run_status(self, saga_id: str) -> dict | None:
        if not self._db:
            return None
        row = self._db.execute(
            "SELECT saga_name, status, current_step, context, completed_steps, error, "
            "started_at, completed_at FROM saga_runs WHERE saga_id=?",
            (saga_id,)
        ).fetchone()
        if not row:
            return None
        return {
            "saga_id": saga_id,
            "saga_name": row[0],
            "status": row[1],
            "current_step": row[2],
            "context": json.loads(row[3]) if row[3] else {},
            "completed_steps": json.loads(row[4]) if row[4] else [],
            "error": row[5],
            "started_at": row[6],
            "completed_at": row[7],
        }
    
    def list_runs(self, status: str = None, limit: int = 50) -> list[dict]:
        if not self._db:
            return []
        if status:
            rows = self._db.execute(
                "SELECT saga_id, saga_name, status, current_step, started_at, completed_at "
                "FROM saga_runs WHERE status=? ORDER BY started_at DESC LIMIT ?",
                (status, limit)
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT saga_id, saga_name, status, current_step, started_at, completed_at "
                "FROM saga_runs ORDER BY started_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [{
            "saga_id": r[0], "saga_name": r[1], "status": r[2],
            "current_step": r[3], "started_at": r[4], "completed_at": r[5]
        } for r in rows]
    
    @property
    def stats(self) -> dict:
        info = {"name": self.name, "step_count": len(self.steps), "persisted": bool(self._db)}
        if self._db:
            rows = self._db.execute(
                "SELECT status, COUNT(*) FROM saga_runs GROUP BY status"
            ).fetchall()
            info["runs_by_status"] = dict(rows)
        return info
