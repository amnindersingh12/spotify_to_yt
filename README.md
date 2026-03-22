# ytspotify
A clean, GUI-based Python script that takes your Spotify playlist (or Liked Songs) and perfectly clones them into a newly generated YouTube playlist.

## Table of Contents
* [Technologies](#Technologies)
* [Setup](#LocalSetup)
* [Troubleshooting](#Troubleshooting)

## Technologies
* [CustomTkinter] (For modern Graphics User Interface)
* [Spotipy] (For automatic Spotify OAuth and Pagination)
* [Youtube Data API v3]
* [Spotify Web API]
* [Python Dotenv]

## LocalSetup
1) **Install All Dependencies:**   
`pip3 install -r requirements.txt`

2) **Create Your Spotify Credentials (`.env`)**
    * We use Spotipy to securely manage OAuth, which means you never have to manually regenerate expiring tokens!
    * Go to your [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/).
    * Create an app, and edit its settings so its "Redirect URI" is exactly `http://localhost:8888/callback`.
    * Copy `.env.example` into a new file called `.env`.
    * Paste your new App's `Client ID` and `Client Secret` into the `.env` file.

3) **Enable Oauth For Youtube (`client_secrets.json`)**   
    * You need to authorize your app with Google to create YouTube playlists for you. Just follow the guide here [Set Up Youtube Oauth](https://developers.google.com/youtube/v3/getting-started) to generate a credential file! 
    * Download your `client_secret.json` from the Google Cloud Console and place it in the same directory as this project.

4) **Run the File**  
`python3 create_playlist.py`   
    * A sleek GUI window will pop up.
    * You will be immediately directed to your browser to log into Google and Spotify once safely.
    * Click `START SYNC` to clone your music library automatically!

## Troubleshooting
* **QuotaExceeded**: This means you have reached the maximum number of requests that you can make through a single Google project per day. You can either wait until tomorrow or create a new project in the Google Cloud Console.

   [Youtube Data API v3]: <https://developers.google.com/youtube/v3>
   [Spotify Web API]: <https://developer.spotify.com/documentation/web-api/>
   [Spotipy]: <https://spotipy.readthedocs.io/en/2.22.1/>
   [CustomTkinter]: <https://customtkinter.tomschimansky.com/>
