import json
import os

import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
import requests
import youtube_dl

from exceptions import ResponseException
from secrets import spotify_token, spotify_playlist_id


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
        scopes = ["https://www.googleapis.com/auth/youtube","https://www.googleapis.com/auth/youtube.force-ssl","https://www.googleapis.com/auth/youtube.readonly"]
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

    def get_song_name(self):

        query = "https://api.spotify.com/v1/playlists/{}/tracks?market=ES&fields=items(track(name%2Cartists(name)))&limit=59&offset=41".format(
            spotify_playlist_id)
        response = requests.get(
            query,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer {}".format(spotify_token)
            }
        )
        response_json = response.json()
        play_id="PLvcDEv0bQcCg9eR1_ijfTKHAMc_FPKtXH"
        # self.create_playlist()
        

        for i in range(len(response_json['items'])):
            song_name = response_json['items'][i]['track']['name']
            artist_name = response_json['items'][i]['track']['artists'][0]['name']
            name = song_name + " " + artist_name
            print(name)
            request = self.youtube_client.search().list(
                part="snippet",
                order="viewCount",
                q=name
            )
            response = request.execute()
            videoID = str(response['items'][0]["id"]["videoId"])

            
            request = self.youtube_client.playlistItems().insert(
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
            response = request.execute()

        print(response)




         

if __name__ == '__main__':
    cp = CreatePlaylist()
    cp.get_song_name()
