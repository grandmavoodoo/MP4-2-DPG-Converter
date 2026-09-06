#!/usr/bin/env python3
"""
dpg-convert.py  -  Convert video to Nintendo DS .DPG (Moonshell / R4).

Terminal companion to dpg-converter.html. Uses a native `ffmpeg` binary for the
heavy lifting (fast, handles full-length movies) and assembles the .dpg container
itself. The container format is byte-for-byte the same as the HTML tool and matches
the dpg4x / dpgconv reference converters.

  Video : MPEG-1, 256x192 (fills the screen by default; --letterbox / --stretch)
  Audio : 16-bit PCM stereo (DPG0) or MP2 stereo (DPG2/DPG4)
  Output: DPG0 (classic Moonshell 1.x), DPG2 (+seek), or DPG4 (+thumbnail, Moonshell 2)

Examples
  python dpg-convert.py movie.mp4
  python dpg-convert.py movie.mkv -V 4 -r 24 -b 768
  python dpg-convert.py clip.mp4 -s 00:01:30 -t 120 -o out.dpg
  python dpg-convert.py *.mp4 -o dpg_out/          # batch
"""
import argparse, os, sys, struct, shutil, subprocess, tempfile, glob

MP2_RATES = {48000, 44100, 32000, 24000, 22050, 16000}

# --------------------------------------------------------------------------- #
#  ffmpeg discovery
# --------------------------------------------------------------------------- #
def find_tool(name, override=None):
    if override:
        if os.path.isfile(override):
            return override
        found = shutil.which(override)
        if found:
            return found
    found = shutil.which(name)
    if found:
        return found
    exe = name + (".exe" if os.name == "nt" else "")
    for base in (os.environ.get("FFMPEG_HOME", ""),
                 r"C:\ffmpeg\bin", r"C:\Program Files\ffmpeg\bin",
                 os.path.expanduser("~/ffmpeg/bin")):
        if base:
            cand = os.path.join(base, exe)
            if os.path.isfile(cand):
                return cand
    # Windows: winget usually installs ffmpeg here but doesn't always add it to
    # PATH; also check a Krita bundle. Auto-find it so --ffmpeg isn't needed.
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA", "")
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        patterns = []
        if local:
            patterns.append(os.path.join(local, "Microsoft", "WinGet", "Packages", "*FFmpeg*", "**", exe))
            patterns.append(os.path.join(local, "Microsoft", "WinGet", "Links", exe))
        patterns.append(os.path.join(pf, "Krita (x64)", "bin", exe))
        for pat in patterns:
            hits = sorted(glob.glob(pat, recursive=True))
            for hit in hits:
                if os.path.isfile(hit):
                    return hit
    return None

def require_ffmpeg(args):
    ff = find_tool("ffmpeg", args.ffmpeg)
    fp = find_tool("ffprobe", args.ffprobe)
    if not ff:
        sys.stderr.write(
            "\nERROR: `ffmpeg` was not found on your PATH.\n\n"
            "This tool needs the native ffmpeg. Install it, then re-run:\n"
            "  Windows : winget install --id Gyan.FFmpeg -e\n"
            "            (or: choco install ffmpeg)\n"
            "  macOS   : brew install ffmpeg\n"
            "  Linux   : sudo apt install ffmpeg\n\n"
            "Open a NEW terminal after installing so PATH updates, or pass\n"
            "  --ffmpeg C:\\path\\to\\ffmpeg.exe\n\n")
        sys.exit(2)
    return ff, fp

# --------------------------------------------------------------------------- #
#  DPG container assembly  (verified against dpg4x / dpgconv)
# --------------------------------------------------------------------------- #
def scan_video(video: bytes):
    """Return (frame_count, gop_index_bytes).
    frames  = count of MPEG-1 picture start codes (00 00 01 00)
    gop     = for each GOP header (00 00 01 B8): <int32 frames_before><int32 byte_offset>
    """
    entries = bytearray()
    frames = 0
    find = video.find
    i = find(b"\x00\x00\x01", 0)
    n = len(video)
    while i != -1 and i + 3 < n:
        c = video[i + 3]
        if c == 0x00:            # picture_start_code
            frames += 1
        elif c == 0xB8:          # group_start_code (GOP header)
            entries += struct.pack("<ii", frames, i)
        i = find(b"\x00\x00\x01", i + 3)
    if not entries:              # single-GOP fallback: index the sequence header
        j = video.find(b"\x00\x00\x01\xB3")
        if j != -1:
            entries += struct.pack("<ii", 0, j)
    return frames, bytes(entries)

