import os
from xml.etree.ElementTree import Element, SubElement, tostring

# Define the directory containing the PNG files
input_dir = "assets/outputs/"

# Define the output resource file
output_file = "assets/outputs/spritesheet_atlas.tres"

# Create the root resource element
root = Element("gd_resource", {
    "type": "AtlasTexture",
    "format": "xml",
    "version": "1"
})

# Create the metadata element
metadata = SubElement(root, "meta", {
    "format": "xml",
    "engine_version": "4.0"
})

# Create the atlas element
atlas = SubElement(root, "atlas")

# List all PNG files in the input directory
png_files = [f for f in os.listdir(input_dir) if f.lower().endswith(".png")]

# Generate the resource file content
for filename in png_files:
    file_path = os.path.join(input_dir, filename)
    # For simplicity, we assume each PNG is a separate texture in the atlas
    # In a real scenario, you'd calculate or read the coordinates from a spritesheet
    texture = SubElement(atlas, "texture", {
        "path": f"res://{file_path}",
        "rect": "Rect2(0, 0, 1, 1)"  # Placeholder for actual coordinates
    })

# Convert the XML tree to a string
xml_str = tostring(root, encoding="unicode", method="xml")

# Write the XML content to the output file
with open(output_file, "w") as f:
    f.write(xml_str)

# Print completion message
print("Godot AtlasTexture resource file generated successfully at:", output_file)