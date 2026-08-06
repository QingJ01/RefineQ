"""Hard-stop coverage for untrusted material extraction work."""

from __future__ import annotations

import multiprocessing
import time

import pytest

from refineq.knowledge.execution import SubprocessTimeoutError, run_in_subprocess


def test_timed_out_subprocess_is_terminated_before_returning() -> None:
    children_before = {process.pid for process in multiprocessing.active_children()}
    started_at = time.monotonic()

    with pytest.raises(SubprocessTimeoutError):
        run_in_subprocess(time.sleep, 5.0, timeout_seconds=0.1)

    elapsed = time.monotonic() - started_at
    children_after = {process.pid for process in multiprocessing.active_children()}
    assert elapsed < 2.0
    assert children_after == children_before
