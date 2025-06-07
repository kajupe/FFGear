import bpy
from bpy.types import AddonPreferences
from bpy.props import StringProperty, EnumProperty, BoolProperty
from . import icons
from . import helpers
from . import auto_updating

#¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤#
# DEFINITIONS
#¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤#

repo_release_url = "https://api.github.com/repos/kajupe/FFGear/releases/latest"
repo_release_download_url = "https://github.com/kajupe/FFGear/releases"
current_version = "Unknown"
latest_version = "Unknown"

#¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤#
# PREFERENCES
#¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤#

class FFGEAR_AddonPreferences(AddonPreferences):
    bl_idname = __package__

    disable_meteor_icon: BoolProperty(
        name="Disable Meteor Icon",
        description="Disables drawing the Meteor icon on the FFGear panel, in case you find it distracting",
        default=False,
    )

    disable_update_notif: BoolProperty(
        name="Disable Update Notification",
        description="Disables drawing the addon update notification on the FFGear panel, in case you find it distracting. You will still see it here in the preferences window",
        default=False,
    )

    default_meddle_import_path: StringProperty(
        name="Default Meddle Path",
        subtype='DIR_PATH',
        description="Select the default directory for the \"Auto Meddle Setup\" operator"
    )

    spheen: BoolProperty(
        name="Sphere",
        description="Queen Spheen",
        default=False,
    )
    
    def draw(self, context):
        # SETTINGS
        layout = self.layout
        box = layout.box()
        col = box.column()
        col.prop(self, "disable_meteor_icon")
        col.prop(self, "disable_update_notif")
        col.prop(self, "default_meddle_import_path")

        # INFO
        # Informational text block
        box = layout.box()
        col = box.column()
        col.label(text="How to use this addon:", icon='INFO')
        col.label(text="This addon functions best when used in conjunction with a Meddle export.")
        col.label(text="However it's still possible to use without it, just with more work.")
        col.label(text="You can find the FFGear settings in the Material Properties panel.")
        col.label(text="More in-depth instructions are on GitHub, if you need them!")
        col.label(text="Make sure your Meddle exports have cached .mtrl files!!!")
        
        # Links section
        box = layout.box()
        col = box.column()
        col.label(text="Links:", icon='URL')
        # URLs
        row = col.row()
        row.operator("wm.url_open", text="FFGear", icon_value=icons.ffgear_ui_icons["github"].icon_id).url = "https://github.com/kajupe/FFGear"
        row.operator("wm.url_open", text="Meddle", icon_value=icons.ffgear_ui_icons["github"].icon_id).url = "https://github.com/PassiveModding/Meddle"
        row.operator("wm.url_open", text="Support Me", icon_value=icons.ffgear_ui_icons["kofi"].icon_id).url = "https://ko-fi.com/kaj_em"

        # VERSION CHECK
        if latest_version != "Unknown" and current_version != "Unknown":
        # if True:
            if latest_version != current_version:
            # if True:
                box = layout.box()
                col = box.column()
                row = col.row()
                row.label(icon="ERROR", text=f"New version available: {current_version} --> {latest_version}")
                row = col.row()
                # row.operator("wm.url_open", text="Download").url = repo_release_download_url
                if not auto_updating.update_installed:
                    row.operator("ffgear.install_update", text=f"Download & Auto-install", icon="IMPORT")
                else:
                    row.operator("ffgear.restart_blender", text="Restart Blender", icon="FILE_REFRESH")
                row.operator("wm.url_open", text=f"Open GitHub Page", icon_value=icons.ffgear_ui_icons["github"].icon_id).url = "https://github.com/kajupe/FFGear/releases"
        else:
            row = layout.row()
            row.label(text="Failed to check for updates")

        row = layout.row()
        row.prop(self, "spheen")


def register():
    # VERSION CHECK (code stolen from Meddle Tools)
    global current_version
    global latest_version
    current_version, latest_version = helpers.get_addon_version_and_latest() # In other modules we can access the global variables in helpers directly instead of calling this again
    bpy.utils.register_class(FFGEAR_AddonPreferences)

def unregister():
    bpy.utils.unregister_class(FFGEAR_AddonPreferences)