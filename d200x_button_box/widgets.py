"""Live cell widgets.

A key binding with a `widget:` field is drawn by us, not the firmware, and the
daemon re-renders it on a timer and pushes just that cell in place (partial
update, `protocol.CMD_PARTIAL_UPDATE`). No firmware clock/stat overlay, so it
rotates with `device.orientation` like any other icon.

    keys:
      13: {widget: clock}                          # replaces the firmware status clock
      3:  {widget: sysload}                         # CPU / RAM bars
      4:  {widget: shell, cmd: "cat /x", interval: 5, unit: "%"}

Providers are pure `render(binding, size, style) -> png | None`. `interval()`
says how often the daemon should re-check.
"""

from __future__ import annotations

import subprocess
import time

KINDS = ("clock", "sysload", "shell")


def is_widget(binding: dict | None) -> str | None:
    """The widget kind of a binding, if it is one."""
    kind = (binding or {}).get("widget")
    return kind if kind in KINDS else None


def interval(binding: dict) -> float:
    """Seconds between re-renders. `clock` re-checks often but only actually
    changes on the minute; `shell` honours its own `interval`."""
    kind = binding.get("widget")
    if kind == "clock":
        return 15.0
    if kind == "sysload":
        return 2.0
    if kind == "shell":
        return max(1.0, float(binding.get("interval", 5)))
    return 5.0


# --- CPU / RAM from /proc (also feeds the firmware "load" strip) ------------- #
_cpu_prev: tuple[int, int] | None = None


def sysload() -> tuple[int, int, int]:
    """(cpu%, mem%, gpu%). gpu is always 0 -- no portable source."""
    global _cpu_prev
    cpu = 0
    try:
        with open("/proc/stat") as f:
            parts = [int(x) for x in f.readline().split()[1:]]
        idle, total = parts[3] + parts[4], sum(parts)
        if _cpu_prev and total > _cpu_prev[1]:
            cpu = round(100 * (1 - (idle - _cpu_prev[0]) / (total - _cpu_prev[1])))
        _cpu_prev = (idle, total)
    except OSError:
        pass
    mem = 0
    try:
        info: dict[str, int] = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, _, v = line.partition(":")
                info[k] = int(v.split()[0])
        if info.get("MemTotal"):
            mem = round(100 * (1 - info.get("MemAvailable", 0) / info["MemTotal"]))
    except OSError:
        pass
    return max(0, min(100, cpu)), max(0, min(100, mem)), 0


# --- rendering ------------------------------------------------------------- #
def render(binding: dict, size: tuple[int, int] | None, style: dict) -> bytes | None:
    kind = binding.get("widget")
    if kind == "clock":
        return _text_tile(time.strftime("%H:%M"), style, size)

    if kind == "sysload":
        cpu, mem, _ = sysload()
        return _bars(style, [("CPU", cpu), ("RAM", mem)], size)

    if kind == "shell":
        try:
            out = subprocess.run(binding["cmd"], shell=True, capture_output=True,
                                 text=True, timeout=3).stdout.strip().splitlines()
            txt = (out[0] if out else "") + str(binding.get("unit", ""))
        except (OSError, subprocess.SubprocessError, KeyError):
            txt = "err"
        return _text_tile(txt[:8], style, size)

    return None


def _text_tile(text: str, style: dict, size: tuple[int, int] | None) -> bytes:
    """Big centred text, no frame -- for the wide strip and value widgets."""
    import io

    from . import layout

    Image, ImageDraw, _ = layout._pil()
    s = layout.merge_style(style)
    W, H = size or (layout.ICON_SIZE, layout.ICON_SIZE)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for frac in (0.6, 0.5, 0.42, 0.34, 0.28):
        font = layout._text_font(s["font"], round(H * frac))
        box = d.textbbox((0, 0), text, font=font)
        if box[2] - box[0] <= W * 0.9:
            break
    box = d.textbbox((0, 0), text, font=font)
    d.text(((W - (box[2] - box[0])) / 2 - box[0], (H - (box[3] - box[1])) / 2 - box[1]),
           text, font=font, fill=s["fg"])
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _bars(style: dict, rows: list[tuple[str, int]], size: tuple[int, int] | None) -> bytes:
    """A tiny labelled bar chart (0-100 each row): `LABEL ▮▮▮▯▯ 42`."""
    import io

    from . import layout

    Image, ImageDraw, _ = layout._pil()
    s = layout.merge_style(style)
    W, H = size or (layout.ICON_SIZE, layout.ICON_SIZE)
    wide = W > H * 1.3          # the status strip: label + bar + value on one line
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    n = len(rows)
    fs = round(H * (0.18 if wide else 0.16))
    font = layout._text_font(s["font"], fs)
    pad = round(min(W, H) * 0.09)

    def bar(x0, x1, y, h, pct):
        d.rounded_rectangle((x0, y, x1, y + h), radius=h * 0.35, outline=s["border"], width=2)
        if pct:
            fill = "#c0392b" if pct >= 90 else s["fg"]
            d.rounded_rectangle((x0, y, x0 + (x1 - x0) * pct / 100, y + h), radius=h * 0.35, fill=fill)

    if wide:
        lab_w = max(d.textlength(name, font=font) for name, _ in rows) + fs * 0.4
        row_h = (H - 2 * pad) / n
        for i, (name, pct) in enumerate(rows):
            pct = max(0, min(100, pct))
            cy = pad + i * row_h + row_h / 2
            d.text((pad, cy - fs / 2), name, font=font, fill=s["fg"])
            d.text((W - pad - d.textlength(str(pct), font=font), cy - fs / 2), str(pct), font=font, fill=s["fg"])
            bar(pad + lab_w, W - pad - fs * 2.2, cy - fs * 0.35, fs * 0.7, pct)
    else:
        row_h = (H - 2 * pad) / n
        bh = fs * 0.7
        for i, (name, pct) in enumerate(rows):
            pct = max(0, min(100, pct))
            y = pad + i * row_h
            d.text((pad, y), f"{name} {pct}", font=font, fill=s["fg"])
            bar(pad, W - pad, y + fs * 1.25, bh, pct)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
