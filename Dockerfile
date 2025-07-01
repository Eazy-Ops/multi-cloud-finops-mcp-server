FROM python:3.10-slim-buster

WORKDIR /app

# Install Poetry and upgrade pip
RUN pip install --upgrade pip && pip install poetry

# Copy dependency files first for Docker layer caching
COPY pyproject.toml poetry.lock ./

# Avoid creating virtual environments; install only main dependencies
RUN poetry config virtualenvs.create false \
    && poetry install --only main --no-root

# Copy the rest of the application including .env
COPY . .
COPY .env .env

# Set encoding to avoid Rich Unicode issues
ENV PYTHONIOENCODING=utf-8

# Set GCP ADC path explicitly
ENV GOOGLE_APPLICATION_CREDENTIALS=/root/.config/gcloud/application_default_credentials.json

# Optional port (for web version)
EXPOSE 8000

# Start the CLI
CMD ["poetry", "run", "python", "main.py"]
