"""core/single_instance.py — Safe per-user single-instance guard for CHARLIE.

Uses a Windows named mutex so only one Charlie instance can run per user session.
If a second instance starts, it detects the active mutex and exits cleanly without
allocating microphone, playback, Gemini Live, ports 1901/1902, or UI resources.
The Windows kernel automatically destroys/releases the mutex if a process crashes or
terminates, eliminating stale lock files entirely.
"""

from __future__ import annotations

import atexit
import getpass
import hashlib
import logging
import os
import sys

logger = logging.getLogger("charlie.core.single_instance")

_MUTEX_HANDLE = None
_ACQUIRED = False
_ACQUIRED_NAME: str | None = None


def _get_mutex_name(app_name: str = "CharlieAI_Assistant") -> str:
    """Generate user-scoped named mutex identifier."""
    user = (os.environ.get("USERNAME") or getpass.getuser() or "default").strip().lower()
    user_hash = hashlib.sha256(user.encode("utf-8", errors="ignore")).hexdigest()[:12]
    # Local\ prefix ensures session/user isolation in Windows Terminal Services
    return f"Local\\{app_name}_{user_hash}"


def acquire_single_instance(app_name: str = "CharlieAI_Assistant") -> bool:
    """Attempt to acquire named mutex for single-instance guard.

    Returns:
        True if this is the only running instance (lock acquired).
        False if another instance of Charlie is already running.
    """
    global _MUTEX_HANDLE, _ACQUIRED, _ACQUIRED_NAME

    if _ACQUIRED:
        if _ACQUIRED_NAME == app_name:
            return True
        release_single_instance()

    # Windows named mutex implementation via ctypes
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.windll.kernel32
            mutex_name = _get_mutex_name(app_name)
            handle = kernel32.CreateMutexW(None, False, mutex_name)
            last_error = kernel32.GetLastError()

            ERROR_ALREADY_EXISTS = 183
            if last_error == ERROR_ALREADY_EXISTS:
                if handle:
                    kernel32.CloseHandle(handle)
                _MUTEX_HANDLE = None
                _ACQUIRED = False
                _ACQUIRED_NAME = None
                return False

            if not handle:
                # Fallback if mutex creation failed unexpectedly
                _ACQUIRED = True
                _ACQUIRED_NAME = app_name
                return True

            _MUTEX_HANDLE = handle
            _ACQUIRED = True
            _ACQUIRED_NAME = app_name
            atexit.register(release_single_instance)
            return True
        except Exception as e:
            logger.warning(f"[SingleInstance] Windows mutex check fallback: {e}")
            _ACQUIRED = True
            _ACQUIRED_NAME = app_name
            return True
    else:
        # Non-Windows POSIX file lock fallback
        try:
            import fcntl
            lock_path = Path.home() / f".{app_name.lower()}.lock"
            fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _MUTEX_HANDLE = fd
            _ACQUIRED = True
            atexit.register(release_single_instance)
            return True
        except Exception:
            return False


def release_single_instance() -> None:
    """Release mutex handle upon clean application exit."""
    global _MUTEX_HANDLE, _ACQUIRED, _ACQUIRED_NAME
    if not _ACQUIRED:
        return

    if sys.platform == "win32" and _MUTEX_HANDLE is not None:
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.CloseHandle(_MUTEX_HANDLE)
        except Exception:
            pass
        _MUTEX_HANDLE = None
    elif _MUTEX_HANDLE is not None:
        try:
            import fcntl
            fcntl.flock(_MUTEX_HANDLE, fcntl.LOCK_UN)
            os.close(_MUTEX_HANDLE)
        except Exception:
            pass
        _MUTEX_HANDLE = None

    _ACQUIRED = False
    _ACQUIRED_NAME = None


def is_single_instance_acquired() -> bool:
    """Return True if this process holds the single-instance mutex."""
    return _ACQUIRED
