import bpy
import os
import logging
from bpy.props import StringProperty, EnumProperty, PointerProperty, BoolProperty, CollectionProperty
from bpy.types import PropertyGroup, Material
import bpy.utils.previews
from . import helpers
from . import operators

logging.basicConfig()
logger = logging.getLogger('FFGear.properties')
logger.setLevel(logging.INFO)


#¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤#
# ICON STUFF
#¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤#

# Custom Dye Icons will be stored here
preview_collections = {}

def get_dye_items(self, context):
    """Get dye items WITH CUSTOM ICONS"""
    items = []
    pcoll = preview_collections.get("dye_icons")
    if pcoll is None:
        # Fallback items if icons aren't loaded (I do not remember why it has two more things than the ones below)
        return [('0', "No Color", "Default color, no dye applied", "MATERIAL", 0)]

    dyes = [
        ('0', 'No Color', 'Default color, no dye applied'),
        ('1', 'Snow White', ''),
        ('2', 'Ash Grey', ''),
        ('3', 'Goobbue Grey', ''),
        ('4', 'Slate Grey', ''),
        ('5', 'Charcoal Grey', ''),
        ('6', 'Soot Black', ''),
        ('7', 'Rose Pink', ''),
        ('8', 'Lilac Purple', ''),
        ('9', 'Rolanberry Red', ''),
        ('10', 'Dalamud Red', ''),
        ('11', 'Rust Red', ''),
        ('12', 'Wine Red', ''),
        ('13', 'Coral Pink', ''),
        ('14', 'Blood Red', ''),
        ('15', 'Salmon Pink', ''),
        ('16', 'Sunset Orange', ''),
        ('17', 'Mesa Red', ''),
        ('18', 'Bark Brown', ''),
        ('19', 'Chocolate Brown', ''),
        ('20', 'Russet Brown', ''),
        ('21', 'Kobold Brown', ''),
        ('22', 'Cork Brown', ''),
        ('23', 'Qiqirn Brown', ''),
        ('24', 'Opo-opo Brown', ''),
        ('25', 'Aldgoat Brown', ''),
        ('26', 'Pumpkin Orange', ''),
        ('27', 'Acorn Brown', ''),
        ('28', 'Orchard Brown', ''),
        ('29', 'Chestnut Brown', ''),
        ('30', 'Gobbiebag Brown', ''),
        ('31', 'Shale Brown', ''),
        ('32', 'Mole Brown', ''),
        ('33', 'Loam Brown', ''),
        ('34', 'Bone White', ''),
        ('35', 'Ul Brown', ''),
        ('36', 'Desert Yellow', ''),
        ('37', 'Honey Yellow', ''),
        ('38', 'Millioncorn Yellow', ''),
        ('39', 'Coeurl Yellow', ''),
        ('40', 'Cream Yellow', ''),
        ('41', 'Halatali Yellow', ''),
        ('42', 'Raisin Brown', ''),
        ('43', 'Mud Green', ''),
        ('44', 'Sylph Green', ''),
        ('45', 'Lime Green', ''),
        ('46', 'Moss Green', ''),
        ('47', 'Meadow Green', ''),
        ('48', 'Olive Green', ''),
        ('49', 'Marsh Green', ''),
        ('50', 'Apple Green', ''),
        ('51', 'Cactuar Green', ''),
        ('52', 'Hunter Green', ''),
        ('53', 'Ochu Green', ''),
        ('54', 'Adamantoise Green', ''),
        ('55', 'Nophica Green', ''),
        ('56', 'Deepwood Green', ''),
        ('57', 'Celeste Green', ''),
        ('58', 'Turquoise Green', ''),
        ('59', 'Morbol Green', ''),
        ('60', 'Ice Blue', ''),
        ('61', 'Sky Blue', ''),
        ('62', 'Seafog Blue', ''),
        ('63', 'Peacock Blue', ''),
        ('64', 'Rhotano Blue', ''),
        ('65', 'Corpse Blue', ''),
        ('66', 'Ceruleum Blue', ''),
        ('67', 'Woad Blue', ''),
        ('68', 'Ink Blue', ''),
        ('69', 'Raptor Blue', ''),
        ('70', 'Othard Blue', ''),
        ('71', 'Storm Blue', ''),
        ('72', 'Void Blue', ''),
        ('73', 'Royal Blue', ''),
        ('74', 'Midnight Blue', ''),
        ('75', 'Shadow Blue', ''),
        ('76', 'Abyssal Blue', ''),
        ('77', 'Lavender Purple', ''),
        ('78', 'Gloom Purple', ''),
        ('79', 'Currant Purple', ''),
        ('80', 'Iris Purple', ''),
        ('81', 'Grape Purple', ''),
        ('82', 'Lotus Pink', ''),
        ('83', 'Colibri Pink', ''),
        ('84', 'Plum Purple', ''),
        ('85', 'Regal Purple', ''),
        ('86', 'Ruby Red', ''),
        ('87', 'Cherry Pink', ''),
        ('88', 'Canary Yellow', ''),
        ('89', 'Vanilla Yellow', ''),
        ('90', 'Dragoon Blue', ''),
        ('91', 'Turquoise Blue', ''),
        ('92', 'Gunmetal Black', ''),
        ('93', 'Pearl White', ''),
        ('94', 'Metallic Brass', ''),
        ('95', 'Carmine Red', ''),
        ('96', 'Neon Pink', ''),
        ('97', 'Bright Orange', ''),
        ('98', 'Neon Yellow', ''),
        ('99', 'Neon Green ', ''),
        ('100', 'Azure Blue', ''),
        ('101', 'Pure White', ''),
        ('102', 'Jet Black', ''),
        ('103', 'Pastel Pink', ''),
        ('104', 'Dark Red', ''),
        ('105', 'Dark Brown', ''),
        ('106', 'Pastel Green', ''),
        ('107', 'Dark Green', ''),
        ('108', 'Pastel Blue', ''),
        ('109', 'Dark Blue', ''),
        ('110', 'Pastel Purple', ''),
        ('111', 'Dark Purple', ''),
        ('112', 'Metallic Silver', ''),
        ('113', 'Metallic Gold', ''),
        ('114', 'Metallic Red', ''),
        ('115', 'Metallic Orange', ''),
        ('116', 'Metallic Yellow', ''),
        ('117', 'Metallic Green', ''),
        ('118', 'Metallic Sky Blue', ''),
        ('119', 'Metallic Blue', ''),
        ('120', 'Metallic Purple', ''),
        ('121', 'Violet Purple', ''),
        ('122', 'Metallic Pink ', ''),
        ('123', 'Metallic Ruby Red ', ''),
        ('124', 'Metallic Cobalt Green', ''),
        ('125', 'Metallic Dark Blue', '')
    ]

    # Create items with custom icons
    for identifier, name, description in dyes:
        # Get icon or fallback to default
        icon_id = pcoll.get(name, pcoll.get("No Color")).icon_id
        items.append((identifier, name, description, icon_id, int(identifier)))
    
    return items



#¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤#
# DYE LINKING STUFF
#¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤#

# Flag to prevent infinite recursion when synchronizing link_dyes state
_is_synchronizing_links = False
_is_synchronizing_autodye = False
_is_synchronizing_selected_dyes = False

class LinkedMaterialItem(PropertyGroup):
    """An item in the list of linked materials."""
    mat: PointerProperty(
        name="Material",
        type=Material,
        description="A material linked via the FFGear properties"
    )


# ============================ #
# collect_linked_materials function for synchronized lists
# ============================ #
def collect_linked_materials_updatefunction(self, context):
    """
    Update function for the 'link_dyes' BoolProperty.
    
    This just calls the core collect_linked_materials function using the triggering material in self.id_data
    """
    logger.debug("FUNCTION CALL: collect_linked_materials")
    global _is_synchronizing_links
    if _is_synchronizing_links:
        # Prevent recursive calls triggered by setting link_dyes on partners
        logger.debug("Skipping recursive collect_linked_materials_updatefunction call.")
        return

    # 'self' here refers to the FFGearMaterialProperties instance
    triggering_mat = self.id_data
    if not isinstance(triggering_mat, Material):
         return

    collect_linked_materials(triggering_mat)


def collect_linked_materials(source_material):
    """
    Finds related materials and synchronizes the 'linked_materials' list
    across all members of the group. If link_dyes is False this dissolves the group.
    """

    # Use a flag to prevent recursion within this call stack (not used in this function but in the updatefunction)
    global _is_synchronizing_links
    _is_synchronizing_links = True
    try:
        if source_material.ffgear.link_dyes:
            # --- Link Dyes Turned ON ---
            triggering_auto_dye_status = source_material.ffgear.auto_update_dyes
            initial_dye_1 = source_material.ffgear.dye_1
            initial_dye_2 = source_material.ffgear.dye_2
            partners = set()
            # Find potential partners based on the filter criteria
            for mat in bpy.data.materials:
                if mat != source_material and hasattr(mat, 'ffgear') and mat.ffgear.is_created:
                    if helpers.compare_strings_for_one_difference(source_material.name, mat.name):
                        partners.add(mat)

            if len(partners) == 0:
                logger.debug(f"No other materials matching criteria to be linked to {source_material.name}, returning early.")
                return

            # Define the full group (including the triggering material)
            full_group = partners.union({source_material})
            logger.debug(f"  Found group: {[m.name for m in full_group]}")

            # Synchronize lists and link_dyes state across the entire group
            for member_mat in full_group:

                member_props = member_mat.ffgear
                other_members = full_group - {member_mat} # All members except the current one

                # Update the linked_materials list for this member
                member_props.linked_materials.clear()
                for other in other_members:
                    item = member_props.linked_materials.add()
                    item.mat = other

                # Copy dyes initially
                if member_props.dye_1 != initial_dye_1:
                    member_props.dye_1 = initial_dye_1
                if member_props.dye_2 != initial_dye_2:
                    member_props.dye_2 = initial_dye_2

                # Ensure link_dyes is True for all members of the active group
                # This assignment might trigger this update function again,
                # but the _is_synchronizing_links flag should prevent recursion.
                if not member_props.link_dyes:
                     member_props.link_dyes = True

                # Set the auto_update setting to whatever the triggering material had
                # This works
                if member_props.auto_update_dyes != triggering_auto_dye_status:
                    member_props.auto_update_dyes = triggering_auto_dye_status


        else:
            # --- Link Dyes Turned OFF ---
            # Identify the group members from the current list before clearing it
            old_partners = {item.mat for item in source_material.ffgear.linked_materials if item.mat}
            if len(old_partners) == 0:
                logger.debug(f"Link Dyes turned off for {source_material.name} but it had no linked materials, no action needed, returning early.")
                return
            full_old_group = old_partners.union({source_material})
            logger.debug(f"  Dissolving group: {[m.name for m in full_old_group]}")

            # Clear lists and set link_dyes to False for all former members
            for member_mat in full_old_group:
                 # MODIFICATION: Check ffgear exists
                 if member_mat and hasattr(member_mat, 'ffgear') and member_mat.ffgear:
                    member_props = member_mat.ffgear
                    member_props.linked_materials.clear()
                    # Set link_dyes to False. This might trigger this update function
                    # again, but the flag will prevent recursion, and the logic
                    # for link_dyes=False will just confirm the list is empty.
                    if member_props.link_dyes: # Avoid unnecessary updates
                        member_props.link_dyes = False # Triggers update, guarded by flag

    finally:
        # Ensure the flag is always reset, even if errors occur
        _is_synchronizing_links = False


