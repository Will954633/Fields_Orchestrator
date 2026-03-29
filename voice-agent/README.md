# Fields Voice Agent

Voice-controlled AI assistant for Fields Real Estate operations.

## Architecture

```
Android App (push-to-talk)
    │ audio (WAV)
    ▼
FastAPI Backend (vm.fieldsestate.com.au:8090)
    │
    ├─ OpenAI STT (gpt-4o-mini-transcribe) → text
    │
    ├─ Route to LLM:
    │   ├─ Work Mode    → Claude Sonnet (full VM access via claude -p)
    │   └─ Strategy Mode → GPT-5.4 (1M context frontier reasoning)
    │
    ├─ OpenAI TTS (gpt-4o-mini-tts) → audio
    │
    ▼ JSON {transcript, reply, audio_base64}
Android App (plays MP3 response)
```

## Cost Estimate

| Component | Cost |
|-----------|------|
| STT (gpt-4o-mini-transcribe) | ~$0.006/min |
| Claude Sonnet (work mode) | ~$0.01/turn |
| GPT-5.4 (strategy mode) | ~$0.02/turn |
| TTS (gpt-4o-mini-tts) | ~$0.02/response |
| **Total per conversation minute** | **~$0.03-0.05** |

## Backend Setup (VM)

```bash
# 1. Install deps (already done)
source /home/fields/venv/bin/activate
pip install fastapi uvicorn python-multipart

# 2. Set auth token (optional but recommended)
echo 'VOICE_AGENT_TOKEN=your-secret-token-here' >> /home/fields/Fields_Orchestrator/.env

# 3. Install systemd service
sudo cp fields-voice-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now fields-voice-agent

# 4. Check it's running
curl http://localhost:8090/api/health

# 5. Open firewall for port 8090 (if using direct access)
# Or proxy through nginx on vm.fieldsestate.com.au
```

### Nginx Proxy (recommended)

Add to your nginx config for `vm.fieldsestate.com.au`:

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8090;
    proxy_read_timeout 120s;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    client_max_body_size 25M;
}
```

Then the Android app connects to `https://vm.fieldsestate.com.au` (no port needed).

## Android App Setup

1. Open `voice-agent/android-app/` in Android Studio
2. Edit `app/build.gradle.kts` — set `API_BASE_URL` and `API_TOKEN`
3. Build & run on your phone
4. Grant microphone permission when prompted
5. Press and hold the blue button to speak

### Modes

- **Work Mode** (Claude Sonnet): Full VM access. Can run scripts, query databases, check pipeline status, read files. Everything Claude Code can do.
- **Strategy Mode** (GPT-5.4): 1M context frontier model. Business strategy, market analysis, brainstorming. No VM access — pure conversation.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/voice` | Audio in → audio + text out |
| POST | `/api/chat` | Text in → text out (testing) |
| GET | `/api/health` | Health check |
| GET | `/api/history?mode=work` | Conversation history |
| DELETE | `/api/history?mode=work` | Clear history |

### POST /api/voice

```bash
curl -X POST https://vm.fieldsestate.com.au/api/voice \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "audio=@recording.wav" \
  -F "mode=work"
```

Response:
```json
{
  "transcript": "What's the pipeline status?",
  "reply": "The last pipeline run completed successfully at 20:45 AEST...",
  "audio_base64": "//uQxAAA...",
  "audio_format": "mp3",
  "mode": "work"
}
```
