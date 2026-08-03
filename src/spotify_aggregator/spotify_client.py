import os
import json
import time
import fnmatch
from pathlib import Path
from typing import Optional, Dict, List, Any

import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotipy.exceptions import SpotifyException


class SpotifyClient:
    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        refresh_token: Optional[str] = None,
        redirect_uri: str = "http://127.0.0.1:8888/callback",
        cache_path: Optional[str] = None,
    ):
        self.client_id = client_id or os.getenv("SPOTIFY_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("SPOTIFY_CLIENT_SECRET")
        self.refresh_token = refresh_token or os.getenv("SPOTIFY_REFRESH_TOKEN")
        self.redirect_uri = redirect_uri

        if not self.client_id:
            raise ValueError("SPOTIFY_CLIENT_ID must be provided or set as environment variable")
        if not self.client_secret:
            raise ValueError("SPOTIFY_CLIENT_SECRET must be provided or set as environment variable")
        if not self.refresh_token:
            raise ValueError("SPOTIFY_REFRESH_TOKEN must be provided or set as environment variable")

        if cache_path:
            self.cache_path = Path(cache_path)
        else:
            cache_dir = Path(os.getenv("RUNNER_TEMP", os.getenv("TMPDIR", str(Path.home())))) / ".spotify_aggregator"
            cache_dir.mkdir(exist_ok=True, parents=True)
            self.cache_path = cache_dir / "token_cache.json"

        self._init_client()

    def _init_client(self):
        auth_manager = SpotifyOAuth(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
            scope="playlist-modify-public playlist-modify-private playlist-read-private playlist-read-collaborative user-read-private",
            cache_path=str(self.cache_path),
            open_browser=False,
        )

        if self.refresh_token:
            cache_data = {}
            if self.cache_path.exists():
                try:
                    with open(self.cache_path, 'r') as f:
                        cache_data = json.load(f)
                except (json.JSONDecodeError, IOError):
                    pass

            cache_data['refresh_token'] = self.refresh_token
            cache_data['client_id'] = self.client_id
            cache_data['client_secret'] = self.client_secret

            with open(self.cache_path, 'w') as f:
                json.dump(cache_data, f)

            try:
                auth_manager.refresh_access_token(self.refresh_token)
            except Exception as e:
                raise RuntimeError(
                    f"Token refresh failed: {e}. "
                    "The refresh token is invalid or expired — run bin/setup_auth.py "
                    "locally and update the SPOTIFY_REFRESH_TOKEN secret."
                ) from e

        self.client = spotipy.Spotify(auth_manager=auth_manager)

    def _retry_with_backoff(self, func, max_retries: int = 3, base_delay: float = 1.0):
        for attempt in range(max_retries):
            try:
                return func()
            except SpotifyException as e:
                if e.http_status == 429:
                    retry_after = int(e.headers.get('Retry-After', base_delay * (2 ** attempt)))
                    if attempt < max_retries - 1:
                        print(f"Rate limited. Waiting {retry_after} seconds...")
                        time.sleep(retry_after)
                        continue
                elif e.http_status == 401:
                    if attempt < max_retries - 1:
                        print("Token expired. Refreshing...")
                        self._init_client()
                        continue
                raise
            except Exception as e:
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    print(f"Error: {e}. Retrying in {delay} seconds...")
                    time.sleep(delay)
                    continue
                raise

        raise Exception("Max retries exceeded")

    def get_current_user(self) -> Dict[str, Any]:
        return self._retry_with_backoff(lambda: self.client.current_user())

    def get_user_playlists(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        playlists = []
        if not user_id:
            user_id = self.get_current_user()['id']
        
        results = self._retry_with_backoff(
            lambda: self.client.user_playlists(user_id)
        )

        playlists.extend(results['items'])

        while results['next']:
            results = self._retry_with_backoff(lambda: self.client.next(results))
            playlists.extend(results['items'])

        return playlists

    def find_playlist_by_name(self, name: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        playlists = self.get_user_playlists(user_id)
        for playlist in playlists:
            if playlist['name'] == name:
                return playlist
        return None

    def find_playlists_by_pattern(self, pattern: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        playlists = self.get_user_playlists(user_id)
        matches = []
        for playlist in playlists:
            if fnmatch.fnmatch(playlist['name'], pattern):
                matches.append(playlist)
        return matches

    def get_playlist_tracks(self, playlist_id: str) -> List[Dict[str, Any]]:
        tracks = []
        results = self._retry_with_backoff(
            lambda: self.client.playlist_tracks(playlist_id)
        )

        tracks.extend(results['items'])

        while results['next']:
            results = self._retry_with_backoff(lambda: self.client.next(results))
            tracks.extend(results['items'])

        return tracks

    def create_playlist(self, name: str, description: str = "", user_id: Optional[str] = None) -> Dict[str, Any]:
        if not user_id:
            user_id = self.get_current_user()['id']

        return self._retry_with_backoff(
            lambda: self.client.user_playlist_create(
                user_id,
                name,
                public=True,
                description=description
            )
        )

    def replace_playlist_tracks(self, playlist_id: str, track_uris: List[str]):
        batch_size = 100

        if track_uris:
            for i in range(0, len(track_uris), batch_size):
                batch = track_uris[i:i + batch_size]
                if i == 0:
                    self._retry_with_backoff(
                        lambda: self.client.playlist_replace_items(playlist_id, batch)
                    )
                else:
                    self._retry_with_backoff(
                        lambda: self.client.playlist_add_items(playlist_id, batch)
                    )
        else:
            self._retry_with_backoff(
                lambda: self.client.playlist_replace_items(playlist_id, [])
            )
