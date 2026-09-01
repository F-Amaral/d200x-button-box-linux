"""d200x-button-box command-line entrypoint (and the `d200x-buttonboxd` daemon)."""

from __future__ import annotations

import argparse
import logging
import sys

from . import config


def _setup_log(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


_lock_handle = None


def _acquire_lock() -> bool:
    """Single-instance guard: one daemon per machine (it owns the one deck)."""
    import fcntl

    global _lock_handle
    path = config.CONFIG_DIR / "daemon.lock"
    _lock_handle = open(path, "w")
    try:
        fcntl.flock(_lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def cmd_run(args) -> int:
    _setup_log(args.log_level)
    config.bootstrap()
    if not _acquire_lock():
        print("another d200x-buttonboxd is already running", file=sys.stderr)
        return 1
    from .daemon import Daemon

    store = config.ConfigStore()
    if args.profile:
        store.force_profile(args.profile)
        store.resolve()
    daemon = Daemon(store)

    if not args.no_api:
        try:
            from .api import serve

            serve(daemon, store.settings.api)  # background thread
        except ImportError:
            logging.getLogger(__name__).info("API not available yet -- daemon only")

    daemon.run()
    return 0


def cmd_debug(args) -> int:
    """Dump every raw HID report plus the parser's best guess."""
    _setup_log("INFO")
    import time as _t

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
                    emit(f"{_t.strftime('%H:%M:%S')}  {raw[:16].hex(' ')}   ->  {guess}")
    except KeyboardInterrupt:
        pass
    finally:
        dev.close()
        if out:
            out.close()
    return 0


def cmd_init(args) -> int:
    """Create the config dir with settings.yaml + starter profiles."""
    config.bootstrap()
    print(f"config in {config.CONFIG_DIR}")
    print(f"  settings: {config.SETTINGS_PATH}")
    for name in config.list_profiles():
        print(f"  profile:  {config.profile_path(name)}")
    return 0


def cmd_profiles(args) -> int:
    config.bootstrap()
    settings = config.Settings.load()
    for name in config.list_profiles():
        marker = " *" if name == settings.active_profile else ""
        print(f"{name}{marker}")
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


def cmd_icons(args) -> int:
    from . import compose, config, glyphs

    if args.icons_cmd == "action":
        if args.glyph is None and not args.clear:
            cur = glyphs.action_icon_map().get(glyphs._norm(args.label))
            print(f"{args.label!r} -> {cur or '(auto)'}")
            return 0
        glyphs.set_action_icon(args.label, None if args.clear else args.glyph)
        print(f"{args.label!r} -> {'(auto)' if args.clear else args.glyph}"
              f"   ({config.CONFIG_DIR / 'action_icons.yaml'})")
        return 0

    if args.icons_cmd == "new":
        name = args.name.strip().lower()
        if compose.effective_spec(name) is not None and not args.force:
            print(f"{name!r} already exists (use --force to reset it)", file=sys.stderr)
            return 1
        seed = {"base": args.base} if args.base else {"layers": []}
        compose.save_user_spec(name, seed)
        print(f"created {name!r} -> {config.user_icons_dir() / (name + '.png')}")
        print("edit it in the web icon editor (Icons button), or in "
              f"{config.user_icons_dir().parent / 'icons.yaml'}")
        return 0

    if args.icons_cmd == "promote":
        for name in args.names:
            try:
                png = compose.promote_spec(name)
            except KeyError:
                print(f"unknown composed icon: {name}", file=sys.stderr)
                return 1
            print(f"promoted {name} -> {png}")
        print("now commit the PNG(s) + d200x_button_box/assets/composed.yaml")
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


def _add_run_args(p) -> None:
    p.add_argument("--log-level", default="INFO")
    p.add_argument("--profile", help="force this profile instead of auto/settings")
    p.add_argument("--no-api", action="store_true", help="do not start the HTTP API")
    p.set_defaults(func=cmd_run)


def build_daemon_parser() -> argparse.ArgumentParser:
    """`d200x-buttonboxd [OPTIONS]` -- the run subcommand, flattened."""
    p = argparse.ArgumentParser(prog="d200x-buttonboxd")
    _add_run_args(p)
    return p


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="d200x-button-box")
    sub = p.add_subparsers(dest="cmd", required=True)

    _add_run_args(sub.add_parser("run", help="run the daemon (deck -> virtual gamepad + API)"))

    d = sub.add_parser("debug", help="dump raw HID reports to discover your control ids")
    d.add_argument("--out", metavar="FILE", help="also write the report lines to FILE")
    d.add_argument("--no-grab", action="store_true", help="do not grab the deck keyboard")
    d.set_defaults(func=cmd_debug)

    sub.add_parser("init", help="create settings.yaml + starter profiles").set_defaults(func=cmd_init)
    sub.add_parser("profiles", help="list profiles").set_defaults(func=cmd_profiles)
    sub.add_parser("enum", help="list the deck's HID interfaces + perms").set_defaults(func=cmd_enum)
    sub.add_parser("status", help="check the deck is reachable").set_defaults(func=cmd_status)

    ic = sub.add_parser("icons", help="composed (parametric) icon maintenance")
    ics = ic.add_subparsers(dest="icons_cmd", required=True)
    nw = ics.add_parser("new", help="create a blank user composed icon to edit in the web editor")
    nw.add_argument("name", metavar="NAME", help="new icon name, e.g. turn_left")
    nw.add_argument("--base", metavar="TELLTALE", help="start from this tell-tale as the base")
    nw.add_argument("--force", action="store_true", help="overwrite if it exists")
    ac = ics.add_parser("action", help="default icon for a control label (all keys with that label)")
    ac.add_argument("label", metavar="LABEL", help='e.g. "Cycle Lights"')
    ac.add_argument("glyph", nargs="?", help="glyph / composed-icon name (omit to show current)")
    ac.add_argument("--clear", action="store_true", help="remove the override (back to auto)")
    pr = ics.add_parser("promote", help="bake a tuned icon into the shipped defaults + assets/composed.yaml")
    pr.add_argument("names", nargs="+", metavar="NAME", help="composed-icon name(s), e.g. seat_fore")
    ic.set_defaults(func=cmd_icons)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


def daemon_main(argv=None) -> int:
    """Entry point for the `d200x-buttonboxd` console script."""
    args = build_daemon_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
