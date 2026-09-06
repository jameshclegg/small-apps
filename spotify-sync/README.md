# Spotify Sync

Ranks favorite Spotify songs and albums, compares them with an iTunes XML
library, and writes a Markdown shopping list of missing music.

The Spotify Web API does not expose an exact three-year play history. This
tool combines:

- Spotify Extended Streaming History for exact plays and listening time
- API top tracks across short-, medium-, and long-term ranges
- owned `Your Top Songs YYYY` playlists from the selected years

Spotify's 2026 Development Mode rules hide the contents of playlists owned by
Spotify, including the original annual playlists. To include one, copy its
tracks into a playlist you own and keep `Top Songs YYYY` in the copy's name.
The script reports a warning when it finds an annual playlist it cannot read.
Spotify also requires the app owner to have Premium in Development Mode.

## Setup

1. Request **Extended streaming history** from Spotify's account privacy page.
2. Create an app in the [Spotify developer dashboard](https://developer.spotify.com/dashboard).
3. Add `http://127.0.0.1:8888/callback` as a redirect URI.
4. Install the dependency:

```powershell
cd spotify-sync
py -m pip install -r requirements.txt
```

Set the Spotify app credentials in the current PowerShell session:

```powershell
$env:SPOTIPY_CLIENT_ID = "your-client-id"
$env:SPOTIPY_CLIENT_SECRET = "your-client-secret"
$env:SPOTIPY_REDIRECT_URI = "http://127.0.0.1:8888/callback"
```

Do not commit these values. The first API run opens a browser for Spotify
authorization and stores the resulting token in `.cache`, which is ignored by
Git.

Alternatively, omit the environment variables and run the command below. The
tool prompts for the Client ID and a hidden Client Secret; neither value is
written to disk:

```powershell
py spotify_sync.py
```

To avoid entering credentials on every run, store them in Windows Credential
Manager. They remain outside the repository:

```powershell
py spotify_sync.py --configure
```

## Run

Pass the downloaded Spotify ZIP directly:

```powershell
py spotify_sync.py --history "$HOME\Downloads\my_spotify_data.zip"
```

Or pass the extracted export directory:

```powershell
py spotify_sync.py --history "$HOME\Downloads\Spotify Extended Streaming History"
```

By default, the tool searches `OneDrive\Music\iTunes` and uses the most recently
modified XML catalog. On this computer that selects the 2026 catalog in
`Previous iTunes Libraries`. Override either path when needed:

```powershell
py spotify_sync.py `
  --history "$HOME\Downloads\my_spotify_data.zip" `
  --itunes "$HOME\OneDrive\Music\iTunes\iTunes Library.xml" `
  --output "my-favorites.md"
```

To generate a history-only report without Spotify API credentials:

```powershell
py spotify_sync.py --history "$HOME\Downloads\my_spotify_data.zip" --no-api
```

Include tracks from a specific owned playlist by ID or URL:

```powershell
py spotify_sync.py --playlist "https://open.spotify.com/playlist/playlist-id"
```

Create a UK iTunes Store purchase guide and an importable playlist containing
the files already owned:

```powershell
py itunes_purchase_report.py --playlist "spotify-playlist-id"
```

The search is intentionally rate-limited to respect Apple's documented limit
and cached in `.itunes-search-cache.json`. Import the generated `.m3u8` file
into iTunes with **File → Library → Import Playlist**. Rerun after downloading
purchases to refresh the owned playlist. The tool only creates links; it never
makes purchases.

## Interactive history dashboard

Generate a self-contained local dashboard from any Extended Streaming History
directory or ZIP:

```powershell
py spotify_dashboard.py `
  --history "$HOME\OneDrive\Music\my_spotify_data" `
  --playlist "spotify-playlist-id" `
  --output spotify-dashboard.html
```

The optional playlist argument adds contributor and evolution analysis using
the securely stored Spotify credentials. Re-run the same command after placing
a newer export in the history directory. The generated HTML contains its data
and visualizations inline, works offline, and sends no listening history to a
server.

Plays shorter than 30 seconds are treated as skips. Ownership matching ignores
punctuation and common remaster, mono, stereo, deluxe, legacy, and anniversary
labels. Album recommendations require at least two favorite tracks. Review
compilations and artist-credit differences in the generated report before buying.

## Test

```powershell
py -m unittest discover -s tests -v
```
