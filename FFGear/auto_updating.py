import bpy
import requests
import os
import tempfile
import logging

logging.basicConfig()
logger = logging.getLogger('FFGear.auto_updating')
logger.setLevel(logging.INFO)

#¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤#
# Thank you to ShinoMythmaker for giving me tips on how to set this up #
# https://github.com/Shinokage107                                      #
#¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤#

GITHUB_USER = "kajupe"
GITHUB_REPO = "FFGear"
GITHUB_BRANCH = "main"
GITHUB_RAW_URL = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/"

# Local manifest path
extension_directory = str(__package__).split(".")[1] # example of package: bl_ext.vscode_development.FFGear (This will almost always be "user_default")
EXTENSIONS_PATH = bpy.utils.user_resource('EXTENSIONS', path=extension_directory)
FFGEAR_FOLDER = os.path.join(EXTENSIONS_PATH, "FFGear")

update_available = False  # Tracks if an update is available
update_installed = False  # Tracks if an update was successfully installed



#¤¤¤¤¤¤¤¤¤¤¤#
# Functions #
#¤¤¤¤¤¤¤¤¤¤¤#

def get_github_download_url(user, repo, branch):
    """Return the path to a github zip file"""
    return f"https://github.com/{user}/{repo}/archive/refs/heads/{branch}.zip"


def download_addon(url: str, name: str = "download") -> str:
    """Download the selected branch from GitHub and return the ZIP path."""
    temp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(temp_dir, f"{name}.zip")

    try:
        response = requests.get(url, stream=True)
        if response.status_code != 200:
            logger.error(f"Failed to download {url}.")
            return None

        with open(zip_path, 'wb') as zip_file:
            zip_file.write(response.content)

    except Exception as e:
        logger.exception(f"Download error: {e}")
        return None

    return zip_path



#¤¤¤¤¤¤¤¤¤¤¤#
# Operators #
#¤¤¤¤¤¤¤¤¤¤¤#

class FFGearInstallUpdate(bpy.types.Operator):
    """Download and install the latest version of FFGear"""
    bl_idname = "ffgear.install_update"
    bl_label = "Install Update"
    bl_options = {'REGISTER', 'UNDO'}

    proceed_anyways: bpy.props.BoolProperty(
        name="Proceed anyways",
        description="If checked, Blender will attempt the update even if there are unsaved changes (they may be lost if the update crashes).",
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
        layout.label(text="It is recommended that you save before updating, just in case.")
        layout.prop(self, "proceed_anyways")


    def execute(self, context):
        if bpy.data.is_dirty:
            if not self.proceed_anyways:
                self.report({'WARNING'}, "Update cancelled. Confirmation to proceed was not given.")
                return {'CANCELLED'}
            logger.info("User confirmed to proceed with unsaved changes. Proceeding with update.")
        else:
            logger.info("No unsaved changes detected. Proceeding with update.")
        
        global update_available, update_installed

        # Spinny Cursor
        context.window.cursor_set('WAIT')

        try:
            url = get_github_download_url(GITHUB_USER, GITHUB_REPO, GITHUB_BRANCH)
            self.report({'INFO'}, "Downloading update...")
            zip = download_addon(url, GITHUB_REPO)
            
            if zip == None:
                self.report({'ERROR'}, f"Failed to download {GITHUB_REPO}.")
                return {'CANCELLED'}

            try:
                self.report({'INFO'}, "Installing update...")
                bpy.ops.extensions.package_install_files(directory=EXTENSIONS_PATH, filepath=zip, repo=extension_directory, url=url)
                # self.report({'INFO'}, f"Installed {GITHUB_REPO}.")
                update_installed = True
                update_available = False
            except Exception as e:
                error_message = f"Failed to install {GITHUB_REPO}. Error: {str(e)}"
                self.report({'ERROR'}, error_message)
                return {'CANCELLED'}
            
            return {'FINISHED'}
        finally:
            context.window.cursor_set('DEFAULT')



#¤¤¤¤¤¤¤¤¤¤¤¤¤#
# Registering #
#¤¤¤¤¤¤¤¤¤¤¤¤¤#

def register():
    bpy.utils.register_class(FFGearInstallUpdate)

def unregister():
    bpy.utils.unregister_class(FFGearInstallUpdate)