# d200x-button-box

Use an **Ulanzi Stream Controller D200x** as an auxiliary button box for sim
racing on Linux. The daemon reads the deck over USB-HID and re-emits every key,
aux button and encoder as a **virtual gamepad** (`uinput`), so any game — native
or Proton/Wine — sees an ordinary controller you can bind. Per-binding
keystrokes and shell commands are available too, plus per-game profiles,
multi-page layouts, and text/icon labels on the keys.

Built for *Le Mans Ultimate* first, *Assetto Corsa EVO* second, in VR.

> ⚠️ **Vibe-coded.** This entire repository was written through LLM-assisted
> "vibe coding" — exploratory, prompt-driven, with the hardware in the loop.
> It works on the author's setup but has had no formal review. Read the code
> before you rely on it.

## Quickstart

```bash
git clone <this repo> ~/Projetos/d200x-button-box && cd ~/Projetos/d200x-button-box
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
Already bound things in Le Mans Ultimate? "Import from game" pulls the control
names back onto the deck so you can see what each button does.

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

The wire protocol was reverse-engineered by the
[strmdck](https://github.com/redphx/strmdck),
[ulanzi-d200-linux](https://github.com/racerxdl/ulanzi-d200-linux),
[Ulanzi-Deck-Linux](https://github.com/Tyaaa-aa/Ulanzi-Deck-Linux) and
[companion-surface-d200](https://github.com/jcalado/companion-surface-d200)
projects — details in [docs/hardware.md](docs/hardware.md). MIT licensed.
