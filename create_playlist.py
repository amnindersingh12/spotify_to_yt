import os
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

        self.title("Spotify to YouTube API Sync")
        self.geometry("600x650")
        
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

        self.sp_playlist_id_entry = ctk.CTkEntry(self.sp_frame, placeholder_text="Spotify Playlist ID", width=300)
        self.sp_playlist_id_entry.grid(row=3, column=0, padx=35, pady=(0, 10), sticky="w")
        self.sp_playlist_id_entry.configure(state="disabled")

        # Check for environment variables
        self.check_env_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.check_env_frame.grid(row=3, column=0, padx=20, pady=5, sticky="ew")

        env_status = self.check_credentials()
        self.env_label = ctk.CTkLabel(self.check_env_frame, text=env_status, text_color="green" if "Ready" in env_status else "red")
        self.env_label.grid(row=0, column=0, sticky="w")

        # Sync Button
        self.sync_button = ctk.CTkButton(self, text="START SYNC", font=ctk.CTkFont(size=16, weight="bold"), height=50, command=self.start_sync_thread)
        self.sync_button.grid(row=4, column=0, padx=20, pady=10, sticky="ew")

        # Log Box
        self.log_box = ctk.CTkTextbox(self, height=150)
        self.log_box.grid(row=5, column=0, padx=20, pady=10, sticky="nsew")
        self.grid_rowconfigure(5, weight=1)

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

    def log(self, message):
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")
        self.update()

    def start_sync_thread(self):
        self.sync_button.configure(state="disabled", text="SYNCING...")
        self.log_box.delete("0.0", "end")
        threading.Thread(target=self.run_sync, daemon=True).start()

    def run_sync(self):
        try:
            youtube_client = self.get_youtube_client()
            if not youtube_client:
                self.log("Failed to authenticate YouTube.")
                self.sync_button.configure(state="normal", text="START SYNC")
                return

            sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
                scope="user-library-read playlist-read-private",
                redirect_uri="http://localhost:8888/callback"
            ))
            
            songs = self.get_songs_from_spotify(sp)
            if not songs:
                self.log("No songs found or Spotify authentication failed.")
                self.sync_button.configure(state="normal", text="START SYNC")
                return

            self.log(f"Found {len(songs)} songs to sync.")
            
            play_id = self.create_youtube_playlist(youtube_client)
            if not play_id:
                self.log("Failed to create YouTube playlist.")
                self.sync_button.configure(state="normal", text="START SYNC")
                return
                
            self.log(f"Created YouTube Playlist ID: {play_id}")

            for name in songs:
                self.log(f"Searching for: {name}")
                try:
                    request = youtube_client.search().list(part="snippet", order="viewCount", q=name, maxResults=1, type="video")
                    response = request.execute()
                    items = response.get('items', [])
                    
                    if not items:
                        self.log(f" -> Could not find video for: {name}")
                        continue
                        
                    videoID = str(items[0]["id"]["videoId"])

                    add_request = youtube_client.playlistItems().insert(
                        part="snippet",
                        body={"snippet": {"playlistId": play_id, "resourceId": {"kind": "youtube#video", "videoId": videoID}}}
                    )
                    add_request.execute()
                    self.log(f" -> Added to playlist.")
                except Exception as e:
                    self.log(f" -> Error processing: {e}")

            self.log("\nFINISHED SYNCING PLAYLIST!")
        except Exception as e:
            self.log(f"\nCRITICAL ERROR: {e}")
            
        self.sync_button.configure(state="normal", text="START SYNC")

    def get_youtube_client(self):
        self.log("Authenticating with YouTube...")
        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
        try:
            scopes = ["https://www.googleapis.com/auth/youtube", "https://www.googleapis.com/auth/youtube.force-ssl", "https://www.googleapis.com/auth/youtube.readonly"]
            flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file("client_secret.json", scopes)
            credentials = flow.run_local_server(port=0)
            return googleapiclient.discovery.build("youtube", "v3", credentials=credentials)
        except Exception as e:
            self.log(f"YouTube Auth Error: {e}")
            return None

    def create_youtube_playlist(self, client):
        title = self.playlist_name_entry.get().strip() or "My Spotify Sync"
        desc = self.playlist_desc_entry.get().strip() or "Synced via App"
        
        try:
            request = client.playlists().insert(
                part="snippet,status",
                body={"snippet": {"title": title, "description": desc, "tags": ["spotify sync"], "defaultLanguage": "en"}, "status": {"privacyStatus": "public"}}
            )
            return request.execute()['id']
        except Exception as e:
            self.log(f"Error creating playlist: {e}")
            return None

    def get_songs_from_spotify(self, sp):
        self.log("Authenticating and fetching from Spotify...")
        songs = []
        limit = 50
        offset = 0
        mode = self.sync_mode.get()
        playlist_id = self.sp_playlist_id_entry.get().strip()

        if mode == "playlist" and not playlist_id:
            self.log("Please enter a valid Spotify Playlist ID")
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

                offset += limit
                if len(items) < limit:
                    break
            except Exception as e:
                self.log(f"Spotify API Error: {e}")
                break
                
        return songs

if __name__ == "__main__":
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")
    app = SpotifyToYoutubeGUI()
    app.mainloop()
