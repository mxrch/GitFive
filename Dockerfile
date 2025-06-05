# Use a specific Python base image
FROM python:3.10

# Set the working directory
WORKDIR /usr/src/app

# Copy requirements and setup.py
COPY requirements.txt setup.py ./

# Install Python dependencies
RUN python -m pip install --no-cache-dir --upgrade pip && \
    python -m pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application files
COPY . .

# Run setup.py install
RUN python setup.py install

# Define the command to run the application
CMD ["python", "./main.py"]
