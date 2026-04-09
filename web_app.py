import queue
import json
import os
import secrets
import threading
import uuid
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template_string, request, Response, stream_with_context
from dotenv import load_dotenv

import google_auth_oauthlib.flow
import googleapiclient.discovery
import spotipy
from spotipy.oauth2 import SpotifyOAuth

from sync_engine import SpotifyToYoutubeEngine, SyncConfig

load_dotenv()

app = Flask(__name__)
engine = SpotifyToYoutubeEngine()
jobs = {}
job_lock = threading.Lock()
oauth_sessions = {}
oauth_lock = threading.Lock()
APP_ROOT = Path(__file__).resolve().parent
DOTENV_PATH = APP_ROOT / ".env"
YOUTUBE_SECRET_PATH = APP_ROOT / "client_secret.json"


def _public_base_url():
  configured = os.environ.get("PUBLIC_BASE_URL")
  if configured:
    return configured.rstrip("/")

  proto = request.headers.get("X-Forwarded-Proto", "").split(",", 1)[0].strip()
  host = request.headers.get("X-Forwarded-Host") or request.headers.get("Host")
  if proto and host:
    return f"{proto}://{host}".rstrip("/")

  return request.url_root.rstrip("/")


def _callback_url(service):
    return f"{_public_base_url()}/api/oauth/{service}/callback"


def _write_env_file(updates):
    current = {}
    if DOTENV_PATH.exists():
        for line in DOTENV_PATH.read_text().splitlines():
            if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            current[key.strip()] = value.strip()

    current.update({key: value for key, value in updates.items() if value is not None})
    lines = []
    for key in ("SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET", "SPOTIPY_REDIRECT_URI"):
        if key in current and current[key] != "":
            lines.append(f"{key}={current[key]}")
    DOTENV_PATH.write_text("\n".join(lines) + ("\n" if lines else ""))


def _oauth_done_page(service, ok, message):
    title = "Connected" if ok else "Connection Failed"
    return render_template_string(
        """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ title }}</title>
  <style>
    body { margin: 0; font-family: Arial, sans-serif; background: #07101d; color: #eef4ff; display: grid; place-items: center; min-height: 100vh; }
    .card { width: min(520px, 92vw); background: #0c1427; border: 1px solid #23324d; border-radius: 20px; padding: 24px; box-shadow: 0 20px 60px rgba(0,0,0,0.32); }
    h1 { margin-top: 0; font-size: 1.6rem; }
    p { color: #9fb0d0; line-height: 1.6; }
    .ok { color: #86efac; }
    .bad { color: #fca5a5; }
    code { word-break: break-word; }
  </style>
</head>
<body>
  <div class="card">
    <h1 class="{{ 'ok' if ok else 'bad' }}">{{ title }} for {{ service }}</h1>
    <p>{{ message }}</p>
    <p>This window will close automatically.</p>
  </div>
  <script>
    (function () {
      const payload = {{ payload | safe }};
      if (window.opener) {
        window.opener.postMessage(payload, window.location.origin);
      }
      setTimeout(() => window.close(), 900);
    })();
  </script>
</body>
</html>
        """,
        title=title,
        service=service.capitalize(),
        ok=ok,
        message=message,
        payload=json.dumps({"type": "oauth-complete", "service": service, "ok": ok, "message": message}),
    )


@app.get("/api/state")
def api_state():
  return jsonify({
    "ready": engine.ready(),
    "missing": engine.check_credentials(),
    "spotify_connected": bool(engine.spotify_client),
    "youtube_connected": bool(engine.youtube_client),
    "spotify_account_name": engine.spotify_account_name,
    "youtube_account_name": engine.youtube_account_name,
  })


@app.get("/api/config")
def api_config():
  return jsonify({
    "public_base_url": _public_base_url(),
    "spotify_redirect_uri": _callback_url("spotify"),
    "youtube_redirect_uri": _callback_url("youtube"),
  })


