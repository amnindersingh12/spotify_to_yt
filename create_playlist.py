import os
import queue
import re
import threading
import customtkinter as ctk
from dotenv import load_dotenv

import google_auth_oauthlib.flow
import googleapiclient.discovery
import spotipy
from spotipy.oauth2 import SpotifyOAuth

# Load environment variables from .env
load_dotenv()

class SpotifyToYoutubeGUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.spotify_client = None
        self.spotify_account_name = None
        self.youtube_client = None
        self.youtube_account_name = None
        self.current_sync_config = {}
        self.sync_cancel_event = threading.Event()
        self.ui_queue = queue.Queue()

        self.title("Spotify to YouTube API Sync")
        self.geometry("820x860")
        
        # Grid layout
        self.grid_columnconfigure(0, weight=1)

        # Title Label
        self.title_label = ctk.CTkLabel(self, text="Spotify to YouTube Sync", font=ctk.CTkFont(size=24, weight="bold"))
        self.title_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        # YouTube Options Frame
        self.yt_frame = ctk.CTkFrame(self)
        self.yt_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        
        self.yt_label = ctk.CTkLabel(self.yt_frame, text="YouTube Settings", font=ctk.CTkFont(size=16, weight="bold"))
        self.yt_label.grid(row=0, column=0, padx=10, pady=10, sticky="w")
        
        self.playlist_name_entry = ctk.CTkEntry(self.yt_frame, placeholder_text="New YouTube Playlist Name", width=300)
        self.playlist_name_entry.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="w")
        self.playlist_name_entry.insert(0, "My Spotify Sync")

        self.playlist_desc_entry = ctk.CTkEntry(self.yt_frame, placeholder_text="Playlist Description", width=300)
        self.playlist_desc_entry.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="w")
        self.playlist_desc_entry.insert(0, "Synced via App")

        self.privacy_var = ctk.StringVar(value="public")
        self.privacy_menu = ctk.CTkOptionMenu(self.yt_frame, values=["public", "unlisted", "private"], variable=self.privacy_var)
        self.privacy_menu.grid(row=3, column=0, padx=10, pady=(0, 10), sticky="w")

        # Spotify Options Frame
        self.sp_frame = ctk.CTkFrame(self)
        self.sp_frame.grid(row=2, column=0, padx=20, pady=10, sticky="ew")

        self.sp_label = ctk.CTkLabel(self.sp_frame, text="Spotify Source", font=ctk.CTkFont(size=16, weight="bold"))
        self.sp_label.grid(row=0, column=0, padx=10, pady=10, sticky="w")

        self.sync_mode = ctk.StringVar(value="liked")
        
        self.radio_liked = ctk.CTkRadioButton(self.sp_frame, text="Sync Liked Songs", variable=self.sync_mode, value="liked", command=self.toggle_playlist_entry)
        self.radio_liked.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="w")

        self.radio_playlist = ctk.CTkRadioButton(self.sp_frame, text="Sync Specific Playlist", variable=self.sync_mode, value="playlist", command=self.toggle_playlist_entry)
        self.radio_playlist.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="w")

        self.sp_playlist_id_entry = ctk.CTkEntry(self.sp_frame, placeholder_text="Spotify Playlist ID / URL", width=400)
        self.sp_playlist_id_entry.grid(row=3, column=0, padx=35, pady=(0, 10), sticky="w")
        self.sp_playlist_id_entry.configure(state="disabled")

        self.max_songs_entry = ctk.CTkEntry(self.sp_frame, placeholder_text="Max songs to sync (optional)", width=260)
        self.max_songs_entry.grid(row=4, column=0, padx=35, pady=(0, 10), sticky="w")

        self.spotify_hint = ctk.CTkLabel(
            self.sp_frame,
            text="Tip: paste either a playlist ID, spotify:playlist:... or full open.spotify.com URL",
            text_color="gray70"
        )
        self.spotify_hint.grid(row=5, column=0, padx=35, pady=(0, 10), sticky="w")

        # Account connection controls
        self.account_frame = ctk.CTkFrame(self)
        self.account_frame.grid(row=3, column=0, padx=20, pady=10, sticky="ew")
        self.account_frame.grid_columnconfigure(0, weight=1)

        self.account_label = ctk.CTkLabel(self.account_frame, text="Account Connections", font=ctk.CTkFont(size=16, weight="bold"))
        self.account_label.grid(row=0, column=0, padx=10, pady=(10, 6), sticky="w")

        self.spotify_status_label = ctk.CTkLabel(self.account_frame, text="Spotify: Not connected", text_color="red")
        self.spotify_status_label.grid(row=1, column=0, padx=10, pady=(0, 6), sticky="w")

        self.spotify_connect_button = ctk.CTkButton(self.account_frame, text="Connect Spotify", command=self.start_spotify_connect_thread)
        self.spotify_connect_button.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="w")

        self.youtube_status_label = ctk.CTkLabel(self.account_frame, text="YouTube: Not connected", text_color="red")
        self.youtube_status_label.grid(row=3, column=0, padx=10, pady=(0, 6), sticky="w")

        self.youtube_connect_button = ctk.CTkButton(self.account_frame, text="Connect YouTube", command=self.start_youtube_connect_thread)
        self.youtube_connect_button.grid(row=4, column=0, padx=10, pady=(0, 10), sticky="w")

        # Check for environment variables
        self.check_env_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.check_env_frame.grid(row=4, column=0, padx=20, pady=5, sticky="ew")

        env_status = self.check_credentials()
        self.env_label = ctk.CTkLabel(self.check_env_frame, text=env_status, text_color="green" if "Ready" in env_status else "red")
        self.env_label.grid(row=0, column=0, sticky="w")

        # Progress and stats
        self.progress_frame = ctk.CTkFrame(self)
        self.progress_frame.grid(row=5, column=0, padx=20, pady=10, sticky="ew")
        self.progress_frame.grid_columnconfigure(0, weight=1)

        self.sync_status_label = ctk.CTkLabel(self.progress_frame, text="Status: Idle", font=ctk.CTkFont(size=13, weight="bold"))
        self.sync_status_label.grid(row=0, column=0, padx=10, pady=(10, 6), sticky="w")

        self.progress_bar = ctk.CTkProgressBar(self.progress_frame)
        self.progress_bar.grid(row=1, column=0, padx=10, pady=6, sticky="ew")
        self.progress_bar.set(0)

        self.metrics_label = ctk.CTkLabel(self.progress_frame, text="Processed: 0 | Added: 0 | Skipped: 0 | Errors: 0")
        self.metrics_label.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="w")

        # Action Buttons
        self.actions_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.actions_frame.grid(row=6, column=0, padx=20, pady=10, sticky="ew")
        self.actions_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.sync_button = ctk.CTkButton(self.actions_frame, text="START SYNC", font=ctk.CTkFont(size=16, weight="bold"), height=46, command=self.start_sync_thread)
        self.sync_button.grid(row=0, column=0, padx=(0, 8), sticky="ew")
        self.sync_button.configure(state="disabled")

        self.cancel_button = ctk.CTkButton(self.actions_frame, text="Cancel Sync", height=46, command=self.cancel_sync, state="disabled")
        self.cancel_button.grid(row=0, column=1, padx=8, sticky="ew")

        self.clear_log_button = ctk.CTkButton(self.actions_frame, text="Clear Log", height=46, command=self.clear_log)
        self.clear_log_button.grid(row=0, column=2, padx=(8, 0), sticky="ew")

        # Log Box
        self.log_box = ctk.CTkTextbox(self, height=220)
        self.log_box.grid(row=7, column=0, padx=20, pady=10, sticky="nsew")
        self.grid_rowconfigure(7, weight=1)

        self.after(100, self.process_ui_queue)
        self.update_sync_button_state()

    def check_credentials(self):
        missing = []
        if not os.environ.get("SPOTIPY_CLIENT_ID"): missing.append("Spotify Client ID")
        if not os.environ.get("SPOTIPY_CLIENT_SECRET"): missing.append("Spotify Client Secret")
        if not os.path.exists("client_secret.json"): missing.append("client_secret.json")

        if missing:
            return f"Missing config: {', '.join(missing)}\nPlease update .env and restart."
        return "Credentials Status: Ready"

    def toggle_playlist_entry(self):
        if self.sync_mode.get() == "playlist":
            self.sp_playlist_id_entry.configure(state="normal")
        else:
            self.sp_playlist_id_entry.configure(state="disabled")

    def process_ui_queue(self):
        while not self.ui_queue.empty():
            callback, args, kwargs = self.ui_queue.get()
            callback(*args, **kwargs)
        self.after(100, self.process_ui_queue)

    def enqueue_ui(self, callback, *args, **kwargs):
        self.ui_queue.put((callback, args, kwargs))

    def update_sync_button_state(self):
        ready = bool(self.spotify_client and self.youtube_client and "Ready" in self.check_credentials())
        self.sync_button.configure(state="normal" if ready else "disabled")

    def set_syncing_state(self, is_syncing):
        if is_syncing:
            self.sync_button.configure(state="disabled", text="SYNCING...")
            self.cancel_button.configure(state="normal")
            self.spotify_connect_button.configure(state="disabled")
            self.youtube_connect_button.configure(state="disabled")
        else:
            self.sync_button.configure(text="START SYNC")
            self.cancel_button.configure(state="disabled")
            self.spotify_connect_button.configure(state="normal")
            self.youtube_connect_button.configure(state="normal")
            self.update_sync_button_state()

    def reset_progress_ui(self):
        self.progress_bar.set(0)
        self.sync_status_label.configure(text="Status: Preparing sync...")
        self.metrics_label.configure(text="Processed: 0 | Added: 0 | Skipped: 0 | Errors: 0")

    def update_progress_ui(self, processed, total, added, skipped, errors, status_text=None):
        progress = 0 if total <= 0 else min(1.0, processed / total)
        self.progress_bar.set(progress)
        self.metrics_label.configure(text=f"Processed: {processed}/{total} | Added: {added} | Skipped: {skipped} | Errors: {errors}")
        if status_text:
            self.sync_status_label.configure(text=f"Status: {status_text}")

    def set_connection_status(self, service, connected, account_name=None):
        if service == "spotify":
            if connected:
                self.spotify_status_label.configure(text=f"Spotify: Connected as {account_name}", text_color="green")
                self.spotify_connect_button.configure(text="Reconnect Spotify")
            else:
                self.spotify_status_label.configure(text="Spotify: Not connected", text_color="red")
                self.spotify_connect_button.configure(text="Connect Spotify")
        elif service == "youtube":
            if connected:
                self.youtube_status_label.configure(text=f"YouTube: Connected as {account_name}", text_color="green")
                self.youtube_connect_button.configure(text="Reconnect YouTube")
            else:
                self.youtube_status_label.configure(text="YouTube: Not connected", text_color="red")
                self.youtube_connect_button.configure(text="Connect YouTube")

        self.update_sync_button_state()

    def _append_log(self, message):
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")

    def log(self, message):
        self.enqueue_ui(self._append_log, message)

    def clear_log(self):
        self.log_box.delete("0.0", "end")

    def cancel_sync(self):
        self.sync_cancel_event.set()
        self.log("Cancellation requested. Finishing current track...")

    def parse_max_songs(self):
        raw_value = self.max_songs_entry.get().strip()
        if not raw_value:
            return None

        if not raw_value.isdigit() or int(raw_value) <= 0:
            raise ValueError("Max songs must be a positive whole number")

        return int(raw_value)

    def start_spotify_connect_thread(self):
        if "Ready" not in self.check_credentials():
            self.log("Missing credentials. Update .env/client_secret.json first.")
            return

        self.spotify_connect_button.configure(state="disabled")
        self.log("Starting Spotify sign-in flow...")
        threading.Thread(target=self.connect_spotify, daemon=True).start()

    def connect_spotify(self):
        try:
            sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
                scope="user-library-read playlist-read-private",
                redirect_uri=os.environ.get("SPOTIPY_REDIRECT_URI", "http://localhost:8888/callback")
            ))
            profile = sp.current_user()
            account_name = profile.get("display_name") or profile.get("id") or "Unknown"

            self.spotify_client = sp
            self.spotify_account_name = account_name
            self.log(f"Spotify connected: {account_name}")
            self.enqueue_ui(self.set_connection_status, "spotify", True, account_name)
        except Exception as e:
            self.spotify_client = None
            self.spotify_account_name = None
            self.log(f"Spotify Auth Error: {e}")
            self.enqueue_ui(self.set_connection_status, "spotify", False)
        finally:
            self.enqueue_ui(self.spotify_connect_button.configure, state="normal")

    def start_youtube_connect_thread(self):
        if "Ready" not in self.check_credentials():
            self.log("Missing credentials. Update .env/client_secret.json first.")
            return

        self.youtube_connect_button.configure(state="disabled")
        self.log("Starting YouTube sign-in flow...")
        threading.Thread(target=self.connect_youtube, daemon=True).start()

    def connect_youtube(self):
        try:
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

            self.youtube_client = client
            self.youtube_account_name = account_name
            self.log(f"YouTube connected: {account_name}")
            self.enqueue_ui(self.set_connection_status, "youtube", True, account_name)
        except Exception as e:
            self.youtube_client = None
            self.youtube_account_name = None
            self.log(f"YouTube Auth Error: {e}")
            self.enqueue_ui(self.set_connection_status, "youtube", False)
        finally:
            self.enqueue_ui(self.youtube_connect_button.configure, state="normal")

    def start_sync_thread(self):
        if not self.spotify_client or not self.youtube_client:
            self.log("Connect both Spotify and YouTube accounts first.")
            return

        try:
            max_songs = self.parse_max_songs()
        except ValueError as e:
            self.log(str(e))
            return

        self.current_sync_config = {
            "title": self.playlist_name_entry.get().strip() or "My Spotify Sync",
            "desc": self.playlist_desc_entry.get().strip() or "Synced via App",
            "privacy": self.privacy_var.get().strip() or "public",
            "mode": self.sync_mode.get(),
            "playlist_input": self.sp_playlist_id_entry.get().strip(),
            "max_songs": max_songs,
        }

        self.sync_cancel_event.clear()
        self.clear_log()
        self.reset_progress_ui()
        self.set_syncing_state(True)
        threading.Thread(target=self.run_sync, daemon=True).start()

    def run_sync(self):
        processed = 0
        added = 0
        skipped = 0
        errors = 0

        try:
            songs = self.get_songs_from_spotify(
                self.spotify_client,
                mode=self.current_sync_config["mode"],
                playlist_input=self.current_sync_config["playlist_input"],
                max_songs=self.current_sync_config["max_songs"],
            )
            if not songs:
                self.log("No songs found or Spotify authentication failed.")
                self.enqueue_ui(self.update_progress_ui, 0, 0, 0, 0, 0, "No songs to sync")
                return

            total = len(songs)
            self.log(f"Found {total} songs to sync.")
            self.enqueue_ui(self.update_progress_ui, 0, total, 0, 0, 0, "Creating YouTube playlist")
            
            play_id = self.create_youtube_playlist(
                self.youtube_client,
                title=self.current_sync_config["title"],
                desc=self.current_sync_config["desc"],
                privacy=self.current_sync_config["privacy"],
            )
            if not play_id:
                self.log("Failed to create YouTube playlist.")
                self.enqueue_ui(self.update_progress_ui, 0, total, 0, 0, 1, "Playlist creation failed")
                return
                
            self.log(f"Created YouTube Playlist ID: {play_id}")

            for index, name in enumerate(songs, start=1):
                if self.sync_cancel_event.is_set():
                    self.log("Sync cancelled by user.")
                    self.enqueue_ui(self.update_progress_ui, processed, total, added, skipped, errors, "Cancelled")
                    return

                self.log(f"[{index}/{total}] Searching for: {name}")
                try:
                    request = self.youtube_client.search().list(part="snippet", order="viewCount", q=name, maxResults=1, type="video")
                    response = request.execute()
                    items = response.get('items', [])
                    
                    if not items:
                        skipped += 1
                        self.log(f" -> Could not find video for: {name}")
                        processed += 1
                        self.enqueue_ui(self.update_progress_ui, processed, total, added, skipped, errors, "Syncing")
                        continue
                        
                    videoID = str(items[0]["id"]["videoId"])

                    add_request = self.youtube_client.playlistItems().insert(
                        part="snippet",
                        body={"snippet": {"playlistId": play_id, "resourceId": {"kind": "youtube#video", "videoId": videoID}}}
                    )
                    add_request.execute()
                    added += 1
                    self.log(f" -> Added to playlist.")
                except Exception as e:
                    errors += 1
                    self.log(f" -> Error processing: {e}")

                processed += 1
                self.enqueue_ui(self.update_progress_ui, processed, total, added, skipped, errors, "Syncing")

            self.log("\nFINISHED SYNCING PLAYLIST!")
            self.log(f"Summary -> Added: {added}, Skipped: {skipped}, Errors: {errors}")
            self.enqueue_ui(self.update_progress_ui, total, total, added, skipped, errors, "Completed")
        except Exception as e:
            self.log(f"\nCRITICAL ERROR: {e}")
            self.enqueue_ui(self.update_progress_ui, processed, max(processed, 1), added, skipped, errors + 1, "Crashed")
        finally:
            self.enqueue_ui(self.set_syncing_state, False)

    def create_youtube_playlist(self, client, title, desc, privacy):
        try:
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
            return request.execute()['id']
        except Exception as e:
            self.log(f"Error creating playlist: {e}")
            return None

    def get_songs_from_spotify(self, sp, mode, playlist_input, max_songs=None):
        self.log("Authenticating and fetching from Spotify...")
        songs = []
        limit = 50
        offset = 0
        playlist_id = self.normalize_spotify_playlist_id(playlist_input)

        if mode == "playlist" and not playlist_id:
            self.log("Please enter a valid Spotify Playlist ID or playlist URL")
            return []

        while True:
            try:
                if mode == "liked":
                    results = sp.current_user_saved_tracks(limit=limit, offset=offset)
                else:
                    results = sp.playlist_tracks(playlist_id, limit=limit, offset=offset)

                items = results.get('items', [])
                if not items:
                    break
                    
                for item in items:
                    track = item.get('track')
                    if track:
                        song_name = track.get('name', '')
                        artists = track.get('artists', [])
                        artist_name = artists[0].get('name', '') if artists else ''
                        songs.append(f"{song_name} {artist_name}".strip())

                        if max_songs and len(songs) >= max_songs:
                            return songs

                offset += limit
                if len(items) < limit:
                    break
            except Exception as e:
                self.log(f"Spotify API Error: {e}")
                break
                
        return songs

    def normalize_spotify_playlist_id(self, value):
        if not value:
            return ""

        value = value.strip()

        # Accept spotify:playlist:<id> format.
        if value.startswith("spotify:playlist:"):
            return value.split(":")[-1].strip()

        # Accept full open.spotify.com playlist URLs.
        match = re.search(r"open\.spotify\.com/playlist/([A-Za-z0-9]+)", value)
        if match:
            return match.group(1)

        # Fallback: assume a plain playlist ID.
        return value

if __name__ == "__main__":
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")
    app = SpotifyToYoutubeGUI()
    app.mainloop()
