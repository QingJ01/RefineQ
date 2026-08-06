"""Bounded subprocess execution for CPU-heavy, untrusted material parsing."""

from __future__ import annotations

from collections.abc import Callable
from multiprocessing import get_context
from multiprocessing.connection import Connection
from threading import BoundedSemaphore
from typing import Any, TypeVar, cast

from refineq.knowledge.extract import (
    ExtractionLimits,
    MaterialExtractionError,
    MaterialExtractionLimitError,
    extract_text,
)

T = TypeVar("T")
_PROCESS_SLOTS = BoundedSemaphore(value=2)


class SubprocessTimeoutError(TimeoutError):
    """Raised only after the timed-out child process has been stopped and reaped."""


def _child_entry(
    sender: Connection,
    function: Callable[..., Any],
    args: tuple[Any, ...],
) -> None:
    try:
        sender.send(("ok", function(*args)))
    except MaterialExtractionLimitError as error:
        sender.send(("limit", str(error)))
    except MaterialExtractionError as error:
        sender.send(("extraction", str(error)))
    except BaseException:
        sender.send(("unexpected", "Material extraction failed in an isolated worker"))
    finally:
        sender.close()


def _stop(process: Any) -> None:
    if process.is_alive():
        process.terminate()
    process.join(timeout=1.0)
    if process.is_alive():
        process.kill()
        process.join(timeout=1.0)


def run_in_subprocess(
    function: Callable[..., T],
    *args: Any,
    timeout_seconds: float,
) -> T:
    """Run one picklable call with a hard deadline and a global child-process cap."""

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    context = get_context("spawn")
    with _PROCESS_SLOTS:
        receiver, sender = context.Pipe(duplex=False)
        process = context.Process(target=_child_entry, args=(sender, function, args))
        process.start()
        sender.close()
        try:
            if not receiver.poll(timeout_seconds):
                raise SubprocessTimeoutError("Material extraction exceeded its time budget")
            try:
                outcome, payload = receiver.recv()
            except EOFError as error:
                raise MaterialExtractionError(
                    "Material extraction worker exited unexpectedly"
                ) from error
        finally:
            receiver.close()
            _stop(process)

    if outcome == "ok":
        return cast(T, payload)
    if outcome == "limit":
        raise MaterialExtractionLimitError(payload)
    if outcome == "extraction":
        raise MaterialExtractionError(payload)
    raise MaterialExtractionError(payload)


def _extract(
    filename: str,
    content_type: str,
    data: bytes,
    limits: ExtractionLimits,
) -> str:
    return extract_text(filename, content_type, data, limits=limits)


def extract_text_isolated(
    filename: str,
    content_type: str,
    data: bytes,
    limits: ExtractionLimits,
) -> str:
    """Extract in a process that can be forcibly stopped at the configured deadline."""

    return run_in_subprocess(
        _extract,
        filename,
        content_type,
        data,
        limits,
        timeout_seconds=limits.max_processing_seconds + 0.5,
    )
