import os
import sys
import json
import webbrowser
from pathlib import Path
import urllib.parse

import spotipy
from spotipy.oauth2 import SpotifyOAuth
import requests


def main():
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    redirect_uri = "http://127.0.0.1:8888/callback"

    if not client_id:
        print("Error: SPOTIFY_CLIENT_ID environment variable not set")
        print("Please set it with: export SPOTIFY_CLIENT_ID=your_client_id")
        sys.exit(1)

    if not client_secret:
        print("Error: SPOTIFY_CLIENT_SECRET environment variable not set")
        print("Please set it with: export SPOTIFY_CLIENT_SECRET=your_client_secret")
        sys.exit(1)

    print("Starting OAuth authorization...")
    print(f"Using redirect URI: {redirect_uri}")
    print("Make sure this EXACTLY matches the redirect URI in your Spotify app settings!")
    print()

    cache_dir = Path.home() / ".spotify_aggregator"
    cache_dir.mkdir(exist_ok=True)
    cache_path = cache_dir / "token_cache.json"

    scope = "playlist-modify-public playlist-modify-private playlist-read-private playlist-read-collaborative user-read-private"

    auth_params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": scope,
    }

    auth_url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode(auth_params)

    print("Opening browser for authorization...")
    print(f"If the browser doesn't open, visit this URL manually:")
    print(auth_url)
    print()

    webbrowser.open(auth_url)

    print("After authorizing, you'll be redirected to a localhost URL.")
    print("The page may show an error (that's OK - just copy the URL).")
    print("Copy the FULL URL from your browser's address bar and paste it here:")
    response = input("Redirect URL: ").strip()

    try:
        parsed = urllib.parse.urlparse(response)
        params = urllib.parse.parse_qs(parsed.query)
        if "code" not in params:
            print("Error: Could not find authorization code in URL")
            print(f"URL received: {response}")
            sys.exit(1)
        code = params["code"][0]
    except Exception as e:
        print(f"Error parsing URL: {e}")
        print(f"URL received: {response}")
        sys.exit(1)

    print("Exchanging authorization code for tokens...")

    token_url = "https://accounts.spotify.com/api/token"
    token_data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
    }

    response = requests.post(token_url, data=token_data)

    if response.status_code != 200:
        print(f"Error exchanging code for tokens: {response.status_code}")
        print(f"Response: {response.text}")
        sys.exit(1)

    token_info = response.json()

    token_data = {
        'access_token': token_info['access_token'],
        'refresh_token': token_info.get('refresh_token'),
        'expires_at': token_info.get('expires_in'),
        'scope': token_info.get('scope'),
        'client_id': client_id,
        'client_secret': client_secret,
    }

    with open(cache_path, 'w') as f:
        json.dump(token_data, f, indent=2)

    refresh_token = token_info.get('refresh_token')

    if refresh_token:
        print()
        print("=" * 60)
        print("SUCCESS! Authorization complete.")
        print("=" * 60)
        print()
        print("Your refresh token is:")
        print(refresh_token)
        print()
        print("Add this to your GitHub Secrets as SPOTIFY_REFRESH_TOKEN")
        print("You can also set it locally with:")
        print(f"export SPOTIFY_REFRESH_TOKEN={refresh_token}")
        print()
        print(f"Token cache saved to: {cache_path}")
    else:
        print("Warning: No refresh token received. You may need to re-authorize later.")
        print("Access token saved to cache for now.")

    print()
    print("Testing connection...")
    try:
        auth_manager = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scope,
            cache_path=str(cache_path),
        )
        sp = spotipy.Spotify(auth_manager=auth_manager)
        user = sp.current_user()
        print(f"✓ Connected as: {user['display_name']} ({user['id']})")
    except Exception as e:
        print(f"✗ Connection test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
