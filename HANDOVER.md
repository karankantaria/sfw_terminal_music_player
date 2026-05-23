# Handover — terminal-music-player

## What's been built

The full UI and player loop are complete and testable right now using mock data.
No Spotify credentials are needed to run and verify the interface.

### Files

| File | Purpose |
|------|---------|
| `player.py` | Entry point, main loop, keyboard input thread |
| `renderer.py` | All terminal rendering — signal-analysis disguise + panic mode |
| `waveform.py` | Animated Unicode block-char spectrum from audio energy value |
| `spotify_client.py` | `SpotifyClient` (real API, stubbed out) + `MockClient` (works now) |
| `requirements.txt` | `spotipy`, `rich`, `python-dotenv` |
| `.env.example` | Credential template |

### How the disguise works

The currently playing track is rendered as a Python class with a docstring:

```
# src/audio/pipeline/signal_analyzer.py
# src_stream : 'Blinding Lights'  ·  The Weeknd   ← readable by you
# dataset    : After Hours                         ← looks like a comment

class SpectrumAnalyzer:
    """
    INPUT ──▶ FFT(2048) ──▶ BANDPASS ──▶ OUTPUT

    ▂▃▄▆▇█▇▆▅▄▃▄▅▇█▇▅▃▂▁▂▃▅▆▇▆▄▃▂▁▁▂▄▅▆▅▃▂▁   ← waveform animates
    ▁▂▃▅▆▇█▇▅▄▃▂▃▄▆▇█▆▄▂▁▂▄▅▇▇▅▃▂▁▁▃▄▅▅▃▂▁▁

    sample_rate : 44100 Hz       energy   : 0.730
    buffer_size : 2048           tempo    : 171.0 bpm
    loudness    : -5.8 dBFS      valence  : 0.334
    key         : C# minor       shuffle  : off
    volume      : 72%            progress : ████████░░░░  1:24 / 3:22
    """
```

Pressing `Esc` swaps to a scrollable fake dispatcher module (same panic
concept as the epub reader).

---

## How to run now (mock mode)

```bash
pip install -r requirements.txt
set SPOTIFY_MOCK=1        # Windows
# export SPOTIFY_MOCK=1  # Mac/Linux
python player.py
```

---

## What still needs to be done

### 1 — Wire up real Spotify credentials

1. Copy `.env.example` → `.env`
2. Fill in `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` from
   [developer.spotify.com](https://developer.spotify.com/dashboard)
3. In `spotify_client.py`, find the `SpotifyClient.__init__` method and
   uncomment the `SpotifyOAuth` block (lines marked `# TODO`)
4. Delete the `raise NotImplementedError` line directly below it
5. Set `SPOTIFY_MOCK=0` in `.env` (or remove the line)

First run will open a browser for the OAuth login — after that the token
is cached in `.cache` and it's automatic.

### 2 — Add `.env` and `.cache` to `.gitignore`

```
.env
.cache
```

Credentials must not be committed.

### 3 — Test playback controls

With a real client, verify:
- `Space` toggles play/pause
- `n` / `p` skips tracks
- `=` / `-` changes volume (requires Spotify Premium)
- `s` toggles shuffle
- `l` likes/unlikes the current track

### 4 — Handle edge cases

- **No active device** — Spotify returns 404 when no device is open.
  `SpotifyClient` already swallows these exceptions; optionally show a
  better idle message in `renderer._idle_code()`.
- **Token expiry** — `spotipy` handles refresh automatically, but wrap
  the `SpotifyClient` calls in a try/except that re-authenticates on
  `SpotifyOauthError` if needed.
- **Free account** — playback control requires Premium. Detect this from
  the 403 response and show a hint in the status bar.

### 5 — Optional polish

- Auto-panic on idle (no keypress for N seconds → switch to panic view)
- `r` key to seek back to start of track
- Playlist browser (press `o` to open a list of playlists, same TOC-style
  disguise as the epub reader)

---

## Architecture notes

**Threading model**

The player uses two threads:
- **Input thread** — blocks on `_get_key()`, pushes to `key_queue`
- **Main thread** — sleeps for `_REFRESH_HZ` seconds, drains the queue,
  re-fetches Spotify state, redraws

This means keypresses are processed in batches at the start of each
refresh cycle, not instantly. For playback controls this is fine. If
snappier response is needed, move the render call inside the key handler
and keep the sleep only for the background poll.

**API polling rate**

`_REFRESH_HZ = 1.0` — one Spotify API call per second. Spotify's rate
limit is generous for personal use; this is well within it. The mock
client's `tick()` method advances the fake progress bar at the same rate.

**Audio features**

Fetched once per track change (not every poll) since they're static
metadata. Stored in `features` and passed to `renderer` and `waveform`.
