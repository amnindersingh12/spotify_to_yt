  
import json
import os

import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
import requests
import youtube_dl

from exceptions import ResponseException
from secrets import spotify_token, spotify_playlist_id

query = "https://api.spotify.com/v1/playlists/{}/tracks?market=ES&fields=items(track(name%2Cartists(name)))".format(spotify_playlist_id)
response = requests.get(
    query,
    headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer {}".format(spotify_token)
    }
)
response_json = response.json()
print(response_json)