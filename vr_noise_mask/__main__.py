"""vr-noise-mask run | get | set [--volume N] [--enabled on|off] [--device MATCH]"""
import argparse
import json

from .config import load_config, read_state, save_config
from .noise import VOLUME_MAX_PCT


def main():
    ap = argparse.ArgumentParser(prog="vr-noise-mask", description=__doc__)
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("run", help="run the generator (default)")
    sub.add_parser("get", help="print config and runtime state as JSON")
    s = sub.add_parser("set", help="change settings; a running generator applies them live")
    s.add_argument("--volume", type=int, help=f"0-{VOLUME_MAX_PCT}")
    s.add_argument("--enabled", choices=("on", "off"))
    s.add_argument("--device", help="substring of the output device/sink name")
    args = ap.parse_args()

    if args.cmd == "get":
        state = read_state()
        print(json.dumps({**load_config(), "running": bool(state), "active": state.get("active", False)}))
    elif args.cmd == "set":
        cfg = load_config()
        if args.volume is not None:
            cfg["volume_pct"] = max(0, min(args.volume, VOLUME_MAX_PCT))
        if args.enabled:
            cfg["enabled"] = args.enabled == "on"
        if args.device is not None:
            cfg["device_match"] = args.device
        save_config(cfg)
    else:
        from .daemon import run  # heavy imports (numpy, pyaudio) only when generating
        run()


main()
