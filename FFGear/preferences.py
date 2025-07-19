import bpy
from bpy.types import AddonPreferences
from bpy.props import StringProperty, EnumProperty, BoolProperty
from . import icons
from . import helpers
from . import auto_updating
import logging

logging.basicConfig()
logger = logging.getLogger('FFGear.preferences')
logger.setLevel(logging.INFO)

#¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤#
# DEFINITIONS
#¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤#

repo_release_url = "https://api.github.com/repos/kajupe/FFGear/releases/latest"
repo_release_download_url = "https://github.com/kajupe/FFGear/releases"

#¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤#
# PREFERENCES
#¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤#

class FFGEAR_AddonPreferences(AddonPreferences):
    bl_idname = __package__

    disable_update_checking: BoolProperty(
        name="Disable Update Checking",
        description="Disables update checks when the addon loads",
        default=False,
    )

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
        prefs = context.preferences.addons[__package__].preferences
        # SETTINGS
        layout = self.layout
        box = layout.box()
        col = box.column()
        col.prop(self, "disable_update_checking")
        if prefs and not prefs.disable_update_checking:
            col.prop(self, "disable_update_notif")
        col.prop(self, "disable_meteor_icon")
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
        row = col.row()
        row.operator("wm.url_open", text="Wiki", icon="HELP").url = "https://github.com/kajupe/FFGear/wiki/Guides"
        row.operator("wm.url_open", text="Support Me", icon_value=icons.ffgear_ui_icons["kofi"].icon_id).url = "https://ko-fi.com/kaj_em"

        # VERSION CHECK
        

        # Since update checking is delayed by 2s, this will be "Failed to check for updates" until that has happened.
        # So like if someone is REALLY fast and goes into preferences in 2s then they'll get incorrect information.
        # 0/10 addon literally unusable smh
        if prefs.disable_update_checking:
            pass
            logger.debug("Update checking is disabled, prefences not listing anything.")
        elif helpers.latest_version != "Unknown" and helpers.current_version != "Unknown":
            logger.debug(f"Successfully compared these non-unknown versions: latest_version={helpers.latest_version} current_version={helpers.current_version}")
            if helpers.latest_version != helpers.current_version:
                box = layout.box()
                col = box.column()
                row = col.row()
                row.label(icon="ERROR", text=f"New version available: {helpers.current_version} --> {helpers.latest_version}")
                row = col.row()
                row.operator("ffgear.install_update", text=f"Download & Auto-install", icon="IMPORT")
                row.operator("wm.url_open", text=f"Open GitHub Page", icon_value=icons.ffgear_ui_icons["github"].icon_id).url = repo_release_download_url
        else:
            row = layout.row()
            row.label(text="Failed to check for updates")

        row = layout.row()
        row.prop(self, "spheen")


def register():
    
    bpy.utils.register_class(FFGEAR_AddonPreferences)

    prefs = bpy.context.preferences.addons[__package__].preferences
    # Only run the version check if the user has NOT disabled it
    if not prefs.disable_update_checking:
        bpy.app.timers.register(helpers.get_addon_version_and_latest, first_interval=2) # 2 second delay to avoid startup instability and update crashing

def unregister():
    bpy.utils.unregister_class(FFGEAR_AddonPreferences)