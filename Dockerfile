# Use the official Python image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install dependencies first so this layer is cached between code changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code (see .dockerignore)
COPY . /app

# Set default environment variables (overridden by docker-compose.yml)
ENV DATABASE_URL="postgresql+psycopg2://samiksha:password123@postgres:5432/ecommerce_data"
ENV MONGO_URI="mongodb://mongodb:27017"
ENV DATASET_PATH="data/online_retail.csv"

# Port used by the Flask API (newapp.py)
EXPOSE 5001

# Default command; docker-compose.yml sets the command per service
CMD ["python", "data_ingestion.py"]
