"""LiveKit agent worker entrypoint.

This runs as a separate process from the FastAPI server.
It connects to LiveKit, joins rooms, and runs the STT→LLM→TTS pipeline.
"""
