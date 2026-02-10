#!/bin/bash

# Install Sherlock for OSINT searches

# Clone the repository
if [ ! -d "sherlock" ]; then
    git clone https://github.com/sherlock-project/sherlock.git
fi

cd sherlock

# Create a Python virtual environment
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate

# Install required packages
pip install -r requirements.txt

# Notify user that installation is complete
echo "Sherlock has been installed and is ready to use."