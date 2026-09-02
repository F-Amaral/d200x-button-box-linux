# d200x-button-box

Use an **Ulanzi Stream Controller D200x** as an auxiliary button box for sim
racing on Linux. The daemon reads the deck over USB-HID and re-emits every key,
aux button and encoder as a **virtual gamepad** (`uinput`), so any game — native
or Proton/Wine — sees an ordinary controller you can bind.

Built for *Le Mans Ultimate*, *Assetto Corsa EVO* and *Assetto Corsa Rally*, in VR.

> ⚠️ **Vibe-coded.** This entire repository was written through LLM-assisted
> "vibe coding" — exploratory, prompt-driven, with the hardware in the loop.
> It works on the author's setup but has had no formal review. Read the code
> before you rely on it.

## Features

- **Every control is a gamepad button.** 13 LCD keys, the wide status key, 2 aux
  buttons and 3 clickable encoders map to a virtual controller any game can bind
  — native or Proton/Wine. Encoder detents fire one pulse each.
- **Per-game profiles**, switched automatically when a game's process appears
  and dropped when it quits. A `launcher` profile sits on the deck in between
  with buttons that start games and jump into profiles.
- **Multi-page layouts** — 13 keys × N pages, paged with the aux buttons.
- **Labels and icons** on the keys: text, an uploaded image, ISO 7000
  automotive tell-tales (headlights, indicators, wipers, TC, ABS…), or Material
  Icons. A visual icon editor in the web UI for tweaks.
- **Import from a game** — read a game's own controller config and label each
  deck key with what it's actually bound to.
- **Bind-to-game** — the reverse: pick an in-game action in the web UI and it's
  written straight into the game's config.
- **Keystroke and shell-command bindings** too, plus a `hold:` second action on
  any key, and a global **home** button that pops to the launcher mid-race.
- **Web UI** on `http://localhost:8377` — edit everything live, reachable from a
  phone. No build step.

### Game support

"Import" reads the game's bindings onto the deck; "bind-to-game" writes your
choices back into the game.

| Game | Import | Bind-to-game |
|--|:--:|:--:|
| Le Mans Ultimate | ✅ | ✅ |
| Assetto Corsa EVO | ✅ | ✅ |
| Assetto Corsa Rally | ✅ | ✅ |

The deck works as a plain controller in **any** game; the table is only about
the config-file integration. Close the game before writing — each one reads its
controller config at startup.

## Quickstart

```bash
git clone https://github.com/F-Amaral/d200x-button-box-linux d200x-button-box && cd d200x-button-box
python -m venv .venv && . .venv/bin/activate && pip install -e .

sudo cp udev/70-d200x.rules /etc/udev/rules.d/
sudo udevadm control --reload && sudo udevadm trigger --attr-match=idVendor=2207
echo uinput | sudo tee /etc/modules-load.d/uinput.conf && sudo modprobe uinput
# then physically unplug/replug the deck

d200x-button-box init      # ~/.config/d200x-button-box/
d200x-buttonboxd           # run the daemon (+ config UI on http://localhost:8377)
```

Bind the **D200x Button Box** controller in your game's control settings, and
open `http://localhost:8377` to edit bindings, labels, icons and profiles (set
`api.host: 0.0.0.0` + a token in `settings.yaml` to reach it from a phone).
Already have things bound in a supported game? **Import from a game** pulls the
control names back onto the deck so you can see what each button does.

## Docs

- [Installation](docs/installation.md) — dependencies, permissions, service, troubleshooting
- [Configuration](docs/configuration.md) — settings, profiles, pages, bindings, the home button
- [Control API](docs/api.md) — the daemon's HTTP + SSE API
- [Hardware notes](docs/hardware.md) — the D200x, the wire protocol, firmware quirks, credits
- [Roadmap](plans/roadmap.md) — what's done, what's next

## Disclaimer

This software is provided **"as is", without warranty of any kind**, express or
implied. It talks to your USB hardware and creates virtual input devices using
an unofficial, reverse-engineered protocol. **You** are solely responsible for
any damage to your device, computer, or data, and for any consequences of using
it. If that's not acceptable, don't use it. See [LICENSE](LICENSE).

## Credits

Deck icons: **ISO 7000** automotive tell-tale symbols (public domain, via
Wikimedia Commons) and **Material Icons** (Apache-2.0), both bundled.

The wire protocol was reverse-engineered by the
[strmdck](https://github.com/redphx/strmdck),
[ulanzi-d200-linux](https://github.com/racerxdl/ulanzi-d200-linux),
[Ulanzi-Deck-Linux](https://github.com/Tyaaa-aa/Ulanzi-Deck-Linux) and
[companion-surface-d200](https://github.com/jcalado/companion-surface-d200)
projects — details in [docs/hardware.md](docs/hardware.md). MIT licensed.