def rgb_to_thumb(rgb: bytes) -> bytes:
    """256x192 RGB24 -> DS thumbnail: 16-bit ARGB1555 little-endian (98304 bytes)."""
    W, H = 256, 192
    need = W * H * 3
    if len(rgb) < need:
        rgb = rgb + b"\x00" * (need - len(rgb))
    out = bytearray(W * H * 2)
    j = 0
    for p in range(W * H):
        r = rgb[p * 3]; g = rgb[p * 3 + 1]; b = rgb[p * 3 + 2]
        px = (1 << 15) | ((b >> 3) << 10) | ((g >> 3) << 5) | (r >> 3)
        out[j] = px & 0xFF
        out[j + 1] = (px >> 8) & 0xFF
        j += 2
    return bytes(out)

def build_header(version, frames, fps, sample_rate, channels_field,
                 audio_len, video_len, gop_len):
    header_size = 36 if version == 0 else (52 if version == 4 else 48)
    thumb_size = 98304 if version == 4 else 0
    audio_start = header_size + thumb_size
    video_start = audio_start + audio_len
    gop_start = video_start + video_len
    h = bytearray()
    h += b"DPG" + bytes([0x30 + version])           # magic "DPGx"
    h += struct.pack("<i", frames)                  # 4  frame count
    h += struct.pack(">H", fps)                     # 8  fps -> bytes [00, fps]
    h += struct.pack(">H", 0)                        # 10 padding
    h += struct.pack("<i", sample_rate)             # 12 audio sample rate
    h += struct.pack("<i", channels_field)          # 16 channels(PCM) / 0(MP2)
    h += struct.pack("<i", audio_start)             # 20
    h += struct.pack("<i", audio_len)               # 24
    h += struct.pack("<i", video_start)             # 28
    h += struct.pack("<i", video_len)               # 32
    if version >= 2:
        h += struct.pack("<i", gop_start)           # 36
        h += struct.pack("<i", gop_len)             # 40
        h += struct.pack("<i", 3)                   # 44 pixel format = RGB24
    if version == 4:
        h += b"THM0"                                # 48
    assert len(h) == header_size, (len(h), header_size)
    return bytes(h)

# --------------------------------------------------------------------------- #
#  ffmpeg execution + progress
# --------------------------------------------------------------------------- #
def probe_duration(ffprobe, path):
    # Some files have a wrong container duration (seen: 15s claimed for a
    # 2-hour stream), so take the largest of the container and video-stream
    # durations -- that keeps the progress bar honest.
    if not ffprobe:
        return None
    best = None
    for args in (["-show_entries", "format=duration"],
                 ["-select_streams", "v:0", "-show_entries", "stream=duration"]):
        try:
            r = subprocess.run([ffprobe, "-v", "error"] + args +
                               ["-of", "default=nw=1:nk=1", path],
                               capture_output=True, text=True)
            s = (r.stdout.strip().splitlines() or [""])[0]
            v = float(s) if s and s != "N/A" else None
            if v and (best is None or v > best):
                best = v
        except Exception:
            pass
    return best

def probe_fps(ffprobe, path):
    """Return the source video frame rate rounded to a whole number, or None."""
    if not ffprobe:
        return None
    try:
        r = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=r_frame_rate", "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True)
        s = r.stdout.strip()
        if "/" in s:
            num, den = s.split("/")
            val = float(num) / float(den) if float(den) else 0.0
        else:
            val = float(s)
        return int(round(val)) if val > 0 else None
    except Exception:
        return None

def _bar(label, pct):
    w = 28
    fill = int(w * pct / 100 + 0.5)
    sys.stdout.write("\r  %-14s [%s%s] %5.1f%%" %
                     (label, "#" * fill, "-" * (w - fill), pct))
    sys.stdout.flush()

def run_ffmpeg(ff, tail, total, label, quiet, verbose):
    cmd = [ff, "-hide_banner", "-loglevel", "error",
           "-progress", "pipe:1", "-nostats", "-y"] + tail
    if verbose:
        sys.stdout.write("\n  $ " + " ".join(_q(a) for a in cmd) + "\n")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, bufsize=1)
    for line in proc.stdout:
        line = line.strip()
        if not quiet and line.startswith("out_time_us=") and total:
            v = line.split("=", 1)[1]
            if v.isdigit():
                _bar(label, min(100.0, int(v) / 1e6 / total * 100))
        elif line == "progress=end" and not quiet:
            _bar(label, 100.0)
    err = proc.stderr.read()
    rc = proc.wait()
    if not quiet:
        sys.stdout.write("\n")
    if rc != 0:
        raise RuntimeError("ffmpeg failed during %s:\n%s" % (label, err.strip()))

def _q(a):
    return '"%s"' % a if " " in a else a

