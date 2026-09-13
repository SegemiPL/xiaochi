"""Lifecycle management for the bundled open-websearch daemon."""

from __future__ import annotations

import atexit
import json
import logging
import os
import signal
import subprocess
import time
from dataclasses import replace
from pathlib import Path
from typing import Self
from urllib.parse import urlparse

from src.config.websearch import WebSearchSettings
from src.tools.common import PROJECT_ROOT
from src.websearch.client import OpenWebSearchClient, OpenWebSearchError

LOGGER = logging.getLogger(__name__)


class OpenWebSearchSupervisor:
    """Start a bundled daemon when needed and stop only the owned process."""

    def __init__(self, settings: WebSearchSettings | None = None) -> None:
        self.settings = settings or WebSearchSettings.from_env()
        self.process: subprocess.Popen | None = None
        self._log_file = None
        self._atexit_registered = False

    @property
    def owns_process(self) -> bool:
        return self.process is not None

    def start(self) -> bool:
        """Ensure the configured daemon is ready; return whether it was started here."""
        if not self.settings.auto_start:
            LOGGER.info("open-websearch autostart is disabled")
            return False

        parsed = urlparse(self.settings.base_url)
        if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            LOGGER.info("open-websearch uses a remote service; skipping local autostart")
            return False

        if self._daemon_ready():
            if not self._daemon_proxy_compatible():
                if not self._restart_recorded_orphan():
                    raise RuntimeError(
                        "an existing open-websearch daemon is running with incompatible proxy "
                        "settings; stop that daemon and relaunch 3wagent so the configured HTTP "
                        "proxy can take effect"
                    )
            else:
                LOGGER.info("reusing open-websearch daemon at %s", self.settings.base_url)
                return False

        runtime_dir = PROJECT_ROOT / "infra" / "open-websearch"
        executable = runtime_dir / "node_modules" / ".bin" / "open-websearch"
        if not executable.is_file():
            raise RuntimeError(
                "open-websearch is not installed; run "
                "`npm ci --prefix src/infra/open-websearch` first"
            )

        log_dir = PROJECT_ROOT / "workspace" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        self._log_file = (log_dir / "open-websearch.log").open("a", encoding="utf-8")
        env = os.environ.copy()
        _apply_proxy_compatibility(env)
        env.setdefault("DEFAULT_SEARCH_ENGINE", "bing")
        # baidu/sogou are unreliable under agent traffic (302 / anti-bot) but
        # remain available as backups; per-run engine failure tracking skips
        # them once they fail.
        env.setdefault("ALLOWED_SEARCH_ENGINES", "bing,duckduckgo,startpage,baidu,sogou")
        env.setdefault("SEARCH_MODE", "request")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        host = parsed.hostname or "127.0.0.1"
        self.process = subprocess.Popen(
            [str(executable), "serve", "--host", host, "--port", str(port)],
            cwd=runtime_dir,
            env=env,
            stdout=self._log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        self._record_owned_process(executable, host, port)
        atexit.register(self.stop)
        self._atexit_registered = True

        deadline = time.monotonic() + self.settings.startup_timeout_seconds
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                self.stop()
                raise RuntimeError(
                    "open-websearch exited during startup; see "
                    "src/workspace/logs/open-websearch.log"
                )
            if self._daemon_ready():
                LOGGER.info("started open-websearch daemon at %s", self.settings.base_url)
                return True
            time.sleep(0.1)

        self.stop()
        raise RuntimeError(
            "open-websearch did not become ready within "
            f"{self.settings.startup_timeout_seconds}s; see "
            "src/workspace/logs/open-websearch.log"
        )

    def stop(self) -> None:
        """Stop the daemon only when this supervisor started it."""
        process, self.process = self.process, None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        self._remove_owned_process_record(process)
        if self._log_file is not None:
            self._log_file.close()
            self._log_file = None
        if self._atexit_registered:
            atexit.unregister(self.stop)
            self._atexit_registered = False

    def _daemon_ready(self) -> bool:
        probe_settings = replace(self.settings, timeout_seconds=min(self.settings.timeout_seconds, 1))
        try:
            OpenWebSearchClient(probe_settings).status()
        except OpenWebSearchError:
            return False
        return True

    def _daemon_proxy_compatible(self) -> bool:
        expected_env = os.environ.copy()
        _apply_proxy_compatibility(expected_env)
        expected = expected_env.get("USE_PROXY", "false").strip().lower() == "true"
        try:
            status = OpenWebSearchClient(self.settings).status()
        except OpenWebSearchError:
            return False
        summary = status.get("configSummary")
        if not isinstance(summary, dict) or "useProxy" not in summary:
            # Older external daemons do not expose enough information. They
            # remain reusable only when this process does not require proxying.
            return not expected
        return bool(summary.get("useProxy")) == expected

    @property
    def _pid_file(self) -> Path:
        return PROJECT_ROOT / "workspace" / "open-websearch.pid.json"

    def _record_owned_process(self, executable: Path, host: str, port: int) -> None:
        """Record enough identity to recover only this project's orphan later."""
        if self.process is None or not isinstance(getattr(self.process, "pid", None), int):
            return
        self._pid_file.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "daemon_pid": self.process.pid,
            "supervisor_pid": os.getpid(),
            "executable": str(executable.resolve()),
            "host": host,
            "port": port,
        }
        self._pid_file.write_text(json.dumps(record), encoding="utf-8")

    def _remove_owned_process_record(self, process: subprocess.Popen | None) -> None:
        if process is None or not isinstance(getattr(process, "pid", None), int):
            return
        try:
            record = json.loads(self._pid_file.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return
        if record.get("daemon_pid") == process.pid:
            self._pid_file.unlink(missing_ok=True)

    def _restart_recorded_orphan(self) -> bool:
        """Stop an incompatible orphan previously launched by this project.

        A live supervisor is never interrupted.  The daemon PID, executable,
        host and port must all match the local runtime before a signal is sent,
        preventing an old/reused PID from targeting an unrelated process.
        """
        try:
            record = json.loads(self._pid_file.read_text(encoding="utf-8"))
            daemon_pid = int(record["daemon_pid"])
            supervisor_pid = int(record["supervisor_pid"])
        except (OSError, ValueError, TypeError, KeyError):
            return False
        if _process_exists(supervisor_pid):
            return False

        parsed = urlparse(self.settings.base_url)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        host = parsed.hostname or "127.0.0.1"
        executable = (
            PROJECT_ROOT / "infra" / "open-websearch" / "node_modules" / ".bin" / "open-websearch"
        ).resolve()
        if (
            record.get("executable") != str(executable)
            or record.get("host") != host
            or record.get("port") != port
            or not _command_matches_daemon(daemon_pid, executable, host, port)
        ):
            return False

        LOGGER.warning("restarting orphaned open-websearch daemon %s", daemon_pid)
        try:
            os.kill(daemon_pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except OSError:
            return False
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and self._daemon_ready():
            time.sleep(0.1)
        if self._daemon_ready():
            return False
        self._pid_file.unlink(missing_ok=True)
        return True

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.stop()


def _apply_proxy_compatibility(env: dict[str, str]) -> None:
    """Translate conventional proxy variables to open-websearch's opt-in pair.

    open-websearch intentionally ignores HTTP(S)_PROXY.  That is surprising in
    a host application whose Python and shell traffic already use those
    variables, and left DuckDuckGo/Startpage unreachable while the daemon
    reported "No proxy configured".  An explicit USE_PROXY value always wins;
    otherwise reuse the first configured HTTP proxy without inventing a host-
    specific default.
    """
    if "USE_PROXY" in env:
        return
    proxy_url = next(
        (
            env.get(name, "").strip()
            for name in (
                "OPEN_WEBSEARCH_PROXY_URL",
                "PROXY_URL",
                "HTTPS_PROXY",
                "https_proxy",
                "HTTP_PROXY",
                "http_proxy",
            )
            if env.get(name, "").strip()
        ),
        "",
    )
    if not proxy_url:
        return
    parsed = urlparse(proxy_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        LOGGER.warning("ignoring unsupported open-websearch proxy URL scheme")
        return
    env["USE_PROXY"] = "true"
    env["PROXY_URL"] = proxy_url


def _process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _command_matches_daemon(pid: int, executable: Path, host: str, port: int) -> bool:
    try:
        completed = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    command = completed.stdout.strip()
    return (
        completed.returncode == 0
        and str(executable) in command
        and f"serve --host {host} --port {port}" in command
    )
