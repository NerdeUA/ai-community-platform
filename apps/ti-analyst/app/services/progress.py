"""Shared pipeline progress state — written by scheduler & nodes, read by API."""
import threading

_lock = threading.Lock()
_state: dict = {}


def update(**kwargs) -> None:
    with _lock:
        _state.update(kwargs)


def get() -> dict:
    with _lock:
        return dict(_state)


def clear() -> None:
    with _lock:
        _state.clear()
