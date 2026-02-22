# audit_logger.py
# Append-only, versioned, plain-text audit logging with hash chaining.

import os
import json
import hashlib
import datetime
from typing import Any, Optional


class AuditLogger:
    """
    Plain-text, append-only logger for audit runs.

    Features:
    - Creates a new file per run.
    - Includes device-specific versioning (v1, v2, v3...).
    - Hash-chains logs for the same device_id for tamper-evidence.
    - Writes structured sections (titles + JSON-formatted bodies).
    """

    def __init__(self, log_dir: str = "audit_logs"):
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)

        self.current_file_path: Optional[str] = None
        self.current_file_handle = None
        self.current_run_id: Optional[str] = None
        self.current_device_id: Optional[str] = None
        self.current_version: Optional[int] = None

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------
    def start_new_run(self, run_id: str, device_id: str = "unknown"):
        """
        Begins a new log file for this run.

        - Computes next version for the device_id.
        - Computes hash of previous log (if any) for hash chaining.
        - Opens a new file and writes a header.
        """
        if self.current_file_handle is not None:
            raise RuntimeError("A run is already active. Call end_run() first.")

        self.current_run_id = run_id
        self.current_device_id = device_id

        version = self._compute_next_version(device_id)
        self.current_version = version

        timestamp = datetime.datetime.utcnow().isoformat()

        filename = f"{run_id}_dev-{self._sanitize_device_id(device_id)}_v{version}.txt"
        self.current_file_path = os.path.join(self.log_dir, filename)

        prev_hash = self._get_previous_hash(device_id, version - 1) if version > 1 else None

        self.current_file_handle = open(self.current_file_path, "w", encoding="utf-8")

        header = {
            "run_id": run_id,
            "device_id": device_id,
            "version": version,
            "timestamp_utc": timestamp,
            "previous_version": version - 1 if version > 1 else None,
            "previous_log_hash": prev_hash
        }

        self._write_line("=== AUDIT RUN HEADER ===")
        self._write_line(json.dumps(header, indent=2, sort_keys=True))
        self._write_line("")  # blank line

    def log_section(self, title: str, content: Any):
        """
        Writes a titled section to the current log file.
        Content is JSON-serialized where possible.
        """
        if self.current_file_handle is None:
            raise RuntimeError("No active run. Call start_new_run() first.")

        self._write_line(f"\n=== {title} ===")
        formatted = self._format_content(content)
        self._write_line(formatted)

    def end_run(self):
        """
        Closes the current log file.
        """
        if self.current_file_handle is not None:
            self._write_line("\n=== END OF RUN ===")
            self.current_file_handle.close()
            self.current_file_handle = None
            self.current_file_path = None
            self.current_run_id = None
            self.current_device_id = None
            self.current_version = None

    # ------------------------------------------------------------------
    # INTERNAL HELPERS
    # ------------------------------------------------------------------
    def _write_line(self, text: str):
        if self.current_file_handle is not None:
            self.current_file_handle.write(text + "\n")

    def _format_content(self, content: Any) -> str:
        """
        Try to JSON-dump dicts/lists; fall back to str() otherwise.
        """
        try:
            return json.dumps(content, indent=2, sort_keys=True, default=str)
        except TypeError:
            return str(content)

    def _sanitize_device_id(self, device_id: str) -> str:
        """
        Sanitize device_id for use in filenames.
        """
        return "".join(c for c in str(device_id) if c.isalnum() or c in ("-", "_"))

    def _compute_next_version(self, device_id: str) -> int:
        """
        Scans existing logs for this device_id and returns next version number.
        v1 if no previous logs exist.
        """
        sanitized = self._sanitize_device_id(device_id)
        prefix = f"_dev-{sanitized}_v"

        max_version = 0
        for fname in os.listdir(self.log_dir):
            if prefix in fname:
                try:
                    # filename pattern: <run_id>_dev-<device>_v<version>.txt
                    version_str = fname.split(prefix)[-1].split(".")[0]
                    v = int(version_str)
                    if v > max_version:
                        max_version = v
                except (ValueError, IndexError):
                    continue

        return max_version + 1

    def _get_previous_hash(self, device_id: str, prev_version: int) -> Optional[str]:
        """
        Loads the previous version log for this device and returns its SHA-256 hash.
        If not found, returns None.
        """
        if prev_version < 1:
            return None

        sanitized = self._sanitize_device_id(device_id)
        prefix = f"_dev-{sanitized}_v{prev_version}.txt"

        # find file with this version
        for fname in os.listdir(self.log_dir):
            if fname.endswith(prefix):
                prev_path = os.path.join(self.log_dir, fname)
                return self._file_sha256(prev_path)

        return None

    def _file_sha256(self, path: str) -> str:
        """
        Computes SHA-256 hash of a file's contents.
        """
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
