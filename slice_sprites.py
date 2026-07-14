from PIL import Image
import os

try:
    # Open the spritesheet image
    spritesheet = Image.open('assets/inputs/spritesheet.png')
    # Ensure the output directory exists
    os.makedirs('assets/outputs/', exist_ok=True)

    # Define the size of each sprite
    sprite_size = 32

    # Get the width and height of the spritesheet
    sheet_width, sheet_height = spritesheet.size

    # Calculate the number of columns and rows
    num_cols = sheet_width // sprite_size
    num_rows = sheet_height // sprite_size

    # Loop through each row and column to crop and save each sprite
    for row in range(num_rows):
        for col in range(num_cols):
            # Calculate the box for the current sprite
            left = col * sprite_size
            upper = row * sprite_size
            right = left + sprite_size
            lower = upper + sprite_size

            # Crop the sprite from the spritesheet
            sprite = spritesheet.crop((left, upper, right, lower))

            # Define the filename for the sprite
            filename = f'sprite_{row}_{col}.png'
            output_path = os.path.join('assets/outputs/', filename)

            # Save the sprite to the output directory
            sprite.save(output_path)

    print("All sprites have been successfully saved to 'assets/outputs/'.")
except FileNotFoundError:
    print("Error: The file 'assets/inputs/spritesheet.png' was not found.")
except Exception as e:
    print(f"An error occurred: {e}")