import os
import re
import threading
from dataclasses import dataclass

from dotenv import load_dotenv

import google_auth_oauthlib.flow
import googleapiclient.discovery
import spotipy
from spotipy.oauth2 import SpotifyOAuth

load_dotenv()


@dataclass
class SyncConfig:
    title: str = "My Spotify Sync"
    desc: str = "Synced via App"
    privacy: str = "public"
    mode: str = "liked"
    playlist_input: str = ""
    max_songs: int | None = None


class SpotifyToYoutubeEngine:
    def __init__(self):
        self.spotify_client = None
        self.youtube_client = None
        self.spotify_account_name = None
        self.youtube_account_name = None
        self._lock = threading.Lock()

    def set_spotify_client(self, client, account_name):
        with self._lock:
            self.spotify_client = client
            self.spotify_account_name = account_name

    def set_youtube_client(self, client, account_name):
        with self._lock:
            self.youtube_client = client
            self.youtube_account_name = account_name

    def check_credentials(self):
        missing = []
        if not os.environ.get("SPOTIPY_CLIENT_ID"):
            missing.append("Spotify Client ID")
        if not os.environ.get("SPOTIPY_CLIENT_SECRET"):
            missing.append("Spotify Client Secret")
        if not os.path.exists("client_secret.json"):
            missing.append("client_secret.json")
        return missing

    def ready(self):
        return not self.check_credentials()

    def connect_spotify(self, logger=None):
        sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            scope="user-library-read playlist-read-private",
            redirect_uri=os.environ.get("SPOTIPY_REDIRECT_URI", "http://localhost:8888/callback")
        ))
        profile = sp.current_user()
        account_name = profile.get("display_name") or profile.get("id") or "Unknown"
        with self._lock:
            self.spotify_client = sp
            self.spotify_account_name = account_name
        if logger:
            logger(f"Spotify connected: {account_name}")
        return account_name

    def connect_youtube(self, logger=None):
        scopes = [
            "https://www.googleapis.com/auth/youtube",
            "https://www.googleapis.com/auth/youtube.force-ssl"
        ]
        flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file("client_secret.json", scopes)
        credentials = flow.run_local_server(port=0)
        client = googleapiclient.discovery.build("youtube", "v3", credentials=credentials)

        channel_response = client.channels().list(part="snippet", mine=True, maxResults=1).execute()
        items = channel_response.get("items", [])
        account_name = "Unknown"
        if items:
            account_name = items[0].get("snippet", {}).get("title") or account_name

        with self._lock:
            self.youtube_client = client
            self.youtube_account_name = account_name
        if logger:
            logger(f"YouTube connected: {account_name}")
        return account_name

    def normalize_spotify_playlist_id(self, value):
        if not value:
            return ""

        value = value.strip()
        if value.startswith("spotify:playlist:"):
            return value.split(":")[-1].strip()

        match = re.search(r"open\.spotify\.com/playlist/([A-Za-z0-9]+)", value)
        if match:
            return match.group(1)

        return value

    def fetch_songs(self, config: SyncConfig, logger=None):
        songs = []
        limit = 50
        offset = 0
        playlist_id = self.normalize_spotify_playlist_id(config.playlist_input)

        if config.mode == "playlist" and not playlist_id:
            raise ValueError("Please enter a valid Spotify Playlist ID or playlist URL")

        if not self.spotify_client:
            self.connect_spotify(logger=logger)

        sp = self.spotify_client

        while True:
            if config.mode == "liked":
                results = sp.current_user_saved_tracks(limit=limit, offset=offset)
            else:
                results = sp.playlist_tracks(playlist_id, limit=limit, offset=offset)

            items = results.get("items", [])
            if not items:
                break

            for item in items:
                track = item.get("track")
                if not track:
                    continue
                song_name = track.get("name", "")
                artists = track.get("artists", [])
                artist_name = artists[0].get("name", "") if artists else ""
                songs.append(f"{song_name} {artist_name}".strip())

                if config.max_songs and len(songs) >= config.max_songs:
                    return songs

            offset += limit
            if len(items) < limit:
                break

        return songs

    def create_youtube_playlist(self, client, title, desc, privacy):
        request = client.playlists().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": title,
                    "description": desc,
                    "tags": ["spotify sync"],
                    "defaultLanguage": "en"
                },
                "status": {"privacyStatus": privacy}
            }
        )
        return request.execute()["id"]

    def sync(self, config: SyncConfig, logger=None, progress=None, cancel_event=None):
        if not self.youtube_client:
            self.connect_youtube(logger=logger)

        songs = self.fetch_songs(config, logger=logger)
        total = len(songs)
        if logger:
            logger(f"Found {total} songs to sync.")

        if total == 0:
            if progress:
                progress(0, 0, 0, 0, 0, "No songs to sync")
            return {"processed": 0, "added": 0, "skipped": 0, "errors": 0, "playlist_id": None}

        playlist_id = self.create_youtube_playlist(
            self.youtube_client,
            title=config.title,
            desc=config.desc,
            privacy=config.privacy,
        )

        processed = 0
        added = 0
        skipped = 0
        errors = 0

        if logger:
            logger(f"Created YouTube Playlist ID: {playlist_id}")

        for index, name in enumerate(songs, start=1):
            if cancel_event and cancel_event.is_set():
                if logger:
                    logger("Sync cancelled by user.")
                break

            if logger:
                logger(f"[{index}/{total}] Searching for: {name}")

            try:
                request = self.youtube_client.search().list(
                    part="snippet",
                    order="viewCount",
                    q=name,
                    maxResults=1,
                    type="video"
                )
                response = request.execute()
                items = response.get("items", [])

                if not items:
                    skipped += 1
                    if logger:
                        logger(f" -> Could not find video for: {name}")
                else:
                    video_id = str(items[0]["id"]["videoId"])
                    add_request = self.youtube_client.playlistItems().insert(
                        part="snippet",
                        body={"snippet": {"playlistId": playlist_id, "resourceId": {"kind": "youtube#video", "videoId": video_id}}}
                    )
                    add_request.execute()
                    added += 1
                    if logger:
                        logger(" -> Added to playlist.")
            except Exception as exc:
                errors += 1
                if logger:
                    logger(f" -> Error processing: {exc}")

            processed += 1
            if progress:
                progress(processed, total, added, skipped, errors, "Syncing")

        if logger:
            logger("\nFINISHED SYNCING PLAYLIST!")
            logger(f"Summary -> Added: {added}, Skipped: {skipped}, Errors: {errors}")

        if progress:
            status = "Cancelled" if cancel_event and cancel_event.is_set() else "Completed"
            progress(processed if processed else 0, total, added, skipped, errors, status)

        return {
            "processed": processed,
            "added": added,
            "skipped": skipped,
            "errors": errors,
            "playlist_id": playlist_id,
        }
