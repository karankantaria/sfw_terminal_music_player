"""
Spotify API client.

Reads credentials from environment variables (or a .env file loaded by
the caller). Set SPOTIFY_MOCK=1 to use MockClient without any API calls —
useful for UI development and testing.

Required env vars:
    SPOTIFY_CLIENT_ID
    SPOTIFY_CLIENT_SECRET
    SPOTIFY_REDIRECT_URI   (default: http://127.0.0.1:8888/callback)

Required Spotify scopes (Premium account needed for playback control):
    user-read-playback-state
    user-modify-playback-state
    user-read-currently-playing
    user-library-read
    user-library-modify
"""

import os

SCOPE = (
    'user-read-playback-state '
    'user-modify-playback-state '
    'user-read-currently-playing '
    'user-library-read '
    'user-library-modify'
)


# ── Real client (requires spotipy + credentials) ──────────────────────────────

class SpotifyClient:
    def __init__(self):
        # TODO: uncomment once credentials are configured
        from spotipy import Spotify
        from spotipy.oauth2 import SpotifyOAuth
        self._sp = Spotify(auth_manager=SpotifyOAuth(
            client_id     = os.environ['SPOTIFY_CLIENT_ID'],
            client_secret = os.environ['SPOTIFY_CLIENT_SECRET'],
            redirect_uri  = os.getenv('SPOTIFY_REDIRECT_URI', 'http://127.0.0.1:8888/callback'),
            scope         = SCOPE,
        ))
        #raise NotImplementedError("Configure .env and uncomment SpotifyOAuth block")

    def get_current_track(self) -> dict | None:
        """Return current playback state or None if nothing is playing."""
        try:
            pb = self._sp.current_playback()
            if not pb or not pb.get('item'):
                return None
            item = pb['item']
            return {
                'id':          item['id'],
                'name':        item['name'],
                'artist':      item['artists'][0]['name'],
                'album':       item['album']['name'],
                'duration_ms': item['duration_ms'],
                'progress_ms': pb['progress_ms'],
                'is_playing':  pb['is_playing'],
                'shuffle':     pb.get('shuffle_state', False),
                'repeat':      pb.get('repeat_state', 'off'),
                'volume':      (pb.get('device') or {}).get('volume_percent', 50),
            }
        except Exception:
            return None

    def get_audio_features(self, track_id: str) -> dict | None:
        try:
            feats = self._sp.audio_features([track_id])
            return feats[0] if feats else None
        except Exception:
            return None

    def is_liked(self, track_id: str) -> bool:
        try:
            return self._sp.current_user_saved_tracks_contains([track_id])[0]
        except Exception:
            return False

    def play_pause(self) -> None:
        try:
            pb = self._sp.current_playback()
            if pb and pb['is_playing']:
                self._sp.pause_playback()
            else:
                self._sp.start_playback()
        except Exception:
            pass

    def next_track(self) -> None:
        try:
            self._sp.next_track()
        except Exception:
            pass

    def prev_track(self) -> None:
        try:
            self._sp.previous_track()
        except Exception:
            pass

    def set_volume(self, pct: int) -> None:
        try:
            self._sp.volume(max(0, min(100, pct)))
        except Exception:
            pass

    def toggle_shuffle(self) -> None:
        try:
            pb = self._sp.current_playback()
            if pb:
                self._sp.shuffle(not pb['shuffle_state'])
        except Exception:
            pass

    def toggle_like(self, track_id: str) -> bool | None:
        """Toggle saved status. Returns new liked state or None on error."""
        try:
            if self._sp.current_user_saved_tracks_contains([track_id])[0]:
                self._sp.current_user_saved_tracks_delete([track_id])
                return False
            else:
                self._sp.current_user_saved_tracks_add([track_id])
                return True
        except Exception:
            return None


# ── Mock client (no credentials needed) ───────────────────────────────────────

class MockClient:
    """Simulates Spotify responses for UI development."""

    _TRACKS = [
        {
            'id': 'mock-001',
            'name': 'Blinding Lights',
            'artist': 'The Weeknd',
            'album': 'After Hours',
            'duration_ms': 200_040,
            'is_playing': True,
            'shuffle': False,
            'repeat': 'off',
            'volume': 72,
        },
        {
            'id': 'mock-002',
            'name': 'Levitating',
            'artist': 'Dua Lipa',
            'album': 'Future Nostalgia',
            'duration_ms': 203_064,
            'is_playing': True,
            'shuffle': False,
            'repeat': 'off',
            'volume': 72,
        },
        {
            'id': 'mock-003',
            'name': 'Stay',
            'artist': 'The Kid LAROI, Justin Bieber',
            'album': 'F*CK LOVE 3: OVER YOU',
            'duration_ms': 141_805,
            'is_playing': True,
            'shuffle': False,
            'repeat': 'off',
            'volume': 72,
        },
    ]

    _FEATURES = [
        {'energy': 0.730, 'loudness': -5.8,  'tempo': 171.0, 'valence': 0.334, 'key': 1,  'mode': 0},
        {'energy': 0.823, 'loudness': -4.1,  'tempo': 103.0, 'valence': 0.915, 'key': 5,  'mode': 1},
        {'energy': 0.686, 'loudness': -4.8,  'tempo': 169.9, 'valence': 0.644, 'key': 10, 'mode': 1},
    ]

    def __init__(self):
        self._idx       = 0
        self._progress  = 30_000
        self._liked     = [False, False, False]

    def _track(self) -> dict:
        t = dict(self._TRACKS[self._idx])
        t['progress_ms'] = self._progress
        return t

    def get_current_track(self) -> dict:
        return self._track()

    def get_audio_features(self, _track_id: str) -> dict:
        return dict(self._FEATURES[self._idx])

    def is_liked(self, _track_id: str) -> bool:
        return self._liked[self._idx]

    def play_pause(self) -> None:
        t = self._TRACKS[self._idx]
        t['is_playing'] = not t['is_playing']

    def next_track(self) -> None:
        self._idx      = (self._idx + 1) % len(self._TRACKS)
        self._progress = 0

    def prev_track(self) -> None:
        self._idx      = (self._idx - 1) % len(self._TRACKS)
        self._progress = 0

    def set_volume(self, pct: int) -> None:
        for t in self._TRACKS:
            t['volume'] = max(0, min(100, pct))

    def toggle_shuffle(self) -> None:
        t = self._TRACKS[self._idx]
        t['shuffle'] = not t['shuffle']

    def toggle_like(self, _track_id: str) -> bool:
        self._liked[self._idx] = not self._liked[self._idx]
        return self._liked[self._idx]

    def tick(self, ms: int = 1000) -> None:
        """Advance playback position — call each refresh cycle."""
        t = self._TRACKS[self._idx]
        if t['is_playing']:
            self._progress = min(self._progress + ms, t['duration_ms'])


def get_client():
    """Return MockClient if SPOTIFY_MOCK=1, else real SpotifyClient."""
    if os.getenv('SPOTIFY_MOCK', '0') == '1':
        return MockClient()
    return SpotifyClient()
