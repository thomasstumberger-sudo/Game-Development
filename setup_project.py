# Setup project directories
import os
from pathlib import Path

# Define the directories to create
directories = [
    Path('assets/inputs'),
    Path('assets/outputs'),
    Path('logs')
]

# Create each directory if it doesn't exist and print a message
for dir_path in directories:
    if not dir_path.exists():
        dir_path.mkdir(parents=True)
        print(f"Created directory: {dir_path}")
    else:
        print(f"Directory already exists: {dir_path}")
        