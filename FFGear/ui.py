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
            if not layout:
                return
            layout.label(text="", icon_value=icons.ffgear_ui_icons["meteor"].icon_id)
        

    def draw(self, context):
        layout = self.layout
        if not layout:
            return
        material = context.material

        # Setup Box
        setup_box = layout.box()
        header_row = setup_box.row(align=True)
        header_row.prop(material.ffgear_ui, "setup_panel_open", icon="DOWNARROW_HLT" if material.ffgear_ui.setup_panel_open else "RIGHTARROW", icon_only=True, emboss=False)
        header_row.label(text="Setup:")
        
        if material.ffgear_ui.setup_panel_open:
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
                            icon_value=icons.ffgear_ui_icons["spheen"].icon_id)
            else:
                row.operator("ffgear.automaterial", 
                            text="Create This Material" if not is_created else "Reset This Material", 
                            icon='NODE_MATERIAL')

            # Normal Offset Button
            row = col.row(align=True)
            row.operator("ffgear.offset_along_normals", icon='ORIENTATION_NORMAL')



        
        # Dye Selection Box
        dye_box = layout.box()
        header_row = dye_box.row(align=True)
        header_row.prop(material.ffgear_ui, "dye_panel_open", icon="DOWNARROW_HLT" if material.ffgear_ui.dye_panel_open else "RIGHTARROW", icon_only=True, emboss=False)
        header_row.label(text="Dye Colors:")
            
        if material.ffgear_ui.dye_panel_open:
            # Warn (large) if the material was created without MTRL file (if there is a filepath then added, this goes away in favor of a smaller one at the bottom of the panel)
            if material.ffgear.created_without_mtrl and not material.ffgear.mtrl_filepath and material.ffgear.is_created:
                dye_box.label(icon="ERROR", text=f"Material Created without MTRL File!")
                col = dye_box.column(align=True)
                col.label(text=f"This material was created without access")
                col.label(text=f"to a .mtrl file. Dyeing is disabled until one is added.")
                col.label(text=f"Results may look worse than desired.")
            # If created, Warn if MTRL file goes missing
            elif not material.ffgear.mtrl_filepath and material.ffgear.is_created:
                dye_box.label(icon="ERROR", text=f"MTRL File Missing!")
                col = dye_box.column(align=True)
                col.label(text=f"Dyeing functionality requires a MTRL file!")
                col.label(text=f"You can select one in the above panel.")

            # Show dyes before creation (because that can speed up creation and looks nice to new users) or when it IS created and has a MTRL filepath
            if material.ffgear.mtrl_filepath or not material.ffgear.is_created:
                col = dye_box.column(align=True)
                col.prop(material.ffgear, "dye_1")
                col.prop(material.ffgear, "dye_2")

            if material.ffgear.is_created:
                col.separator()
                # Update Buttons, Linking, Etc.
                if material.ffgear.mtrl_filepath:
                    row = col.row(align=True)
                    row.operator("ffgear.get_meddle_dyes", icon='EYEDROPPER', text="")
                    row.operator("ffgear.update_dyed_ramps", icon='FILE_REFRESH', text="Update Color Ramps")
                    current_auto_dye_status = material.ffgear.get("auto_update_dyes", True)
                    row.prop(material.ffgear, "auto_update_dyes", icon_value=icons.ffgear_ui_icons["auto_on"].icon_id if current_auto_dye_status else icons.ffgear_ui_icons["auto_off"].icon_id, text="")
                    current_link_dyes_status = material.ffgear.get("link_dyes", True)
                    row.prop(material.ffgear, "link_dyes", icon='DECORATE_LINKED' if current_link_dyes_status else 'UNLINKED', text="")
                # Use Meddle Color Data
                if material.ffgear.is_created:
                    row = col.row(align=True)
                    row.operator("ffgear.use_meddle_color_data", text="Load Colorset from Meddle")

                # Linked Materials panel
                linked_materials = material.ffgear.linked_materials
                num_linked_materials = len(linked_materials)
                if material.ffgear.link_dyes and not material.ffgear.created_without_mtrl:
                    linked_mat_box = dye_box.box()
                    linked_mat_box.label(icon="DECORATE_LINKED" if num_linked_materials > 0 else "UNLINKED", text="Linked To:")
                    col = linked_mat_box.column(align=True)
                    
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


        # Warnings
        any_warning = ((material.ffgear_warnings.created_without_mtrl and material.ffgear.mtrl_filepath) or
                       material.ffgear_warnings.stocking_uncertain_textures or
                       material.ffgear_warnings.stocking_missing_textures)
        
        if any_warning:
            warning_box = layout.box()
            header_row = warning_box.row(align=True)
            header_row.prop(material.ffgear_ui, "warnings_panel_open", icon="DOWNARROW_HLT" if material.ffgear_ui.warnings_panel_open else "RIGHTARROW", icon_only=True, emboss=False)
            header_row.label(text="Warnings (hover to read, click to dismiss):" if material.ffgear_ui.warnings_panel_open else "Warnings:")

            if material.ffgear_ui.warnings_panel_open:
                # Created Without MTRL File warning
                if material.ffgear_warnings.created_without_mtrl and material.ffgear.mtrl_filepath: # Also require a mtrl_filepath because without it, this warning already exists in the Dye section
                    row = warning_box.row(align=True)
                    row.alignment = 'LEFT'
                    row.prop(material.ffgear_warnings, "created_without_mtrl", icon='ERROR', emboss=False)
                    row.prop(material.ffgear_warnings, "created_without_mtrl", emboss=False, icon='BLANK1', icon_only=True)
                # Stocking uncertain
                if material.ffgear_warnings.stocking_uncertain_textures:
                    row = warning_box.row(align=True)
                    row.alignment = 'LEFT'
                    row.prop(material.ffgear_warnings, "stocking_uncertain_textures", icon='ERROR', emboss=False)
                    row.prop(material.ffgear_warnings, "stocking_uncertain_textures", emboss=False, icon='BLANK1', icon_only=True)
                # Stocking missing
                if material.ffgear_warnings.stocking_missing_textures:
                    row = warning_box.row(align=True)
                    row.alignment = 'LEFT'
                    row.prop(material.ffgear_warnings, "stocking_missing_textures", icon='ERROR', emboss=False)
                    row.prop(material.ffgear_warnings, "stocking_missing_textures", emboss=False, icon='BLANK1', icon_only=True)


        # Update Notification
        latest_name = helpers.latest_version_name
        if self.prefs and not self.prefs.disable_update_checking and not self.prefs.disable_update_notif:
            if helpers.current_version != helpers.latest_version and helpers.current_version != "Unknown" and helpers.latest_version != "Unknown":
                box = layout.box()
                box.label(icon="ERROR", text=f"A new update to FFGear is available!")
                col = box.column(align=True)
                col.label(text=f"Installed: {helpers.current_version}")
                col.label(text=f"Latest:      {helpers.latest_version}")
                col.label(text=f"{latest_name}")
                col = box.column()
                row = col.row(align=False)
                row.operator("ffgear.install_update", text=f"Download & Auto-install", icon="IMPORT")
                row.operator("wm.url_open", text=f"Open GitHub Page", icon_value=icons.ffgear_ui_icons["github"].icon_id).url = "https://github.com/kajupe/FFGear/releases"
            


def register():
    bpy.utils.register_class(FFGearMaterialPanel)

def unregister():
    bpy.utils.unregister_class(FFGearMaterialPanel)