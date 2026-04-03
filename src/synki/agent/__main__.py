"""
Synki Voice Companion Agent

Main entry point for running the LiveKit voice agent.

Usage:
    # Development mode (with hot reload)
    uv run python -m synki.agent dev
    
    # Production mode
    uv run python -m synki.agent start

Make sure to set up your .env.local file with the required API keys.
"""

from livekit import agents
from synki.agent.companion_agent import server


def main():
    """Main entry point."""
    agents.cli.run_app(server)


if __name__ == "__main__":
    main()
