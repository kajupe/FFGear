import bpy
import requests
import json
import os
import tempfile
import shutil
import zipfile
import sys
import subprocess
import logging

import helpers

logging.basicConfig()
logger = logging.getLogger('FFGear.auto_updating')
logger.setLevel(logging.INFO)

#¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤#
# Thank you to the Mektools development team for the basis to much of this code #
# https://github.com/MekuMaki/Mektools                                          #
#¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤#

GITHUB_USER = "kajupe"
GITHUB_REPO = "FFGear"
GITHUB_RAW_URL = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/"

# Local manifest path
extension_directory = str(__package__).split(".")[1] # example of package: bl_ext.vscode_development.FFGear (This will almost always be "user_default")
EXTENSIONS_PATH = bpy.utils.user_resource('EXTENSIONS', path=extension_directory)
FFGEAR_FOLDER = os.path.join(EXTENSIONS_PATH, "FFGear")

update_available = False  # Tracks if an update is available
update_installed = False  # Tracks if an update was successfully installed



class FFGearRestartBlender(bpy.types.Operator):
    """Restart Blender, with confirmation for unsaved changes"""
    bl_idname = "ffgear.restart_blender"
    bl_label = "Restart Blender"

    confirm_discard_changes: bpy.props.BoolProperty(
        name="Discard unsaved changes and restart",
        description="If checked, Blender will restart even if there are unsaved changes (they will be lost).",
        default=False,
    )

    # This method is called when the operator is run from the UI.
    def invoke(self, context, event):
        if bpy.data.is_dirty:
            # If the file has unsaved changes, show the confirmation dialog.
            return context.window_manager.invoke_props_dialog(self, width=350)
        else:
            # No unsaved changes, so we can proceed directly to execute.
            return self.execute(context)


    # This method is called by invoke_props_dialog to draw the contents of our confirmation dialog.
    def draw(self, context):
        layout = self.layout
        layout.label(text="The current Blender file has unsaved changes.", icon='ERROR')
        layout.label(text="Restarting will discard these changes if not saved.")
        layout.prop(self, "confirm_discard_changes")


    def execute(self, context):
        if bpy.data.is_dirty:
            if not self.confirm_discard_changes:
                self.report({'WARNING'}, "Restart cancelled. Confirmation to discard unsaved changes was not given.")
                return {'CANCELLED'}
            logger.info("User confirmed to discard unsaved changes. Proceeding with restart.")
        else:
            logger.info("No unsaved changes detected. Proceeding with restart.")

        # Get Blender executable path
        blender_exe = sys.argv[0]  # This should point to Blender's executable

        # Ensure the executable exists before proceeding
        if not os.path.exists(blender_exe):
            self.report({'ERROR'}, "Could not determine Blender executable path.")
            return {'CANCELLED'}

        # Restart Blender
        try:
            self.report({'INFO'}, "Attempting to launch new Blender instance...")
            subprocess.Popen([blender_exe])  # Launch a new Blender process
            self.report({'INFO'}, "New Blender instance launched. Closing current instance...")
            bpy.ops.wm.quit_blender()  # Close current instance.
        except Exception as e:
            self.report({'ERROR'}, f"Failed to restart Blender: {e}")
            return {'CANCELLED'}

        return {'FINISHED'}



class FFGearInstallUpdate(bpy.types.Operator):
    """Download and install the latest version of FFGear"""
    bl_idname = "ffgear.install_update"
    bl_label = "Install Update"

    def execute(self, context):
        global update_available, update_installed
        
        bpy.context.window.cursor_set('WAIT')
        
        # branch = local_manifest.get("feature_name", "main")
        branch = "main" # Maybe change this later on to allow different branches? Selectable in preferences?
        download_url = f"https://github.com/{GITHUB_USER}/{GITHUB_REPO}/archive/refs/heads/{branch}.zip"

        # Download the update ZIP file
        self.report({'INFO'}, "Downloading update...")
        try:
            response = requests.get(download_url, stream=True)
            if response.status_code != 200:
                self.report({'ERROR'}, "Failed to download update.")
                return {'CANCELLED'}
            
            # Save the file to a temporary location
            temp_dir = tempfile.mkdtemp()
            zip_path = os.path.join(temp_dir, "update.zip")

            with open(zip_path, "wb") as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
        except Exception as e:
            self.report({'ERROR'}, f"Download failed: {e}")
            return {'CANCELLED'}


        # Extract and replace the existing extension
        self.report({'INFO'}, "Installing update...")

        try:
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                extracted_folder = os.path.join(temp_dir, "ffgear_extracted")
                zip_ref.extractall(extracted_folder)

                # Locate the actual "FFGear" folder inside the extracted directory
                extracted_main_folder = os.path.join(extracted_folder, os.listdir(extracted_folder)[0])  # This is "FFGear-main"
                extracted_FFGEAR_FOLDER = os.path.join(extracted_main_folder, "FFGear")  # This is the actual extension

                # Ensure the target extension folder exists
                if not os.path.exists(FFGEAR_FOLDER):
                    os.makedirs(FFGEAR_FOLDER)

                # Remove the old version
                shutil.rmtree(FFGEAR_FOLDER, ignore_errors=True)

                # Move the inner "FFGear" folder to the correct location
                shutil.move(extracted_FFGEAR_FOLDER, FFGEAR_FOLDER)

        except Exception as e:
            self.report({'ERROR'}, f"Installation failed: {e}")
            return {'CANCELLED'}

        # Mark update as installed and reset update_available
        update_installed = True
        update_available = False  # No more updates available

        self.report({'INFO'}, "Update installed! Please restart Blender to apply changes.")
        
        bpy.context.window.cursor_set('DEFAULT')
        return {'FINISHED'}



#¤¤¤¤¤¤¤¤¤¤¤¤¤#
# Registering #
#¤¤¤¤¤¤¤¤¤¤¤¤¤#

def register():
    bpy.utils.register_class(FFGearRestartBlender)
    bpy.utils.register_class(FFGearInstallUpdate)

def unregister():
    bpy.utils.unregister_class(FFGearInstallUpdate)
    bpy.utils.unregister_class(FFGearRestartBlender)