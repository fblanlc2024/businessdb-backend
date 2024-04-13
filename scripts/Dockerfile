FROM python:3.11.5-slim

# Set a directory for the app
WORKDIR /usr/src/app

# Copy the dependencies file
COPY requirements.txt ./

# Install any dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the content of the local src directory to the working directory
COPY . .

# Command to run on container start
CMD [ "python", "./scripts/auto_backup.py" ]