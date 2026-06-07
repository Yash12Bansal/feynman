# Sharing Feynman to a cohort (local + ngrok)

How to share the locally-running app to remote testers so that **everything works —
including live "Ask Feynman" voice doubts**. Tuned for **≤10 concurrent** users.

## TL;DR
- **Don't add workers.** At ≤10 concurrent, every server (backend :8000, preview :8080,
  agent worker) is single-process *async* and that's already plenty. Watching a precomputed
  lecture is light: client-side playback + tiny 35–70 KB audio fragments.
- **The one thing that's actually broken for remote users is LiveKit on `localhost`.** Live
  doubts connect WebRTC **directly** from the browser, bypassing the ngrok tunnel, so
  `ws://localhost:7880` is unreachable for anyone but you. Lectures still play (that's
  client-side); only Ask-Feynman silently fails. **Fix = LiveKit Cloud (config only).**
- The only real scale risk at 10 is **ngrok bandwidth for the audio** — offload if it stalls.

## 1. Make live doubts work remotely — switch to LiveKit Cloud (required)

WebRTC media/signaling cannot ride an ngrok HTTP tunnel, so a local LiveKit can't serve
remote browsers. Use LiveKit Cloud (free tier is plenty for ≤10):

1. Create a project at <https://cloud.livekit.io> → copy the project URL
   (`wss://<project>.livekit.cloud`), **API key**, and **API secret**.
2. Backend `.env`:
   ```
   LIVEKIT_URL=wss://<project>.livekit.cloud
   LIVEKIT_API_KEY=<key>
   LIVEKIT_API_SECRET=<secret>
   ```
3. `frontend/.env.local`:
   ```
   VITE_LIVEKIT_URL=wss://<project>.livekit.cloud
   ```
4. Restart **both** the backend and the agent worker so the worker re-registers with the
   cloud project (dispatch stays automatic — no code change):
   ```
   make dev-backend     # picks up the new URL
   make dev-worker      # agent registers with LiveKit Cloud
   ```
5. The local LiveKit Docker container is now unused — you can leave it or stop it.

**Bonus:** all real-time media now flows browser ↔ LiveKit Cloud, *off* your ngrok tunnel,
which also lightens ngrok.

## 2. Doubt pipeline keys (already OK, optional upgrade)
`ANTHROPIC_API_KEY` (planner/classifier LLM) and `OPENAI_API_KEY` are set, so STT+TTS run on
the OpenAI fallback (`gpt-4o-mini-transcribe` / `gpt-4o-mini-tts`) — **doubts work today**.
For better real-time voice quality/latency, add `DEEPGRAM_API_KEY` (STT) and
`CARTESIA_API_KEY` (TTS); the pipeline prefers them automatically.

## 3. Serve to the cohort
1. `make dev` (worker + backend :8000 + frontend :5173 + preview :8080; docker services up).
2. `make share` (tunnels :5173 via your reserved ngrok domain).
3. Ensure the ngrok domain is in **Firebase → Authentication → Authorized domains** (sign-in
   already works, so this is set).

Keep the **Vite dev server** as the front door at this scale — its proxy is what routes
`/api`→:8000 and `/lecture-api` + `/lecture-artifacts`→:8080. (A production build would drop
that proxy and need nginx/Caddy — not worth it for ≤10.) **Don't edit source files during a
live session** — the dev server's reloads will hiccup connected users.

## 4. If audio stalls (the one genuine scale risk at 10)
All lecture audio (~15–74 MB per chapter, streamed in fragments) flows through the single
ngrok tunnel + single preview worker. For ≤10 it's usually fine; if you see buffering:
- Serve `data_pre_compute_v2/artifacts/` (audio + diagrams) from a CDN/static host (Firebase
  Storage / Cloudflare R2 / a cheap static deploy) so audio bypasses ngrok entirely, **or**
- Use a paid/dedicated ngrok tunnel for more bandwidth.
- (Optional, minor) give the preview server a couple of workers — note it currently launches
  with `uvicorn.run(app, …)` (an app instance), which ignores `workers=N`; using workers
  needs the import-string form and the module importable from CWD.

## 5. Verify (the real proof — do this from a different machine/network)
1. After the LiveKit Cloud switch + restart, open the ngrok URL on **two** remote devices,
   sign in, open the same lecture.
2. Both should **watch with audio** (already worked before).
3. On each, tap **Ask Feynman** and speak. In the browser console you should see
   **`[LiveKit] Connected to room`** (not an error), the doubt is captured, and the spoken
   answer plays back. That is the proof remote doubts work — which they cannot on `localhost`.
4. The agent worker log shows a `worker.session_start` per room; one worker handles ~20–30
   rooms, so 10 is comfortable.

## What about CORS / Firebase?
The browser hits the ngrok origin and Vite proxies `/api` server-side, so requests are
same-origin and CORS isn't triggered. If you ever see CORS errors, set
`FRONTEND_URL=https://<your-ngrok-domain>` in the backend `.env`.
