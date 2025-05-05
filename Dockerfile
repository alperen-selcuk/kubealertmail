FROM python:3.9-slim

WORKDIR /app

# Copy application code
COPY . .

# Install requirements
RUN pip install --no-cache-dir flask kubernetes flask-sqlalchemy sqlalchemy psycopg2-binary

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Expose port for the web interface
EXPOSE 5000

# Run the application
CMD ["python", "main.py"]
