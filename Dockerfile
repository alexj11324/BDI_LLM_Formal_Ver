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

# Set working directory
WORKDIR /app

# Copy requirements and install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir mcp

# Copy planbench_data (contains VAL source)
COPY planbench_data /app/planbench_data

# Compile VAL
WORKDIR /app/planbench_data/planner_tools/VAL
# Clean any existing artifacts and build validate
# We ignore errors in make clean just in case
RUN make clean || true
RUN make validate

# Verify VAL compilation
RUN ls -l validate && ./validate --help || echo "VAL help check failed (expected if no args)"

# Return to app root
WORKDIR /app

# Copy source code
COPY src /app/src

# Set environment variables
ENV PYTHONPATH=/app
# Set VAL path explicitly to the compiled binary
ENV VAL_VALIDATOR_PATH=/app/planbench_data/planner_tools/VAL/validate

# Entrypoint for the MCP server
CMD ["python", "src/interfaces/mcp_server.py"]