@app.post("/api/settings")
def api_settings():
  data = request.get_json(force=True, silent=True) or {}
  updates = {
    "SPOTIPY_CLIENT_ID": data.get("spotify_client_id") or os.environ.get("SPOTIPY_CLIENT_ID"),
    "SPOTIPY_CLIENT_SECRET": data.get("spotify_client_secret") or os.environ.get("SPOTIPY_CLIENT_SECRET"),
    "SPOTIPY_REDIRECT_URI": data.get("spotify_redirect_uri") or os.environ.get("SPOTIPY_REDIRECT_URI") or _callback_url("spotify"),
  }

  _write_env_file(updates)
  os.environ.update({key: value for key, value in updates.items() if value})

  youtube_secret_json = data.get("youtube_client_secret_json")
  if youtube_secret_json:
    YOUTUBE_SECRET_PATH.write_text(youtube_secret_json.strip() + "\n")

  return jsonify({
    "ok": True,
    "missing": engine.check_credentials(),
  })


@app.post("/api/connect/<service>")
def api_connect(service):
  if service not in {"spotify", "youtube"}:
    return jsonify({"error": "Unknown service"}), 404

  missing = engine.check_credentials()
  if service == "spotify" and ("Spotify Client ID" in missing or "Spotify Client Secret" in missing):
    return jsonify({
      "error": "Spotify credentials are missing",
      "missing": missing,
      "redirect_uri": _callback_url("spotify"),
    }), 400

  if service == "youtube" and "client_secret.json" in missing:
    return jsonify({
      "error": "YouTube client_secret.json is missing",
      "missing": missing,
      "redirect_uri": _callback_url("youtube"),
    }), 400

  if service == "spotify":
    callback_url = _callback_url("spotify")
    state_token = secrets.token_urlsafe(16)
    auth_manager = SpotifyOAuth(
      scope="user-library-read playlist-read-private playlist-read-collaborative",
      redirect_uri=callback_url,
      client_id=os.environ.get("SPOTIPY_CLIENT_ID"),
      client_secret=os.environ.get("SPOTIPY_CLIENT_SECRET"),
      cache_path=str(APP_ROOT / ".spotify-token-cache"),
      show_dialog=True,
    )
    auth_url = auth_manager.get_authorize_url(state=state_token)
    with oauth_lock:
      oauth_sessions[state_token] = {"service": service, "auth_manager": auth_manager}
    return jsonify({"service": service, "auth_url": auth_url, "redirect_uri": callback_url})

  callback_url = _callback_url("youtube")
  flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
    str(YOUTUBE_SECRET_PATH),
    scopes=[
      "https://www.googleapis.com/auth/youtube",
      "https://www.googleapis.com/auth/youtube.force-ssl",
    ],
  )
  flow.redirect_uri = callback_url
  auth_url, state_token = flow.authorization_url(prompt="consent", access_type="offline", include_granted_scopes="true")
  with oauth_lock:
    oauth_sessions[state_token] = {"service": service, "flow": flow}
  return jsonify({"service": service, "auth_url": auth_url, "redirect_uri": callback_url})


@app.get("/api/oauth/<service>/callback")
def api_oauth_callback(service):
  if service not in {"spotify", "youtube"}:
    return jsonify({"error": "Unknown service"}), 404

  error = request.args.get("error")
  if error:
    return _oauth_done_page(service, False, f"{service.capitalize()} login was cancelled: {error}")

  state = request.args.get("state")
  code = request.args.get("code")
  if not state or not code:
    return _oauth_done_page(service, False, "Missing OAuth state or authorization code.")

  with oauth_lock:
    session = oauth_sessions.pop(state, None)

  if not session or session.get("service") != service:
    return _oauth_done_page(service, False, "OAuth session expired. Please try again.")

  try:
    if service == "spotify":
      auth_manager = session["auth_manager"]
      auth_manager.get_access_token(code, as_dict=True)
      spotify_client = spotipy.Spotify(auth_manager=auth_manager)
      profile = spotify_client.current_user()
      account_name = profile.get("display_name") or profile.get("id") or "Unknown"
      engine.set_spotify_client(spotify_client, account_name)
      return _oauth_done_page(service, True, f"Connected as {account_name}.")

    flow = session["flow"]
    flow.fetch_token(code=code)
    youtube_client = googleapiclient.discovery.build("youtube", "v3", credentials=flow.credentials)
    channel_response = youtube_client.channels().list(part="snippet", mine=True, maxResults=1).execute()
    items = channel_response.get("items", [])
    account_name = "Unknown"
    if items:
      account_name = items[0].get("snippet", {}).get("title") or account_name
    engine.set_youtube_client(youtube_client, account_name)
    return _oauth_done_page(service, True, f"Connected as {account_name}.")
  except Exception as exc:
    return _oauth_done_page(service, False, str(exc))

