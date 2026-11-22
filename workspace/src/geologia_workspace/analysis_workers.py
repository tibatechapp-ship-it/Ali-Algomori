"""Bounded analysis workers — reference-matched spatial analysis off the request path.

Governing sequence step 4: «التحليل المكاني المطابق لمرجع عبر Workers» —
spatial analysis matched to a reference runs in dedicated workers, not on
the request thread. The pool is bounded by construction (worker count and
queue depth both env-bounded); an analysis request that arrives to a full
queue is refused with a classified code instead of piling up silently, and
a long-running analysis is refused on timeout with a classified code. Every
refusal is an honest statement, not a silent degradation.

The pool is process-wide (one pool per API process), created lazily, and
deliberately thread-based: the reference-matched spatial kernels
(``utm_equations``, ``geospatial``) release nothing but CPU-bound Python
arithmetic on bounded payloads, and a bounded thread pool isolates the
request path from that arithmetic without a second interpreter per
analysis.
"""
from __future__ import annotations

import concurrent.futures
import os
import threading
from typing import Any, Callable, Dict, Optional

# Local bounded env helper (documented twin of core reception.bounded_env_int;
# the layers are separate distributions by ADR-0001).
def _bounded_env_int(name: str, default: int, minimum: int,
                     maximum: int) -> int:
    """Read an env-bounded integer: out-of-band or malformed values fall
    back to the default instead of being trusted (never-trust-declarations,
    applied to our own configuration too)."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    if value < minimum or value > maximum:
        return default
    return value


# Defaults: small, bounded, overridable by environment.
DEFAULT_MAX_WORKERS = 2
DEFAULT_QUEUE_CAP = 16
DEFAULT_TIMEOUT_S = 30


def max_workers() -> int:
    return _bounded_env_int("GEOLOGIA_ANALYSIS_WORKERS", DEFAULT_MAX_WORKERS,
                            minimum=1, maximum=8)


def queue_cap() -> int:
    return _bounded_env_int("GEOLOGIA_ANALYSIS_QUEUE", DEFAULT_QUEUE_CAP,
                            minimum=1, maximum=256)


def analysis_timeout_s() -> int:
    return _bounded_env_int("GEOLOGIA_ANALYSIS_TIMEOUT_S", DEFAULT_TIMEOUT_S,
                            minimum=1, maximum=600)


class AnalysisRefused(RuntimeError):
    """A classified refusal from the analysis pool — raised, never swallowed."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class AnalysisWorkers:
    """Bounded worker pool with classified refusals at both boundaries."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._executor: Optional[concurrent.futures.ThreadPoolExecutor] = None
        self._in_flight = 0

    def _ensure_executor(self) -> concurrent.futures.ThreadPoolExecutor:
        with self._lock:
            if self._executor is None:
                self._executor = concurrent.futures.ThreadPoolExecutor(
                    max_workers=max_workers(),
                    thread_name_prefix="geologia-analysis",
                )
            return self._executor

    def submit_analysis(
        self,
        fn: Callable[..., Any],
        *args: Any,
        timeout_s: Optional[int] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Run ``fn`` in a worker; return a truth-classified envelope.

        Returns ``{"ok": True, "result": <fn result>, "truth_class":
        "verified_content", "executed_in": "analysis_worker"}`` on success.

        Refusals (``AnalysisRefused`` with a classified code):
        - ``analysis.refusal.workers_saturated``: the bounded queue is full
          (in-flight + queued >= cap) — the caller gets an honest refusal
          instead of an unbounded wait;
        - ``analysis.refusal.timeout``: the worker exceeded the timeout —
          the result is abandoned (the worker thread itself is never killed;
          the refusal states that the analysis did not finish, which is the
          honest claim).

        Any exception raised by ``fn`` is re-raised untouched: the pool
        never converts a kernel error into a fake success.
        """
        cap = queue_cap()
        with self._lock:
            if self._in_flight >= cap:
                raise AnalysisRefused(
                    "analysis.refusal.workers_saturated",
                    f"bounded analysis queue is full ({self._in_flight} "
                    f"in-flight >= {cap}); retry after in-flight work "
                    f"completes",
                )
            self._in_flight += 1
        executor = self._ensure_executor()
        try:
            future = executor.submit(fn, *args, **kwargs)
        except RuntimeError as exc:  # executor shutdown mid-flight
            with self._lock:
                self._in_flight -= 1
            raise AnalysisRefused(
                "analysis.refusal.pool_unavailable", str(exc)) from exc
        limit = timeout_s if timeout_s is not None else analysis_timeout_s()
        try:
            result = future.result(timeout=limit)
        except concurrent.futures.TimeoutError as exc:
            future.cancel()
            raise AnalysisRefused(
                "analysis.refusal.timeout",
                f"analysis exceeded {limit}s and was abandoned; no result "
                f"is claimed",
            ) from exc
        except AnalysisRefused:
            raise
        except Exception:
            # Kernel errors propagate untouched — the envelope only wraps
            # the pool's own boundaries, never the analysis result.
            raise
        finally:
            with self._lock:
                self._in_flight -= 1
        return {
            "ok": True,
            "result": result,
            "truth_class": "verified_content",
            "executed_in": "analysis_worker",
        }


_WORKERS: Optional[AnalysisWorkers] = None
_WORKERS_LOCK = threading.Lock()


def get_analysis_workers() -> AnalysisWorkers:
    """Process-wide singleton: one bounded pool per API process."""
    global _WORKERS
    if _WORKERS is None:
        with _WORKERS_LOCK:
            if _WORKERS is None:
                _WORKERS = AnalysisWorkers()
    return _WORKERS
