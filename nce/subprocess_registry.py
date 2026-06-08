"""Thread-safe registry for active child subprocesses to prevent zombie/orphaned processes."""

from __future__ import annotations

import logging
import subprocess
import threading
from collections.abc import Generator
from contextlib import contextmanager

log = logging.getLogger("nce.subprocess_registry")

_lock = threading.Lock()
_active_processes: set[subprocess.Popen] = set()


def register_process(proc: subprocess.Popen) -> None:
    """Register a running subprocess."""
    with _lock:
        _active_processes.add(proc)
        log.debug("Registered subprocess PID=%d", proc.pid)


def unregister_process(proc: subprocess.Popen) -> None:
    """Unregister a finished/terminated subprocess."""
    with _lock:
        _active_processes.discard(proc)
        log.debug("Unregistered subprocess PID=%d", proc.pid)


@contextmanager
def tracked_process(proc: subprocess.Popen) -> Generator[subprocess.Popen, None, None]:
    """Context manager to register and automatically unregister a subprocess."""
    register_process(proc)
    try:
        yield proc
    finally:
        unregister_process(proc)


def terminate_all() -> None:
    """Terminate and kill all registered subprocesses.

    Called during server shutdown or task cancellation to ensure no child
    processes are left running (preventing zombie/orphaned processes).
    """
    with _lock:
        procs = list(_active_processes)
        _active_processes.clear()

    if not procs:
        return

    log.info("Terminating %d active child subprocess(es)...", len(procs))

    # Send SIGTERM (terminate) to all processes
    for proc in procs:
        try:
            if proc.poll() is None:
                log.info("Sending terminate to subprocess PID=%d", proc.pid)
                proc.terminate()
        except OSError as e:
            log.debug("Failed to terminate subprocess PID=%d: %s", proc.pid, e)

    # Wait briefly for processes to exit
    for proc in procs:
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            pass
        except OSError:
            pass

    # Send SIGKILL (kill) to any processes still alive
    for proc in procs:
        try:
            if proc.poll() is None:
                log.warning("Subprocess PID=%d did not terminate; killing it.", proc.pid)
                proc.kill()
                proc.wait()
        except OSError as e:
            log.debug("Failed to kill subprocess PID=%d: %s", proc.pid, e)
