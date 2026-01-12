# Spotify Playlist Aggregator

A CLI tool that automatically aggregates multiple Spotify playlists into a single "master" playlist.

## Features

- Aggregate tracks from multiple source playlists into one target playlist
- Automatic deduplication by track URI
- Support for glob pattern matching on playlist names (e.g., "202*" matches "2023", "2024", etc.)
- Preserves track order from source playlists
- Dry-run mode to preview changes
- GitHub Actions integration for scheduled automation

## Setup

### 1. Install uv

If you don't have `uv` installed:

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or with Homebrew
brew install uv

# Or with pip
pip install uv
```

### 2. Install Dependencies

```bash
# Sync dependencies (creates virtual environment automatically)
uv sync

# Or if you want to install in an existing environment
uv pip install -e .
```

### 3. Create Spotify App

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create a new app
3. Note your **Client ID** and **Client Secret**
4. Add a redirect URI: `http://127.0.0.1:8888/callback`

### 4. Initial OAuth Authorization

Run the setup script to get your refresh token:

```bash
export SPOTIFY_CLIENT_ID=your_client_id
export SPOTIFY_CLIENT_SECRET=your_client_secret
uv run python bin/setup_auth.py
```

This will:
- Open a browser for authorization
- Save a refresh token locally
- Display the refresh token to add to GitHub Secrets

### 5. Configure GitHub Secrets

Add these secrets to your GitHub repository:
- `SPOTIFY_CLIENT_ID` - Your Spotify app client ID
- `SPOTIFY_CLIENT_SECRET` - Your Spotify app client secret
- `SPOTIFY_REFRESH_TOKEN` - The refresh token from step 3

### 6. Create Config File

Copy the example config and customize it:

```bash
cp config.example.yaml config.yaml
```

Then edit `config.yaml` with your playlist names:

```yaml
target_playlist: "All Time Favorites"
source_playlists:
  - "2023"
  - "2024"
  - "2025"
```

Or use glob patterns:

```yaml
target_playlist: "All Time Favorites"
source_playlists:
  - "202*"  # Matches 2020, 2021, 2022, etc.
```

## Usage

### Local Run

```bash
# Set environment variables
export SPOTIFY_CLIENT_ID=your_client_id
export SPOTIFY_CLIENT_SECRET=your_client_secret
export SPOTIFY_REFRESH_TOKEN=your_refresh_token

# Run aggregation
uv run spotify-aggregate --config config.yaml

# Dry-run mode (preview changes without applying)
uv run spotify-aggregate --config config.yaml --dry-run
```

### GitHub Actions

The workflow runs automatically on a schedule (configure in `.github/workflows/aggregate.yml`).

You can also trigger it manually from the Actions tab.

## How It Works

1. Reads the config file to identify source and target playlists
2. Authenticates with Spotify using OAuth refresh token
3. Fetches all playlists and resolves names to IDs
4. Expands glob patterns to matching playlist names
5. Fetches all tracks from each source playlist
6. Deduplicates tracks by track URI
7. Orders tracks by source playlist order (as listed in config)
8. Replaces target playlist contents with aggregated tracks

## Error Handling

The tool handles:
- Missing or ambiguous playlist names
- Rate limiting (with exponential backoff)
- Token expiration (automatic refresh)
- Network errors (with retry logic)
- Invalid config format

## License

MIT
