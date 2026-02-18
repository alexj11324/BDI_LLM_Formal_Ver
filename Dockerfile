# Use python 3.11 slim image
FROM python:3.11-slim

# Install system dependencies required for compiling VAL and running the server
RUN apt-get update && apt-get install -y \
    build-essential \
    flex \
    bison \
    make \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r app && useradd -r -g app app

# Set working directory
WORKDIR /app

# Copy requirements and install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy planbench_data (contains VAL source)
COPY --chown=app:app planbench_data /app/planbench_data

# Compile VAL
WORKDIR /app/planbench_data/planner_tools/VAL
RUN make clean || true
RUN make validate && chmod +x validate && chown app:app validate

# Return to app root
WORKDIR /app

# Copy source code
COPY --chown=app:app src /app/src

# Set environment variables
ENV PYTHONPATH=/app
ENV VAL_VALIDATOR_PATH=/app/planbench_data/planner_tools/VAL/validate

# Run as non-root
USER app

# Entrypoint for the MCP server
CMD ["python", "src/interfaces/mcp_server.py"]
