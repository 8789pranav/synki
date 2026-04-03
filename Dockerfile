FROM python:3.11-slim

WORKDIR /app

# Install uv
RUN pip install uv

# Copy project files
COPY pyproject.toml .
COPY src/ src/

# Install dependencies
RUN uv sync --no-dev

# Download model files
RUN uv run python -c "from livekit.plugins import silero; silero.VAD.load()"

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run the agent
CMD ["uv", "run", "python", "-m", "synki.agent", "start"]
