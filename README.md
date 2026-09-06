# DS Movies — MP4 → DPG converter

Convert videos into **`.dpg`** files you can play in **Moonshell** on a **Nintendo DS / DS Lite** with an **R4** (or similar) flashcart.

There are two tools in this folder — use whichever you prefer:

| Tool | Best for | Needs |
|------|----------|-------|
| **`dpg-convert.py`** (terminal) | Full movies, batches, speed | Python 3 + native `ffmpeg` |
| **`dpg-converter.html`** (browser) | Quick one-offs, no install | Just a browser + a local web server |

Both produce the same DPG format. The terminal tool is much faster and handles long movies; the browser tool needs nothing installed but is slower.

---

## What a DPG is

A `.dpg` is the video container Moonshell plays on the DS. Inside it:

- **Video** — MPEG-1, **256×192** (the DS screen size)
- **Audio** — MP2 or 16-bit PCM stereo
- **Header** — tells Moonshell where the audio/video/thumbnail live

There are several versions. Which one you want depends on your Moonshell:

| Version | Audio | Extras | Use it for |
|---------|-------|--------|------------|
| **DPG4** | MP2 | Thumbnail + fast-seek index | **Moonshell 2** (most modern R4 setups) — **default** |
| **DPG2** | MP2 | Fast-seek index | **Moonshell 1.x** |
| **DPG0** | 16-bit PCM stereo | — | Classic / oldest Moonshell 1.x |

> If a video won't open on your card, you're probably on a different Moonshell version — try another `-V`.

---

## 1. Terminal tool — `dpg-convert.py`

### Requirements

- **Python 3** (already installed if `python --version` works)
- **native `ffmpeg`** (with `ffprobe`)

Install ffmpeg once:

```bash
winget install --id Gyan.FFmpeg -e
```

Then **open a new terminal** so it's found. The script also **auto-detects** an ffmpeg that winget installed even if it isn't on your PATH, so in most cases it just works. If not, point it at the binary with `--ffmpeg C:\path\to\ffmpeg.exe`.

### Quick start

```bash
python dpg-convert.py movie.mp4
```

That makes `movie.dpg` next to the input, using the Moonshell 2 defaults (DPG4, MP2 audio, the source's own frame rate, fills the 256×192 screen).

### All commands / options

```
python dpg-convert.py [options] INPUT [INPUT ...]
```

| Option | Default | What it does |
|--------|---------|--------------|
| `INPUT` | — | One or more video files (`.mp4`, `.mkv`, `.mov`, `.avi`, `.webm`, …). Wildcards like `*.mp4` work. |
| `-o, --output PATH` | next to input | Output `.dpg` file (single input) or a **folder** (for batches). |
| `-V, --dpg-version {0,2,4}` | `4` | DPG version. `4` = Moonshell 2, `2` = Moonshell 1.x, `0` = classic PCM. |
| `-a, --audio {pcm,mp2}` | mp2 (v4/v2), pcm (v0) | Force the audio codec. |
| `-r, --fps FPS` | `auto` | `auto` matches the source video's frame rate; or give a number (e.g. `15`, `24`). Auto is capped at 30 for smooth DS playback. |
| `-b, --bitrate KBPS` | `768` | Video bitrate in kbps. Lower = smaller files; higher = better quality. |
| `--rate HZ` | 32768 (PCM) / 32000 (MP2) | Audio sample rate. |
| `--ab KBPS` | `128` | MP2 audio bitrate. |
| `-s, --start T` | start | Start time — `00:01:30` or seconds like `90`. |
| `-t, --duration T` | whole video | How much to encode — `120` (seconds) or `00:02:00`. |
| `--letterbox` | off | Fit inside 256×192 with **black bars** (keeps whole frame, no cropping). |
| `--stretch` | off | Stretch to 256×192, **ignoring aspect ratio** (distorts). |
| `--color16` | off | Reduce each frame to 16-bit color (RGB565). Off = best quality. |
| `--ffmpeg PATH` | auto | Path to the `ffmpeg` binary. |
| `--ffprobe PATH` | auto | Path to the `ffprobe` binary. |
| `--keep-temp` | off | Keep the intermediate audio/video files (for debugging). |
| `-q, --quiet` | off | No progress bars. |
| `--verbose` | off | Print the exact ffmpeg commands. |

### How the video fits the screen

The DS screen is 256×192. By default the tool **fills** it:

- **Fill** (default) — scales the video to cover the whole screen, then crops the overflow. No black bars, no distortion, but the edges of very wide/tall videos get cut.
- **`--letterbox`** — shows the *entire* frame with black bars where it doesn't fit. Nothing is cropped.
- **`--stretch`** — forces the exact frame into 256×192, squishing it. Rarely what you want.

### Examples

Convert a whole movie for Moonshell 2 (default):
```bash
python dpg-convert.py movie.mp4
```

Just a 5-minute clip starting at 10:00:
```bash
python dpg-convert.py movie.mp4 -s 00:10:00 -t 300 -o clip.dpg
```

Keep the whole frame with black bars instead of cropping:
```bash
python dpg-convert.py movie.mp4 --letterbox
```

Smaller file (lower bitrate + 15 fps):
```bash
python dpg-convert.py movie.mp4 -b 384 -r 15
```

Classic PCM format for old Moonshell 1.x:
```bash
python dpg-convert.py movie.mp4 -V 0
```

Convert every mp4 in the folder into a `dpg_out` directory:
```bash
python dpg-convert.py *.mp4 -o dpg_out/
```

---

## 2. Browser tool — `dpg-converter.html`

No install needed, but it can't be opened by double-clicking (the video engine won't start from a `file://` page). Serve the folder locally:

```bash
python -m http.server 8000
```

Then open **http://localhost:8000/dpg-converter.html**, drop in a video, pick your settings, and click **Convert**. Use the **Test encoder support** button first to confirm your browser can run it.

It's slower than the terminal tool and best for short clips.

---

## Getting the video onto your DS

1. Copy the `.dpg` file to your R4 microSD card (a `/DPG` or `/MOONSHL2` folder is tidy, but anywhere works).
2. Put the card in the DS, boot it, open **Moonshell**, browse to the file, and play.

---

## Tips & troubleshooting

- **`ffmpeg was not found`** — install it (see above) and open a **new** terminal, or pass `--ffmpeg <path>`.
- **The video won't play on the DS** — your card is probably on a different Moonshell version. Try `-V 2` (Moonshell 1.x) or `-V 0` (classic).
- **Audio silent or wrong speed on DPG0/PCM** — use the default DPG4 (or `-V 2`) with MP2 audio.
- **Big files / long encode** — a full-length movie makes a large `.dpg` (hundreds of MB) and takes a few minutes. Trim with `-s` / `-t`, or lower `-b`.
- **A file reports the wrong length** — some videos have incorrect duration info in their metadata. The tool reads the video stream directly, so it still converts the whole thing; if you only want part, use `-s` / `-t`.
- **See what ffmpeg is doing** — add `--verbose`.

---

*Output format verified against the dpg4x / dpgconv reference converters. Video is standard MPEG-1; audio is MP2 or 16-bit PCM.*
