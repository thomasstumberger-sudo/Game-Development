import os

# Define the directory containing the PNG files
directory = 'assets/outputs/'

# Loop through all files in the directory
for filename in os.listdir(directory):
    # Check if the file is a PNG
    if filename.lower().endswith('.png'):
        # Construct full file path
        file_path = os.path.join(directory, filename)

        # Generate the name for the configuration file
        config_filename = f"{os.path.splitext(filename)[0]}.png.import"
        config_file_path = os.path.join(directory, config_filename)

        # Write the mock Godot 4 configuration to the file
        with open(config_file_path, 'w') as config_file:
            config_file.write('[remap]\n')
            config_file.write('path="res://.godot/imported/{}"\n'.format(filename))

        # Print confirmation for each configuration file created
        print(f"Created configuration file: {config_file_path}")