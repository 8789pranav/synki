"""
Synki Voice Companion Agent

Main entry point for running the LiveKit voice agents.

BOTH AGENTS RUN ON THE SAME SERVER:
1. synki-companion - The girlfriend persona for regular calls
2. synki-topic-caller - A soft, caring helper for scheduled topic calls

Usage:
    # Run the agent server (handles BOTH girlfriend and topic calls)
    uv run python -m synki.agent start
    
    # Development mode
    uv run python -m synki.agent dev

The API dispatches to the correct agent by passing agent_name in the token:
- agent_name="synki-companion" for girlfriend calls
- agent_name="synki-topic-caller" for scheduled topic calls

Make sure to set up your .env.local file with the required API keys.
"""

from livekit import agents


def main():
    """Main entry point - runs both agents on the same server."""
    # Both agents are registered on the same server in companion_agent.py
    # - synki-companion: girlfriend persona
    # - synki-topic-caller: soft friend for topic calls
    from synki.agent.companion_agent import server
    agents.cli.run_app(server)


if __name__ == "__main__":
    main()
