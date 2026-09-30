import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "vr-noise-mask"
CONFIG_PATH = CONFIG_DIR / "config.json"
STATE_PATH = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "vr-noise-mask.json"

DEFAULTS = {
    "volume_pct": 10,
    "device_match": "index",
    "enabled": True,
}


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    try:
        loaded = json.loads(CONFIG_PATH.read_text())
        cfg.update({k: v for k, v in loaded.items() if k in DEFAULTS})
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return cfg


def save_config(cfg: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2))
    tmp.replace(CONFIG_PATH)  # atomic, so the daemon never reads a half-written file


def read_state() -> dict:
    """Daemon-published runtime state: {"pid": int, "active": bool}. Empty if
    the daemon isn't running."""
    try:
        state = json.loads(STATE_PATH.read_text())
        pid = int(state["pid"])
        os.kill(pid, 0)
        if b"vr_noise_mask" not in Path(f"/proc/{pid}/cmdline").read_bytes():
            return {}  # stale file, PID reused by something else
        return state
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return {}


def write_state(active: bool):
    STATE_PATH.write_text(json.dumps({"pid": os.getpid(), "active": active}))


def clear_state():
    try:
        STATE_PATH.unlink()
    except OSError:
        pass
