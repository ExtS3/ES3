from __future__ import annotations

import asyncio
import queue
import threading
import traceback
from urllib.parse import urlparse

from .action_schema import validate_agent_action
from .observation_schema import normalize_observations

_ALLOWED_TARGETS = {
    "mock_or_localhost_only",
    "localhost",
    "127.0.0.1",
    "mock.local",
    "http://localhost",
    "http://127.0.0.1",
}
_ALLOWED_EMULATED_HOSTS = {"web.telegram.org", "accounts.google.com", "mail.google.com", "drive.google.com"}


def _is_local_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except Exception:
        return False

    host = (parsed.hostname or "").lower()
    if host in {"localhost", "127.0.0.1", "mock.local"}:
        return True
    return False


def _is_allowed_emulated_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except Exception:
        return False
    if parsed.scheme != "https":
        return False
    return (parsed.hostname or "").lower() in _ALLOWED_EMULATED_HOSTS


def _empty_observation(note: str | None = None) -> dict:
    obs = normalize_observations(
        {
            "network_requests": [],
            "runtime_messages": [],
            "storage_events": [],
            "dom_events": [],
            "timers": [],
            "execution": {
                "mock_target_used": True,
                "real_service_used": False,
                "real_secret_observed": False,
                "non_localhost_sensitive_transmission": False,
            },
        }
    )
    obs["notes"] = [note] if note else []
    return obs


def _target_is_safe(action: dict) -> bool:
    target = action.get("target")
    if isinstance(target, str) and target.strip():
        target = target.strip()
        if target not in _ALLOWED_TARGETS:
            if target.startswith("http://") or target.startswith("https://"):
                if not _is_local_url(target) and not _is_allowed_emulated_url(target):
                    return False
            else:
                return False

    action_input = action.get("input")
    if isinstance(action_input, dict):
        url = action_input.get("url")
        if isinstance(url, str) and url.strip():
            u = url.strip()
            if u not in _ALLOWED_TARGETS and not _is_local_url(u) and not _is_allowed_emulated_url(u):
                return False

    return True


class DynamicActionAdapter:
    def __init__(self, harness=None):
        self.harness = harness
        self._task_q: queue.Queue = queue.Queue()
        self._worker: threading.Thread | None = None
        self._worker_started = False
        self._worker_shutdown_completed = False
        self._last_worker_diag = {"running_loop": False, "loop_id": None, "loop_type": None}
        if harness is not None:
            self._ensure_worker()

    @staticmethod
    def _loop_state() -> dict:
        try:
            loop = asyncio.get_running_loop()
            return {"running_loop": True, "loop_id": id(loop), "loop_type": type(loop).__name__}
        except RuntimeError:
            return {"running_loop": False, "loop_id": None, "loop_type": None}

    def _ensure_worker(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        self._worker = threading.Thread(target=self._worker_main, name="playwright-sync-worker", daemon=True)
        self._worker.start()
        self._worker_started = True

    def _worker_main(self) -> None:
        self._last_worker_diag = self._loop_state()
        while True:
            item = self._task_q.get()
            if not isinstance(item, tuple) or not item:
                continue
            op = item[0]
            if op == "__shutdown__":
                result_q = item[1]
                try:
                    cleanup_result = None
                    if self.harness is not None:
                        cleanup_result = self.harness.close()
                    self._worker_shutdown_completed = True
                    result_q.put(("ok", cleanup_result))
                except Exception as exc:
                    result_q.put(("error", exc, traceback.format_exc()))
                return
            if op == "action":
                action, result_q = item[1], item[2]
                try:
                    res = self._execute_action_direct(action)
                    result_q.put(("ok", res))
                except Exception as exc:
                    result_q.put(("error", exc, traceback.format_exc()))

    def _execute_action_direct(self, action: dict) -> dict:
        harness = self.harness
        if harness is None:
            return _empty_observation("harness not set")
        normalizer = getattr(harness, "normalize_action_target", None)
        if callable(normalizer):
            action = normalizer(action)
        action_name = action.get("action")
        method = getattr(harness, str(action_name), None)
        if callable(method):
            raw = method(action)
            obs = normalize_observations(raw)
            obs["notes"] = []
            return obs
        fallback = getattr(harness, "execute_action", None)
        if callable(fallback):
            raw = fallback(action)
            obs = normalize_observations(raw)
            obs["notes"] = []
            return obs
        return _empty_observation(f"unsupported action in harness: {action_name}")

    def execute_action(self, action: dict) -> dict:
        loop_diag = self._loop_state()
        print(
            f"[thread_diag] location=execute_action thread={threading.current_thread().name} "
            f"running_loop={loop_diag['running_loop']} loop_id={loop_diag['loop_id']}",
            flush=True,
        )
        valid, reason = validate_agent_action(action)
        if not valid:
            return _empty_observation(f"invalid action blocked: {reason}")

        if not _target_is_safe(action):
            return _empty_observation("unsafe target/url blocked")

        action_name = action.get("action")
        if action_name == "finish_analysis":
            return _empty_observation("finish_analysis")

        if self.harness is None:
            return _empty_observation("harness not set")
        self._ensure_worker()
        result_q: queue.Queue = queue.Queue(maxsize=1)
        self._task_q.put(("action", action, result_q))
        try:
            status, payload, *rest = result_q.get(timeout=60)
        except queue.Empty:
            obs = _empty_observation("playwright worker timeout")
            obs["execution"]["playwright_worker_thread_name"] = "playwright-sync-worker"
            obs["execution"]["playwright_worker_started"] = self._worker_started
            obs["execution"]["playwright_worker_running_loop"] = bool(self._last_worker_diag.get("running_loop"))
            obs["execution"]["playwright_worker_shutdown_completed"] = self._worker_shutdown_completed
            return obs
        if status == "error":
            obs = _empty_observation(f"playwright worker error: {payload}")
        else:
            obs = payload
        if isinstance(obs, dict):
            exec_info = obs.get("execution", {}) if isinstance(obs.get("execution", {}), dict) else {}
            exec_info["playwright_worker_thread_name"] = "playwright-sync-worker"
            exec_info["playwright_worker_started"] = self._worker_started
            exec_info["playwright_worker_running_loop"] = bool(self._last_worker_diag.get("running_loop"))
            exec_info["playwright_worker_shutdown_completed"] = self._worker_shutdown_completed
            obs["execution"] = exec_info
        return obs

    def close(self):
        if self._worker is None or not self._worker.is_alive():
            cleanup_result = None
            if self.harness is not None:
                cleanup_result = self.harness.close()
            self._worker_shutdown_completed = True
            return cleanup_result
        result_q: queue.Queue = queue.Queue(maxsize=1)
        self._task_q.put(("__shutdown__", result_q))
        try:
            status, payload, *rest = result_q.get(timeout=30)
        except Exception:
            return None
        self._worker_shutdown_completed = True
        if status == "ok":
            return payload
        return None


_default_adapter = DynamicActionAdapter()


def bind_harness(harness) -> None:
    _default_adapter.harness = harness


def execute_action(action: dict) -> dict:
    return _default_adapter.execute_action(action)
