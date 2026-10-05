"""Measure layout rendering and HID writes, restoring the running service.

Run with the application's Python environment. Without --hardware only render
layouts; --hardware temporarily stops the user service to own the deck safely.
Results measure host write completion, not firmware screen draw completion.
"""
import argparse
import errno
import json
import os
from pathlib import Path
import statistics
import subprocess
import time
import urllib.request

from d200x_button_box import config, device, layout, protocol


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hardware", action="store_true")
    parser.add_argument("--server", action="store_true", help="Exercise live API switching and measure HTTP responsiveness")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    if args.server and args.hardware:
        parser.error("--server and --hardware are separate benchmarks")
    settings = config.Settings.load()
    base = f"http://127.0.0.1:{settings.api.port}/api/"
    headers = {"X-Token": settings.api.token} if settings.api.token else {}
    def api(path, body=None):
        req = urllib.request.Request(base + path, headers=headers,
                                     data=json.dumps(body).encode() if body is not None else None)
        if body is not None:
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.load(response)
    if args.server:
        saved = api("state")
        samples = []
        try:
            for repeat in range(args.repeats):
                for name in config.list_profiles():
                    profile = config.load_profile(name)
                    for index in range(profile.n_pages):
                        started = time.perf_counter()
                        if index == 0:
                            api("activate", {"profile": name})
                        else:
                            api("page", {"page": index})
                        acknowledged = time.perf_counter()
                        state = api("state")
                        read = time.perf_counter()
                        samples.append(dict(profile=name, page=index, repeat=repeat,
                                            request_ms=(acknowledged-started)*1000,
                                            state_request_ms=(read-acknowledged)*1000,
                                            connected=state["device"]["connected"]))
                        time.sleep(0.4)  # separate destinations, allow cold preparation
        finally:
            api("activate", {"profile": saved["profile"]["forced"] or "auto"})
            time.sleep(0.4)
            api("page", {"page": saved["profile"]["page"]})
        output = json.dumps({"server_samples": samples}, indent=2)
        if args.output:
            args.output.write_text(output + "\n")
        print(output)
        return
    env = dict(os.environ, XDG_RUNTIME_DIR=f"/run/user/{os.getuid()}",
               DBUS_SESSION_BUS_ADDRESS=f"unix:path=/run/user/{os.getuid()}/bus")
    def service(action):
        return subprocess.run(["systemctl", "--user", action, "d200x-button-box.service"],
                              env=env, check=True, capture_output=True)
    saved = None
    if args.hardware:
        saved = api("state")
        service("stop")
    samples = []
    dev = None
    archive_count = [0]
    original_archive = layout._archive
    def counted_archive(*arguments):
        archive_count[0] += 1
        return original_archive(*arguments)
    layout._archive = counted_archive
    try:
        if args.hardware:
            dev = device.Device()
        for name in config.list_profiles():
            profile = config.load_profile(name)
            for index, page in enumerate(profile.pages):
                for repeat in range(args.repeats):
                    archive_count[0] = 0
                    start = time.perf_counter()
                    payload = layout.build_set_buttons(page, settings.icon, settings.orientation)
                    rendered = time.perf_counter()
                    packets = protocol.frame_packets(protocol.CMD_SET_BUTTONS, payload)
                    framed = time.perf_counter()
                    transient = short = 0
                    write_ms = None
                    if dev:
                        start_write = time.perf_counter()
                        for packet in packets:
                            wire = b"\x00" + packet
                            try:
                                count = os.write(dev._fd, wire)
                                short += count != len(wire)
                            except OSError as error:
                                if error.errno in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EINTR):
                                    transient += 1
                                else:
                                    raise
                        write_ms = (time.perf_counter() - start_write) * 1000
                    samples.append(dict(profile=name, page=index, repeat=repeat,
                                        render_ms=(rendered-start)*1000,
                                        framing_ms=(framed-rendered)*1000,
                                        payload_bytes=len(payload), packets=len(packets),
                                        archive_attempts=archive_count[0], payload_safe=layout._payload_safe(payload),
                                        write_ms=write_ms, dropped_writes=transient, short_writes=short))
                    if dev:
                        dev.heartbeat()
                        time.sleep(0.3)  # separate uploads; not part of measured time
    finally:
        layout._archive = original_archive
        if dev:
            dev.close()

        if saved:
            service("start")
            # Preserve the user's current profile/page without changing YAML.
            for attempt in range(30):
                try:
                    api("state")
                    break
                except OSError:
                    time.sleep(0.5)
            api("activate", {"profile": saved["profile"]["forced"] or "auto"})
            time.sleep(0.5)
            api("page", {"page": saved["profile"]["page"]})

    result = {"samples": samples, "hardware": args.hardware,
              "median_render_ms": statistics.median(s["render_ms"] for s in samples),
              "median_write_ms": statistics.median(s["write_ms"] for s in samples) if args.hardware else None}
    output = json.dumps(result, indent=2)

    if args.output:
        args.output.write_text(output + "\n")

    print(output)


if __name__ == "__main__":
    main()
