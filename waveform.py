"""Generates animated waveform bars from audio energy/tempo values."""

import math

BLOCKS = ' ▁▂▃▄▅▆▇█'


def generate(energy: float, width: int, t: float, rows: int = 2) -> list:
    """
    Return `rows` strings of Unicode block chars simulating a spectrum analyser.

    energy : 0.0–1.0  (from Spotify audio features)
    width  : number of bars per row
    t      : time in seconds (increments each refresh to animate)
    """
    lines = []
    for row in range(rows):
        line = ''.join(_bar(energy, t, i, width, row) for i in range(width))
        lines.append(line)
    return lines


def _bar(energy: float, t: float, i: int, width: int, row: int) -> str:
    # Bell-curve spectral shape peaking around the lower-mid frequencies
    center  = width * 0.35
    spread  = width * 0.40
    spectral = math.exp(-((i - center) ** 2) / (2 * spread ** 2))

    # Two slow animation waves with different phases per row
    wave = (
        math.sin(i * 0.30 + t * 2.1        ) * 0.15
      + math.sin(i * 0.72 - t * 1.4 + row  ) * 0.10
    )

    amp = energy * spectral + wave
    return BLOCKS[max(0, min(8, int(amp * 8)))]
