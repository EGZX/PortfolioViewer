# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies
# curl is used for the healthcheck
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose port 8501 for Streamlit
EXPOSE 8501

# Healthcheck to ensure the app is running
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# Run the application
ENTRYPOINT ["streamlit", "run", "portfolio_viewer.py", "--server.port=8501", "--server.address=0.0.0.0"]