# --------------------------------------------------------------------------- #
#  Conversion of one file
# --------------------------------------------------------------------------- #
def geom(mode):
    """256x192 geometry filter for the chosen fit mode."""
    if mode == "stretch":                        # distort to fill
        return "scale=256:192"
    if mode == "letterbox":                       # fit inside, black bars
        return ("scale=256:192:force_original_aspect_ratio=decrease,"
                "pad=256:192:(ow-iw)/2:(oh-ih)/2:color=black")
    # fill (default): scale to cover the screen, then centre-crop the overflow
    return "scale=256:192:force_original_aspect_ratio=increase,crop=256:192"

def build_vf(fps, mode, color16):
    vf = "fps=%d,%s" % (fps, geom(mode))
    if color16:
        vf += ",format=rgb565"
    vf += ",format=yuv420p"
    return vf

def convert_one(inp, outp, o, ff, fp):
    version = o.dpg_version
    # Resolve frame rate: 'auto' matches the source file (rounded to a whole
    # number, which MPEG-1 and the DPG header require), capped for smooth DS decode.
    if str(o.fps).lower() == "auto":
        fps = probe_fps(fp, inp) or 24
        if fps > 30:
            print("  note: source is %d fps; capping to 30 for smooth DS playback "
                  "(pass -r %d to force)." % (fps, fps))
            fps = 30
        print("  frame rate: %d fps (matched to source)" % fps)
    else:
        fps = int(o.fps)
    mode = "stretch" if o.stretch else ("letterbox" if o.letterbox else "fill")
    audio_codec = o.audio or ("pcm" if version == 0 else "mp2")
    if audio_codec == "pcm":
        sample_rate = o.rate or 32768
        channels_field = 2
    else:
        sample_rate = o.rate or 32000
        if sample_rate not in MP2_RATES:
            print("  note: %d Hz isn't valid for MP2; using 32000 Hz." % sample_rate)
            sample_rate = 32000
        channels_field = 0

    total = probe_duration(fp, inp)
    if total and o.start:
        total = max(0.0, total - _time_to_sec(o.start))
    if o.duration:
        d = _time_to_sec(o.duration)
        total = min(total, d) if total else d

    trim = []
    if o.start:    trim += ["-ss", o.start]
    if o.duration: trim += ["-t", o.duration]

    tmp = tempfile.mkdtemp(prefix="dpg_")
    vpath = os.path.join(tmp, "v.m1v")
    apath = os.path.join(tmp, "a.bin")
    tpath = os.path.join(tmp, "t.rgb")
    try:
        # ---- video ----  plain mpeg1video with a hard VBV ceiling so the DS
        # decoder never sees a bitrate spike.  (Encoder "quality" flags like
        # -trellis / -mpv_flags +mv0 / -mbd rd broke MPEG-1 rate control here —
        # ~100x bitrate blow-up and huge slowdown — so they are intentionally out.)
        run_ffmpeg(ff, trim + ["-i", inp, "-an", "-vf", build_vf(fps, mode, o.color16),
                   "-r", str(fps), "-c:v", "mpeg1video",
                   "-b:v", "%dk" % o.bitrate, "-maxrate", "%dk" % o.bitrate,
                   "-bufsize", "%dk" % max(64, o.bitrate // 2),
                   "-g", "15", "-strict", "experimental",
                   "-f", "mpeg1video", vpath],
                   total, "video", o.quiet, o.verbose)
        # ---- audio ----
        if audio_codec == "pcm":
            run_ffmpeg(ff, trim + ["-i", inp, "-vn", "-ar", str(sample_rate), "-ac", "2",
                       "-f", "s16le", apath], total, "audio (pcm)", o.quiet, o.verbose)
        else:
            run_ffmpeg(ff, trim + ["-i", inp, "-vn", "-ar", str(sample_rate), "-ac", "2",
                       "-c:a", "mp2", "-b:a", "%dk" % o.ab, "-f", "mp2", apath],
                       total, "audio (mp2)", o.quiet, o.verbose)
        # ---- thumbnail (DPG4) ----
        thumb = b""
        if version == 4:
            at = o.start or "00:00:01"
            run_ffmpeg(ff, ["-ss", at, "-i", inp, "-frames:v", "1", "-vf",
                       geom(mode) + ",format=rgb24",
                       "-f", "rawvideo", tpath], None, "thumbnail", o.quiet, o.verbose)
            thumb = rgb_to_thumb(open(tpath, "rb").read())

        video = open(vpath, "rb").read()
        audio = open(apath, "rb").read()
        frames, gop = scan_video(video)
        if version < 2:
            gop = b""          # DPG0 has no GOP index section
        header = build_header(version, frames, fps, sample_rate, channels_field,
                              len(audio), len(video), len(gop))

        with open(outp, "wb") as f:
            f.write(header)
            if thumb: f.write(thumb)
            f.write(audio)
            f.write(video)
            if gop: f.write(gop)

        size = os.path.getsize(outp)
        secs = frames / fps if fps else 0
        print("  -> %s  (DPG%d, %d frames / %.1fs, %s audio, %.1f MB)" %
              (os.path.basename(outp), version, frames, secs,
               "PCM %dHz" % sample_rate if audio_codec == "pcm" else "MP2 %dHz" % sample_rate,
               size / 1048576))
    finally:
        if o.keep_temp:
            print("  (kept temp files in %s)" % tmp)
        else:
            shutil.rmtree(tmp, ignore_errors=True)

def _time_to_sec(t):
    t = str(t).strip()
    if ":" in t:
        parts = [float(x) for x in t.split(":")]
        s = 0.0
        for p in parts:
            s = s * 60 + p
        return s
    return float(t)

# --------------------------------------------------------------------------- #
#  CLI
# --------------------------------------------------------------------------- #
def out_path_for(inp, o, multi):
    base = os.path.splitext(os.path.basename(inp))[0] + ".dpg"
    if o.output:
        if multi or o.output.endswith(("/", "\\")) or os.path.isdir(o.output):
            os.makedirs(o.output, exist_ok=True)
            return os.path.join(o.output, base)
        return o.output                      # single file, explicit name
    return os.path.join(os.path.dirname(os.path.abspath(inp)), base)

def main():
    p = argparse.ArgumentParser(
        description="Convert video to Nintendo DS .DPG (Moonshell / R4).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Defaults are tuned for Moonshell 2: DPG4 (thumbnail + fast seek),\n"
               "MP2 audio, and the source video's own frame rate.\n"
               "DPG0 = 16-bit PCM stereo 32768 Hz (classic Moonshell 1.x).")
    p.add_argument("inputs", nargs="+", metavar="INPUT", help="video file(s); globs allowed")
    p.add_argument("-o", "--output", metavar="PATH",
                   help="output .dpg file (single input) or a directory (batch)")
    p.add_argument("-V", "--dpg-version", type=int, choices=[0, 2, 4], default=4,
                   help="DPG container version (default 4 = Moonshell 2)")
    p.add_argument("-a", "--audio", choices=["pcm", "mp2"],
                   help="audio codec (default: mp2 for V4/V2, pcm for V0)")
    p.add_argument("-r", "--fps", default="auto",
                   help="frame rate: 'auto' matches the source file (default), or a number")
    p.add_argument("-b", "--bitrate", type=int, default=768, help="video kbps (default 768)")
    p.add_argument("--rate", type=int, help="audio sample rate Hz (default 32768 PCM / 32000 MP2)")
    p.add_argument("--ab", type=int, default=128, help="MP2 audio kbps (default 128)")
    p.add_argument("-s", "--start", metavar="T", help="start time, e.g. 00:01:30 or 90")
    p.add_argument("-t", "--duration", metavar="T", help="duration to encode, e.g. 120 or 00:02:00")
    p.add_argument("--letterbox", action="store_true",
                   help="fit inside 256x192 with black bars (default fills the screen, cropping overflow)")
    p.add_argument("--stretch", action="store_true",
                   help="stretch to 256x192, ignoring aspect ratio (distorts)")
    p.add_argument("--color16", action="store_true",
                   help="quantize each frame to 16-bit color (RGB565); off by default for best quality")
    p.add_argument("--ffmpeg", help="path to ffmpeg binary")
    p.add_argument("--ffprobe", help="path to ffprobe binary")
    p.add_argument("--keep-temp", action="store_true", help="keep intermediate files")
    p.add_argument("-q", "--quiet", action="store_true", help="no progress bars")
    p.add_argument("--verbose", action="store_true", help="print ffmpeg commands")
    o = p.parse_args()

    ff, fp = require_ffmpeg(o)

    # expand globs (helps on Windows where the shell doesn't)
    files = []
    for pat in o.inputs:
        m = glob.glob(pat)
        files.extend(m if m else [pat])
    missing = [f for f in files if not os.path.isfile(f)]
    if missing:
        sys.stderr.write("ERROR: file(s) not found:\n  " + "\n  ".join(missing) + "\n")
        sys.exit(1)

    multi = len(files) > 1
    print("DPG converter  |  ffmpeg: %s" % ff)
    ok = 0
    for f in files:
        outp = out_path_for(f, o, multi)
        print("\n%s" % os.path.basename(f))
        try:
            convert_one(f, outp, o, ff, fp)
            ok += 1
        except KeyboardInterrupt:
            sys.stderr.write("\naborted.\n"); sys.exit(130)
        except Exception as e:
            sys.stderr.write("  FAILED: %s\n" % e)
    print("\nDone: %d/%d converted." % (ok, len(files)))
    sys.exit(0 if ok == len(files) else 1)

if __name__ == "__main__":
    main()
