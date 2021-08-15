# -*- coding: utf-8 -*-

# Sample Python code for youtube.playlists.insert
# See instructions for running these code samples locally:
# https://developers.google.com/explorer-help/guides/code_samples#python

import os

import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors

scopes = ["https://www.googleapis.com/auth/youtube.force-ssl"]


def create_playlist(self):
    """Create A New Playlist"""
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

    api_service_name = "youtube"
    api_version = "v3"
    client_secrets_file = "new.json"

    # Get credentials and create an API client
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
        client_secrets_file, scopes)
    credentials = flow.run_console()
    youtube = googleapiclient.discovery.build(
        api_service_name, api_version, credentials=credentials)
        
    request = youtube.playlists().insert(
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
    playlist_id = str(response['id'])
    print(playlist_id)


def search_song_on_yt(self, song_name):
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

    api_service_name = "youtube"
    api_version = "v3"
    client_secrets_file = "new.json"

    # Get credentials and create an API client
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
        client_secrets_file, scopes)
    credentials = flow.run_console()
    youtube = googleapiclient.discovery.build(
        api_service_name, api_version, credentials=credentials)

    request = youtube.search().list(
        part="snippet",
        order="viewCount",
        q=self.song_name
    )
    response = request.execute()
    videoID = str(response['items'][0]["id"]["videoId"])
    print(videoID)
    return videoID


def spotify_song_to_yt():

    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

    api_service_name = "youtube"
    api_version = "v3"
    client_secrets_file = "new.json"

    # Get credentials and create an API client
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
        client_secrets_file, scopes)
    credentials = flow.run_console()
    youtube = googleapiclient.discovery.build(
        api_service_name, api_version, credentials=credentials)

    request = youtube.playlistItems().insert(
        part="snippet",
        body={
            "snippet": {
                "playlistId": "PLD1cuCHkkkEkPpLTDr-eOl5PWPBIoKaj1",
                "resourceId": {
                    "kind": "youtube#video",
                    "videoId": "xvZqHgFz51I"
                }
            }
        }
    )
    response = request.execute()

    print(response)


if __name__ == "__main__":
    create_playlist()
    search_song_on_yt()
    spotify_song_to_yt()

