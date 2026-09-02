# Installation

## Requirements

- Linux with `uinput` and `hidraw` (any recent kernel)
- Python 3.10+
- An Ulanzi Stream Controller **D200x**

## Install

```bash
git clone https://github.com/F-Amaral/d200x-button-box-linux d200x-button-box
cd d200x-button-box
python -m venv .venv && . .venv/bin/activate
pip install -e .
```

## Permissions

```bash
sudo cp udev/70-d200x.rules /etc/udev/rules.d/
sudo udevadm control --reload
sudo udevadm trigger --attr-match=idVendor=2207
echo uinput | sudo tee /etc/modules-load.d/uinput.conf
sudo modprobe uinput
```

Then **physically unplug and replug the deck** — `uaccess` is not applied to a
device that is already connected, and `udevadm trigger` does not fix that.

The rule filename must sort before systemd's `73-seat-late.rules`, hence `70-`.
It grants your logged-in user access to the deck's USB node, its `hidraw`
nodes, its keyboard `event` nodes, and `/dev/uinput`. If `uaccess` still doesn't
grant access on your setup, uncomment the `MODE="0666"` fallback lines in the
rule file and reload.

Optional — only if you use `{key: ...}` bindings on Wayland:

```bash
sudo pacman -S ydotool && systemctl --user enable --now ydotool
```

## First run

```bash
d200x-button-box init          # writes ~/.config/d200x-button-box/
d200x-buttonboxd               # run the daemon
```

Check the virtual gamepad with `evtest` or `jstest /dev/input/js0` — you should
see **D200x Button Box** and its buttons firing when you press deck keys.

To discover raw control ids (only needed if yours differ from the defaults):

```bash
d200x-button-box debug
```

## Run as a service

```bash
mkdir -p ~/.config/systemd/user
cp systemd/d200x-button-box.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now d200x-button-box
```

## Troubleshooting

| Symptom | Fix |
|--|--|
| `no D200x hidraw node` | `lsusb` to confirm `2207:0019`; try a USB 2.0 port straight off the motherboard |
| `open failed` / permission denied | rule not applied — reinstall `70-d200x.rules`, reload, **physically replug**; check `getfacl /dev/bus/usb/.../<dev>` lists your user |
| deck shows a colour-circle animation, stops responding | the `heartbeat_seconds` watchdog isn't running — check the daemon is alive; don't set it to 0 |
| `d200x-button-box debug` prints nothing on keypress | expected before the SET_BUTTONS handshake — `debug` sends it automatically now; if still nothing, capture and open an issue |
| keys type `calc` / `cmd` into your terminal | the deck's firmware keyboard — the daemon grabs it (`grab_keyboard: true`); make sure the daemon is running |
