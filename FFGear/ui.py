import bpy
from . import icons
from . import helpers
from . import auto_updating

class FFGearMaterialPanel(bpy.types.Panel):
    """FFGear Material Panel"""
    bl_label = "FFGear"
    bl_idname = "MATERIAL_PT_ffgear"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "material"
    bl_options = {'DEFAULT_CLOSED'}


    @property
    def prefs(self):
        # __package__ is "bl_ext.user_default.FFGear"
        return bpy.context.preferences.addons[__package__].preferences


    @classmethod
    def poll(cls, context):
        return context.material is not None


    def draw_header(self, context):
        if self.prefs and not self.prefs.disable_meteor_icon:
            layout = self.layout
            layout.label(text="", icon_value=icons.ffgear_ui_icons["meteor"].icon_id)
        

    def draw(self, context):
        layout = self.layout
        material = context.material

        # Setup Box
        setup_box = layout.box()
        setup_box.label(text="Setup:")
        
        setup_box.operator("ffgear.meddle_setup", icon='MATERIAL', text="Automatic Meddle Setup")

        # MTRL file selection with Fetch button
        col = setup_box.column(align=True)
        row = col.row(align=True)
        row.prop(material.ffgear, "mtrl_filepath", text="MTRL File")
        row.operator("ffgear.open_mtrl_browser", text="", icon='FILE_FOLDER')

        # Texture file selection (grouped together)
        col = setup_box.column(align=True)
        
        row = col.row(align=True)
        row.prop(material.ffgear, "diffuse_filepath", text="Diffuse Texture")
        row.operator("ffgear.open_diffuse_browser", text="", icon='FILE_FOLDER')
        
        row = col.row(align=True)
        row.prop(material.ffgear, "mask_filepath", text="Mask Texture")
        row.operator("ffgear.open_mask_browser", text="", icon='FILE_FOLDER')
        
        row = col.row(align=True)
        row.prop(material.ffgear, "normal_filepath", text="Normal Texture")
        row.operator("ffgear.open_normal_browser", text="", icon='FILE_FOLDER')

        row = col.row(align=True)
        row.prop(material.ffgear, "id_filepath", text="ID Texture")
        row.operator("ffgear.open_id_browser", text="", icon='FILE_FOLDER')

        # Fetch Textures Buttons
        row = col.row(align=True)
        if material.ffgear.mtrl_filepath:
            row.operator("ffgear.fetch_mtrl_textures", text="Fetch Textures from MTRL", icon='VIEWZOOM')
        row.operator("ffgear.fetch_meddle_textures", text="Fetch Textures from Meddle", icon='VIEWZOOM')
        row.operator("ffgear.copy_texture_paths", text="", icon='COPYDOWN')
        
        # Add some space
        setup_box.separator(factor=0.25)
        
        # Auto-material Buttons
        col = setup_box.column(align=True)
        row = col.row(align=True)
        is_created = material.ffgear.get("is_created", False)
        # Swaps the entire button since I can't swap between using icon and icon_value apparently
        if self.prefs.spheen:
            row.operator("ffgear.automaterial", 
                        text="Create This Material" if not is_created else "Reset This Material", 
                        icon_value=icons.ffgear_ui_icons["spheen"].icon_id if self.prefs.spheen else 0)
        else:
            row.operator("ffgear.automaterial", 
                        text="Create This Material" if not is_created else "Reset This Material", 
                        icon='NODE_MATERIAL')


        # Dye Selection Box
        box = layout.box()
        box.label(text="Dye Colors:")
        
        col = box.column(align=True)
        col.prop(material.ffgear, "dye_1")
        col.prop(material.ffgear, "dye_2")

        # Add update buttons if MTRL file is selected
        if material.ffgear.mtrl_filepath:
            col.separator()
            row = col.row(align=True)
            row.operator("ffgear.get_meddle_dyes", icon='EYEDROPPER', text="")
            row.operator("ffgear.update_dyed_ramps", icon='FILE_REFRESH', text="Update Color Ramps")
            current_auto_dye_status = material.ffgear.get("auto_update_dyes", True)
            row.prop(material.ffgear, "auto_update_dyes", icon_value=icons.ffgear_ui_icons["auto_on"].icon_id if current_auto_dye_status else icons.ffgear_ui_icons["auto_off"].icon_id, text="")
            current_link_dyes_status = material.ffgear.get("link_dyes", True)
            row.prop(material.ffgear, "link_dyes", icon='DECORATE_LINKED' if current_link_dyes_status else 'UNLINKED', text="")

        # Linked Materials panel (test)
        linked_materials = material.ffgear.linked_materials
        num_linked_materials = len(linked_materials)
        if material.ffgear.link_dyes and material.ffgear.is_created:
            box = layout.box()
            box.label(icon="DECORATE_LINKED" if num_linked_materials > 0 else "UNLINKED", text="Linked To:")
            col = box.column(align=True)
            
            if num_linked_materials > 0:
                for item in material.ffgear.linked_materials:
                    if isinstance(item.mat, bpy.types.Material):
                        col.label(text="        "+item.mat.name)
                    else:
                        col.label(text="        A missing material!")
            else:
                col.label(text='        None :(')
                col.label(text='        Links can only be established between')
                col.label(text='        variants of the same material like "_a_" and "_b_"')

        # Update Notification
        current = helpers.current_version
        latest = helpers.latest_version
        latest_name = helpers.latest_version_name
        if self.prefs and not self.prefs.disable_update_notif and current != latest and current != "Unknown" and latest != "Unknown":
        # if True:
            box = layout.box()
            box.label(icon="ERROR", text=f"A new update to FFGear is available!")
            col = box.column(align=True)
            col.label(text=f"Installed: {current}")
            col.label(text=f"Latest:      {latest}")
            col.label(text=f"{latest_name}")
            col = box.column()
            row = col.row(align=False)
            if not auto_updating.update_installed:
                row.operator("ffgear.install_update", text=f"Download & Auto-install", icon="IMPORT")
            else:
                row.operator("ffgear.restart_blender", text="Restart Blender", icon="FILE_REFRESH")
            row.operator("wm.url_open", text=f"Open GitHub Page", icon_value=icons.ffgear_ui_icons["github"].icon_id).url = "https://github.com/kajupe/FFGear/releases"
            


def register():
    bpy.utils.register_class(FFGearMaterialPanel)

def unregister():
    bpy.utils.unregister_class(FFGearMaterialPanel)