# ============================ #
# sync_dyes_in_group, for making sure the selected dyes are the same
# ============================ #
def sync_dyes_in_group(self, context):
    """
    Update function for dye EnumProperties (dye_1, dye_2).
        Synchronizes the changed dye value to all materials in the linked group.
        If self.auto_update_dyes is True, triggers ramp updates for the whole group.
    """
    logger.debug("FUNCTION CALL: sync_dyes_in_group")
    triggering_props = self
    triggering_mat = triggering_props.id_data
    triggering_created_status = triggering_props.is_created
        
    # Skip faulty cases
    if not triggering_created_status:
        logger.debug("sync_dyes_in_group triggered but material is not set as having been created. returning early.")
        return
    if not isinstance(triggering_mat, Material):
        logger.warning(f"sync_dyes_in_group was (somehow) provided a non-material: {triggering_mat}")
        return

    is_linked = triggering_props.link_dyes and len(triggering_props.linked_materials) > 0

    # --- Step 1: Synchronize Dyes (if linked) ---
    if is_linked:
        # If a material is forcibly deleted this function breaks, we check for that here first
        for item in triggering_props.linked_materials:
            if not isinstance(item.mat, Material):
                logger.warning(f"An item among the linked materials of {triggering_mat.name} did not contain a material. An attempt to filter it out will be made. Dyeing might behave unexpectedly.")
        safe_group_of_material_items = [item for item in triggering_props.linked_materials if isinstance(item.mat, Material)]
        print(f"safe_group: {safe_group_of_material_items}")


        logger.debug(f"Syncing dye values in this group: {[item.mat.name for item in safe_group_of_material_items]}")
        global _is_synchronizing_selected_dyes
        _is_synchronizing_selected_dyes = True # Disallow ramp updates down in handle_auto_update_toggle
        new_dye_1 = triggering_props.dye_1
        new_dye_2 = triggering_props.dye_2
        updated_dye_count = 0
        internal_sync_is_ongoing = None # Used to ensure that the _is_synchronizing_selected_dyes isn't turned off when updating dye 1 re-triggers this function
                                        # This could potentially be replaced with a check like the other ones have but this seems to work for now

        for item in safe_group_of_material_items:
            member_mat = item.mat
            if member_mat and hasattr(member_mat, 'ffgear') and member_mat.ffgear: # The second check is for if the attribute exists but is None
                member_props = member_mat.ffgear
                dye1_changed = member_props.dye_1 != new_dye_1
                dye2_changed = member_props.dye_2 != new_dye_2

                if dye1_changed or dye2_changed:
                    # Prevent loops by disabling the partner's auto_update temporarily
                    # Note: We disable auto_update_dyes, not link_dyes
                    original_auto_update_flag = member_props.auto_update_dyes
                    member_props.auto_update_dyes = False
                    try:
                        internal_sync_is_ongoing = True
                        if dye1_changed: member_props.dye_1 = new_dye_1 # Triggers sync_dyes_in_group on member (but should return early)
                        if dye2_changed: member_props.dye_2 = new_dye_2 # Triggers sync_dyes_in_group on member (but should return early)
                    finally:
                        # Ensure flag is restored even if update fails
                        member_props.auto_update_dyes = original_auto_update_flag # This line will try to update the dyes again but won't because of the flag on the line below
                        internal_sync_is_ongoing = False # It has ended, we updated both dye values
                    updated_dye_count += 1

        if not internal_sync_is_ongoing and internal_sync_is_ongoing != None:
            _is_synchronizing_selected_dyes = False # Allows ramp updates in handle_auto_update_toggle again


    # --- Step 2: Update Ramps (if auto_update_dyes is True on trigger) ---
    if triggering_props.auto_update_dyes:
        logger.debug(f"FFGear: Auto Update Dyes is ON for {triggering_mat.name}. Triggering ramp updates...")
        # Determine the full group to update ramps for
        if is_linked:
            group_to_update = {triggering_mat}.union({item.mat for item in safe_group_of_material_items if item.mat})
        else:
            group_to_update = {triggering_mat} # Only update the triggering material if not linked

        logger.debug(f"  Updating ramps for group: {[m.name for m in group_to_update]}")
        for mat_to_update in group_to_update:
            if mat_to_update: # Ensure material exists
                 # Call the operator responsible for updating ramps for a single material
                 # We assume the operator uses context or needs the material name.
                 # Pass material name for clarity if operator supports it.
                 logger.debug(f"    Calling ramp update operator for: {mat_to_update.name}")
                 try:
                     # Example: Pass material name if operator accepts it
                     operators.FFGearUpdateDyedRamps.perform_update_on_material(mat_to_update, hard_reset=False)
                 except Exception as e:
                     # Operator might not exist or failed
                     logger.warning(f"    Warning: Failed to call 'ffgear.update_dyed_ramps' for {mat_to_update.name}. Error: {e}")
                     # Fallback or alternative update method could go here if needed
    else: # Debug
        logger.debug(f"FFGear: Auto Update Dyes is OFF for {triggering_mat.name}. Skipping ramp updates.")


