# Use an official lightweight Python runtime
FROM python:3.11-slim

# Set working directory inside the container
WORKDIR /app

# Set environment variables to prevent bytecode creation and buffer output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Copy requirements file first to leverage Docker cache layer
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application files to container
COPY . .

# Expose port 8000 for Uvicorn
EXPOSE 8000

# Start Uvicorn bound to 0.0.0.0 to accept external cloud traffic
CMD ["uvicorn", "paywall_api:app", "--host", "0.0.0.0", "--port", "8000"]