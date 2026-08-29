"""d200x-button-box command-line entrypoint."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import DEFAULT_PATH, Config, default_yaml


def _setup_log(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def cmd_run(args) -> int:
    _setup_log(args.log_level)
    from .daemon import Daemon

    Daemon(Config.load(args.config)).run()
    return 0


def cmd_debug(args) -> int:
    """Dump every raw HID report plus the parser's best guess.

    Use this the first time you plug the deck in: press each key and turn each
    knob, and note which `index` / action each one produces. That is what the
    `keys:` / `knobs:` sections of the config refer to.
    """
    _setup_log("INFO")
    import time

    from . import protocol
    from .device import Device
    from .keyboard import KeyboardSink

    out = open(args.out, "w", buffering=1) if args.out else None
    dev = Device()
    dev.send_init()  # without a SET_BUTTONS upload the device reports nothing

    def emit(line: str) -> None:
        print(line)
        if out:
            out.write(line + "\n")

    print(f"reading {dev.path}. Press keys / turn knobs. Ctrl-C to stop.")
    if not args.no_grab:
        print("(grabbing the deck keyboard so its factory macros don't fire)")
    print()
    try:
        with KeyboardSink(enabled=not args.no_grab):
            while True:
                raw = dev.read_raw(0.2)
                if raw:
                    ev = protocol.parse_input(raw)
                    if ev:
                        guess = f"{ev.name} {ev.action}"
                    elif raw[2:4] == b"\x01\x0b":
                        guess = "(ack)"
                    else:
                        guess = "(unparsed)"
                    emit(f"{time.strftime('%H:%M:%S')}  {raw[:16].hex(' ')}   ->  {guess}")
    except KeyboardInterrupt:
        pass
    finally:
        dev.close()
        if out:
            out.close()
    return 0


def cmd_gen_config(args) -> int:
    path = Path(args.config or DEFAULT_PATH)
    if path.exists() and not args.force:
        print(f"{path} already exists; pass --force to overwrite", file=sys.stderr)
        return 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(default_yaml())
    print(f"wrote {path}")
    return 0


def cmd_enum(args) -> int:
    """List the D200x hidraw nodes, their USB interface, and access perms."""
    import subprocess

    from .device import list_hidraw

    nodes = list_hidraw()
    if not nodes:
        print("no D200x hidraw node — check `lsusb` / try another USB port", file=sys.stderr)
        return 1
    for path, iface in nodes:
        role = {0: "deck protocol", 1: "HID keyboard"}.get(iface, "?")
        ls = subprocess.run(["ls", "-l", path], capture_output=True, text=True).stdout.strip()
        print(f"{path}  interface={iface} ({role})")
        print(f"    {ls}")
    return 0


def cmd_status(args) -> int:
    _setup_log("WARNING")
    from .device import Device

    try:
        dev = Device()
    except RuntimeError as ex:
        print(ex, file=sys.stderr)
        return 1
    print("D200x reachable.")
    dev.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-c", "--config", help=f"config path (default: {DEFAULT_PATH})")

    p = argparse.ArgumentParser(prog="d200x-button-box")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", parents=[common], help="run the daemon (deck -> virtual gamepad)")
    r.add_argument("--log-level", default="INFO")
    r.set_defaults(func=cmd_run)

    d = sub.add_parser("debug", parents=[common],
                       help="dump raw HID reports to discover your control ids")
    d.add_argument("--out", metavar="FILE", help="also write the report lines to FILE")
    d.add_argument("--no-grab", action="store_true",
                   help="do not grab the deck keyboard (factory macros will fire)")
    d.set_defaults(func=cmd_debug)

    g = sub.add_parser("gen-config", parents=[common], help="write a starter config.yaml")
    g.add_argument("--force", action="store_true")
    g.set_defaults(func=cmd_gen_config)

    sub.add_parser("status", parents=[common],
                   help="check the deck is reachable").set_defaults(func=cmd_status)

    sub.add_parser("enum", parents=[common],
                   help="list the deck's HID interfaces + device-node perms").set_defaults(func=cmd_enum)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
