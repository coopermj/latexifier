# Use TeX Live as base for full LaTeX support
FROM texlive/texlive:latest

# Install pip for system Python and dependencies for Quarto
RUN apt-get update && apt-get install -y \
    python3-pip \
    python3-venv \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Quarto
RUN wget -q https://github.com/quarto-dev/quarto-cli/releases/download/v1.4.557/quarto-1.4.557-linux-amd64.deb \
    && dpkg -i quarto-1.4.557-linux-amd64.deb \
    && rm quarto-1.4.557-linux-amd64.deb

# Create app directory
WORKDIR /app

# Create virtual environment
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Upgrade pip
RUN pip install --upgrade pip wheel

# Install Python dependencies (prefer binary wheels)
COPY requirements.txt .
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

# Copy application code
COPY app/ ./app/

# Create storage directory
RUN mkdir -p /data/styles /data/fonts /data/temp

# Set environment variables
ENV STORAGE_PATH=/data
ENV PYTHONUNBUFFERED=1

# Railway sets PORT env var
ENV PORT=8000

# Run the application (uses $PORT)
CMD uvicorn app.main:app --host 0.0.0.0 --port $PORT
