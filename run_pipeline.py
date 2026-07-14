import subprocess
import os
import sys

def run_script(script_name):
    """Run a Python script using subprocess and check for errors."""
    try:
        result = subprocess.run(
            [sys.executable, script_name],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return result
    except subprocess.CalledProcessError as e:
        print(f"Error running {script_name}:")
        print(e.stderr)
        sys.exit(1)

def count_files_in_directory(directory):
    """Count the number of files in a directory and its subdirectories."""
    file_count = 0
    for root, dirs, files in os.walk(directory):
        for file in files:
            file_count += 1
    return file_count

def main():
    print("Starting sprite processing pipeline...")

    # Run the sprite slicer
    print("Running 'slice_sprites.py'...")
    run_script('slice_sprites.py')

    # Run the sprite packager
    print("Running 'package_sprites.py'...")
    run_script('package_sprites.py')

    # Count total files processed
    total_files = count_files_in_directory('assets/outputs') # Replace with actual output directory

    print(f"Sprite processing pipeline completed successfully. Total files processed: {total_files}")

if __name__ == "__main__":
    main()