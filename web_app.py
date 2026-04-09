import queue
import json
import threading
import uuid

from flask import Flask, jsonify, redirect, render_template_string, request, Response, stream_with_context

from sync_engine import SpotifyToYoutubeEngine, SyncConfig

app = Flask(__name__)
engine = SpotifyToYoutubeEngine()
jobs = {}
job_lock = threading.Lock()


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


@app.post("/api/connect/<service>")
def api_connect(service):
  try:
    if service == "spotify":
      account_name = engine.connect_spotify()
      return jsonify({"service": service, "connected": True, "account_name": account_name})

    if service == "youtube":
      account_name = engine.connect_youtube()
      return jsonify({"service": service, "connected": True, "account_name": account_name})

    return jsonify({"error": "Unknown service"}), 404
  except Exception as exc:
    return jsonify({"service": service, "connected": False, "error": str(exc)}), 500

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
    @media (max-width: 920px) {
      .hero-grid, .grid, .accounts { grid-template-columns: 1fr; }
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
    const startBtn = document.getElementById('startBtn');
    const cancelBtn = document.getElementById('cancelBtn');
    const connectSpotifyBtn = document.getElementById('connectSpotify');
    const connectYoutubeBtn = document.getElementById('connectYoutube');

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
        : 'Fix the missing credentials before attempting login.';
      startBtn.disabled = !(spotifyReady && youtubeReady && state.ready);
      connectSpotifyBtn.disabled = !state.ready;
      connectYoutubeBtn.disabled = !state.ready;
    }

    async function loadState() {
      const response = await fetch('/api/state');
      const state = await response.json();
      renderConnectionState(state);
    }

    async function connectService(service, button) {
      button.disabled = true;
      button.textContent = 'Connecting...';
      try {
        const response = await fetch(`/api/connect/${service}`, { method: 'POST' });
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.error || `Failed to connect ${service}`);
        }
        appendLog(`${service} connected: ${data.account_name || 'Unknown'}`);
        await loadState();
      } catch (err) {
        appendLog(`Error: ${err.message}`);
      } finally {
        button.disabled = false;
        button.textContent = service === 'spotify' ? 'Connect Spotify' : 'Connect YouTube';
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

    connectSpotifyBtn.addEventListener('click', () => connectService('spotify', connectSpotifyBtn));
    connectYoutubeBtn.addEventListener('click', () => connectService('youtube', connectYoutubeBtn));

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
