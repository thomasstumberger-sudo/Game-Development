"""One-off generator for Wayfarer's sound effects.

The source tilesets came with no audio, and the design brief calls for
short, cheap, load-once-and-cache sfx rather than any music/streaming --
so instead of sourcing external files, these are synthesized directly
with stdlib `wave` + `math`. Run this script once to (re)populate
assets/sfx/*.wav; the files it produces are checked in like any other
asset, this script does not run at game startup.

    ../venv/bin/python3 tools/gen_sfx.py
"""

import math
import os
import struct
import wave

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "sfx")
SAMPLE_RATE = 22050


def _envelope(i, n, attack, decay):
    """Linear attack/decay envelope, 0..1."""
    if i < attack:
        return i / attack if attack else 1.0
    remaining = n - i
    if remaining < decay:
        return remaining / decay if decay else 0.0
    return 1.0


def _tone(freq_fn, duration, attack=0.0, decay=0.0, wave_shape="sine", amp=0.5):
    n = int(SAMPLE_RATE * duration)
    attack_n = int(SAMPLE_RATE * attack)
    decay_n = int(SAMPLE_RATE * decay)
    samples = []
    phase = 0.0
    for i in range(n):
        t = i / SAMPLE_RATE
        freq = freq_fn(t)
        phase += freq / SAMPLE_RATE
        phase %= 1.0
        if wave_shape == "square":
            v = 1.0 if phase < 0.5 else -1.0
        elif wave_shape == "saw":
            v = 2.0 * phase - 1.0
        else:
            v = math.sin(2 * math.pi * phase)
        env = _envelope(i, n, attack_n, decay_n)
        samples.append(v * env * amp)
    return samples


def _concat(*chunks):
    out = []
    for c in chunks:
        out.extend(c)
    return out


def _write(name, samples):
    path = os.path.join(OUT_DIR, f"{name}.wav")
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SAMPLE_RATE)
        frames = b"".join(
            struct.pack("<h", max(-32767, min(32767, int(s * 32767))))
            for s in samples
        )
        f.writeframes(frames)
    print(f"wrote {path} ({len(samples) / SAMPLE_RATE:.2f}s)")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    # Sharp, low-effort blip -- plays on every successful attack, so it has
    # to be cheap-sounding and very short or spam becomes annoying.
    _write("hit", _tone(lambda t: 220, 0.07, attack=0.002, decay=0.05, wave_shape="square", amp=0.35))

    # Descending sweep -- enemy defeated.
    _write("kill", _tone(lambda t: 500 - 1400 * t, 0.25, attack=0.005, decay=0.18, wave_shape="saw", amp=0.4))

    # Two quick ascending notes -- item pickup.
    _write(
        "pickup",
        _concat(
            _tone(lambda t: 600, 0.07, attack=0.002, decay=0.05, amp=0.35),
            _tone(lambda t: 900, 0.09, attack=0.002, decay=0.06, amp=0.35),
        ),
    )

    # Four-note major arpeggio -- level up.
    notes = [523.25, 659.25, 783.99, 1046.50]
    levelup = _concat(*[
        _tone(lambda t, f=f: f, 0.11, attack=0.004, decay=0.08, amp=0.35) for f in notes
    ])
    _write("levelup", levelup)

    # Low, short thud -- room transition / door.
    _write("door", _tone(lambda t: 100 - 40 * t, 0.12, attack=0.002, decay=0.1, wave_shape="sine", amp=0.45))


if __name__ == "__main__":
    main()
