"""
Renders the player disguised as a real-time signal analysis Python module.
Track name / artist are hidden as source-code comments; everything else
looks like diagnostic output from an audio processing pipeline.
"""

import os
import shutil
from typing import Optional

from rich.console import Console
from rich.syntax import Syntax
from rich.text import Text

console = Console()

_KEY_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']


def _progress_bar(progress_ms: int, duration_ms: int, width: int = 28) -> str:
    frac   = progress_ms / max(duration_ms, 1)
    filled = int(frac * width)
    return '█' * filled + '░' * (width - filled)


def _fmt_ms(ms: int) -> str:
    s = ms // 1000
    return f"{s // 60}:{s % 60:02d}"


def render_player(
    track: Optional[dict],
    features: Optional[dict],
    waveform_lines: list,
    liked: Optional[bool] = None,
    resumed: bool = False,
) -> None:
    """Clear the screen and draw the full player UI."""
    term_w, _ = shutil.get_terminal_size((120, 40))

    # Waveform width: terminal width minus line-number gutter (7) and
    # docstring indent (4) and padding (2)
    wv_width = max(20, term_w - 13)

    if not track:
        code = _idle_code()
    else:
        code = _playing_code(track, features, waveform_lines, wv_width, liked)

    syntax = Syntax(
        code, 'python',
        theme='monokai',
        line_numbers=True,
        start_line=142,
    )

    is_playing = bool(track and track.get('is_playing'))
    play_icon  = '▶' if is_playing else '⏸'
    fname      = 'signal_analyzer.py'

    # Tab bar
    tabs = Text()
    tabs.append('  main.py  ',      style='dim on #2d2d2d')
    tabs.append('  pipeline.py  ',  style='dim on #2d2d2d')
    tabs.append(f'  {fname}  ',     style='bold white on #1e1e1e')
    tabs.append('  utils.py  ',     style='dim on #2d2d2d')
    tabs.append('  config.py  ',    style='dim on #2d2d2d')

    # Status bar
    status = Text()
    status.append('  ⎇ main  ',       style='bold on #0e639c')
    status.append(f'  {fname}  ',     style='on #37373d')
    status.append('  Python 3.11  ',  style='on #252526')
    status.append('  UTF-8  ',        style='on #252526')
    status.append(f'  {play_icon}  ', style='bold on #1e4620' if is_playing else 'on #3c3c3c')
    if resumed:
        status.append('  ↩ resumed  ', style='bold on #1e4620')

    hint = Text()
    hint.append(
        '  Space play/pause   n/p track   =/- volume   s shuffle   l like   Esc panic   q quit',
        style='dim',
    )

    os.system('cls' if os.name == 'nt' else 'clear')
    console.print(tabs)
    console.print(syntax)
    console.print(status)
    console.print(hint)


# ── Code templates ────────────────────────────────────────────────────────────

def _idle_code() -> str:
    return (
        '# src/audio/pipeline/signal_analyzer.py\n'
        '# No active stream detected\n'
        '\n'
        'class SpectrumAnalyzer:\n'
        '    """\n'
        '    Waiting for input stream...\n'
        '    Ensure source device is active and retry.\n'
        '    """\n'
        '\n'
        '    def __init__(self):\n'
        '        self._initialized = False\n'
        '        self._pipeline    = None\n'
    )


def _playing_code(
    track: dict,
    features: Optional[dict],
    waveform_lines: list,
    wv_width: int,
    liked: Optional[bool],
) -> str:
    f = features or {}

    energy   = f.get('energy',   0.5)
    loudness = f.get('loudness', -10.0)
    tempo    = f.get('tempo',    120.0)
    valence  = f.get('valence',  0.5)
    key_idx  = int(f.get('key',  0)) % 12
    mode     = 'major' if f.get('mode', 1) else 'minor'
    key_str  = f"{_KEY_NAMES[key_idx]} {mode}"

    shuffle  = 'on' if track.get('shuffle') else 'off'
    volume   = f"{track.get('volume', 50)}%"
    liked_str = ' ♥' if liked else ''

    bar      = _progress_bar(track.get('progress_ms', 0), track.get('duration_ms', 1))
    time_str = f"{_fmt_ms(track.get('progress_ms', 0))} / {_fmt_ms(track.get('duration_ms', 1))}"

    # Indent waveform rows inside the docstring
    wv = '\n'.join(f'    {ln[:wv_width]}' for ln in waveform_lines)

    # Track info as source-code comments (readable by user, opaque to passerby)
    name   = track.get('name',   'Unknown').replace("'", "\\'")
    artist = track.get('artist', 'Unknown')
    album  = track.get('album',  'Unknown')

    return (
        f'# src/audio/pipeline/signal_analyzer.py\n'
        f'# src_stream : \'{name}\'{liked_str}  ·  {artist}\n'
        f'# dataset    : {album}\n'
        f'\n'
        f'class SpectrumAnalyzer:\n'
        f'    """\n'
        f'    INPUT ──▶ FFT(2048) ──▶ BANDPASS ──▶ OUTPUT\n'
        f'\n'
        f'{wv}\n'
        f'\n'
        f'    sample_rate : 44100 Hz       energy   : {energy:.3f}\n'
        f'    buffer_size : 2048           tempo    : {tempo:.1f} bpm\n'
        f'    loudness    : {loudness:.1f} dBFS     valence  : {valence:.3f}\n'
        f'    key         : {key_str:<14}  shuffle  : {shuffle}\n'
        f'    volume      : {volume:<14}  progress : {bar}  {time_str}\n'
        f'    """\n'
        f'\n'
        f'    def process(self, frame: bytes) -> bytes:\n'
        f'        return self._pipeline.run(frame)\n'
    )


# ── Panic mode ────────────────────────────────────────────────────────────────

def render_panic(scroll_offset: int, panic_code: str) -> int:
    """Render the panic-mode fake code view. Returns visible line count."""
    term_w, term_h = shutil.get_terminal_size((120, 40))
    visible = max(5, term_h - 3)

    all_lines = panic_code.splitlines()
    total     = len(all_lines)
    page      = all_lines[scroll_offset: scroll_offset + visible]
    while len(page) < visible:
        page.append('')

    syntax = Syntax(
        '\n'.join(page), 'python',
        theme='monokai',
        line_numbers=True,
        start_line=scroll_offset + 1,
    )

    fname = 'dispatcher.py'
    tabs  = Text()
    tabs.append('  config.py  ',    style='dim on #2d2d2d')
    tabs.append(f'  {fname}  ',     style='bold white on #1e1e1e')
    tabs.append('  utils.py  ',     style='dim on #2d2d2d')
    tabs.append('  test_core.py  ', style='dim on #2d2d2d')
    tabs.append('  __init__.py  ',  style='dim on #2d2d2d')

    status = Text()
    status.append('  ⎇ main  ',                                    style='bold on #0e639c')
    status.append(f'  {fname}  ',                                   style='on #37373d')
    status.append('  Python 3.11  ',                                style='on #252526')
    status.append('  UTF-8  ',                                      style='on #252526')
    status.append(f'  Ln {scroll_offset + 1}/{total}, Col 1  ',    style='on #252526')

    hint = Text()
    hint.append(
        '  j/↓ k/↑ scroll   d/u half-page   Space/b page   Esc return   q quit',
        style='dim',
    )

    os.system('cls' if os.name == 'nt' else 'clear')
    console.print(tabs)
    console.print(syntax)
    console.print(status)
    console.print(hint)

    return visible
