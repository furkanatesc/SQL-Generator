"""Secret resolution (Sprint 32.2).

Single place the backend reads secrets from the environment. Each contract secret
(`secret=True` in `app/config_contract.py`) can be supplied either directly as `<NAME>` or,
following the Docker secrets convention, as a file path in `<NAME>_FILE` (e.g.
`/run/secrets/nl2sql_api_key`). The file wins; if it is configured but unusable the secret
is treated as missing (no silent fallback to a possibly stale env value) and startup
validation reports `SECRET_FILE_UNREADABLE`.

The file is re-read on every call (tiny, bounded) so a rotated secret takes effect without
a restart. Nothing here logs or formats secret values or file paths.
"""
import os
from dataclasses import dataclass, field
from typing import Literal, Mapping, Optional

# Literal names on purpose: the 32.1 drift guard scans the code for them.
SECRET_FILE_VARS: dict[str, str] = {
    "NL2SQL_API_KEY": "NL2SQL_API_KEY_FILE",
    "NVIDIA_API_KEY": "NVIDIA_API_KEY_FILE",
}

MAX_SECRET_FILE_BYTES = 64 * 1024


@dataclass(frozen=True)
class SecretResolution:
    name: str
    source: Literal["file", "env", "none"]
    value: Optional[str] = field(default=None, repr=False)
    error: Optional[Literal["unreadable", "empty", "too_large"]] = None
    conflict: bool = False

    @property
    def file_var(self) -> str:
        return SECRET_FILE_VARS[self.name]


def _read_secret_file(path: str) -> tuple[Optional[str], Optional[str]]:
    try:
        with open(path, "rb") as f:
            raw = f.read(MAX_SECRET_FILE_BYTES + 1)
    except OSError:
        return None, "unreadable"
    if len(raw) > MAX_SECRET_FILE_BYTES:
        return None, "too_large"
    try:
        value = raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        return None, "unreadable"
    if not value:
        return None, "empty"
    return value, None


def resolve_secret_detail(name: str, environ: Optional[Mapping[str, str]] = None) -> SecretResolution:
    file_var = SECRET_FILE_VARS[name]  # KeyError for anything outside the contract
    env = os.environ if environ is None else environ
    file_path = env.get(file_var) or None
    env_value = env.get(name) or None

    if file_path:
        value, error = _read_secret_file(file_path)
        return SecretResolution(name, "file", value, error, conflict=env_value is not None)
    if env_value:
        return SecretResolution(name, "env", env_value)
    return SecretResolution(name, "none")


def resolve_secret(name: str, environ: Optional[Mapping[str, str]] = None) -> Optional[str]:
    return resolve_secret_detail(name, environ).value


def known_secret_values(environ: Optional[Mapping[str, str]] = None) -> set[str]:
    """Every resolvable secret value, for redaction."""
    values = (resolve_secret(name, environ) for name in SECRET_FILE_VARS)
    return {v for v in values if v}