DASHBOARD_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Spotify to YouTube Live</title>
  <style>
    :root {
      --bg: #07101d;
      --panel: #0c1427;
      --panel-2: #121d35;
      --panel-3: #172742;
      --text: #eef4ff;
      --muted: #9fb0d0;
      --accent: #4ade80;
      --accent-2: #38bdf8;
      --accent-3: #a78bfa;
      --danger: #fb7185;
      --border: #23324d;
      --shadow: 0 20px 60px rgba(0,0,0,0.32);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: Inter, "Segoe UI", Tahoma, sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(56,189,248,0.16), transparent 26%),
        radial-gradient(circle at bottom right, rgba(74,222,128,0.12), transparent 24%),
        var(--bg);
    }
    .wrap { width: min(1200px, 92vw); margin: 0 auto; padding: 28px 0 56px; }
    .hero, .panel {
      background: linear-gradient(180deg, rgba(12,20,39,0.96), rgba(8,13,25,0.98));
      border: 1px solid var(--border);
      box-shadow: var(--shadow);
      border-radius: 24px;
    }
    .hero {
      padding: 26px;
      margin-bottom: 18px;
      display: grid;
      gap: 14px;
      position: relative;
      overflow: hidden;
    }
    .hero::after {
      content: "";
      position: absolute;
      inset: auto -80px -80px auto;
      width: 240px;
      height: 240px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(56,189,248,0.22), rgba(56,189,248,0));
      pointer-events: none;
    }
    .eyebrow {
      display: inline-flex; width: fit-content; padding: 6px 12px; border-radius: 999px;
      background: rgba(74,222,128,0.08); border: 1px solid rgba(74,222,128,0.22);
      color: #bbf7d0; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.08em;
    }
    h1 { margin: 10px 0 8px; font-size: clamp(2rem, 4vw, 3rem); }
    .lead { margin: 0; color: var(--muted); line-height: 1.65; max-width: 900px; }
    .hero-grid { display: grid; grid-template-columns: 1.2fr 0.8fr; gap: 16px; align-items: stretch; }
    .stat-row { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 6px; }
    .stat {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border-radius: 999px;
      padding: 7px 11px;
      font-size: 0.82rem;
      color: #dbeafe;
      background: rgba(56,189,248,0.08);
      border: 1px solid rgba(56,189,248,0.18);
    }
    .grid { display: grid; grid-template-columns: 420px 1fr; gap: 18px; }
    .panel { padding: 18px; }
    .field { margin-bottom: 12px; }
    label { display: block; margin-bottom: 6px; color: var(--muted); font-size: 0.9rem; }
    input, textarea, select {
      width: 100%; padding: 10px 12px; border-radius: 12px; border: 1px solid var(--border);
      background: var(--panel-2); color: var(--text); outline: none;
    }
    textarea { min-height: 88px; resize: vertical; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 10px; }
    .btn {
      border: 0; border-radius: 12px; padding: 10px 14px; font-weight: 700; cursor: pointer;
      transition: transform 120ms ease, filter 120ms ease; text-decoration: none; display: inline-flex; align-items: center; justify-content: center;
    }
    .btn:hover { transform: translateY(-1px); filter: brightness(1.05); }
    .btn-primary { background: linear-gradient(135deg, var(--accent), #8bffb4); color: #052e16; }
    .btn-secondary { background: transparent; color: var(--text); border: 1px solid var(--border); }
    .btn-danger { background: var(--danger); color: white; }
    .accounts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-bottom: 14px; }
    .account-card {
      background: linear-gradient(180deg, rgba(23,39,66,0.9), rgba(12,20,39,0.95));
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 14px;
      display: grid;
      gap: 10px;
    }
    .account-card h3 { margin: 0; font-size: 1rem; }
    .account-status { color: var(--muted); font-size: 0.88rem; line-height: 1.4; }
    .account-status.ready { color: #86efac; }
    .account-status.warn { color: #fde68a; }
    .hint-note { color: var(--muted); font-size: 0.86rem; line-height: 1.55; margin-top: 10px; }
    .status-box {
      background: rgba(23, 35, 58, 0.82); border: 1px solid var(--border); border-radius: 18px; padding: 14px;
    }
    .status-row { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; margin-bottom: 10px; }
    .chip {
      border-radius: 999px; padding: 6px 10px; background: rgba(56,189,248,0.08); border: 1px solid rgba(56,189,248,0.18); color: #bae6fd; font-size: 0.8rem;
    }
    .progress { width: 100%; height: 10px; border-radius: 999px; background: rgba(148,163,184,0.2); overflow: hidden; }
    .bar { height: 100%; width: 0%; background: linear-gradient(90deg, var(--accent), var(--accent-2)); }
    .metrics { margin-top: 10px; color: var(--muted); font-size: 0.92rem; }
    .log {
      margin-top: 14px; height: 470px; overflow: auto; background: #050914; border-radius: 18px; padding: 14px;
      border: 1px solid var(--border); white-space: pre-wrap; color: #dbeafe; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 0.88rem;
    }
    .small { color: var(--muted); font-size: 0.92rem; line-height: 1.5; }
    .warning { color: #fbbf24; }
    .error { color: #fca5a5; }
    .banner {
      display: none;
      margin-top: 12px;
      padding: 12px 14px;
      border-radius: 16px;
      border: 1px solid rgba(251, 191, 36, 0.35);
      background: rgba(251, 191, 36, 0.08);
      color: #fde68a;
      line-height: 1.6;
    }
    .banner strong { color: #fff7cd; }
    .modal-backdrop {
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(3, 7, 18, 0.72);
      backdrop-filter: blur(8px);
      align-items: center;
      justify-content: center;
      z-index: 50;
      padding: 20px;
    }
    .modal-card {
      width: min(720px, 96vw);
      max-height: 90vh;
      overflow: auto;
      background: linear-gradient(180deg, rgba(12,20,39,0.98), rgba(8,13,25,0.99));
      border: 1px solid var(--border);
      border-radius: 24px;
      box-shadow: var(--shadow);
      padding: 22px;
    }
    .modal-card h2 { margin-top: 0; }
    .modal-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }
    .modal-grid .field:last-child { grid-column: 1 / -1; }
    .modal-note {
      color: var(--muted);
      line-height: 1.55;
      margin: 8px 0 14px;
    }
    .file-path {
      margin-top: 8px;
      color: #cbd5e1;
      font-size: 0.9rem;
    }
    @media (max-width: 920px) {
      .hero-grid, .grid, .accounts { grid-template-columns: 1fr; }
      .modal-grid { grid-template-columns: 1fr; }
      .grid { grid-template-columns: 1fr; }
      .log { height: 320px; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <div class="hero-grid">
        <div>
          <span class="eyebrow">Live App</span>
          <h1>Spotify to YouTube, running on the VM</h1>
          <p class="lead">Connect Spotify and YouTube from the UI, then sync liked songs or a playlist into a YouTube playlist while watching progress update live.</p>
          <div class="stat-row">
            <span class="stat">Real-time progress</span>
            <span class="stat">Account login UI</span>
            <span class="stat">Custom playlist privacy</span>
          </div>
        </div>
        <div class="status-box">
          <div class="status-row">
            <span class="chip" id="jobState">No job running</span>
            <span class="chip" id="jobId">job: -</span>
          </div>
          <div class="progress"><div class="bar" id="bar"></div></div>
          <div class="metrics" id="metrics">Added: 0 | Skipped: 0 | Errors: 0</div>
          <div class="banner" id="configBanner"></div>
        </div>
      </div>
      <div class="actions">
        <a class="btn btn-secondary" href="/projects/">Back to Projects</a>
        <a class="btn btn-secondary" href="/projects/spotify-to-yt/">Project Overview</a>
      </div>
    </section>

    <div class="grid">
      <section class="panel">
        <h2 style="margin-top:0">Account Login</h2>
        <div class="accounts">
          <div class="account-card">
            <h3>Spotify</h3>
            <div id="spotifyStatus" class="account-status warn">Not connected.</div>
            <button class="btn btn-primary" id="connectSpotify">Connect Spotify</button>
          </div>
          <div class="account-card">
            <h3>YouTube</h3>
            <div id="youtubeStatus" class="account-status warn">Not connected.</div>
            <button class="btn btn-primary" id="connectYoutube">Connect YouTube</button>
          </div>
        </div>
        <div class="hint-note">Use the buttons above to authenticate. The sync button stays disabled until both accounts are connected.</div>

        <h2 style="margin-top:22px">Sync Controls</h2>
        <div class="field">
          <label>Playlist Name</label>
          <input id="title" value="My Spotify Sync">
        </div>
        <div class="field">
          <label>Description</label>
          <textarea id="desc">Synced via Live VM App</textarea>
        </div>
        <div class="row">
          <div class="field">
            <label>Privacy</label>
            <select id="privacy">
              <option value="public">public</option>
              <option value="unlisted">unlisted</option>
              <option value="private">private</option>
            </select>
          </div>
          <div class="field">
            <label>Max Songs</label>
            <input id="maxSongs" placeholder="optional">
          </div>
        </div>
        <div class="field">
          <label>Spotify Source</label>
          <select id="mode">
            <option value="liked">Liked Songs</option>
            <option value="playlist">Specific Playlist</option>
          </select>
        </div>
        <div class="field">
          <label>Spotify Playlist ID / URL</label>
          <input id="playlistInput" placeholder="Paste a playlist ID, URL, or spotify:playlist:...">
        </div>
        <div class="actions">
          <button class="btn btn-primary" id="startBtn">Start Sync</button>
          <button class="btn btn-danger" id="cancelBtn" disabled>Cancel</button>
        </div>
        <p class="small warning">First-time login uses the VM’s OAuth flow. If a browser window appears on the VM, complete the sign-in there, then return here and start sync.</p>
        <p id="statusText" class="small">Idle.</p>
      </section>

      <section class="panel">
        <div class="status-box">
          <div class="status-row">
            <span class="chip" id="counts">0 / 0</span>
            <span class="chip" id="apiReady">Checking login status...</span>
          </div>
          <div class="small" id="stateDetails">Waiting for account login.</div>
        </div>
        <div class="log" id="log"></div>
      </section>
    </div>
  </div>

  <div class="modal-backdrop" id="configModal">
    <div class="modal-card">
      <h2>Configure login on the fly</h2>
      <p class="modal-note" id="configModalNote">Enter the missing OAuth details here, save them to the VM, then the browser login popup will open automatically.</p>
      <div class="small" style="margin-bottom: 14px;">
        Spotify Web API checklist: create an app in the Spotify Developer Dashboard, copy Client ID and Client Secret, and add the exact Redirect URI shown below to your app Redirect URI allowlist.
      </div>
      <div class="modal-grid">
        <div class="field">
          <label>Spotify Client ID</label>
          <input id="spotifyClientId" placeholder="Spotify app client id">
        </div>
        <div class="field">
          <label>Spotify Client Secret</label>
          <input id="spotifyClientSecret" placeholder="Spotify app client secret">
        </div>
        <div class="field">
          <label>Spotify Redirect URI</label>
          <input id="spotifyRedirectUri" readonly>
          <div class="file-path">Use this in your Spotify app settings.</div>
        </div>
        <div class="field">
          <label>YouTube client_secret.json file</label>
          <input id="youtubeSecretFile" type="file" accept=".json,application/json">
          <div class="file-path" id="youtubeFileName">No file selected</div>
        </div>
        <div class="field">
          <label>Or paste client_secret.json</label>
          <textarea id="youtubeSecretText" placeholder='{"installed": {...}}'></textarea>
        </div>
      </div>
      <div class="actions" style="margin-top: 14px;">
        <button class="btn btn-primary" id="saveConfigBtn">Save And Continue</button>
        <button class="btn btn-secondary" id="cancelConfigBtn">Cancel</button>
      </div>
    </div>
  </div>

  <script>
    let activeJob = null;
    const logEl = document.getElementById('log');
    const jobStateEl = document.getElementById('jobState');
    const jobIdEl = document.getElementById('jobId');
    const countsEl = document.getElementById('counts');
    const apiReadyEl = document.getElementById('apiReady');
    const barEl = document.getElementById('bar');
    const metricsEl = document.getElementById('metrics');
    const statusTextEl = document.getElementById('statusText');
    const spotifyStatusEl = document.getElementById('spotifyStatus');
    const youtubeStatusEl = document.getElementById('youtubeStatus');
    const stateDetailsEl = document.getElementById('stateDetails');
    const configBannerEl = document.getElementById('configBanner');
    const configModalEl = document.getElementById('configModal');
    const configModalNoteEl = document.getElementById('configModalNote');
    const spotifyClientIdEl = document.getElementById('spotifyClientId');
    const spotifyClientSecretEl = document.getElementById('spotifyClientSecret');
    const spotifyRedirectUriEl = document.getElementById('spotifyRedirectUri');
    const youtubeSecretFileEl = document.getElementById('youtubeSecretFile');
    const youtubeSecretTextEl = document.getElementById('youtubeSecretText');
    const youtubeFileNameEl = document.getElementById('youtubeFileName');
    const saveConfigBtn = document.getElementById('saveConfigBtn');
    const cancelConfigBtn = document.getElementById('cancelConfigBtn');
    const startBtn = document.getElementById('startBtn');
    const cancelBtn = document.getElementById('cancelBtn');
    const connectSpotifyBtn = document.getElementById('connectSpotify');
    const connectYoutubeBtn = document.getElementById('connectYoutube');
    let pendingConnectService = null;
    let pendingConnectButton = null;
    let loginPopup = null;

    function appendLog(line) {
      logEl.textContent += line + '\n';
      logEl.scrollTop = logEl.scrollHeight;
    }

    function setState(state) {
      jobStateEl.textContent = state;
    }

    function setProgress(data) {
      const total = data.total || 0;
      const processed = data.processed || 0;
      const pct = total ? Math.min(100, Math.round((processed / total) * 100)) : 0;
      barEl.style.width = pct + '%';
      countsEl.textContent = `${processed} / ${total}`;
      metricsEl.textContent = `Added: ${data.added || 0} | Skipped: ${data.skipped || 0} | Errors: ${data.errors || 0}`;
      statusTextEl.textContent = data.status ? `Status: ${data.status}` : 'Idle.';
    }

    function renderConnectionState(state) {
      const spotifyReady = state.spotify_connected;
      const youtubeReady = state.youtube_connected;
      spotifyStatusEl.textContent = spotifyReady ? `Connected as ${state.spotify_account_name || 'Spotify user'}` : 'Not connected.';
      youtubeStatusEl.textContent = youtubeReady ? `Connected as ${state.youtube_account_name || 'YouTube user'}` : 'Not connected.';
      spotifyStatusEl.className = spotifyReady ? 'account-status ready' : 'account-status warn';
      youtubeStatusEl.className = youtubeReady ? 'account-status ready' : 'account-status warn';
      apiReadyEl.textContent = state.ready ? 'Credentials ready' : `Missing: ${(state.missing || []).join(', ')}`;
      stateDetailsEl.textContent = state.ready
        ? 'Both account logins can be connected from the UI.'
        : 'This app is online. Click connect, then configure the missing OAuth details in the popup if needed.';
      startBtn.disabled = !(spotifyReady && youtubeReady && state.ready);

      connectSpotifyBtn.disabled = false;
      connectYoutubeBtn.disabled = false;
      connectSpotifyBtn.textContent = 'Connect Spotify';
      connectYoutubeBtn.textContent = 'Connect YouTube';

      if (!state.ready) {
        configBannerEl.style.display = 'block';
        configBannerEl.innerHTML = '<strong>Login setup required:</strong> Click a connect button, then save the missing OAuth details in the popup. The redirect URI for Spotify is shown in the setup modal.';
      } else {
        configBannerEl.style.display = 'none';
      }
    }

    async function loadState() {
      const response = await fetch('/api/state');
      const state = await response.json();
      renderConnectionState(state);
    }

    function openConfigModal(service, missing, redirectUri) {
      pendingConnectService = service;
      pendingConnectButton = service === 'spotify' ? connectSpotifyBtn : connectYoutubeBtn;
      configModalNoteEl.textContent = missing && missing.length
        ? `Missing: ${missing.join(', ')}. Fill the fields below, save, then the login popup will open automatically.`
        : 'Enter the OAuth details below, save them to the VM, then the login popup will open automatically.';
      spotifyRedirectUriEl.value = redirectUri || '';
      configModalEl.style.display = 'flex';
    }

    function closeConfigModal() {
      configModalEl.style.display = 'none';
      pendingConnectService = null;
      pendingConnectButton = null;
    }

    function openAuthPopup(authUrl, service) {
      const width = 560;
      const height = 760;
      const left = Math.max(0, Math.round((window.screen.width - width) / 2));
      const top = Math.max(0, Math.round((window.screen.height - height) / 2));
      loginPopup = window.open(authUrl, `${service}-oauth`, `width=${width},height=${height},left=${left},top=${top}`);
      if (!loginPopup) {
        appendLog('Popup blocked. Please allow popups for this site and try again.');
        return false;
      }
      return true;
    }

    async function continueConnectFlow(service) {
      try {
        const response = await fetch(`/api/connect/${service}`, { method: 'POST' });
        const data = await response.json();
        if (!response.ok) {
          openConfigModal(service, data.missing || [], data.redirect_uri);
          return;
        }
        if (!openAuthPopup(data.auth_url, service)) {
          return;
        }
        appendLog(`${service} login popup opened. Complete sign-in there, then return here.`);
      } catch (err) {
        appendLog(`Error: ${err.message}`);
      }
    }

    async function openConnectSetup(service) {
      try {
        appendLog(`Opening ${service} setup...`);
        const response = await fetch('/api/config');
        const config = await response.json();
        openConfigModal(
          service,
          [],
          service === 'spotify' ? config.spotify_redirect_uri : config.youtube_redirect_uri,
        );
      } catch (err) {
        appendLog(`Error: ${err.message}`);
      }
    }

    async function saveOAuthConfig() {
      const service = pendingConnectService;
      const file = youtubeSecretFileEl.files && youtubeSecretFileEl.files[0];
      let youtubeJson = youtubeSecretTextEl.value.trim();
      if (!youtubeJson && file) {
        youtubeJson = await file.text();
      }

      const payload = {
        spotify_client_id: spotifyClientIdEl.value.trim(),
        spotify_client_secret: spotifyClientSecretEl.value.trim(),
        spotify_redirect_uri: spotifyRedirectUriEl.value.trim(),
        youtube_client_secret_json: youtubeJson || null,
      };

      const response = await fetch('/api/settings', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || 'Failed to save OAuth settings');
      }

      appendLog('OAuth settings saved. Starting login...');
      closeConfigModal();
      await loadState();
      if (service) {
        await continueConnectFlow(service);
      }
    }

    async function startSync() {
      logEl.textContent = '';
      startBtn.disabled = true;
      cancelBtn.disabled = false;
      appendLog('Starting sync...');

      const payload = {
        title: document.getElementById('title').value.trim(),
        desc: document.getElementById('desc').value.trim(),
        privacy: document.getElementById('privacy').value,
        mode: document.getElementById('mode').value,
        playlist_input: document.getElementById('playlistInput').value.trim(),
        max_songs: document.getElementById('maxSongs').value.trim() || null,
      };

      const response = await fetch('/api/jobs', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.error || 'Failed to start job');
      }
      const job = await response.json();
      activeJob = job.job_id;
      jobIdEl.textContent = 'job: ' + activeJob;
      setState('Running');
      watchJob(activeJob);
    }

    async function cancelSync() {
      if (!activeJob) return;
      await fetch(`/api/jobs/${activeJob}/cancel`, { method: 'POST' });
      appendLog('Cancellation requested.');
    }

    function watchJob(jobId) {
      const source = new EventSource(`/api/jobs/${jobId}/stream`);
      source.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'log') {
          appendLog(data.message);
        } else if (data.type === 'progress') {
          setProgress(data);
        } else if (data.type === 'state') {
          setState(data.state);
          if (data.state === 'completed' || data.state === 'error' || data.state === 'cancelled') {
            startBtn.disabled = false;
            cancelBtn.disabled = true;
            source.close();
          }
        }
      };
      source.onerror = () => {
        source.close();
        setState('Disconnected');
        startBtn.disabled = false;
        cancelBtn.disabled = true;
      };
    }

    startBtn.addEventListener('click', () => startSync().catch((err) => {
      appendLog('Error: ' + err.message);
      startBtn.disabled = false;
      cancelBtn.disabled = true;
      setState('Error');
    }));
    cancelBtn.addEventListener('click', () => cancelSync().catch((err) => appendLog('Error: ' + err.message)));

    connectSpotifyBtn.addEventListener('click', () => openConnectSetup('spotify'));
    connectYoutubeBtn.addEventListener('click', () => openConnectSetup('youtube'));
    cancelConfigBtn.addEventListener('click', closeConfigModal);
    saveConfigBtn.addEventListener('click', () => saveOAuthConfig().catch((err) => appendLog('Error: ' + err.message)));

    youtubeSecretFileEl.addEventListener('change', () => {
      const file = youtubeSecretFileEl.files && youtubeSecretFileEl.files[0];
      youtubeFileNameEl.textContent = file ? file.name : 'No file selected';
    });

    window.addEventListener('message', async (event) => {
      if (!event.data || event.data.type !== 'oauth-complete') return;
      if (event.data.ok) {
        appendLog(`${event.data.service} login completed: ${event.data.message || 'Connected'}`);
        await loadState();
      } else {
        appendLog(`${event.data.service} login failed: ${event.data.message || 'Unknown error'}`);
      }
      if (loginPopup && !loginPopup.closed) {
        loginPopup.close();
      }
      loginPopup = null;
    });

    loadState().catch((err) => {
      apiReadyEl.textContent = 'Could not load state';
      appendLog('Error: ' + err.message);
    });
  </script>
</body>
</html>
"""


@app.get("/")
def root():
    return redirect("/projects/", code=302)


@app.get("/live/")
def live_dashboard():
    return render_template_string(DASHBOARD_TEMPLATE)


@app.get("/projects/spotify-to-yt/live")
@app.get("/projects/spotify-to-yt/live/")
def live_dashboard_public():
  return render_template_string(DASHBOARD_TEMPLATE)


@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "ready": engine.ready(),
        "missing": engine.check_credentials(),
    })


@app.post("/api/jobs")
def create_job():
    data = request.get_json(force=True, silent=True) or {}
    try:
        max_songs = data.get("max_songs")
        if max_songs in ("", None):
            max_songs = None
        elif isinstance(max_songs, str):
            max_songs = int(max_songs)
        else:
            max_songs = int(max_songs)
    except ValueError:
        return jsonify({"error": "Max songs must be a positive whole number"}), 400

    job_id = str(uuid.uuid4())
    event_queue = queue.Queue()
    cancel_event = threading.Event()

    job = {
        "job_id": job_id,
        "queue": event_queue,
        "cancel_event": cancel_event,
        "state": "queued",
        "snapshot": {
            "title": data.get("title") or "My Spotify Sync",
            "desc": data.get("desc") or "Synced via App",
            "privacy": data.get("privacy") or "public",
            "mode": data.get("mode") or "liked",
            "playlist_input": data.get("playlist_input") or "",
            "max_songs": max_songs,
        },
    }

    with job_lock:
        jobs[job_id] = job

    def logger(message):
        event_queue.put({"type": "log", "message": message})

    def progress(processed, total, added, skipped, errors, status):
        event_queue.put({
            "type": "progress",
            "processed": processed,
            "total": total,
            "added": added,
            "skipped": skipped,
            "errors": errors,
            "status": status,
        })
        if status in {"Completed", "Cancelled", "Crashed", "No songs to sync"}:
            state = status.lower().replace(" ", "-")
            event_queue.put({"type": "state", "state": state})

    def worker():
        try:
            with job_lock:
                jobs[job_id]["state"] = "running"
            event_queue.put({"type": "state", "state": "running"})
            engine.sync(SyncConfig(**job["snapshot"]), logger=logger, progress=progress, cancel_event=cancel_event)
            if cancel_event.is_set():
                event_queue.put({"type": "state", "state": "cancelled"})
            else:
                event_queue.put({"type": "state", "state": "completed"})
        except Exception as exc:
            event_queue.put({"type": "log", "message": f"CRITICAL ERROR: {exc}"})
            event_queue.put({"type": "state", "state": "error"})
        finally:
            with job_lock:
                jobs[job_id]["state"] = "finished"

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return jsonify({"job_id": job_id})


@app.post("/api/jobs/<job_id>/cancel")
def cancel_job(job_id):
    with job_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    job["cancel_event"].set()
    job["queue"].put({"type": "log", "message": "Cancellation requested from browser."})
    return jsonify({"ok": True})


@app.get("/api/jobs/<job_id>/stream")
def stream_job(job_id):
  with job_lock:
    job = jobs.get(job_id)
  if not job:
    return jsonify({"error": "Job not found"}), 404

  def event_stream():
    queue_ref = job["queue"]
    yield f"data: {json.dumps({'type': 'state', 'state': job['state']})}\n\n"
    while True:
      payload = queue_ref.get()
      yield f"data: {json.dumps(payload)}\n\n"
      if payload.get("type") == "state" and payload.get("state") in {"completed", "cancelled", "error", "no-songs-to-sync"}:
        break

  return Response(stream_with_context(event_stream()), mimetype="text/event-stream")


if __name__ == "__main__":
  app.run(host="127.0.0.1", port=5000, debug=False)
