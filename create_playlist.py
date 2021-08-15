import json
import os

import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
import requests
import youtube_dl

from exceptions import ResponseException



class CreatePlaylist:
    def __init__(self):
        self.youtube_client = self.get_youtube_client()
        self.all_song_info = {}

    def get_youtube_client(self):
        """ Log Into Youtube, Copied from Youtube Data API """
        # Disable OAuthlib's HTTPS verification when running locally.
        # *DO NOT* leave this option enabled in production.
        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

        api_service_name = "youtube"
        api_version = "v3"
        client_secrets_file = "new.json"

        # Get credentials and create an API client
        scopes = ["https://www.googleapis.com/auth/youtube.readonly"]
        flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
            client_secrets_file, scopes)
        credentials = flow.run_console()

        # from the Youtube DATA API
        youtube_client = googleapiclient.discovery.build(
            api_service_name, api_version, credentials=credentials)

        return youtube_client

    def create_playlist(self):
        """Create A New Playlist"""
    

        request = self.youtube_client.playlists().insert(
            part="snippet,status",
            body={
            "snippet": {
                "title": "XO ke Ganne",
                "description": "This is a sample playlist description.",
                "tags": [
                "sample playlist",
                "API call"
                ],
                "defaultLanguage": "en"
            },
            "status": {
                "privacyStatus": "public"
            }
            }
        )
        response = request.execute()
        playlist_id = response['id']
      
        return playlist_id
    song_name="Starboy The Weeknd"
    def search_song_on_yt(self, song_name):
   
        request = self.youtube_client.search().list(
            part="snippet",
            order="viewCount",
            q=self.song_name
        )
        response = request.execute()
        videoID = str(response['items'][0]["id"]["videoId"])
        print(videoID)
        return videoID


    def add_video_to_playlist(self):
        self.search_song_on_yt(song_name)
        request = self.youtube_client.playlistItems().insert(
            part="snippet",
            body={
            "snippet": {
                "playlistId": self.playlist_id,
                "resourceId": {
                "kind": "youtube#video",
                "videoId": self.videoID
                }
            }
            }
        )
        response = request.execute()

        print(response)


if __name__ == '__main__':
    cp = CreatePlaylist()
    cp.add_video_to_playlist()
