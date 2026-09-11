from __future__ import annotations

import threading
from typing import Any


class JobManager:
    """One reconstruction at a time, with cooperative cancellation."""

    def __init__(self):
        self._lock = threading.Lock()
        self._events: dict[str, threading.Event] = {}
        self._services: dict[str, Any] = {}

    def event_for(self, job_id: str) -> threading.Event:
        with self._lock:
            event = self._events.get(job_id)
            if event is None:
                event = threading.Event()
                self._events[job_id] = event
            return event

    def register(self, job_id: str, service: Any) -> None:
        with self._lock:
            self._services[job_id] = service

    def is_cancelled(self, job_id: str) -> bool:
        with self._lock:
            event = self._events.get(job_id)
            return bool(event and event.is_set())

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            event = self._events.get(job_id)
            if event is None:
                event = threading.Event()
                self._events[job_id] = event
            event.set()
            service = self._services.get(job_id)
        if service is not None:
            try:
                service.cancel()
            except Exception:
                pass
        return True

    def finish(self, job_id: str) -> None:
        with self._lock:
            self._events.pop(job_id, None)
            self._services.pop(job_id, None)


job_manager = JobManager()
