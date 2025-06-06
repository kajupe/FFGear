import bpy
import os
import logging

logging.basicConfig()
logger = logging.getLogger('FFGear.icons')
logger.setLevel(logging.INFO)

ffgear_ui_icons = None

# Color icons are handled in properties.py

def register():
    global ffgear_ui_icons
    ffgear_ui_icons = bpy.utils.previews.new()
    icons_dir = os.path.join(os.path.dirname(__file__), "assets", "ui_icons")
    logger.debug(f"Looking for icons in: {icons_dir}")
    # Load all icons (png and svg only)
    for filename in os.listdir(icons_dir):
        if filename.endswith(".png") or filename.endswith(".svg"):
            icon_name = os.path.splitext(filename)[0]
            logger.debug(f"    Loading icon: {icon_name}")
            ffgear_ui_icons.load(icon_name, os.path.join(icons_dir, filename), 'IMAGE')
    return ffgear_ui_icons

def unregister():
    global ffgear_ui_icons
    bpy.utils.previews.remove(ffgear_ui_icons)