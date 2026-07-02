"""Generate the bundled move sounds — app/data/sounds/*.wav.

The sounds are synthesized (a damped-sine "wood knock" with a noise
attack), so there is nothing to license and nothing to download. Dev-only;
the resulting tiny WAV files are committed.

Usage:  python tools/build_sounds.py
"""

from __future__ import annotations

import math
import random
import struct
import sys
import wave
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "app" / "data" / "sounds"
SAMPLE_RATE = 44100


def _knock(duration: float, partials: list, decay: float,
           noise_level: float, gain: float, seed: int) -> list:
    """A percussive knock: damped sine partials + a short noise attack.
    `partials` is a list of (frequency_hz, relative_amplitude)."""
    rng = random.Random(seed)
    samples = []
    n = int(SAMPLE_RATE * duration)
    for i in range(n):
        t = i / SAMPLE_RATE
        tone = sum(amp * math.sin(2 * math.pi * freq * t)
                   for freq, amp in partials)
        tone *= math.exp(-t / decay)
        noise = (rng.random() * 2 - 1) * noise_level * math.exp(-t / 0.004)
        # 1.5ms linear attack so the transient doesn't click.
        attack = min(1.0, t / 0.0015)
        samples.append((tone + noise) * attack * gain)
    return samples


def _mix(*layers) -> list:
    """Overlay (offset_seconds, samples) layers into one buffer."""
    total = max(int(off * SAMPLE_RATE) + len(s) for off, s in layers)
    out = [0.0] * total
    for offset, samples in layers:
        start = int(offset * SAMPLE_RATE)
        for i, value in enumerate(samples):
            out[start + i] += value
    return out


def _write(name: str, samples: list):
    peak = max(abs(s) for s in samples) or 1.0
    scale = 0.85 / peak   # normalize with headroom
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / name
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(SAMPLE_RATE)
        frames = b"".join(
            struct.pack("<h", int(max(-1.0, min(1.0, s * scale)) * 32767))
            for s in samples)
        fh.writeframes(frames)
    print(f"wrote {path} ({path.stat().st_size} bytes, "
          f"{len(samples) / SAMPLE_RATE * 1000:.0f} ms)")


def main() -> int:
    # Move: a dry, soft wood tap.
    move = _knock(duration=0.12,
                  partials=[(196.0, 0.6), (476.0, 0.25), (890.0, 0.15)],
                  decay=0.018, noise_level=0.35, gain=0.9, seed=1)
    _write("move.wav", move)

    # Capture: lower, heavier, with a faint second knock — piece takes piece.
    hit = _knock(duration=0.14,
                 partials=[(152.0, 0.7), (368.0, 0.3), (702.0, 0.18)],
                 decay=0.024, noise_level=0.45, gain=1.0, seed=2)
    tap = _knock(duration=0.08,
                 partials=[(210.0, 0.5), (520.0, 0.2)],
                 decay=0.012, noise_level=0.3, gain=0.45, seed=3)
    _write("capture.wav", _mix((0.0, hit), (0.028, tap)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
