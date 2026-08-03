import argparse
import fnmatch
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import List, Dict, Optional, Set, Any

from spotify_aggregator.config import Config, ConfigError
from spotify_aggregator.spotify_client import SpotifyClient


def _print(msg: str, **kwargs):
    print(msg, **kwargs)
    sys.stdout.flush()


_PLAYLIST_ID_RE = re.compile(
    r'^(?:spotify:playlist:|https://open\.spotify\.com/playlist/)?([0-9A-Za-z]{22})(?:\?.*)?$'
)


def _playlist_id(ref: str) -> Optional[str]:
    match = _PLAYLIST_ID_RE.match(ref)
    return match.group(1) if match else None


class PlaylistAggregator:
    def __init__(self, client: SpotifyClient, config: Config, dry_run: bool = False):
        self.client = client
        self.config = config
        self.dry_run = dry_run
        self._listing = None

    def _get_listing(self) -> List[Dict[str, Any]]:
        if self._listing is None:
            try:
                self._listing = self.client.get_user_playlists()
            except Exception as e:
                _print(f"Warning: could not fetch playlist listing: {e}")
                self._listing = []
            _print(f"Fetched {len(self._listing)} playlists")
        return self._listing

    def discover_playlists(self, pattern: str, owner_id: str) -> List[Dict[str, Any]]:
        cache_path = Path(os.getenv("PLAYLIST_CACHE_FILE", ".playlist_cache.json"))
        listing = self._get_listing()

        if listing:
            by_name: Dict[str, Dict[str, Any]] = {}
            for p in listing:
                if p['owner']['id'] != owner_id or not fnmatch.fnmatch(p['name'], pattern):
                    continue
                if p['name'] in by_name:
                    _print(f"  Warning: multiple playlists named '{p['name']}'; "
                           f"using the first one listed")
                else:
                    by_name[p['name']] = p
            discovered = sorted(by_name.values(), key=lambda p: p['name'])
            try:
                cache_path.write_text(json.dumps(
                    [{'id': p['id'], 'name': p['name']} for p in discovered],
                    indent=2) + "\n")
            except IOError as e:
                _print(f"  Warning: could not write discovery cache: {e}")
            return discovered

        if cache_path.exists():
            cached = json.loads(cache_path.read_text())
            _print(f"  Listing unavailable; falling back to {len(cached)} "
                   f"cached playlists from {cache_path}")
            return [self.client.get_playlist(entry['id']) for entry in cached]

        raise ValueError(
            f"Playlist listing unavailable and no discovery cache ({cache_path}) "
            "exists. Run once from a network where the listing works to seed it."
        )

    def resolve_playlist_names(self, patterns: List[str]) -> List[Dict[str, Any]]:
        resolved = []
        seen_ids = set()

        for pattern in patterns:
            pid = _playlist_id(pattern)
            if pid:
                playlist = self.client.get_playlist(pid)
                if playlist['id'] not in seen_ids:
                    resolved.append(playlist)
                    seen_ids.add(playlist['id'])
            elif '*' in pattern or '?' in pattern or '[' in pattern:
                matches = [p for p in self._get_listing() if fnmatch.fnmatch(p['name'], pattern)]
                if not matches:
                    raise ValueError(f"No playlists found matching pattern: {pattern}")
                matches.sort(key=lambda p: p['name'])
                for match in matches:
                    if match['id'] not in seen_ids:
                        resolved.append(match)
                        seen_ids.add(match['id'])
            else:
                playlist = next((p for p in self._get_listing() if p['name'] == pattern), None)
                if not playlist:
                    raise ValueError(
                        f"Playlist not found: {pattern} (if the playlist exists, the "
                        "listing endpoint may be unavailable — use its ID instead)"
                    )
                if playlist['id'] not in seen_ids:
                    resolved.append(playlist)
                    seen_ids.add(playlist['id'])

        return resolved

    def collect_tracks_routed(
        self,
        year_playlists: List[Dict[str, Any]],
        extra_playlists: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        years = sorted(year_playlists, key=lambda p: p['name'])
        year_keys = [int(p['name']) for p in years]
        buckets: Dict[int, List[Dict[str, Any]]] = {y: [] for y in year_keys}

        print(f"Collecting tracks from {len(years)} year playlist(s), routing "
              f"{len(extra_playlists)} extra(s) by added year...")

        year_tracks = {}
        for playlist in years:
            _print(f"  - {playlist['name']} ({playlist['tracks']['total']} tracks)")
            year_tracks[int(playlist['name'])] = self.client.get_playlist_tracks(playlist['id'])

        for playlist in extra_playlists:
            _print(f"  - {playlist['name']} ({playlist['tracks']['total']} tracks)")
            routed = Counter()
            for item in self.client.get_playlist_tracks(playlist['id']):
                if not (item['track'] and item['track']['uri']):
                    continue
                year = int(item['added_at'][:4]) if item.get('added_at') else year_keys[-1]
                year = min(max(year, year_keys[0]), year_keys[-1])
                while year not in buckets:
                    year -= 1
                buckets[year].append(item)
                routed[year] += 1
            _print(f"      routed to: {dict(sorted(routed.items()))}")

        all_tracks = []
        seen_uris: Set[str] = set()
        for year in year_keys:
            for item in year_tracks[year] + buckets[year]:
                uri = item['track']['uri'] if item['track'] else None
                if uri and uri not in seen_uris:
                    all_tracks.append(item)
                    seen_uris.add(uri)

        print(f"\nTotal unique tracks: {len(all_tracks)}")
        return all_tracks

    def collect_tracks(self, playlists: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        all_tracks = []
        seen_uris: Set[str] = set()

        print(f"Collecting tracks from {len(playlists)} source playlist(s)...")

        for playlist in playlists:
            _print(f"  - {playlist['name']} ({playlist['tracks']['total']} tracks)")
            tracks = self.client.get_playlist_tracks(playlist['id'])

            for track_item in tracks:
                if track_item['track'] and track_item['track']['uri']:
                    track_uri = track_item['track']['uri']
                    if track_uri not in seen_uris:
                        all_tracks.append(track_item)
                        seen_uris.add(track_uri)

        print(f"\nTotal unique tracks: {len(all_tracks)}")
        return all_tracks

    def get_track_uris(self, track_items: List[Dict[str, Any]]) -> List[str]:
        uris = []
        for item in track_items:
            if item['track'] and item['track']['uri']:
                uris.append(item['track']['uri'])
        return uris

    def aggregate(self):
        try:
            _print("Authenticating...")
            user = self.client.get_current_user()
            _print(f"Authenticated as: {user['display_name']} ({user['id']})\n")

            _print("Resolving source playlists...")
            source_playlists = []
            seen_ids: Set[str] = set()

            if self.config.discover_pattern:
                discovered = self.discover_playlists(self.config.discover_pattern, user['id'])
                _print(f"  Discovered {len(discovered)} playlist(s) matching "
                       f"'{self.config.discover_pattern}'")
                for playlist in discovered:
                    if playlist['id'] not in seen_ids:
                        source_playlists.append(playlist)
                        seen_ids.add(playlist['id'])

            explicit = self.config.source_playlists + self.config.extra_playlists
            for playlist in self.resolve_playlist_names(explicit):
                if playlist['id'] not in seen_ids:
                    source_playlists.append(playlist)
                    seen_ids.add(playlist['id'])

            _print(f"Found {len(source_playlists)} source playlist(s):")
            for pl in source_playlists:
                _print(f"  - {pl['name']}")
            _print("")

            year_blocks = [p for p in source_playlists if re.fullmatch(r'\d{4}', p['name'] or '')]
            extras = [p for p in source_playlists if p not in year_blocks]
            if self.config.get('route_extras_by_added_year') and year_blocks and extras:
                all_tracks = self.collect_tracks_routed(year_blocks, extras)
            else:
                all_tracks = self.collect_tracks(source_playlists)
            track_uris = self.get_track_uris(all_tracks)

            if not track_uris:
                _print("No tracks to aggregate.")
                return

            _print(f"\nResolving target playlist: {self.config.target_playlist}")
            target_id = _playlist_id(self.config.target_playlist)
            if target_id:
                target_playlist = self.client.get_playlist(target_id)
            else:
                target_playlist = self.client.find_playlist_by_name(self.config.target_playlist)

            if not target_playlist:
                if self.dry_run:
                    print(f"  [DRY RUN] Would create playlist: {self.config.target_playlist}")
                    current_uris = set()
                else:
                    print(f"  Creating playlist: {self.config.target_playlist}")
                    target_playlist = self.client.create_playlist(
                        self.config.target_playlist,
                        description="Aggregated playlist created by spotify-aggregator"
                    )
                    current_tracks = self.client.get_playlist_tracks(target_playlist['id'])
                    current_uris = set(self.get_track_uris(current_tracks))
            else:
                _print(f"  Found existing playlist: {target_playlist['name']}")
                current_tracks = self.client.get_playlist_tracks(target_playlist['id'])
                current_uris = set(self.get_track_uris(current_tracks))

            new_uris = set(track_uris)

            to_add = new_uris - current_uris
            to_remove = current_uris - new_uris

            _print(f"\nCurrent tracks in target: {len(current_uris)}")
            _print(f"Tracks to add: {len(to_add)}")
            _print(f"Tracks to remove: {len(to_remove)}")

            if self.dry_run:
                _print("\n[DRY RUN] Would update playlist with:")
                _print(f"  - {len(track_uris)} total tracks")
                if to_add:
                    print(f"  - {len(to_add)} new tracks")
                if to_remove:
                    print(f"  - {len(to_remove)} tracks to be removed")
                _print("\nRun without --dry-run to apply changes.")
            else:
                _print(f"\nUpdating playlist with {len(track_uris)} tracks...")
                self.client.replace_playlist_tracks(target_playlist['id'], track_uris)
                _print("✓ Playlist updated successfully!")

        except ValueError as e:
            _print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            _print(f"Unexpected error: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Aggregate multiple Spotify playlists into one master playlist"
    )
    parser.add_argument(
        '--config',
        required=True,
        help='Path to config file (YAML or JSON)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would change without making modifications'
    )

    args = parser.parse_args()

    try:
        config = Config(args.config)
        client = SpotifyClient()
        aggregator = PlaylistAggregator(client, config, dry_run=args.dry_run)
        aggregator.aggregate()

    except ConfigError as e:
        print(f"Config error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
