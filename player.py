#!/usr/bin/env python3
"""
terminal-music-player — Spotify player disguised as a signal analysis tool.

Usage:
    python player.py             # real Spotify (requires .env)
    SPOTIFY_MOCK=1 python player.py   # mock data, no credentials needed

Keys:
    Space       Play / pause
    n / p       Next / previous track
    = / -       Volume up / down (5%)
    s           Toggle shuffle
    l           Like / unlike current track
    Esc         Toggle panic mode (fake Python module)
    q           Quit
"""

import os
import queue
import sys
import threading
import time

from dotenv import load_dotenv

load_dotenv()

from rich.live import Live

from spotify_client import get_client
from renderer import player_renderable, panic_renderable
from waveform import generate

# ── Panic-mode fake code (same style as epub reader) ─────────────────────────

_PANIC_CODE = '''\
from __future__ import annotations

import asyncio
import hashlib
import logging
import struct
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Dict, Generator, Iterator, List, Optional, Tuple

logger = logging.getLogger(__name__)

_MAGIC   = b"\\xde\\xad\\xbe\\xef"
_VERSION = (2, 4, 1)
_DEFAULT_TTL = 86_400


class State(Enum):
    IDLE     = auto()
    RUNNING  = auto()
    DRAINING = auto()
    STOPPED  = auto()
    FAULTED  = auto()


@dataclass
class Config:
    workers:       int   = 4
    batch_size:    int   = 256
    retry_limit:   int   = 3
    timeout_ms:    int   = 5_000
    backoff:       float = 1.5
    enable_ckpt:   bool  = True
    ckpt_interval: int   = 100
    codec:         str   = "lz4"
    sink:          Path  = Path("./sink")
    _tag: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        blob = f"{self.workers}:{self.batch_size}:{self.timeout_ms}"
        self._tag = hashlib.sha1(blob.encode()).hexdigest()[:8]

    @property
    def tag(self) -> str:
        return self._tag

    def validate(self) -> None:
        if self.workers < 1:
            raise ValueError("workers must be >= 1")
        if self.backoff < 1.0:
            raise ValueError("backoff factor must be >= 1.0")


class RingBuffer:
    __slots__ = ("_buf", "_cap", "_head", "_tail", "_size")

    def __init__(self, capacity: int) -> None:
        self._buf  = [None] * capacity
        self._cap  = capacity
        self._head = self._tail = self._size = 0

    def push(self, item: Any) -> Optional[Any]:
        evicted = None
        if self._size == self._cap:
            evicted    = self._buf[self._tail]
            self._tail = (self._tail + 1) % self._cap
        else:
            self._size += 1
        self._buf[self._head] = item
        self._head = (self._head + 1) % self._cap
        return evicted

    def __iter__(self) -> Iterator[Any]:
        idx = self._tail
        for _ in range(self._size):
            yield self._buf[idx]
            idx = (idx + 1) % self._cap

    def __len__(self) -> int:
        return self._size


def _backoff(attempt: int, base: float = 0.05, factor: float = 1.5, cap: float = 30.0) -> float:
    return min(base * (factor ** attempt), cap)


def sliding_window(seq: list, size: int, step: int = 1) -> Generator[list, None, None]:
    if size > len(seq):
        return
    for i in range(0, len(seq) - size + 1, step):
        yield seq[i : i + size]


def normalise(values: List[float], *, lo: float = 0.0, hi: float = 1.0) -> List[float]:
    mn, mx = min(values), max(values)
    span = mx - mn or 1.0
    return [lo + (v - mn) / span * (hi - lo) for v in values]


class Stage:
    def __init__(self, name: str, fn: Callable, weight: float = 1.0) -> None:
        self.name     = name
        self._fn      = fn
        self.weight   = weight
        self._calls   = 0
        self._elapsed = 0.0

    def __call__(self, data: Any) -> Any:
        t0 = time.perf_counter()
        result = self._fn(data)
        self._elapsed += time.perf_counter() - t0
        self._calls   += 1
        return result

    @property
    def avg_ms(self) -> float:
        return (self._elapsed / self._calls * 1_000) if self._calls else 0.0


class Pipeline:
    def __init__(self, name: str = "default") -> None:
        self.name    = name
        self._stages: List[Stage] = []

    def add(self, name: str, fn: Callable, weight: float = 1.0) -> "Pipeline":
        self._stages.append(Stage(name, fn, weight))
        return self

    def run(self, data: Any) -> Any:
        for stage in self._stages:
            data = stage(data)
        return data

    def profile(self) -> Dict[str, float]:
        return {s.name: round(s.avg_ms, 3) for s in self._stages}


class Dispatcher:
    def __init__(self, cfg: Config) -> None:
        cfg.validate()
        self._cfg   = cfg
        self._q: asyncio.Queue = asyncio.Queue(maxsize=cfg.batch_size * 2)
        self._state = State.IDLE
        self._stats: Dict[str, int] = defaultdict(int)
        self._hooks: List[Callable] = []
        self._buf   = RingBuffer(capacity=512)

    def hook(self, fn: Callable) -> Callable:
        self._hooks.append(fn)
        return fn

    async def run_batch(self, items: List[Dict]) -> Tuple[int, int]:
        ok = fail = 0
        for i, item in enumerate(items):
            if await self._dispatch(item):
                ok += 1
            else:
                fail += 1
            if self._cfg.enable_ckpt and i % self._cfg.ckpt_interval == 0:
                await self._checkpoint(i)
        return ok, fail

    async def _dispatch(self, item: Dict[str, Any]) -> bool:
        for attempt in range(self._cfg.retry_limit):
            try:
                await asyncio.wait_for(
                    self._invoke(item),
                    timeout=self._cfg.timeout_ms / 1_000,
                )
                self._stats["ok"] += 1
                return True
            except asyncio.TimeoutError:
                self._stats["timeout"] += 1
                logger.warning("timeout attempt=%d", attempt)
            except Exception as exc:
                self._stats["err"] += 1
                logger.error("dispatch error: %s", exc)
            await asyncio.sleep(_backoff(attempt, factor=self._cfg.backoff))
        self._state = State.FAULTED
        return False

    async def _invoke(self, item: Dict[str, Any]) -> None:
        for hook in self._hooks:
            res = hook(item)
            if asyncio.iscoroutine(res):
                await res
        self._buf.push(item)

    async def _checkpoint(self, idx: int) -> None:
        path = self._cfg.sink / f"{self._cfg.tag}_{idx:06d}.bin"
        logger.debug("ckpt → %s", path)
'''

