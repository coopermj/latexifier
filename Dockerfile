# Use TeX Live as base for full LaTeX support
FROM texlive/texlive:latest

# Install pip for system Python
RUN apt-get update && apt-get install -y \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

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

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
