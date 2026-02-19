# LiveKit Module — Real-Time Voice

Handles WebRTC-based real-time voice communication between Feynman and the classroom.

## Architecture

The LiveKit agent worker runs as a **separate process** from the FastAPI server:

- FastAPI = request/response (REST API, WebSocket for visuals)
- LiveKit worker = long-running process (joins rooms, runs STT→LLM→TTS pipeline)

## Files

| File          | Purpose                                        |
| ------------- | ---------------------------------------------- |
| `worker.py`   | Agent worker entrypoint — the separate process |
| `room.py`     | Room creation and management                   |
| `pipeline.py` | STT/LLM/TTS provider configuration             |

## Providers

- **STT**: Deepgram (primary)
- **LLM**: Anthropic Claude (frontier teaching), OpenAI GPT (sub-tasks)
- **TTS**: Cartesia (primary)
- **VAD**: Silero (voice activity detection)
- **Turn detection**: LiveKit turn-detector plugin