_PANIC_TOTAL = len(_PANIC_CODE.splitlines())


# ── Keyboard input ────────────────────────────────────────────────────────────

def _get_key() -> str:
    if os.name == 'nt':
        import msvcrt
        b = msvcrt.getch()
        if b in (b'\x00', b'\xe0'):
            b2 = msvcrt.getch()
            return {
                b'H': 'UP',   b'P': 'DOWN',
                b'K': 'LEFT', b'M': 'RIGHT',
                b'I': 'PGUP', b'Q': 'PGDN',
            }.get(b2, 'UNKNOWN')
        if b == b'\x03':
            return 'QUIT'
        if b == b'\x1b':
            return 'ESC'
        try:
            return b.decode('utf-8')
        except Exception:
            return ''
    else:
        import tty, termios
        fd  = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == '\x1b':
                nxt = sys.stdin.read(1)
                if nxt == '[':
                    code = sys.stdin.read(1)
                    if code in ('5', '6'):
                        sys.stdin.read(1)
                    return {'A': 'UP', 'B': 'DOWN', '5': 'PGUP', '6': 'PGDN'}.get(code, 'UNKNOWN')
                return 'ESC'
            if ch in ('\x03', '\x04'):
                return 'QUIT'
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


# ── Main ──────────────────────────────────────────────────────────────────────

_RENDER_HZ   = 10    # frames per second — waveform animation rate
_SPOTIFY_POLL = 2.0  # seconds between Spotify API calls


