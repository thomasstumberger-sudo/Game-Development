#!/bin/bash

TARGET_DIR="assets/inputs"

echo "Watching directory: $TARGET_DIR for changes..."

# Loop and wait for close_write events (when a file is fully saved/copied)
inotifywait -m -e close_write --format "%f" "$TARGET_DIR" | while read -r FILENAME
do
    # Check if the modified file is a PNG spritesheet
    if [[ "$FILENAME" =~ \.png$ ]]; then
        echo "Detected change in: $FILENAME. Running asset pipeline..."
        python3 run_pipeline.py
        
        # Also run our new atlas generator if it's ready
        if [ -f "generate_atlas.py" ]; then
            python3 generate_atlas.py
        fi
        echo "Pipeline run completed!"
    fi
done