# ============================ #
# Update handler for the auto_update_dyes toggle itself
# ============================ #
def handle_auto_update_toggle(self, context):
    """
    Update function for the 'auto_update_dyes' BoolProperty.
    If toggled ON, triggers a ramp update for the material and its linked group.
    If linking is enabled, syncs the 'auto_update_dyes' property across the other materials.
    """
    logger.debug("FUNCTION CALL: handle_auto_update_toggle")
    global _is_synchronizing_autodye
    if _is_synchronizing_autodye or _is_synchronizing_selected_dyes:
        # Prevent recursive calls triggered by setting auto_update_dyes on partners
        # Not sure if this is needed here anymore but I had an issue with it before so it stays. Can't hurt.
        # The selected dyes check though IS needed or it will preemptively update ramps when syncing those values and re-enabling auto_update_dyes
        return
    
    _is_synchronizing_autodye = True
    try:
        # Get data
        triggering_props = self
        triggering_mat = triggering_props.id_data
        triggering_auto_dye_status = triggering_props.auto_update_dyes
        triggering_created_status = triggering_props.is_created
        
        # Skip faulty cases
        if not triggering_created_status:
            logger.debug("handle_auto_update_toggle triggered but material is not set as having been created. returning early.")
            return
        if not isinstance(triggering_mat, Material):
            return
        
        is_linked = triggering_props.link_dyes and len(triggering_props.linked_materials) > 0
        if is_linked:
            other_mats = {item.mat for item in triggering_props.linked_materials if item.mat}
            group_to_update = {triggering_mat}.union(other_mats)
        else:
            other_mats = {}
            group_to_update = {triggering_mat}

        # Sync auto_update_dyes
        for other_mat in other_mats:
            if other_mat.ffgear.auto_update_dyes != triggering_auto_dye_status:
                other_mat.ffgear.auto_update_dyes = triggering_auto_dye_status

        # Cause a ramp update
        if triggering_props.auto_update_dyes:
            logger.debug(f"Auto Update Dyes toggled ON for {triggering_mat.name}. Triggering ramp update for group.")
            logger.debug(f"  Updating ramps for group: {[m.name for m in group_to_update]}")
            for mat_to_update in group_to_update:
                if mat_to_update:
                    logger.debug(f"    Calling ramp update operator for: {mat_to_update.name}")
                    operators.FFGearUpdateDyedRamps.perform_update_on_material(mat_to_update, hard_reset=False)

    except Exception as e:
        logger.exception(f"Error in handle_auto_update_toggle: {e}")
    finally:
        _is_synchronizing_autodye = False



#¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤#
# PROPERTIES
#¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤#

# Properties that live on the material
class FFGearMaterialProperties(bpy.types.PropertyGroup):
    """Property group for storing FFGear material data"""
    
    is_created: BoolProperty(
        name="Is Created",
        description="Whether this material has been created by FFGear",
        default=False
    )

    created_without_mtrl: BoolProperty(
        name="Created Without MTRL",
        description="Whether this material was created using false mtrl data or not",
        default=False
    )
    
    mtrl_filepath: StringProperty(
        name="MTRL File",
        description="Path to the MTRL file containing material data",
        default=""
    )
    
    diffuse_filepath: StringProperty(
        name="Diffuse Texture",
        description="Path to the (VERY OPTIONAL) Diffuse texture file",
        default=""
    )

    id_filepath: StringProperty(
        name="ID Texture",
        description="Path to the ID texture file",
        default=""
    )
    
    mask_filepath: StringProperty(
        name="Mask Texture",
        description="Path to the mask texture file",
        default=""
    )
    
    normal_filepath: StringProperty(
        name="Normal Texture",
        description="Path to the normal map texture file",
        default=""
    )

    template_type: bpy.props.EnumProperty(
        name="Template Type",
        description="Detected template type for this material",
        items=[
            ('ENDWALKER', "Endwalker", "Endwalker template format"),
            ('DAWNTRAIL', "Dawntrail", "Dawntrail template format")
        ],
        default='DAWNTRAIL'
    )

    is_legacy_shader: BoolProperty(
        name="Legacy Shader",
        description="Whether this material uses the legacy character shader",
        default=False
    )

    dye_1: EnumProperty(
        name="Channel 1",
        description="Primary dye color for the material",
        items=get_dye_items,
        default=0,
        update=sync_dyes_in_group
    )
    
    dye_2: EnumProperty(
        name="Channel 2",
        description="Secondary dye color for the material",
        items=get_dye_items,
        default=0,
        update=sync_dyes_in_group
    )

    auto_update_dyes: BoolProperty(
        name="Auto Update Dyes",
        description="Automatically recalculate the material's color ramps when either of the dyes are changed",
        default=True,
        update=handle_auto_update_toggle
    )

    link_dyes: BoolProperty(
        name="Link Dyes",
        description='Automatically set the dyes of variants to this object (such as "_a_" and "_b_") to the same as this material\'s.\nToggle this to re-do the search',
        default=True,
        update=collect_linked_materials_updatefunction
    )

    linked_materials: CollectionProperty(
        type=LinkedMaterialItem,
        name="Linked Materials",
        description="Materials whose dyes are linked to this one"
    )

def register():
    global preview_collections

    # Create new preview collection
    pcoll = bpy.utils.previews.new()
    
    # Path to dye icons folder
    icons_dir = os.path.join(os.path.dirname(__file__), "assets", "dye_icons")
    
    # Load all icons
    for filename in os.listdir(icons_dir):
        if filename.endswith(".png"):
            icon_name = os.path.splitext(filename)[0]
            pcoll.load(icon_name, os.path.join(icons_dir, filename), 'IMAGE')
    
    preview_collections["dye_icons"] = pcoll

    # Register classes and whatnot
    bpy.utils.register_class(LinkedMaterialItem)
    bpy.utils.register_class(FFGearMaterialProperties)
    bpy.types.Material.ffgear = PointerProperty(type=FFGearMaterialProperties)

def unregister():
    global preview_collections
    
    # Remove preview collection
    for pcoll in preview_collections.values():
        bpy.utils.previews.remove(pcoll)
    preview_collections.clear()
    
    # Unregister classes
    if hasattr(bpy.types.Material, 'ffgear'):
        del bpy.types.Material.ffgear
    bpy.utils.unregister_class(FFGearMaterialProperties)
    bpy.utils.unregister_class(LinkedMaterialItem)