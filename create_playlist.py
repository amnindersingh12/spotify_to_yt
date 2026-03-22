#  Author:      Amninder Singh
#
#  This is a simple little module I wrote to make my life easier.
#  I didn't find anything like it over the internet, so I wrote my own.
#  I wrote this to create a playlist from a list of songs from a spotify playlist.


import os
import google_auth_oauthlib.flow
import googleapiclient.discovery
import requests

# adding spotify credentials
try:
    from secrets import spotify_token, spotify_playlist_id
except ImportError:
    print("Please create a secrets.py file with spotify_token and spotify_playlist_id variables.")
    exit(1)


class CreatePlaylist:

    """
    This is the main class that will be used to create a playlist.
    """

    def __init__(self, youtube_playlist_name="My Spotify Sync", youtube_playlist_desc="Synced from Spotify"):
        self.youtube_playlist_name = youtube_playlist_name
        self.youtube_playlist_desc = youtube_playlist_desc
        self.youtube_client = self.get_youtube_client()
        self.all_song_info = {}

    def get_youtube_client(self):
        """ Log Into Youtube, Copied from Youtube Data API """

        # Disabling OAuthlib's HTTPS verification
        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

        api_service_name = "youtube"
        api_version = "v3"
        
        # youtube api key here
        client_secrets_file = "client_secret.json"

        if not os.path.exists(client_secrets_file):
            print(f"Error: {client_secrets_file} not found. Please download it from Google Cloud Console.")
            exit(1)

        # Get credentials and create an API client
        scopes = ["https://www.googleapis.com/auth/youtube", "https://www.googleapis.com/auth/youtube.force-ssl",
                  "https://www.googleapis.com/auth/youtube.readonly"]
        flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
            client_secrets_file, scopes)
        credentials = flow.run_console()

        # from the Youtube DATA API
        youtube_client = googleapiclient.discovery.build(
            api_service_name, api_version, credentials=credentials)

        return youtube_client

    def create_playlist(self):
        """
        To Create A New Playlist, calling the Youtube API's playlist.insert method. 
        """

        try:
            request = self.youtube_client.playlists().insert(
                part="snippet,status",
                body={
                    "snippet": {
                        # title of the playlist
                        "title": self.youtube_playlist_name,
                        "description": self.youtube_playlist_desc,
                        "tags": [
                            "spotify sync",
                            "API call"
                        ],
                        "defaultLanguage": "en"
                    },
                    "status": {
                        "privacyStatus": "public"
                    }
                }
            )

            # executing the above request and storing the response
            response = request.execute()
            # returning the playlist ID
            return response['id']
        except Exception as e:
            print(f"Error creating playlist: {e}")
            return None

    def get_songs_from_spotify(self, source_type="playlist"):
        """
        Fetches all songs from the specified Spotify playlist or 'Liked Songs' handling pagination.
        """
        songs = []
        limit = 50
        offset = 0
        
        while True:
            if source_type == "liked":
                # endpoint for user's liked songs
                query = f"https://api.spotify.com/v1/me/tracks?limit={limit}&offset={offset}"
            else:
                # endpoint for a specific playlist
                query = f"https://api.spotify.com/v1/playlists/{spotify_playlist_id}/tracks?fields=items(track(name%2Cartists(name)))&limit={limit}&offset={offset}"

            # getting the response
            response = requests.get(
                query,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {spotify_token}"
                }
            )

            if response.status_code == 401:
                print("Error: Spotify token is invalid or expired. Please update it in secrets.py.")
                break
            elif response.status_code != 200:
                print(f"Error fetching from Spotify: {response.text}")
                break

            response_json = response.json()
            items = response_json.get('items', [])
            
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
            
            # If we got fewer than limit, we've reached the end
            if len(items) < limit:
                break
                
        return songs

    def sync_playlist(self, source_type="playlist"):
        """
        Fetches songs from Spotify, creates a YouTube playlist, and adds videos to it.
        """
        songs = self.get_songs_from_spotify(source_type=source_type)
        if not songs:
            print("No songs found in Spotify or could not authenticate.")
            return

        print(f"Found {len(songs)} songs to sync.")
        
        # create the youtube playlist
        play_id = self.create_playlist()
        if not play_id:
            print("Failed to create YouTube playlist. Exiting.")
            return
            
        print(f"Created YouTube Playlist with ID: {play_id}")

        for name in songs:
            print(f"Searching for: {name}")

            try:
                # searching the song and sorting the result based on the viewcount
                request = self.youtube_client.search().list(
                    part="snippet",
                    order="viewCount",
                    q=name,
                    maxResults=1,
                    type="video"
                )

                # saving the videoId of the song
                response = request.execute()
                items = response.get('items', [])
                
                if not items:
                    print(f"  -> Could not find video for: {name}")
                    continue
                    
                videoID = str(items[0]["id"]["videoId"])

                # adding the song video to the playlist
                add_request = self.youtube_client.playlistItems().insert(
                    part="snippet",
                    body={
                        "snippet": {
                            "playlistId": play_id,
                            "resourceId": {
                                "kind": "youtube#video",
                                "videoId": videoID
                            }
                        }
                    }
                )
                add_request.execute()
                print(f"  -> Added to playlist.")
            except Exception as e:
                print(f"  -> Error processing song '{name}': {e}")

        print("Finished syncing playlist!")


if __name__ == '__main__':
    print("Welcome to Spotify to YouTube Sync!")
    print("1. Sync a specific playlist (ID from secrets.py)")
    print("2. Sync your Liked Songs")
    choice = input("Enter your choice (1 or 2): ").strip()

    source = "playlist"
    playlist_name = "My Spotify Playlist Sync"
    if choice == '2':
        source = "liked"
        playlist_name = "My Spotify Liked Songs"

    cp = CreatePlaylist(youtube_playlist_name=playlist_name)
    cp.sync_playlist(source_type=source)
