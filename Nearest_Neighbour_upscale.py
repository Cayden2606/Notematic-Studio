from pathlib import Path

from PIL import Image


def nearest_neighbour_upscale(image_path, scale_factor):
    image = Image.open(image_path)
    new_width = image.width * scale_factor
    new_height = image.height * scale_factor
    return image.resize((new_width, new_height), resample=Image.NEAREST)


paths_to_upscale = [
    "static\\textures\\Repeaters\\repeater-powered-1t.png",
    "static\\textures\\Repeaters\\repeater-powered-2t.png",
    "static\\textures\\Repeaters\\repeater-powered-3t.png",
    "static\\textures\\Repeaters\\repeater-powered-4t.png",
    "static\\textures\\Repeaters\\repeater-unpowered-1t.png",
    "static\\textures\\Repeaters\\repeater-unpowered-2t.png",
    "static\\textures\\Repeaters\\repeater-unpowered-3t.png",
    "static\\textures\\Repeaters\\repeater-unpowered-4t.png",
    "static\\textures\\Redstone_Dust\\redstone_dust_cross-powered.png",
    "static\\textures\\Redstone_Dust\\redstone_dust_cross-unpowered.png",
    "static\\textures\\Redstone_Dust\\redstone_dust_T-powered.png",
    "static\\textures\\Redstone_Dust\\redstone_dust_T-unpowered.png",
    "static\\textures\\Redstone_Dust\\redstone_dust_top-powered.png",
    "static\\textures\\Redstone_Dust\\redstone_dust_top-unpowered.png",
    "static\\textures\\Redstone_Dust\\redstone_dust_bottom-powered.png",
    "static\\textures\\Redstone_Dust\\redstone_dust_bottom-unpowered.png",
]


for path in paths_to_upscale:
    upscaled_image = nearest_neighbour_upscale(path, 2)
    output_path = Path(path).with_name(f"{Path(path).stem}_upscaled.png")
    upscaled_image.save(output_path)