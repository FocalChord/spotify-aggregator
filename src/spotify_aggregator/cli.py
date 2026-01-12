import argparse
import sys
from typing import List, Dict, Set, Any

from spotify_aggregator.config import Config, ConfigError
from spotify_aggregator.spotify_client import SpotifyClient


class PlaylistAggregator:
    def __init__(self, client: SpotifyClient, config: Config, dry_run: bool = False):
        self.client = client
        self.config = config
        self.dry_run = dry_run

    def resolve_playlist_names(self, patterns: List[str]) -> List[Dict[str, Any]]:
        all_playlists = self.client.get_user_playlists()
        resolved = []
        seen_ids = set()

        for pattern in patterns:
            if '*' in pattern or '?' in pattern or '[' in pattern:
                matches = self.client.find_playlists_by_pattern(pattern)
                if not matches:
                    raise ValueError(f"No playlists found matching pattern: {pattern}")
                matches.sort(key=lambda p: p['name'])
                for match in matches:
                    if match['id'] not in seen_ids:
                        resolved.append(match)
                        seen_ids.add(match['id'])
            else:
                playlist = self.client.find_playlist_by_name(pattern)
                if not playlist:
                    raise ValueError(f"Playlist not found: {pattern}")
                if playlist['id'] not in seen_ids:
                    resolved.append(playlist)
                    seen_ids.add(playlist['id'])

        return resolved

    def collect_tracks(self, playlists: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        all_tracks = []
        seen_uris: Set[str] = set()

        print(f"Collecting tracks from {len(playlists)} source playlist(s)...")

        for playlist in playlists:
            print(f"  - {playlist['name']} ({playlist['tracks']['total']} tracks)")
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
            user = self.client.get_current_user()
            print(f"Authenticated as: {user['display_name']} ({user['id']})\n")

            print("Resolving source playlists...")
            source_playlists = self.resolve_playlist_names(self.config.source_playlists)
            print(f"Found {len(source_playlists)} source playlist(s):")
            for pl in source_playlists:
                print(f"  - {pl['name']}")
            print()

            all_tracks = self.collect_tracks(source_playlists)
            track_uris = self.get_track_uris(all_tracks)

            if not track_uris:
                print("No tracks to aggregate.")
                return

            print(f"\nResolving target playlist: {self.config.target_playlist}")
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
                print(f"  Found existing playlist: {target_playlist['name']}")
                current_tracks = self.client.get_playlist_tracks(target_playlist['id'])
                current_uris = set(self.get_track_uris(current_tracks))

            new_uris = set(track_uris)

            to_add = new_uris - current_uris
            to_remove = current_uris - new_uris

            print(f"\nCurrent tracks in target: {len(current_uris)}")
            print(f"Tracks to add: {len(to_add)}")
            print(f"Tracks to remove: {len(to_remove)}")

            if self.dry_run:
                print("\n[DRY RUN] Would update playlist with:")
                print(f"  - {len(track_uris)} total tracks")
                if to_add:
                    print(f"  - {len(to_add)} new tracks")
                if to_remove:
                    print(f"  - {len(to_remove)} tracks to be removed")
                print("\nRun without --dry-run to apply changes.")
            else:
                print(f"\nUpdating playlist with {len(track_uris)} tracks...")
                self.client.replace_playlist_tracks(target_playlist['id'], track_uris)
                print("✓ Playlist updated successfully!")

        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Unexpected error: {e}", file=sys.stderr)
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
