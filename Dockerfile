# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the new project structure
COPY src/ /app/src/
COPY pyproject.toml /app/

# Install the application and its dependencies
RUN pip install .

# Copy the modem data for testing
COPY modems/ /app/modems/

# Use the new console script as the entrypoint
ENTRYPOINT ["sagemcom2mqtt"] 