def main() -> None:
    try:
        client = get_client()
    except Exception as exc:
        print(f"Failed to connect to Spotify: {exc}")
        sys.exit(1)

    key_queue:  queue.Queue    = queue.Queue()
    stop_event: threading.Event = threading.Event()

    # Initial state
    track    = client.get_current_track()
    features = client.get_audio_features(track['id']) if track else None
    liked    = client.is_liked(track['id'])            if track else None
    last_id  = track['id'] if track else None

    in_panic     = False
    panic_offset = 0
    panic_shown  = 20
    t_start      = time.monotonic()
    last_poll    = time.monotonic()

    def input_loop() -> None:
        while not stop_event.is_set():
            try:
                key_queue.put(_get_key())
            except Exception:
                pass

    threading.Thread(target=input_loop, daemon=True).start()

    with Live(screen=True, refresh_per_second=_RENDER_HZ) as live:
      while True:
        now = time.monotonic() - t_start

        # Poll Spotify on interval (not every frame)
        if time.monotonic() - last_poll >= _SPOTIFY_POLL:
            if hasattr(client, 'tick'):
                client.tick(int(_SPOTIFY_POLL * 1000))
            fresh = client.get_current_track()
            if fresh:
                track = fresh
                if fresh['id'] != last_id:
                    last_id  = fresh['id']
                    features = client.get_audio_features(last_id)
                    liked    = client.is_liked(last_id)
            else:
                track = None
            last_poll = time.monotonic()

        # Render every frame
        wv_lines = generate(
            energy=(features or {}).get('energy', 0.5),
            width=80,
            t=now,
        )

        if in_panic:
            renderable, panic_shown = panic_renderable(panic_offset, _PANIC_CODE)
        else:
            renderable = player_renderable(track, features, wv_lines, liked)

        live.update(renderable)
        time.sleep(1 / _RENDER_HZ)

        # Drain keys accumulated this frame
        keys = []
        while not key_queue.empty():
            try:
                keys.append(key_queue.get_nowait())
            except queue.Empty:
                break

        for key in keys:
            # ── Panic mode ──────────────────────────────────────────
            if in_panic:
                max_p = max(0, _PANIC_TOTAL - panic_shown)
                if key in ('q', 'QUIT'):
                    stop_event.set()
                    return
                elif key == 'ESC':
                    in_panic = False
                elif key in ('j', 'DOWN'):
                    panic_offset = min(panic_offset + 1, max_p)
                elif key in ('k', 'UP'):
                    panic_offset = max(0, panic_offset - 1)
                elif key == 'd':
                    panic_offset = min(panic_offset + panic_shown // 2, max_p)
                elif key == 'u':
                    panic_offset = max(0, panic_offset - panic_shown // 2)
                elif key in ('f', ' ', 'PGDN'):
                    panic_offset = min(panic_offset + panic_shown, max_p)
                elif key in ('b', 'PGUP'):
                    panic_offset = max(0, panic_offset - panic_shown)
                elif key == 'g':
                    panic_offset = 0
                elif key == 'G':
                    panic_offset = max_p
                continue

            # ── ESC → enter panic ────────────────────────────────────
            if key == 'ESC':
                in_panic = True
                continue

            # ── Player controls ──────────────────────────────────────
            if key in ('q', 'QUIT'):
                stop_event.set()
                return
            elif key == ' ':
                client.play_pause()
            elif key == 'n':
                client.next_track()
                track    = client.get_current_track()
                if track:
                    last_id  = track['id']
                    features = client.get_audio_features(last_id)
                    liked    = client.is_liked(last_id)
            elif key == 'p':
                client.prev_track()
                track    = client.get_current_track()
                if track:
                    last_id  = track['id']
                    features = client.get_audio_features(last_id)
                    liked    = client.is_liked(last_id)
            elif key == '=':
                vol = (track or {}).get('volume', 50)
                client.set_volume(vol + 5)
            elif key == '-':
                vol = (track or {}).get('volume', 50)
                client.set_volume(vol - 5)
            elif key == 's':
                client.toggle_shuffle()
            elif key == 'l' and track:
                liked = client.toggle_like(track['id'])


if __name__ == '__main__':
    main()
