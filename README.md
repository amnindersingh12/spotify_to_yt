# ytspotify
A Spotify-to-YouTube sync tool with two interfaces:
- Desktop GUI (`create_playlist.py`) for local use.
- Live web dashboard (`web_app.py`) for VM-hosted use behind nginx.

## Table of Contents
* [Technologies](#Technologies)
* [Local Setup](#LocalSetup)
* [Live Web Setup](#LiveWebSetup)
* [Video Walkthrough](#VideoWalkthrough)
* [Updated Instructions](#UpdatedInstructions)
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

3) **Enable OAuth For YouTube (`client_secret.json`)**   
    * You need to authorize your app with Google to create YouTube playlists for you. Just follow the guide here [Set Up Youtube Oauth](https://developers.google.com/youtube/v3/getting-started) to generate a credential file! 
    * Download your `client_secret.json` from the Google Cloud Console and place it in the same directory as this project.

4) **Run the File**  
`python3 create_playlist.py`   
    * A sleek GUI window will pop up.
    * Click `Connect Spotify` and complete OAuth in your browser.
    * Click `Connect YouTube` and complete OAuth in your browser.
    * Confirm both account status labels turn green.
    * Click `START SYNC` to clone your music library automatically.

## LiveWebSetup
This mode is for hosting on your VM with nginx proxying to Flask.

1) **Install dependencies**
`pip3 install -r requirements.txt`

2) **Spotify App Setup (required)**
* Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/) and create an app.
* Add this exact Redirect URI in your Spotify app settings:
    * `https://alreadytaken.me/api/oauth/spotify/callback`
* Copy Client ID and Client Secret.

3) **Google OAuth Setup (required for YouTube)**
* Create OAuth client credentials in Google Cloud.
* Download `client_secret.json` and place it in this project root.

4) **Run the live dashboard service**
* The Flask app is intended to run on `127.0.0.1:5000`.
* nginx should proxy:
    * `/projects/spotify-to-yt/live/` to `/live/`
    * `/api/` to Flask `/api/`

5) **Connect from the UI**
* Open `https://alreadytaken.me/projects/spotify-to-yt/live/`
* Click `Connect Spotify` or `Connect YouTube`.
* The modal lets you enter missing OAuth settings on the fly.
* After saving, the dashboard opens the OAuth popup and updates account state when login completes.

## VideoWalkthrough
* Setup and demo video: https://youtu.be/9yDr8gOOADE

## UpdatedInstructions
1) Open the live page: `https://alreadytaken.me/projects/spotify-to-yt/live/`
2) Click `Connect Spotify` and fill the modal if credentials are missing.
3) In Spotify Developer Dashboard, ensure this Redirect URI is allowlisted exactly:
    * `https://alreadytaken.me/api/oauth/spotify/callback`
4) Click `Connect YouTube` and upload or paste `client_secret.json` in the modal.
5) Complete both OAuth popups and confirm both accounts show as connected.
6) Start sync with your playlist options.

## Account Login UI
* Spotify and YouTube sign-in are now explicit steps in the app UI.
* The app shows which Spotify and YouTube accounts are currently connected.
* `START SYNC` stays disabled until both accounts are connected.
* You can reconnect either account at any time from the connect buttons.

## Oracle VM Hosting (Project Hub)
* The site files live on the VM Desktop at `/home/ubuntu/Desktop/alreadytaken.me`.
* The VM now serves a project hub at `/projects/`.
* The Spotify-to-YouTube app has its own project page at `/projects/spotify-to-yt/`.
* The live browser dashboard is at `/projects/spotify-to-yt/live/`.
* The root URL redirects to the projects hub.
* To expose the site publicly, point `alreadytaken.me` to this VM's public IP and keep nginx on port 80.
* The old `8080` Python server can still be used for quick internal testing, but the nginx site is the public entry point.

## Troubleshooting
* **QuotaExceeded**: This means you have reached the maximum number of requests that you can make through a single Google project per day. You can either wait until tomorrow or create a new project in the Google Cloud Console.

   [Youtube Data API v3]: <https://developers.google.com/youtube/v3>
   [Spotify Web API]: <https://developer.spotify.com/documentation/web-api/>
   [Spotipy]: <https://spotipy.readthedocs.io/en/2.22.1/>
   [CustomTkinter]: <https://customtkinter.tomschimansky.com/>
