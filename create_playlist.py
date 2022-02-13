#  Author:      Amninder Singh
#
#  This is a simple little module I wrote to make my life easier.
#  I didn't find anything like it over the internet, so I wrote my own.
#  I wrote this to create a playlist from a list of songs from a spotify playlist.


import json
import os

import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
import requests
import youtube_dl

# adding spotify credentials
from secrets import spotify_token, spotify_playlist_id


class CreatePlaylist:

    """
    This is the main class that will be used to create a playlist.
    """

    def __init__(self):
        self.youtube_client = self.get_youtube_client()
        self.all_song_info = {}

    def get_youtube_client(self):
        """ Log Into Youtube, Copied from Youtube Data API """

        # Disabling OAuthlib's HTTPS verification
        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

        api_service_name = "youtube"
        api_version = "v3"
        client_secrets_file = "new.json"

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

        request = self.youtube_client.playlists().insert(
            part="snippet,status",
            body={
                "snippet": {

                    # title of the playlist
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

        # executing the above request and storing the response
        response = request.execute()

        # returning the playlist ID
        playlist_id = response['id']
        return playlist_id

    def get_song_name(self):
        """
        This function will get the song name from the youtube link.
        """

        # api call to get the song name
        query = "https://api.spotify.com/v1/playlists/{}/tracks?market=ES&fields=items(track(name%2Cartists(name)))&limit=59&offset=41".format(
            spotify_playlist_id)

        # getting the response
        response = requests.get(
            query,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer {}".format(spotify_token)
            }
        )

        response_json = response.json()

        # playlist id where the songs will be added
        play_id = "PLvcDEv0bQcCg9eR1_ijfTKHAMc_FPKtXH"

        # uncomment this if running the code for the first time to create a new playlist
        # self.create_playlist()

        # looping
        for i in range(len(response_json['items'])):
            song_name = response_json['items'][i]['track']['name']
            artist_name = response_json['items'][i]['track']['artists'][0]['name']
            name = song_name + " " + artist_name

            # printing the name of the song and the artist
            print(name)

            # searching the song and sorting the result based on the viewcount
            request = self.youtube_client.search().list(
                part="snippet",
                order="viewCount",
                q=name
            )

            # saving the videoId of the song
            response = request.execute()
            videoID = str(response['items'][0]["id"]["videoId"])

            # adding the song video to the playlist
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
