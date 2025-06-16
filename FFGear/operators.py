import bpy
import os
import re
import logging
import collections

from bpy.types import Operator
from pathlib import Path
from . import stm_utils
from . import mtrl_handler
from . import helpers
from . import properties
from .mtrl_handler import MaterialFlags
from .stm_utils import StainingTemplate
from enum import Enum
from typing import List, Optional, Union, Dict, Tuple, Any
from dataclasses import dataclass

# # Profiling
# import cProfile
# import pstats
# import io

logging.basicConfig()
logger = logging.getLogger('FFGear.operators')
logger.setLevel(logging.INFO) # Apparently the level above is a fucking sham and a fraud (oh I removed it at some point sick)


##### SIMPLE EXPLANATION ON HOW THE AUTO-SETUP WORKS #####
# There are two different operators for automatically generating a material, the normal FFGearAutoMaterial operator and the FFGearMeddleSetup operator.
# I'll start by describing the normal one because the meddle one just builds on top of what that one does.
#
# The operator starts by getting the materials we want to adjust, and the objects we want to potentially affect, and then creates a "material mapping"
# This is a dictionary where the key is the original material, which we will later process, and the value is a list of tuples (object, material_slot_index) where that material can be found.
# So the key material can be mapped to where it's used across the objects we're considering (usually all objects, but only the selected objects if that modifier is held)
#
# It then sends that data to the process_shared_materials() function which loops over all the materials in the material mapping and processes them with its own specialized function that differs slightly between normal and Meddle
# In the normal version it calls process_shared_materials(create_ffgear_material)
# create_ffgear_material() creates a copy of the template material shipped with the addon and applies the original material's settings to it. Important to note though: it is a brand new material.
# It then uses the data stored in the material (mtrl file, textures, etc) to modify the template material
# Once a material has been looped over by process_shared_materials() and an FFGear material has been created, it uses the material mapping to replace all of the instances of the original material with the new one
# It then continues on to the next material, and the cycle continues.
# So the operator calls process_shared_materials() once which in turn calls create_ffgear_material() once per new material
#
# The meddle operator instead calls process_shared_materials() once but then calls process_meddle_material() once per material which then calls create_ffgear_material() once
# The in-between step of process_meddle_material() tries to do all of the necessary setup like mtrl file and texture selection automatically before creating the material.
# Other than that it's the same thing.
##########################################################


#¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤#
# FUNCTIONS
#¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤#

def rename_datablock_to_original(datablock, datablock_category):
    """
    Makes sure the specified datablock is named as the original, meaning it has no ".###" suffix
    
    Args:
        datablock: The datablock to rename. It must have a .name attribute to read and edit.
        datablock_category: The type of data it is. If the datablock is a material, this should be bpy.data.materials
    
    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        original_name: str = datablock.name
        regex = r"\.\d{3}$" # String must end in .### where # is a digit (\. is a dot, \d is a digit and {3} means it has to match exactly three times, $ is the end of the string)
        if re.search(regex, original_name):
            unnumbered_name = original_name.rsplit('.', 1)[0]
            if unnumbered_name in datablock_category:
                # Find highest valued suffix
                highest_suffix = 0
                for data in datablock_category:
                    if data.name.startswith(unnumbered_name) and re.search(regex, data.name): # Find all numbered variants of the datablock
                        suffix_as_index = int(data.name.rsplit('.', 1)[1])
                        if suffix_as_index > highest_suffix:
                            highest_suffix = suffix_as_index

                suffix_to_give_previous_original = "."+str(highest_suffix+1).zfill(3) #zfill adds "0" to the left of the string until specified length is reached

                datablock_category[unnumbered_name].name = unnumbered_name+suffix_to_give_previous_original # This should make the original datablock have a suffix that is one higher than the highest existing one
                datablock.name = unnumbered_name
            else: # there is no original so just rename it
                datablock.name = unnumbered_name

    except Exception as e:
        return False, str(e)


def collect_material_slots_for_objects(objects, filter_func=None):
    """
    Collect all material slots that need processing across given objects.
    
    Args:
        objects: List of objects to check
        filter_func: Optional function to filter materials (takes material as argument)
        
    Returns:
        dict: The key is the material, the value is a list of tuples (obj, slot_index)
    """
    material_mapping = {}
    
    for obj in objects:
        if not obj.material_slots:
            continue
            
        for slot_index, slot in enumerate(obj.material_slots):
            if not slot.material:
                continue
                
            # Apply filter if provided
            if filter_func and not filter_func(slot.material):
                continue
                
            # Add to mapping
            if slot.material not in material_mapping:
                material_mapping[slot.material] = []
            material_mapping[slot.material].append((obj, slot_index))
    
    return material_mapping


def process_shared_materials(material_mapping, hard_reset, process_func):
    """
    Process materials and handle sharing across objects
    
    Args:
        material_mapping: Dict mapping materials to a list of (object, slot_idx) tuples
        hard_reset: Boolean, whether or not to replace existing addon assets like tile images and node groups with the ones on disk.
        process_func: Function that processes a single material. Should take (original_material, hard_reset)
                      and return (success, message, new_material)
    
    Returns:
        tuple: (processed_count, skipped_count)
    """
    processed = 0
    skipped = 0
    processed_material_info = {}
    
    # APPEND A TEMPLATE MATERIAL.
    # The create_ffgear_material() function should then create a copy of it for each material and use that instead of appending. 
    library_path = bpy.path.abspath(bpy.path.native_pathsep(os.path.join(os.path.dirname(__file__), "assets", "material_library.blend")))
    with bpy.data.libraries.load(library_path, link=False) as (data_from, data_to):
        if "FFGear Template Material" not in data_from.materials:
            logger.error("Template material not found in library")
            return 0, 0
        data_to.materials = ["FFGear Template Material"]
    # Get a reference to the newly appended material
    local_template_material = data_to.materials[0]

    # Material Loop
    for original_material, slots in material_mapping.items(): # A live reference to the material mapping, "slots" is the list of tuples of (object, slot_index)
        if not slots:
            continue

        new_material = None
        try:
            # Process (create, basically) the FFGear material
            success, message, new_material = process_func(original_material, local_template_material, hard_reset) #Lambda (in the automaterial and meddle operators)

            if not success:
                logger.warning(f"Failed to process material: {message}")
                skipped += 1
                continue

            # Update all slots that used this material
            for obj, slot_index in slots:
                obj.material_slots[slot_index].material = new_material
            
            # Store material data and name for cleanup after the loop
            processed_material_info[new_material] = new_material.name
            
            processed += 1
        except Exception as e:
            logger.error(f"Ran into an unknown error when running process_shared_materials: {e}")

    # REMOVE THE TEMPLATE MATERIAL WE GOT BEFORE
    bpy.data.materials.remove(local_template_material)

    # Remove leftover versions of the material
    regex = r"\.\d{3}$" # String must end in .### where # is a digit (\. is a dot, \d is a digit and {3} means it has to match exactly three times, $ is the end of the string)
    processed_base_names = set(processed_material_info.values())
    for mat_data in bpy.data.materials:
        if mat_data.users == 0: # Cheap check first
            if mat_data in processed_material_info:
                 continue # Skip it if it's the one we just created, don't delete that.
            name = mat_data.name
            for base_name in processed_base_names: # Check if the material matches (is a duplicate of) one of the newly added ones
                if len(name) == len(base_name)+4 and name.startswith(base_name+".") and re.search(regex, name) != None:
                    bpy.data.materials.remove(mat_data)

    return processed, skipped


def get_new_materials_from_mapping(material_mapping):
    """
    Gets the materials from where things were mapped to, due to a material mapping process. 
    
    Args:
        material_mapping (dict): Material mapping dictionary
        
    Returns:
        materials (list): List of all the new materials
    """
    materials = []
    for non_ffgear_material in material_mapping.keys():
        first_obj, first_material_slot_index = material_mapping[non_ffgear_material][0]
        material = first_obj.material_slots[first_material_slot_index].material
        materials.append(material)
    return materials


def get_meddle_dyes(material):
    """
    Sets the material's dye properties to what's stored in the custom attributes from Meddle.

    Args:
        material: the material to process

    Returns:
        tuple: (bool: success, str: message)
    """
    stored_auto_setting = material.ffgear.auto_update_dyes

    try:
        material.ffgear.auto_update_dyes = False
        material.ffgear.dye_1 = str(material["Stain0Id"])
    except KeyError:
        message = f"The stain IDs were not found in the custom properties of the material. This could be because your model was exported with a Meddle version prior to 0.1.29"
        material.ffgear.auto_update_dyes = stored_auto_setting
        return False, message

    try:
        material.ffgear.dye_2 = str(material["Stain1Id"])
    except KeyError:
        message = f"The second stain ID was not found in the custom properties of the material, but the first was. It's possible that it's been mistakenly deleted somehow"
        material.ffgear.auto_update_dyes = stored_auto_setting
        return False, message
    
    material.ffgear.auto_update_dyes = stored_auto_setting
    
    return True, "Success"


def find_texture_file(directory: Path, base_name, recursive=False):
    """
    Search for a texture file with the given base name.
    
    Args:
        directory: Path object for the directory to search
        base_name: Base name of the texture without extension
        recursive: Whether to search recursively through subdirectories
        
    Returns:
        str or None: Path to found texture file or None if not found
    """
    extensions = ['.png', '.jpg', '.jpeg', '.exr', '.tiff', '.tif']
    
    if recursive:
        for path in directory.rglob("*"):
            if path.is_file() and path.stem == base_name:
                if path.suffix.lower() in extensions:
                    return str(path)
    else:
        for ext in extensions:
            potential_file = directory / f"{base_name}{ext}"
            if potential_file.exists():
                return str(potential_file)
    
    return None


def find_textures_from_mtrl(mtrl_data: dict, search_dir: Path, recursive=False):
    """
    Find texture files based on MTRL data.
    
    Args:
        mtrl_data: Dictionary containing MTRL file data
        search_dir: Path object for directory to search
        recursive: Whether to search recursively through subdirectories
        
    Returns:
        tuple: (diffuse_tex, mask_tex, norm_tex, id_tex) paths as strings. None if not found
    """
    diffuse_tex = None
    mask_tex = None
    norm_tex = None
    id_tex = None
    
    textures = mtrl_data.get('textures', [])

    # Process each texture from the MTRL
    for tex in textures:
        tex_name = Path(tex['path']).stem
        logger.debug(f"Looking for texture name: {tex_name}")
        # Determine texture type and valid suffixes
        tex_type = None
        valid_suffixes = None
        
        if tex_name.endswith('_diff') or tex_name.endswith('_d'):
            tex_type = 'diffuse'
            valid_suffixes = ['diff', 'd'] # I don't actually know if they can be "diff" but I'm including it to be safe
        elif tex_name.endswith('_mask') or tex_name.endswith('_m'):
            tex_type = 'mask'
            valid_suffixes = ['mask', 'm']
        elif tex_name.endswith('_norm') or tex_name.endswith('_n'):
            tex_type = 'normal'
            valid_suffixes = ['norm', 'n']
        elif tex_name.endswith('_id'):
            tex_type = 'id'
            valid_suffixes = ['id']
            
        if not valid_suffixes:
            logger.warning(f"No valid suffix found for texture search, skipping this texture: {tex_name}")
            continue            
            
        # Also look for variants with .tex extension (for each already valid suffix, so 'n'.png will also check for 'n.tex'.png)
        valid_suffixes.extend(suffix+'.tex' for suffix in valid_suffixes.copy())
        logger.debug(f"Valid suffixes for this texture: {valid_suffixes}")

        # Get base name without suffix
        for suffix in valid_suffixes:
            if tex_name.endswith('_' + suffix):
                tex_name = tex_name[:-len(suffix)-1]
                break
                
        # Search for file with each valid suffix
        found_path = None
        for suffix in valid_suffixes:
            if found_path:  # Skip if we already found one
                continue
                
            search_name = f"{tex_name}_{suffix}"
            logger.debug(f"Searching for: {search_name}, in: {search_dir}")
            found_path = find_texture_file(search_dir, search_name, recursive)

        # Store result in appropriate variable
        if found_path != None:
            logger.debug(f"Found texture path: {found_path}")
            if tex_type == 'diffuse':
                diffuse_tex = found_path
            elif tex_type == 'mask':
                mask_tex = found_path
            elif tex_type == 'normal':
                norm_tex = found_path
            elif tex_type == 'id':
                id_tex = found_path
        else:
            logger.debug(f"Could not find the texture in that directory.")
                
    return diffuse_tex, mask_tex, norm_tex, id_tex


def get_textures_from_meddle_data(cache_dir, material):
    """
    Just grabs and returns the texture paths from the Meddle custom properties of the material.
    
    Args:
        cache_dir (str): the cache directory path
        material (Material): the material with the meddle data

    Returns:
        tuple: (diffuse_tex_path, id_tex_path, mask_tex_path, norm_tex_path) as strings or None
    """
    try:
        diffuse_tex_path = os.path.join(cache_dir, material["g_SamplerDiffuse_PngCachePath"])
    except:
        diffuse_tex_path = None
    
    try:
        mask_tex_path = os.path.join(cache_dir, material["g_SamplerMask_PngCachePath"])
    except:
        mask_tex_path = None
    
    try:
        norm_tex_path = os.path.join(cache_dir, material["g_SamplerNormal_PngCachePath"])
    except:
        norm_tex_path = None

    try:
        id_tex_path = os.path.join(cache_dir, material["g_SamplerIndex_PngCachePath"])
    except:
        id_tex_path = None
    
    return diffuse_tex_path, mask_tex_path, norm_tex_path, id_tex_path


def construct_false_meddle_mtrl_data(material: bpy.types.Material):
    """
    Creates some mtrl data to use for material creation based on the ColorTable attribute in the Meddle data

    Args:
        material (material): The material that has the ColorTable, Material Flags, etc.

    Returns:
        mtrl_data (dict)
    """

    #¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤#
    ### COLORSET DATA ### and colorset_type check
    #¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤#

    meddle_color_table = material.get("ColorTable")
    if not meddle_color_table:
        logger.error(f"Could not get ColorTable property from material: {material.name}")
        return None

    colorset_data = []

    rows = meddle_color_table["ColorTable"]["Rows"]

    num_rows = len(rows)
    colorset_type = None
    if num_rows == 32:
        colorset_type = mtrl_handler.ColorsetType.DAWNTRAIL
    elif num_rows == 16:
        colorset_type = mtrl_handler.ColorsetType.ENDWALKER
    else:
        logger.error(f"Got an unexpected row count from ColorTable when constructing fake mtrl data: {num_rows}")
        return None

    row_num = 0
    for row in rows:
        
        tile_matrix_uu, tile_matrix_uv, tile_matrix_vu, tile_matrix_vv = row["TileMatrix"].values()
        # Decompose the tile matrix
        tile_transform = mtrl_handler.decompose_tile_matrix(
            tile_matrix_uu, tile_matrix_uv, tile_matrix_vu, tile_matrix_vv
        )

        row_data = {
            'row_number': row_num+1,
            'group': 'A' if row_num % 2 == 0 else 'B',
            'diffuse': [x for x in row["Diffuse"].values()],
            'diffuse_unknown': 0.5, # (Gloss) on legacy shaders, FFGear uses it as Roughness, Meddle does not provide it
            'specular': [x for x in row["Specular"].values()],
            'specular_unknown': 0.5, # (Specular Power) on legacy shaders, FFGear uses it as Sheen Rate, Meddle does not provide it
            'emissive': [x for x in row["Emissive"].values()],
            'emissive_unknown': None,
            'sheen_rate': row["SheenRate"],
            'sheen_tint_rate': row["SheenTint"],
            'sheen_aperture': row["SheenAptitude"], # May not be the correct mapping from Meddle but I think it is
            'sheen_unknown': None,
            'roughness': row["Roughness"],
            'pbr_unknown': None,
            'metalness': row["Metalness"],
            'anisotropy_blending': row["Anisotropy"],
            'effect_unknown_r': None,
            'sphere_map_opacity': row["SphereMask"], # May not be the correct mapping from Meddle but I think it is
            'effect_unknown_b': None,
            'effect_unknown_a': None,
            'shader_template_id': row["ShaderId"],
            'tile_map_id': row["TileIndex"],
            'tile_map_opacity': row["TileAlpha"],
            'sphere_map_id': row["SphereIndex"],
            'tile_scale_x': tile_transform['scale_x'],
            'tile_scale_y': tile_transform['scale_y'],
            'tile_rotation_deg': tile_transform['rotation_deg'],
            'tile_shear_deg': tile_transform['shear_deg'],
            'tile_matrix_raw': {'uu': tile_matrix_uu, 'uv': tile_matrix_uv, 'vu': tile_matrix_vu, 'vv': tile_matrix_vv}
        }

        colorset_data.append(row_data)
        row_num += 1


    #¤¤¤¤¤¤¤¤¤¤¤#
    ### FLAGS ###
    #¤¤¤¤¤¤¤¤¤¤¤#

    # Initialize as 0, which is no flags
    # Then add flags using bitwise OR operator |=
    flags = mtrl_handler.MaterialFlags(0)

    # Backface Culling
    show_backfaces = material.get("RenderBackfaces", None)
    if show_backfaces != None:
        if not show_backfaces: # We want to hide them
            flags |= mtrl_handler.MaterialFlags.HideBackfaces
    else: # Couldn't get from meddle, assume we want to hide them
        logger.warning(f"Couldn't read flag RenderBackfaces from Meddle data when constructing false mtrl data, hiding by default. Material: {material.name}")
        flags |= mtrl_handler.MaterialFlags.HideBackfaces


    #¤¤¤¤¤¤¤¤¤¤¤¤¤¤#
    ### TEXTURES ###
    #¤¤¤¤¤¤¤¤¤¤¤¤¤¤#

    textures = []
    potential_meddle_properties = ("g_SamplerDiffuse", "g_SamplerNormal", "g_SamplerMask", "g_SamplerIndex")
    for prop in potential_meddle_properties:
        prop_value = material.get(prop, None)
        if prop_value != None:
            textures.append({"path": prop_value, "flags": 0})


    #¤¤¤¤¤¤¤¤¤¤¤#
    ### FINAL ###
    #¤¤¤¤¤¤¤¤¤¤¤#

    mtrl_data = {
        "colorset_data": colorset_data,
        "material_flags": flags,
        "shader_name": material.get("ShaderPackage", "Unknown"),
        "textures": textures,
        "colorset_type": colorset_type
    }

    return mtrl_data


def apply_material_flags(material, flags):
    """
    Apply material settings based on MTRL flags
    
    Args:
        material: Blender material to modify
        flags: MaterialFlags enum containing the flags
        
    Returns:
        bool: True if any settings were modified
    """
    if not material or not flags:
        return False
        
    modified = False
    
    # Keep track of all modifications for logging
    applied_flags = []
    
    # Backface Culling
    if MaterialFlags.HideBackfaces in flags:
        material.use_backface_culling = True
        nodes = material.node_tree.nodes
        node = nodes.get("Backface Culling")
        if node:
            node.mute = False
        applied_flags.append("HideBackfaces -> Enabled backface culling")
    else:
        material.use_backface_culling = False
    
    # Log the changes if any were made
    if applied_flags:
        logger.debug(f"Applied flags to {material.name}:")
        for flag in applied_flags:
            logger.debug(f"  {flag}")
        modified = True
    else:
        logger.debug(f"No material flags needed changes for {material.name}")
        
    return modified


def material_name_is_valid(material_name:str):
    """
    Checks if a string is a valid Meddle Material name. Supports pre and post Meddle 0.1.29 naming
    
    Args:
        material_name (str): The string to check 
        
    Returns:
        bool: True if the string matches, otherwise False
    """
    if material_name:
        if (('character.shpk' in material_name or 'characterlegacy.shpk' in material_name) or # 0.1.29 behavior
            ('_character_' in material_name or '_characterlegacy_' in material_name)): # pre 0.1.29 behavior
                return True
        else:
            return False
    else:
        logger.warning(f"No name provided to material_name_is_valid function. Returning False")
        return False



#¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤#
# COLOR RAMP UPDATING STUFF
#¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤#

@dataclass
class ColorChannel:
    """Defines how a color channel should be populated"""
    mtrl_key: str           # Key in MTRL data to read from
    default: float = 0.0    # Default value if not specified
    can_be_dyed: bool = False
    # Dictionary mapping template types to special handling rules
    template_rules: Dict[StainingTemplate, Dict[str, Any]] = None

    def __post_init__(self):
        # Initialize empty rules dict if none provided
        if self.template_rules is None:
            self.template_rules = {}

@dataclass 
class MtrlProperty:
    """Defines how to handle a specific MTRL color ramp"""
    name: str              # Display name 
    node_label: str        # Label to look for in node tree
    channels: Dict[str, ColorChannel]  # Mapping of rgba channels to their data source

# Define the properties and their channel mappings, which data ends up on which ramp
MTRL_PROPERTIES = {
    "Diffuse": MtrlProperty(
        name="Diffuse Colors",
        node_label="Ramp 1",
        channels={
            "r": ColorChannel("diffuse[0]", can_be_dyed=True),
            "g": ColorChannel("diffuse[1]", can_be_dyed=True),
            "b": ColorChannel("diffuse[2]", can_be_dyed=True),
            "a": ColorChannel("", default=1.0)
        }
    ),
    "Specular": MtrlProperty(
        name="Specular & Sheen Rate",
        node_label="Ramp 2",
        channels={
            "r": ColorChannel("specular[0]", can_be_dyed=True),
            "g": ColorChannel("specular[1]", can_be_dyed=True),
            "b": ColorChannel("specular[2]", can_be_dyed=True),
            "a": ColorChannel(
                "sheen_rate", 
                can_be_dyed=True,
                template_rules={
                    StainingTemplate.ENDWALKER: {
                        "force_value": "specular_unknown" # specular_unknown (Specular Power) on legacy shaders
                    }
                }
            )
        }
    ),
    "Emissive": MtrlProperty(
        name="Emissive & Sheen Tint",
        node_label="Ramp 3",
        channels={
            "r": ColorChannel("emissive[0]", can_be_dyed=True),
            "g": ColorChannel("emissive[1]", can_be_dyed=True),
            "b": ColorChannel("emissive[2]", can_be_dyed=True),
            "a": ColorChannel(
                "sheen_tint_rate", 
                can_be_dyed=True,
                template_rules={
                    StainingTemplate.ENDWALKER: {
                        "force_value": 0.98
                    }
                }
            )
        }
    ),
    "PBR": MtrlProperty(
        name="PBR & Tiles",
        node_label="Ramp 4",
        channels={
            "r": ColorChannel(
                "roughness", 
                can_be_dyed=True,
                template_rules={
                    StainingTemplate.ENDWALKER: {
                        "change_key": "diffuse_unknown", # diffuse_unknown (Gloss) on legacy shaders
                        "expression": lambda x: 0.9 * (1.0 - (x - 5.0) / 20.0), # Map 25 to 0 (Very shiny) and 5 to 0.9 (Not shiny)
                        "min_value": 0.0,
                        "max_value": 1.0
                    }
                }
            ),
            "g": ColorChannel("metalness", can_be_dyed=True),
            "b": ColorChannel("tile_map_id"),
            "a": ColorChannel("tile_map_opacity")
        }
    ),
    "TileMap": MtrlProperty(
        name="Tile Transforms",
        node_label="Ramp 5",
        channels={
            "r": ColorChannel("tile_scale_x"),
            "g": ColorChannel("tile_scale_y"),
            "b": ColorChannel(
                "tile_rotation_deg",
                template_rules={
                    StainingTemplate.ENDWALKER: {
                        "add": 1000.0
                    },
                    StainingTemplate.DAWNTRAIL: {
                        "add": 1000.0
                    }
                }
            ), # Because these can be negative values but color ramps don't support negative values, we add 1000 and then subtract it in the material
            "a": ColorChannel(
                "tile_shear_deg",
                template_rules={
                    StainingTemplate.ENDWALKER: {
                        "add": 1000.0
                    },
                    StainingTemplate.DAWNTRAIL: {
                        "add": 1000.0
                    }
                }
            )
        }
    ),
    "SphereMap": MtrlProperty(
        name="Sphere Map",
        node_label="Ramp 6",
        channels={
            "r": ColorChannel("sphere_map_id", can_be_dyed=True, default=1.0),
            "g": ColorChannel("sphere_map_opacity", can_be_dyed=True, default=0.0),
            "b": ColorChannel("", default= 0.0),
            "a": ColorChannel("", default= 0.0)
        }
    )
}


# Naming it with an underscore signifies that it's just a helper function, the more you know
def _get_value_from_row(row_data: dict, key: str, default: float) -> float:
    """Helper to get a value from a specific MTRL key within row_data."""
    if not key:
        return default
    try:
        if '[' in key:
            base_key, index_str = key.split('[', 1)
            index = int(index_str.rstrip(']'))
            container = row_data.get(base_key)

            # Check if container exists, is list/tuple, and index is valid
            if isinstance(container, (list, tuple)) and 0 <= index < len(container):
                 val = container[index]
                 return float(val)
            else:
                 logger.warning(f"Invalid key '{key}': Base key '{base_key}' not found, not list/tuple, or index {index} out of bounds in row_data. Returning default {default}.")
                 return default
        else:
            value = row_data.get(key)
            if value is not None:
                return float(value)
            else:
                return default
    except (KeyError, IndexError, ValueError, TypeError) as e:
        logger.warning(f"Error accessing key '{key}' in row_data: {e}. Returning default {default}.")
        return default


def get_mtrl_value(
    row_data: dict,
    channel: ColorChannel,
    dye_info: Optional[dict] = None,
    template_type: Optional[StainingTemplate] = None,
    dye_channels: Optional[Dict[int, str]] = None
) -> float:
    """Get a single channel value from MTRL data, handling dyes if applicable"""
    
    # logger.debug(f"CALL: get_mtrl_value")

    effective_mtrl_key = channel.mtrl_key
    value: Optional[float] = None

    # Cache base_property and index calculations
    base_property = effective_mtrl_key.split('[')[0] if '[' in effective_mtrl_key else effective_mtrl_key
    index = None
    if '[' in effective_mtrl_key:
        index = int(effective_mtrl_key.split('[')[1].rstrip(']'))

    # Unsure about what's happening here? Valid for what
    valid = True if template_type and channel.template_rules and template_type in channel.template_rules else False

    # Check template rules first
    if valid:
        rules = channel.template_rules[template_type]
        
        if "change_key" in rules:
            effective_mtrl_key = rules["change_key"]
            # After changing key, update base_property and index
            base_property = effective_mtrl_key.split('[')[0] if '[' in effective_mtrl_key else effective_mtrl_key
            index = None
            if '[' in effective_mtrl_key:
                index = int(effective_mtrl_key.split('[')[1].rstrip(']'))

        # Check for forced value (can be number or another key)
        if "force_value" in rules:
            forced = rules["force_value"]
            if isinstance(forced, (int, float)):
                return float(forced) # Return with forced numeric value
            elif isinstance(forced, str):
                # Force value is another key, look that one up instead
                # Use the original channel's default if the forced key isn't found
                return _get_value_from_row(row_data, forced, channel.default)
            else:
                 logger.warning(f"Template rule 'force_value' has unexpected type: {type(forced)}. Ignoring.")

    # Since we didn't override the value, get base value from MTRL data
    # logger.debug(f"Material Key: {effective_mtrl_key}")
    value = _get_value_from_row(row_data, effective_mtrl_key, channel.default)

    # Apply dye modifications if needed (uses mtrl_key)
    if channel.can_be_dyed and dye_info and dye_channels:
        for channel_num, dye_id in dye_channels.items():
            if dye_id != '0': # 0 meaning "No Dye"
                if stm_utils.should_apply_dye(dye_info, base_property, channel_num):
                    modified = stm_utils.get_modified_value(dye_info, base_property, dye_id)
                    if modified is not None:
                        # If we got back a list, extract the appropriate component
                        if isinstance(modified, (list, tuple)):
                            # Use cached index if available
                            if index is not None:
                                value = modified[index]
                            else:
                                value = modified[0]  # Default to first component if no index
                        else:
                            value = modified

    # Apply template modifiers if any
    if valid:
        rules = channel.template_rules[template_type]
        
        if "add" in rules:
            value += rules["add"]

        if "subtract" in rules:
            value -= rules["subtract"]

        if "expression" in rules:
            expression_func = rules["expression"]
            # Check if it's a callable function (like a lambda)
            if callable(expression_func):
                try:
                    # Pass the current value as the argument 'x'
                    value = float(expression_func(value))
                except Exception as e:
                    logger.error(f"Error executing lambda expression for key '{effective_mtrl_key}' with x={value}: {e}", exc_info=True)
                    # Keep value before error
            else:
                logger.warning(f"Rule 'expression' for key '{effective_mtrl_key}' is not callable (expected lambda/function), ignoring.")

        if "scale_factor" in rules:
            value *= rules["scale_factor"]
            
        if "min_value" in rules:
            value = max(value, rules["min_value"])
            
        if "max_value" in rules:
            value = min(value, rules["max_value"])

    return value


def update_color_ramp_values(
        element,
        row_data: dict,
        property_def: MtrlProperty,
        dye_info: Optional[dict] = None,
        template_type: Optional[StainingTemplate] = None,
        dye_channels: Optional[Dict[int, str]] = None) -> None:
    """Update color ramp element with values from a single row"""
    channels = property_def.channels
    # Use list comprehension to build the color array quickly
    element.color = [get_mtrl_value(row_data, channels[channel], dye_info, template_type, dye_channels)
                    for channel in ('r', 'g', 'b', 'a')]


# Could pass some data into the sub-functions for a little bit of extra speed
def update_color_ramps(material, mtrl_data, hard_reset=False):
    """Update existing color ramps in the material using MTRL data"""

    logger.debug(f"CALL: update_color_ramps (material(name)={material.name}, mtrl_data=tooLongToLogIDontWantTo, hard_reset={hard_reset})")

    if not material.use_nodes or not mtrl_data:
        logger.error("No material nodes or MTRL data")
        return False


    ########## INITIAL SETUP ##########

    try:
        # Get shader type and colorset info
        is_legacy = mtrl_data.get('shader_name', '') == "characterlegacy.shpk"
        colorset_type = mtrl_data.get('colorset_type')

        # Determine template type with proper fallback logic
        forced_template = (
            stm_utils.StainingTemplate.ENDWALKER if is_legacy else (
                stm_utils.StainingTemplate.ENDWALKER if colorset_type.value == 512 
                else stm_utils.StainingTemplate.DAWNTRAIL
            )
        )
        
        # Store in material property and use for processing
        material.ffgear.template_type = forced_template.name
        
        logger.debug(f"Material \"{material.name}\"template type set to: {forced_template.name}" + 
                   (" (Forced due to legacy shader)" if is_legacy else ""))
        
        template_type = stm_utils.StainingTemplate[material.ffgear.template_type]

        # Get dye channels
        dye_channels = {
            1: material.ffgear.dye_1,
            2: material.ffgear.dye_2
        }

        # Used to skip steps later on
        is_created = material.ffgear.is_created

        # Personally mapped values that should be closer to the exact breaking points of the textures. Put just to the left of the breaking point of the Picto 100 Top's texture but they could vary a little so constant interpolation is probably still bad.
        custom_ramp_positions = [0, 0.0703, 0.1328, 0.2031, 0.2656, 0.3359, 0.3984, 0.4687, 0.5312, 0.5976, 0.6640, 0.7304, 0.7968, 0.8632, 0.9296, 1] # 16 values total

        # --- Pre-process colorset data ---
        # Group rows by the 'group' key for O(1) lookup later, instead of O(N) filtering per node.
        # It's just each row put in a dict as a list under its group as the key. {"A": [row data], "B": [row data]}
        grouped_mtrl_data = collections.defaultdict(list)
        for row in mtrl_data['colorset_data']:
            group_key = row.get('group') # "A" or "B"
            if group_key is not None:
                 grouped_mtrl_data[group_key].append(row)
            else:
                 logger.warning(f"Row found without 'group' key in colorset_data: {row}")

        # List comprehension should be faster than doing it in the for loop?
        nodes_to_process = [node for node in material.node_tree.nodes if node.type == 'VALTORGB'] # All color ramp nodes
        prop_map_by_prefix = {prop.node_label: prop for prop in MTRL_PROPERTIES.values()} # Prefix being "Ramp 1", "Ramp 2", etc.

        ########## END INITIAL SETUP ##########



        ########## LOOP OVER NODES ##########

        for node in nodes_to_process:
            # Find matching property definition for this node
            prop_def = None
            node_label = node.label
            # Attempt lookup using the pre-built map
            for prefix, prop in prop_map_by_prefix.items():
                 if node_label.startswith(prefix):
                     prop_def = prop
                     break # Found the first match
                    
            if not prop_def:
                logger.debug(f"No matching MTRL property found for node '{node_label}'")
                continue

            # Get group (string, A or B)
            if '(Group ' not in node_label:
                logger.warning(f"Node label '{node_label}' does not contain '(Group ..)' identifier.")
                continue
            try:
                # Split carefully and handle potential errors
                parts = node_label.split('(Group ')
                if len(parts) < 2 or not parts[1].endswith(')'):
                     raise ValueError("Label format error")
                group:str = parts[1].rstrip(')')
            except Exception as e:
                logger.warning(f"Could not extract group from node label '{node_label}': {e}")
                continue
            
            # Get rows for this group, pre-grouped
            group_rows = grouped_mtrl_data.get(group) # O(1) lookup using the defaultdict
            if not group_rows:
                logger.debug(f"No colorset data found for group '{group}' (from node '{node_label}')")
                continue # Skip if this group has no data
            
            len_group_rows = len(group_rows)
            use_custom_ramp_positions = False
            if len_group_rows == len(custom_ramp_positions):
                use_custom_ramp_positions = True

            ##### ELEMENT REUSE #####
            # Check if we can re-use the elements in the color ramp rather than remove and re-add them
            use_old_elements = True
            ramp_has_mismatched_element_count = len(node.color_ramp.elements) != len_group_rows
            if not is_created or not use_custom_ramp_positions or ramp_has_mismatched_element_count or hard_reset: # On first execution or if we're somehow dealing with not 16 elements
                # Clear existing elements after the first
                while len(node.color_ramp.elements) > 1:
                    node.color_ramp.elements.remove(node.color_ramp.elements[-1])
                use_old_elements = False
            
            ##### LOOP OVER ALL THE ROWS, UPDATE THE RAMPS #####
            # Each row is a mtrl row, row_data in the mtrl_handler
            debug_counter = 0
            for i, row in enumerate(group_rows):

                ##### GET DYE INFO #####
                dye_info = None
                if 'dye' in row:
                    dye_info = row['dye'] # Found as dye_info in the mtrl_handler
                    # Make sure template type is set for dye processing
                    dye_info['template_type'] = template_type # dawntrail or endwalker


                ##### DOES ANY OF THE RGBA FOR THIS ELEMENT EVEN NEED CHANGING DUE TO A DYE CHANGE #####
                # As a slight optimization, this stuff could get passed to update_color_ramp_values and down
                # However this block already means that we skip the vast mahority of calls to update_color_ramp_values
                # Without this there will always be 160 updates, with this it's down to around 25 usually.
                # Passing this data would be faster, but would make the code more ass to work with
                if is_created and not hard_reset and use_old_elements: # only if we're gonna be working with the pre-existing 16 elements
                    update_needed_due_to_dye = False
                    if dye_info and dye_channels:
                        # Check if *any* channel ('r', 'g', 'b', 'a') needs updating due to *any* active dye
                        for c_key in ('r', 'g', 'b', 'a'):
                            channel_def = prop_def.channels.get(c_key)
                            if channel_def and channel_def.can_be_dyed:

                                # Figure out what property we're dealing with
                                effective_mtrl_key = channel_def.mtrl_key # Start with original key
                                # Check if template rules apply and potentially change the key
                                valid_template = template_type and channel_def.template_rules and template_type in channel_def.template_rules
                                if valid_template:
                                    rules = channel_def.template_rules[template_type]
                                    if "change_key" in rules:
                                        effective_mtrl_key = rules["change_key"] # Update key if rule exists

                                base_property = effective_mtrl_key.split('[')[0] if '[' in effective_mtrl_key else effective_mtrl_key

                                # Check against active dye channels using the *correct* base_property
                                for channel_num, dye_id in dye_channels.items():
                                    if stm_utils.should_apply_dye(dye_info, base_property, channel_num):
                                        update_needed_due_to_dye = True
                                        break # Dye applies to this channel, stop checking dyes for it
                                if update_needed_due_to_dye:
                                    break # Dye applies to *some* channel, stop checking other channels
                    
                    # If the material is created AND no dye updates are needed for this row, skip processing this element
                    if not update_needed_due_to_dye:
                        # Could potentially check that the element position and stuff is still fine here, but for now let's assume it's correct.
                        continue # Skip the update_color_ramp_values call, move on to the next element


                ##### GET COLOR RAMP ELEMENT #####
                if use_old_elements: # Will always fail on a hard reset
                    element = node.color_ramp.elements[i] # The element exists, reference it directly
                else:
                    if use_custom_ramp_positions:
                        position = custom_ramp_positions[i]
                    else:
                        position = i / (len_group_rows - 1) if len_group_rows > 1 else 0 # Basically i / 15 so index 15 (entry 16) equals 1, but dynamic so it's cooler

                    # Create new element if needed
                    if i > 0:
                        element = node.color_ramp.elements.new(position)
                    else:
                        element = node.color_ramp.elements[0]
                        element.position = position
                

                ##### DO THE UPDATE #####
                update_color_ramp_values(
                    element, # Knob on the color ramp node
                    row,
                    prop_def,
                    dye_info,
                    template_type,
                    dye_channels
                )
                debug_counter += 1  
        
        return True
        
    except Exception as e:
        logger.error(f"Error updating color ramps: {str(e)}")
        return False


def setup_image_node(nodes, filepath, label):
    """Setup an image texture node with the given parameters"""
    # Get existing node
    node = nodes.get(label)
    if not node:
        logger.warning(f"Node '{label}' not found in material")
        return None

    if filepath:
        # Check if image is already loaded
        image_name = os.path.basename(filepath)
        img = bpy.data.images.get(image_name)
        if not img:
            try:
                # Load new image
                img = bpy.data.images.load(bpy.path.abspath(filepath))
                img.colorspace_settings.name = 'Non-Color'
            except Exception as e:
                logger.error(f"Error loading image {filepath}: {e}")
                return node

        node.image = img
    
    return node


def cleanup_duplicate_node_groups(material, hard_reset):
    """
    Check material for numbered node groups and replace with original versions if they exist.
    
    Args:
        material: The material to check for duplicate node groups
        hard_reset: If True, the new version of the node group found on disk will be used instead of re-using the old one.
    """
    regex = r"\.\d{3}$" # String must end in .### where # is a digit (\. is a dot, \d is a digit and {3} means it has to match exactly three times, $ is the end of the string)
    nodes_with_new_duplicate_groups = []
    for node in material.node_tree.nodes:
        if node.type == 'GROUP':
            logger.debug(f"Processing this group node: {node}")
            if node.node_tree:
                node_group_name = node.node_tree.name
                if re.search(regex, node_group_name): # If an image node has an image with a number suffix (meaning if it's a new version)
                    nodes_with_new_duplicate_groups.append(node)
    
    performed_hard_reset = False
    # We add them to a list before changing anything to avoid changing nodes that will be searched in the future before it's their turn
    for node in nodes_with_new_duplicate_groups: #only in current material
        node_group_name = node.node_tree.name
        new_node_group = bpy.data.node_groups[node_group_name]
        unnumbered_name = node_group_name.rsplit('.', 1)[0]
        
        # Default behavior
        if unnumbered_name in bpy.data.node_groups and not hard_reset: 
            node.node_tree = bpy.data.node_groups[unnumbered_name] # Replace with the original already in the file
            if new_node_group.users == 0:
                bpy.data.node_groups.remove(new_node_group) # Remove the other one (the newly imported one) if it's no longer used.

        # Hard reset behavior
        # Imports the new node group and replaces all other uses with it
        elif unnumbered_name in bpy.data.node_groups and hard_reset:
            performed_hard_reset = True
            other_variants_of_node_group = []
            all_group_nodes = []

            for material in bpy.data.materials:
                if material.use_nodes:
                    for node in material.node_tree.nodes:
                        if node.type == 'GROUP':
                            all_group_nodes.append(node)

            for node_group in bpy.data.node_groups:
                if node_group.name.startswith(unnumbered_name) and node_group.name != node_group_name: # All node groups that share the base name but NOT the one we're currently considering as being the latest
                    other_variants_of_node_group.append(node_group)

            for node_group in other_variants_of_node_group:
                for node in all_group_nodes:
                    if node.node_tree in other_variants_of_node_group:
                        node.node_tree = new_node_group # Set it to one of the newly imported groups instead
                if node_group.users == 0:
                    bpy.data.node_groups.remove(node_group) # Remove all other versions of the group if it's not being used anywhere else.
            
            rename_datablock_to_original(new_node_group, bpy.data.node_groups)
    
    # SINCE GROUPS CAN CONTAIN OTHER GROUPS, WE SHOULD RUN A CHECK AT THE VERY END TO FIND NODE GROUPS WITH A SUFFIX BUT THAT COULD SAFELY BE RENAMED INTO AN ORIGINAL
    if performed_hard_reset:
        suffix_node_group_references = []
        # Save a reference to all groups with suffixes
        for node_group in bpy.data.node_groups:
            if re.search(regex, node_group.name):
                suffix_node_group_references.append(node_group)
        # Rename things
        for node_group in suffix_node_group_references:
            base_name = node_group.name.rsplit('.', 1)[0]
            if base_name in bpy.data.node_groups:
                if bpy.data.node_groups[base_name].users != 0:
                    continue # Just ignore it, it already exists and is in use.
                else:
                    bpy.data.node_groups.remove(bpy.data.node_groups[base_name]) # Remove unused original node
                    node_group.name = base_name # Rename to the original
            else:
                node_group.name = base_name


def cleanup_duplicate_images(material, hard_reset):
    """
    Check material for numbered images and replace with original versions if they exist.
    
    Args:
        material: The material to check for duplicate images
        hard_reset: If True, the new version of the image found on disk will be used instead of re-using the old one.
    """
    regex = r"\.\d{3}$" # String must end in .### where # is a digit (\. is a dot, \d is a digit and {3} means it has to match exactly three times, $ is the end of the string)
    nodes_with_new_duplicate_images = []
    for node in material.node_tree.nodes:
        if node.type == 'TEX_IMAGE':
            logger.debug(f"Processing this image node: {node}")
            if node.image:
                image_name = node.image.name
                if re.search(regex, image_name): # If an image node has an image with a number suffix (meaning if it's a new version)
                    nodes_with_new_duplicate_images.append(node)
    # We add them to a list before changing anything to avoid changing nodes that will be searched in the future before it's their turn
    for node in nodes_with_new_duplicate_images: #only in current material
        image_name = node.image.name
        new_image = bpy.data.images[image_name]
        unnumbered_name = image_name.rsplit('.', 1)[0]

        # Default behavior
        if unnumbered_name in bpy.data.images and not hard_reset: 
            node.image = bpy.data.images[unnumbered_name] # Replace with the original already in the file
            if new_image.users == 0:
                bpy.data.images.remove(new_image) # Remove the other one (the newly imported one) if it's no longer used.

        # Hard reset behavior
        # Imports the new image and replaces all other uses with it
        elif unnumbered_name in bpy.data.images and hard_reset: # A version of the image exists
            other_variants_of_image = []
            all_image_texture_nodes = []

            for material in bpy.data.materials:
                if material.use_nodes:
                    for node in material.node_tree.nodes:
                        if node.type == 'TEX_IMAGE':
                            all_image_texture_nodes.append(node)

            for image_data in bpy.data.images:
                if image_data.name.startswith(unnumbered_name) and image_data.name != image_name: # All images that share the base name but NOT the one we're currently considering as being the latest
                    other_variants_of_image.append(image_data)

            for image_data in other_variants_of_image:
                for node in all_image_texture_nodes:
                    if node.image in other_variants_of_image:
                        node.image = new_image # Set it to one of the newly imported images instead
                if image_data.users == 0:
                    bpy.data.images.remove(image_data) # Remove all other versions of the image if it's not being used anywhere else. It could still be being used in contexts other than image nodes.
            
            rename_datablock_to_original(new_image, bpy.data.images) 


def get_node_input_by_name(node, name):
    for input in node.inputs:
        if input.name.lower() == name.lower():
            return input


def create_ffgear_material(source_material, local_template_material, hard_reset=False):
    """
    Creates or resets a material based on an FFGear template, copying relevant properties
    from a source material.

    Args:
        source_material (bpy.types.Material): The original material to use as a basis
                                             for naming and copying properties.
        hard_reset (bool): Whether to replace existing addon assets like tile images
                           and node groups with the ones on disk.

    Returns:
        tuple: (success: bool, message: str, resulting_material: bpy.types.Material | None)
               Returns the newly created/configured material on success, None on failure.
    """

    logger.debug(f"CALL: create_ffgear_material\nsource_material (name) = {source_material.name}\nlocal_template_material (name) = {local_template_material.name}\nhard_reset = {hard_reset}")

    template_mat = None
    mtrl_data = None
    material_is_ancient = False
    false_mtrl_data = None


    # if no mtrl path, skip
    # UNLESS we got false data
    if not (hasattr(source_material, "ffgear") and source_material.ffgear.mtrl_filepath != ""):
        false_mtrl_data = construct_false_meddle_mtrl_data(source_material)
        if false_mtrl_data:
            logger.warning(f"This material had no mtrl file path but false mtrl data was constructed from Meddle properties: {source_material.name}")
        else:
            logger.error(f"Got to create_ffgear_material but couldn't find a mtrl path or construct false mtrl data, skipping: {source_material.name}")
            return False, "No MTRL or False Mtrl Data", None

    try:
        ##### Store Properties from Source Material #####
        old_ffgear_settings = {}
        if hasattr(source_material, "ffgear"):
            try:
                for prop in source_material.ffgear.bl_rna.properties:
                    if not prop.is_readonly:
                        old_ffgear_settings[prop.identifier] = getattr(source_material.ffgear, prop.identifier)
            except Exception as e:
                logger.warning(f"Could not read all FFGear properties from '{source_material.name}': {e}")

        old_custom_props = {}
        # Exclude the reserved '_RNA_UI' key
        for key in source_material.keys():
            if key != "_RNA_UI":
                try:
                    old_custom_props[key] = source_material[key]
                except Exception as e:
                     logger.warning(f"Could not read custom property '{key}' from '{source_material.name}': {e}")

        ##### Create a copy of the template material to work with #####
        template_mat = local_template_material.copy()

        ##### Cleanup & Name Changing #####
        # Clean up any duplicate node groups and images
        cleanup_duplicate_node_groups(template_mat, hard_reset)
        cleanup_duplicate_images(template_mat, hard_reset)

        # Set material name (Make sure it's at least in the same name category, even if it has a suffix)
        new_name = source_material.name
        if not new_name.startswith("FFGear "):
            new_name = f"FFGear {new_name}"
        template_mat.name = new_name
        actual_name = template_mat.name
        logger.debug(f"Tried renaming template mat to {new_name}, it ended up as {actual_name}")
        if new_name != actual_name:
            # Make sure the material doesn't have a numbered suffix 
            rename_datablock_to_original(template_mat, bpy.data.materials)
        

        ##### Apply Settings and Properties #####
        # Set material settings
        template_mat.surface_render_method = 'DITHERED'
        
        # Apply old FFGear settings to new material
        logger.debug(f"Applying old material's FFGear settings to template material")
        if hasattr(template_mat, "ffgear") and old_ffgear_settings:
            for prop, value in old_ffgear_settings.items():
                try:
                    # Check if property exists before setting
                    if hasattr(template_mat.ffgear, prop):
                        if prop in ["link_dyes"]: # Properties to skip applying
                            logger.debug(f"Skipping FFGear setting: \"{prop}\" with value: {value}")
                            continue
                        setattr(template_mat.ffgear, prop, value)
                    else:
                        logger.warning(f"Property '{prop}' not found on new material '{actual_name}'.")
                except Exception as e:
                    logger.warning(f"Could not set FFGear property '{prop}' on '{actual_name}': {e}")
        else:
            logger.error(f"Couldn't apply old FFGear settings to new material!")
        # logger.debug(f"FINISHED: Applying old material's FFGear settings to template material")

        # Apply old custom properties
        logger.debug("Applying old custom props to new material")
        for key, value in old_custom_props.items():
            try:
                template_mat[key] = value
            except Exception as e:
                # This might happen if the property type doesn't match or other issues
                logger.debug(f"Skipping applying custom property '{key}' to '{actual_name}': {e}")
        # logger.debug("FINISHED: Applying old custom props to new material")


        ##### Setup Texture Nodes #####
        logger.debug("Setting up texture nodes")
        nodes = template_mat.node_tree.nodes
        
        # Setup Diffuse texture (if it doesn't exist, delete the nodes used for it) and mark as ancient if needed.
        if template_mat.ffgear.diffuse_filepath:
            material_is_ancient = True
            setup_image_node(nodes, template_mat.ffgear.diffuse_filepath, "DIFFUSE TEXTURE")
        else:
            nodes.remove(nodes.get("DIFFUSE TEXTURE"))
            nodes.remove(nodes.get("DIFFUSE REROUTE"))

        # Setup ID texture
        if template_mat.ffgear.id_filepath:
            setup_image_node(nodes, template_mat.ffgear.id_filepath, "ID TEXTURE")
        
        # Setup mask texture
        if template_mat.ffgear.mask_filepath:
            setup_image_node(nodes, template_mat.ffgear.mask_filepath, "MASK TEXTURE")
        
        # Setup normal texture
        if template_mat.ffgear.normal_filepath:
            setup_image_node(nodes, template_mat.ffgear.normal_filepath, "NORMAL TEXTURE")
        # logger.debug("FINISHED: Setting up texture nodes")
        

        # Get dyes if possible, we don't really care if it succeeds or fails
        # logger.debug("Attempting to get meddle dyes")
        get_meddle_dyes(template_mat)
        # logger.debug("FINISHED: Attempting to get meddle dyes")


        ##### Color Ramps & Shader Settings #####
        false_mtrl_data_is_used = False
        # Update color ramps and Material Flags if MTRL file is specified
        if template_mat.ffgear.mtrl_filepath or false_mtrl_data:
            mtrl_filepath = bpy.path.abspath(template_mat.ffgear.mtrl_filepath)
            mtrl_data = mtrl_handler.read_mtrl_file(mtrl_filepath)
            if not mtrl_data:
                mtrl_data = false_mtrl_data # Use false data constructed from meddle properties on the material, not ideal
                false_mtrl_data_is_used = True
            if mtrl_data:
                if not update_color_ramps(template_mat, mtrl_data):
                    logger.warning(f"Failed to update color ramps for {template_mat.name}")
                apply_material_flags(template_mat, mtrl_data["material_flags"])
                # Get shader type
                shader_name = template_mat.get("ShaderPackage", None) # Try from meddle first since it's likely more accurate? Haven't seen mine fail yet but you never know
                if shader_name == None:
                    shader_name = mtrl_data.get('shader_name', None) # Get from mtrl file
                    if shader_name == None:
                        logger.error(f"Failed to get shader type for this material: {template_mat.name}")
        else:
            logger.error(f"Somehow we got really far into create_ffgear_material without a mtrl filepath or false mtrl data. Returning False for template material: {template_mat.name}")
            return False, "What the fuck?", None
        
        # Update legacy-dependent settings
        logger.debug("Updating legacy-dependent settings")
        if mtrl_data and not material_is_ancient:
            if shader_name == "characterlegacy.shpk":
                get_node_input_by_name(template_mat.node_tree.nodes["FFGear Shader"], 'Legacy Roughness Tweak').default_value = 0.5 # Enable the Legacy Roughness Tweak in the Shader (lowers roughness where specular is high)
                get_node_input_by_name(template_mat.node_tree.nodes["FFGear Shader"], 'Specularity Mult').default_value = 1.5 # Increase the specular map a bit
                get_node_input_by_name(template_mat.node_tree.nodes["FFGear Shader"], 'Roughness Mult').default_value = 0.4 # Lower roughness is often better on legacy shaders
                get_node_input_by_name(template_mat.node_tree.nodes["FFGear Shader"], 'Metallic Mult').default_value = 0 # Metallic should not be used on legacy shaders. Normally it's 0 anyways but just in case, I've seen it get an incorrect value when .mtrl is modded before.
                get_node_input_by_name(template_mat.node_tree.nodes["FFGear Shader"], 'Diffuse Gamma').default_value = 1.1 # Lower gamma a bit from 1.2 to brighten it since lower roughness often darkens
                get_node_input_by_name(template_mat.node_tree.nodes["FFGear Shader"], 'Minimum Roughness').default_value = 0.2 # Some legacy things become *too* shiny, though they're generally matte. This helps a little.

        if material_is_ancient:
            get_node_input_by_name(template_mat.node_tree.nodes["FFGear Shader"], 'Specularity Mult').default_value = 1.5
            get_node_input_by_name(template_mat.node_tree.nodes["FFGear Shader"], 'Roughness Mult').default_value = 0.5
            get_node_input_by_name(template_mat.node_tree.nodes["FFGear Shader"], 'Metallic Mult').default_value = 0 
            get_node_input_by_name(template_mat.node_tree.nodes["FFGear Shader"], 'Diffuse Gamma').default_value = 1.1
            get_node_input_by_name(template_mat.node_tree.nodes["FFGear Shader"], 'Minimum Roughness').default_value = 0.4
            get_node_input_by_name(template_mat.node_tree.nodes["FFGear Shader"], 'Material Rgh Influence').default_value = 0
            get_node_input_by_name(template_mat.node_tree.nodes["FFGear Shader"], 'Ancient').default_value = 1
        # logger.debug("FINISHED: Updating legacy-dependent settings")


        ##### RETURN ETC #####
        properties.collect_linked_materials(template_mat) # Look for links (ideally should only be done after *all* materials are created but this works.)
        if len(template_mat.ffgear.linked_materials) == 0: template_mat.ffgear.link_dyes = False # Set linking as False if there weren't any, just to make it more visually apparent that it's not linked to anything else.
        # ^^^ Doing this causes the collect_linked_materials function to be run again, and dissolves any existing groups.
        template_mat.ffgear.is_created = True # Set material as created
        
        if false_mtrl_data_is_used:
            template_mat.ffgear.created_without_mtrl = True
        
        if shader_name:
            message = "" if shader_name in ("character.shpk", "characterlegacy.shpk") else "Shader is of an unsupported type, results may not be as expected!"
        else:
            ""
        return True, message, template_mat
        
    except Exception as e:
        return False, str(e), None
    
    finally:
        logger.debug("DONE: create_ffgear_material")


#¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤#
# OPERATORS
#¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤#

class FFGearOpenMTRLBrowser(Operator):
    """File Select for the MTRL file"""
    bl_idname = "ffgear.open_mtrl_browser"
    bl_label = "Select MTRL File"
    bl_options = {'REGISTER', 'UNDO'}
    
    filepath: bpy.props.StringProperty(subtype="FILE_PATH", default="")
    filter_glob: bpy.props.StringProperty(default="*.mtrl", options={'HIDDEN'})
    
    relative_path: bpy.props.BoolProperty(
        name="Relative Path",
        description="Select the file relative to the blend file",
        default=True
    )
    
    def execute(self, context):
        if self.relative_path and bpy.data.is_saved:
            try:
                rel_path = bpy.path.relpath(self.filepath)
                context.material.ffgear.mtrl_filepath = rel_path
            except ValueError:
                context.material.ffgear.mtrl_filepath = self.filepath
        else:
            context.material.ffgear.mtrl_filepath = self.filepath
            
        return {'FINISHED'}
    
    def invoke(self, context, event):
        try: # Set the default path to the pre-existing one
            current_mtrl_path = context.material.ffgear.mtrl_filepath
            if current_mtrl_path:
                abs_path = bpy.path.abspath(current_mtrl_path)
                if os.path.exists(abs_path):
                    self.filepath = abs_path
        except Exception as e:
             logger.exception(f"Could not access 'context.material.ffgear.mtrl_filepath'. Error: {e}")
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}



class FFGearOpenDiffuseTextureBrowser(Operator):
    """File Select for the Diffuse Texture"""
    bl_idname = "ffgear.open_diffuse_browser"
    bl_label = "Select Diffuse Texture"
    bl_options = {'REGISTER', 'UNDO'}
    
    filepath: bpy.props.StringProperty(subtype="FILE_PATH", default="")
    filter_glob: bpy.props.StringProperty(
        default="*.jpg;*.jpeg;*.png;*.tif;*.tiff;*.exr",
        options={'HIDDEN'}
    )
    
    relative_path: bpy.props.BoolProperty(
        name="Relative Path",
        description="Select the file relative to the blend file",
        default=True
    )
    
    def execute(self, context):
        if self.relative_path and bpy.data.is_saved:
            try:
                rel_path = bpy.path.relpath(self.filepath)
                context.material.ffgear.diffuse_filepath = rel_path
            except ValueError:
                context.material.ffgear.diffuse_filepath = self.filepath
        else:
            context.material.ffgear.diffuse_filepath = self.filepath
        return {'FINISHED'}
    
    def invoke(self, context, event):
        try: # Set the default path to the pre-existing one
            current_diffuse_path = context.material.ffgear.diffuse_filepath
            if current_diffuse_path:
                abs_path = bpy.path.abspath(current_diffuse_path)
                if os.path.exists(abs_path):
                    self.filepath = abs_path
        except Exception as e:
             logger.exception(f"Could not access 'context.material.ffgear.diffuse_filepath'. Error: {e}")
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}



class FFGearOpenMaskTextureBrowser(Operator):
    """File Select for the Mask Texture"""
    bl_idname = "ffgear.open_mask_browser"
    bl_label = "Select Mask Texture"
    bl_options = {'REGISTER', 'UNDO'}
    
    filepath: bpy.props.StringProperty(subtype="FILE_PATH", default="")
    filter_glob: bpy.props.StringProperty(
        default="*.jpg;*.jpeg;*.png;*.tif;*.tiff;*.exr",
        options={'HIDDEN'}
    )
    
    relative_path: bpy.props.BoolProperty(
        name="Relative Path",
        description="Select the file relative to the blend file",
        default=True
    )
    
    def execute(self, context):
        if self.relative_path and bpy.data.is_saved:
            try:
                rel_path = bpy.path.relpath(self.filepath)
                context.material.ffgear.mask_filepath = rel_path
            except ValueError:
                context.material.ffgear.mask_filepath = self.filepath
        else:
            context.material.ffgear.mask_filepath = self.filepath
        return {'FINISHED'}
    
    def invoke(self, context, event):
        try: # Set the default path to the pre-existing one
            current_mask_path = context.material.ffgear.mask_filepath
            if current_mask_path:
                abs_path = bpy.path.abspath(current_mask_path)
                if os.path.exists(abs_path):
                    self.filepath = abs_path
        except Exception as e:
             logger.exception(f"Could not access 'context.material.ffgear.mask_filepath'. Error: {e}")
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}



class FFGearOpenNormalTextureBrowser(Operator):
    """File Select for the Normal Texture"""
    bl_idname = "ffgear.open_normal_browser"
    bl_label = "Select Normal Texture"
    bl_options = {'REGISTER', 'UNDO'}
    
    filepath: bpy.props.StringProperty(subtype="FILE_PATH", default="")
    filter_glob: bpy.props.StringProperty(
        default="*.jpg;*.jpeg;*.png;*.tif;*.tiff;*.exr",
        options={'HIDDEN'}
    )
    
    relative_path: bpy.props.BoolProperty(
        name="Relative Path",
        description="Select the file relative to the blend file",
        default=True
    )
    
    def execute(self, context):
        if self.relative_path and bpy.data.is_saved:
            try:
                rel_path = bpy.path.relpath(self.filepath)
                context.material.ffgear.normal_filepath = rel_path
            except ValueError:
                context.material.ffgear.normal_filepath = self.filepath
        else:
            context.material.ffgear.normal_filepath = self.filepath
        return {'FINISHED'}
    
    def invoke(self, context, event):
        try: # Set the default path to the pre-existing one
            current_normal_path = context.material.ffgear.normal_filepath
            if current_normal_path:
                abs_path = bpy.path.abspath(current_normal_path)
                if os.path.exists(abs_path):
                    self.filepath = abs_path
        except Exception as e:
             logger.exception(f"Could not access 'context.material.ffgear.normal_filepath'. Error: {e}")
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}



class FFGearOpenIDTextureBrowser(Operator):
    """File Select for the ID Texture"""
    bl_idname = "ffgear.open_id_browser"
    bl_label = "Select ID Texture"
    bl_options = {'REGISTER', 'UNDO'}
    
    filepath: bpy.props.StringProperty(subtype="FILE_PATH", default="")
    filter_glob: bpy.props.StringProperty(
        default="*.jpg;*.jpeg;*.png;*.tif;*.tiff;*.exr",
        options={'HIDDEN'}
    )
    
    relative_path: bpy.props.BoolProperty(
        name="Relative Path",
        description="Select the file relative to the blend file",
        default=True
    )
    
    def execute(self, context):
        if self.relative_path and bpy.data.is_saved:
            try:
                rel_path = bpy.path.relpath(self.filepath)
                context.material.ffgear.id_filepath = rel_path
            except ValueError:
                context.material.ffgear.id_filepath = self.filepath
        else:
            context.material.ffgear.id_filepath = self.filepath
        return {'FINISHED'}
    
    def invoke(self, context, event):
        try: # Set the default path to the pre-existing one
            current_id_path = context.material.ffgear.id_filepath
            if current_id_path:
                abs_path = bpy.path.abspath(current_id_path)
                if os.path.exists(abs_path):
                    self.filepath = abs_path
        except Exception as e:
             logger.exception(f"Could not access 'context.material.ffgear.id_filepath'. Error: {e}")
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}



class FFGearFetchMtrlTextures(Operator):
    """Read texture paths from the MTRL file and locate matching texture files"""
    bl_idname = "ffgear.fetch_mtrl_textures"
    bl_label = "Search Folder"
    bl_options = {'REGISTER', 'UNDO'}
    
    directory: bpy.props.StringProperty(
        name="Search Directory",
        description="Directory to search for texture files",
        subtype='DIR_PATH'
    )
    
    # Store texture search data between operator stages
    search_data = {}
    
    @classmethod
    def poll(cls, context):
        return (context.material and
                context.material is not None and 
                context.material.ffgear.mtrl_filepath != "")
    
    def execute(self, context):

        def _set_paths_on_material(diffuse_tex=None, mask_tex=None, norm_tex=None, id_tex=None):
            # Convert to relative paths and set on material (or try to at least, fails if the drive is different or the blend file isn't saved)
            if diffuse_tex:
                try:
                    context.material.ffgear.diffuse_filepath = bpy.path.relpath(diffuse_tex)
                except:
                    context.material.ffgear.diffuse_filepath = diffuse_tex
            if mask_tex:
                try:
                    context.material.ffgear.mask_filepath = bpy.path.relpath(mask_tex)
                except:
                    context.material.ffgear.mask_filepath = mask_tex
            if norm_tex:
                try:
                    context.material.ffgear.normal_filepath = bpy.path.relpath(norm_tex)
                except:
                    context.material.ffgear.normal_filepath = norm_tex
            if id_tex:
                try:
                    context.material.ffgear.id_filepath = bpy.path.relpath(id_tex)
                except:
                    context.material.ffgear.id_filepath = id_tex
                

        # If we have directory input, this is the second stage after folder selection
        if self.directory and self.search_data:
            diffuse_tex, mask_tex, norm_tex, id_tex = find_textures_from_mtrl(
                self.search_data, 
                Path(self.directory),
                recursive=True
            )
            
            # Count found textures
            found_count = sum(1 for x in (diffuse_tex, mask_tex, norm_tex, id_tex) if x)

            if found_count > 0:
                _set_paths_on_material(diffuse_tex, mask_tex, norm_tex, id_tex)
                self.report({'INFO'}, f"Found {found_count} texture{'s' if found_count > 1 else ''}")
            else:
                self.report({'WARNING'}, f"No matching texture files found in selected directory")

            # Clear stored data
            self.search_data.clear()
            return {'FINISHED'}
        
        # First stage - check MTRL directory
        chache_dir = None
        mtrl_filepath = bpy.path.abspath(context.material.ffgear.mtrl_filepath)
        mtrl_directory = Path(mtrl_filepath).parent
        # Check if any part of the path is "cache", we likely want to use that if that's the case
        if "\cache\\" in mtrl_filepath:
            index = mtrl_filepath.find("\cache\\")
            chache_dir = mtrl_filepath[:index + len("\cache\\")]
            logger.debug(f"Cache directory: {chache_dir}")
        else:
            logger.debug(f'Tried auto-detecting a path to check for textures in but couldn\'t find one with "\cache\\".')
        
        try:
            # Read MTRL data
            mtrl_data = mtrl_handler.read_mtrl_file(mtrl_filepath)
            
            if not mtrl_data:
                self.report({'ERROR'}, "Failed to read MTRL file")
                return {'CANCELLED'}
            
            if not mtrl_data.get('textures', []):
                self.report({'INFO'}, "No textures found in MTRL file")
                return {'FINISHED'}
            
            # Try local directory first, but starting at "cache" if that exists in the path
            diffuse_tex, mask_tex, norm_tex, id_tex = find_textures_from_mtrl(
                mtrl_data,
                Path(chache_dir) if chache_dir else mtrl_directory,
                recursive=True
            )

            found_count = sum(1 for x in (diffuse_tex, mask_tex, norm_tex, id_tex) if x)
            
            if found_count > 0:
                _set_paths_on_material(diffuse_tex, mask_tex, norm_tex, id_tex)
                self.report({'INFO'}, f"Found {found_count} texture{'s' if found_count > 1 else ''}")
                return {'FINISHED'}
            else:
                # Store data for second stage and show folder selection
                self.search_data = mtrl_data
                self.report({'INFO'}, "Select a directory to search")
                bpy.context.window_manager.fileselect_add(self)
                return {'RUNNING_MODAL'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Error processing MTRL file: {str(e)}")
            return {'CANCELLED'}



class FFGearCopyTexturePaths(Operator):
    """Copy texture paths from active material to all variants (such as "_a_" and "_b_").
    Hold Ctrl to only consider materials on this object.
    Holt Alt to only consider materials on this object even if it's not a variant"""
    bl_idname = "ffgear.copy_texture_paths"
    bl_label = "Copy to Other Materials"
    bl_options = {'REGISTER', 'UNDO'}
    
    consider_local_materials: bpy.props.BoolProperty(
        name="Consider Only Local Materials",
        description="Only consider materials that are on this object",
        default=False
    )

    disregard_name_match: bpy.props.BoolProperty(
        name="Disregard Name Matching",
        description="Copy the textures to all materials on the object even if they are not a variant of this material",
        default=False
    )

    @classmethod
    def poll(cls, context):
        return (context.material and
                context.material is not None)
    
    def execute(self, context):
        source_material = context.material
        
        if not self.consider_local_materials and not self.disregard_name_match:
            # All other materials
            other_materials_we_care_about = [material for material in bpy.data.materials
                                             if material != source_material]
        else:
            # Other materials on the object
            other_materials_we_care_about = [slot.material for slot in context.object.material_slots 
                                             if slot.material and slot.material != source_material]

        if self.disregard_name_match:
            # Name can be whatever
            matching_materials = other_materials_we_care_about
        else:
            # Material must have a variant name
            matching_materials = [material for material in other_materials_we_care_about
                                  if helpers.compare_strings_for_one_difference(source_material.name, material.name)]
        
        updated_count = 0
        for material in matching_materials:
            if hasattr(material, 'ffgear'):
                material.ffgear.diffuse_filepath = source_material.ffgear.diffuse_filepath
                material.ffgear.id_filepath = source_material.ffgear.id_filepath
                material.ffgear.mask_filepath = source_material.ffgear.mask_filepath
                material.ffgear.normal_filepath = source_material.ffgear.normal_filepath
                updated_count += 1
        
        if updated_count > 0:
            self.report({'INFO'}, f"Copied texture paths to {updated_count} materials")
        else:
            self.report({'INFO'}, f"Found no matching materials")
        return {'FINISHED'}
    
    def invoke(self, context, event):
        # Store events
        self.consider_all_materials = True if event.ctrl else False
        self.disregard_name_match = True if event.alt else False
        return self.execute(context) # Gotta return something, saw an example of this and it works.



class FFGearFetchMeddleTextures(Operator):
    """Read and set texture paths directly from the Meddle data in the custom properties"""
    bl_idname = "ffgear.fetch_meddle_textures"
    bl_label = "Meddle Cache"
    bl_options = {'REGISTER', 'UNDO'}
    
    directory: bpy.props.StringProperty(
        name="Meddle Cache Directory",
        description="Directory containing Meddle cached files",
        subtype='DIR_PATH'
    )
    filter_glob: bpy.props.StringProperty(default="*.nofilesplease", options={'HIDDEN'})
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

    @classmethod
    def poll(cls, context):
        return (context.material and
                context.material is not None)
    
    def execute(self, context):
        material = context.material
        try:

            # Try to calculate the meddle cache path from the existing paths, if we don't already have one
            if not self.directory:
                try:
                    paths_to_check = [material.ffgear.mtrl_filepath, material.ffgear.diffuse_filepath, material.ffgear.mask_filepath, material.ffgear.normal_filepath, material.ffgear.id_filepath]
                    found_path = None
                    for path_to_check in paths_to_check:
                        if path_to_check != None and not found_path: # If we already found one, skip. And it has to be a valid path.
                            found_path = path_to_check
                    if found_path:
                        if "\cache\\" in found_path:
                            index = found_path.find("\cache\\")
                            self.directory = found_path[:index + len("\cache\\")]
                except Exception as e:
                    logger.warning(f"Could not calculate meddle cache path from existing paths: {e}")

            # If we still don't have the directory input, get it from the user via modal
            if not self.directory:
                self.report({'INFO'}, "Select the meddle cache directory")
                context.window_manager.fileselect_add(self)
                return {'RUNNING_MODAL'}
            
            elif self.directory: # We do have the directory, set up the files!

                diffuse_tex_path, mask_tex_path, norm_tex_path, id_tex_path = get_textures_from_meddle_data(self.directory, material)
                if diffuse_tex_path == None and id_tex_path == None and mask_tex_path == None and norm_tex_path == None:
                    self.report({'ERROR'}, f"No textures from Meddle in the material's custom properties")
                    return {'CANCELLED'}
                # Update paths:
                if diffuse_tex_path:
                    material.ffgear.diffuse_filepath = diffuse_tex_path
                if mask_tex_path:
                    material.ffgear.mask_filepath = mask_tex_path
                if norm_tex_path:
                    material.ffgear.normal_filepath = norm_tex_path
                if id_tex_path:
                    material.ffgear.id_filepath = id_tex_path
                return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Error getting texture paths from Meddle data: {str(e)}")
            return {'CANCELLED'}



class FFGearGetDyesFromMeddle(Operator):
    """Get the dyes that are stored in the material's exported Meddle data.\nOnly works with models exported using Meddle 0.1.29 or later"""
    bl_idname = "ffgear.get_meddle_dyes"
    bl_label = "Get Dyes From Meddle"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return context.object is not None
    
    def execute(self, context):
        success, message = get_meddle_dyes(context.material)
        if success == False:
            self.report({'ERROR'}, message)
        return {'FINISHED'}



class FFGearMeddleSetup(Operator):
    """Automatically set up materials using a Meddle cache directory.
    Hold CTRL to only affect selected objects."""
    bl_idname = "ffgear.meddle_setup"
    bl_label = "Select Meddle Cache Folder"
    bl_options = {'REGISTER', 'UNDO'}
    
    directory: bpy.props.StringProperty(
        name="Meddle Cache Directory",
        description="Directory containing Meddle cached files",
        subtype='DIR_PATH'
    )
    filter_glob: bpy.props.StringProperty(default="*.nofilesplease", options={'HIDDEN'})
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    
    # Somewhere to store the CTRL key state
    use_selected: bpy.props.BoolProperty(
        name="Use Selected Only",
        description="Only process materials on selected objects",
        default=False
    )

    # Dictionary to store found MTRL files
    mtrl_cache = {}
    
    first_execution = True

    @property
    def prefs(self):
        # __package__ is "bl_ext.user_default.FFGear", the user_default part can vary
        return bpy.context.preferences.addons[__package__].preferences

    @classmethod
    def poll(cls, context):
        return (context.material and
                context.material is not None and 
                hasattr(context.material, "ffgear"))
    
    # Good, could fail if the paths update from cache/chara... to something else
    def find_all_mtrl_files(self, cache_dir):
        """
        Find and cache all MTRL files in the cache directory
        
        Args:
            cache_dir: The meddle cache directory to search
            
        Returns:
            dictionary: A cache of all found relevant mtrl-files. The key is the name of the file while the value is the full filepath.
        """
        if not self.mtrl_cache:
            equipment_dir = Path(cache_dir) / "chara" / "equipment"
            accessory_dir = Path(cache_dir) / "chara" / "accessory"
            weapon_dir = Path(cache_dir) / "chara" / "weapon" # Weapon shaders and materials have not been tested much
            
            # Search recursively for all .mtrl files in EQUIPMENT FOLDER
            for mtrl_file in equipment_dir.rglob("*.mtrl"):
                self.mtrl_cache[mtrl_file.name] = str(mtrl_file)

            # Search recursively for all .mtrl files in ACCESSORY FOLDER
            for mtrl_file in accessory_dir.rglob("*.mtrl"):
                self.mtrl_cache[mtrl_file.name] = str(mtrl_file)

            # Search recursively for all .mtrl files in WEAPON FOLDER
            for mtrl_file in weapon_dir.rglob("*.mtrl"):
                self.mtrl_cache[mtrl_file.name] = str(mtrl_file)
                
            logger.debug(f"Found {len(self.mtrl_cache)} MTRL files in cache")

    # Good, Only used for old meddle exports
    def find_mtrl_file(self, cache_dir, material_name):
        """Find corresponding MTRL file in Meddle cache""" # OLD METHOD
        base_name = re.split(r'_character(?:legacy)?_', material_name)[0] # Splits the material name on every occurence of "character_" or "characterlegacy_" || ONLY FOR PRE 0.1.29
        mtrl_name = f"{base_name}.mtrl"

        if mtrl_name.startswith("FFGear "):
            mtrl_name = mtrl_name[7:] # Everything after "FFGear ", trim that away so that mtrl_name doesn't have that

        # Initialize cache if needed
        if not self.mtrl_cache:
            self.find_all_mtrl_files(cache_dir)

        return self.mtrl_cache.get(mtrl_name)

    # Much like create_ffgear_material works in the normal material processing, except before it calls create_ffgear_material it automatically sets up other things from meddle
    def process_meddle_material(self, material, local_template_material, hard_reset=False):
        """Process a single material with Meddle setup"""
        if not material.name:
            return False, "No material name", None

        # Find MTRL file
        try:
            mtrl_path = os.path.join(self.directory, material["MtrlCachePath"]) # Primary method of getting the mtrl file
        except KeyError: # Key didn't exist, it's likely an old meddle export
            logger.warning("MTRL file not found in material properties, searching using old method.")
            mtrl_path = self.find_mtrl_file(self.directory, material.name) # This old method often doesn't find modded .mtrl files, but that's because they literally just don't exist in old exports it seems.
        except Exception as e:
            logger.exception(f"Unknown exception reached when looking for MTRL file: {e}")
            return False, "No MTRL file found", None
        if not mtrl_path:
            # Check if fake mtrl data can be constructed instead, happens in create_ffgear_material
            logger.warning("No mtrl file found, proceeding anyways to try and use Meddle ColorTable data.")
            pass
            

        # Get texture paths from Meddle data on material
        diffuse_tex_path, mask_tex_path, norm_tex_path, id_tex_path = get_textures_from_meddle_data(self.directory, material)
        
        # If we couldn't get them using the modern meddle data method, try the old method
        if diffuse_tex_path == None and id_tex_path == None and mask_tex_path == None and norm_tex_path == None and mtrl_path:
            logger.warning(f"Failed to get texture paths from custom material properties on {material.name}, serching disk instead.")
            # Read MTRL data and find textures using shared function
            mtrl_data = mtrl_handler.read_mtrl_file(mtrl_path)
            if not mtrl_data:
                return False, "Failed to read MTRL file", None
            diffuse_tex_path, mask_tex_path, norm_tex_path, id_tex_path = find_textures_from_mtrl(
                mtrl_data, 
                Path(self.directory),
                recursive=True
            )

        if diffuse_tex_path == None and id_tex_path == None and mask_tex_path == None and norm_tex_path == None:
            logger.warning(f"Still no textures found for {material.name}, but proceeding anyways! :D")

        # Update paths on material
        if mtrl_path:
            material.ffgear.mtrl_filepath = mtrl_path
        if diffuse_tex_path:
            material.ffgear.diffuse_filepath = diffuse_tex_path
        if mask_tex_path:
            material.ffgear.mask_filepath = mask_tex_path
        if norm_tex_path:
            material.ffgear.normal_filepath = norm_tex_path
        if id_tex_path:
            material.ffgear.id_filepath = id_tex_path

        # Create FFGear material
        success, message, new_material = create_ffgear_material(material, local_template_material, False)

        if success and message != "":
            self.report({'WARNING'}, message)

        return success, message, new_material

    def execute(self, context):
        if not self.directory:
            self.report({'ERROR'}, "No cache directory selected")
            return {'CANCELLED'}
        
        # # PROFILING START
        # pr = cProfile.Profile()
        # pr.enable()

        # If a file was (somehow) selected rather than a directory
        if not os.path.isdir(self.directory):
            self.directory = os.path.dirname(self.directory)

        cache_dir = Path(self.directory)
        if not cache_dir.exists():
            self.report({'ERROR'}, "Selected directory does not exist")
            return {'CANCELLED'}
        
        # Clear the cache at the start of execution
        self.mtrl_cache.clear()
        
        # First, collect all materials from selected objects that we want to process
        source_materials = set()
        for obj in context.selected_objects:
            for slot in obj.material_slots:
                if (slot.material and material_name_is_valid(slot.material.name) and not slot.material.ffgear.is_created):
                    source_materials.add(slot.material)

        if not source_materials:
            self.report({'WARNING'}, "No valid materials found on selected objects")
            return {'CANCELLED'}

        # Get the objects to process these materials on
        target_objects = context.selected_objects if self.use_selected else bpy.data.objects
        
        # Create filter function that only accepts the source materials
        def filter_func(mat):
            return mat in source_materials

        # Collect material slots
        material_mapping = collect_material_slots_for_objects(
            target_objects, 
            filter_func
        )

        if not material_mapping:
            self.report({'WARNING'}, "No valid materials found to process")
            return {'CANCELLED'}
        
        # Process materials
        processed, skipped = process_shared_materials(
            material_mapping,
            hard_reset=False,
            process_func = lambda mat, ltm, hrs: self.process_meddle_material(mat, ltm, hrs)
        )

        # Report results
        if processed > 0:
            scope = "selected objects" if self.use_selected else "all objects"
            self.report({'INFO'}, f"Processed {len(source_materials)} materials across {scope}" + 
                    (f", skipped {skipped}" if skipped > 0 else ""))
        else:
            if self.mtrl_cache == {}:
                # haha amogus ඞ
                self.report({'WARNING'}, "No MTRL files found! Make sure those are cached in Meddle!")
            else:
                self.report({'WARNING'}, "No materials were processed")
            
        # # PROFILING END
        # pr.disable()
        # # Analysis
        # s = io.StringIO()
        # # Sort stats by cumulative time spent in function
        # sortby = pstats.SortKey.TIME
        # ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
        # ps.print_stats()
        # print("\n--- PROFILING RESULTS ---")
        # print(s.getvalue())
        # print("--- END PROFILING RESULTS ---\n")

        return {'FINISHED'}
    
    def invoke(self, context, event):
        self.use_selected = event.ctrl
        if self.prefs and self.prefs.default_meddle_import_path:
            self.filepath = self.prefs.default_meddle_import_path
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}



class FFGearAutoMaterial(Operator):
    """Create or Reset an FFGear setup for only this material, on all objects using it.
    Hold CTRL to only affect the selected objects.
    Hold Shift to affect all materials on all selected objects.
    Hold Alt to perform a hard reset, replacing existing addon assets and textures with the ones on disk. Some duplicate data blocks may be created."""
    bl_idname = "ffgear.automaterial"
    bl_label = "Create/Reset All Materials"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return (context.material is not None and 
                hasattr(context.material, "ffgear"))
    
    def invoke(self, context, event):
        # Store events
        affect_all_on_selected = True if event.shift else False
        selected_only = True if event.ctrl else False
        do_full_reset = True if event.alt else False
        
        # If ctrl, all we care about are the selected objects.
        if selected_only:
            objects_to_potentially_manipulate = context.selected_objects
            if not objects_to_potentially_manipulate:
                self.report({'WARNING'}, "No objects selected")
                return {'CANCELLED'}
        else:
            objects_to_potentially_manipulate = bpy.data.objects

        # Get the materials to process
        materials_to_process = []
        if affect_all_on_selected:
            for object in context.selected_objects:
                for matslot in object.material_slots:
                    if hasattr(matslot.material, "ffgear") and material_name_is_valid(matslot.material.name) and matslot.material.ffgear.mtrl_filepath != "":
                        materials_to_process.append(matslot.material)
        else:
            the_material = context.material
            if hasattr(the_material, "ffgear") and material_name_is_valid(the_material.name) and matslot.material.ffgear.mtrl_filepath != "":
                materials_to_process.append(the_material)
            
        def filter_func(mat):
            return mat in materials_to_process
            
        # Collect material slots
        material_mapping = collect_material_slots_for_objects(objects_to_potentially_manipulate, filter_func)
        
        if not material_mapping:
            self.report({'WARNING'}, "No matching materials found on any applicable objects")
            return {'CANCELLED'}
            
        # Process materials
        processed, skipped = process_shared_materials(
            material_mapping=material_mapping,
            hard_reset=do_full_reset,
            process_func = lambda mat, ltm, hrs: create_ffgear_material(mat, ltm, hrs)
        )
        
        # Report results
        if processed > 0:
            scope = "selected objects" if selected_only else "scene"
            self.report({'INFO'}, f"Processed {processed} materials in {scope}" +
                       (f", skipped {skipped}" if skipped > 0 else ""))
        else:
            self.report({'WARNING'}, "No materials were processed")
            
        return {'FINISHED'}



class FFGearUpdateDyedRamps(Operator):
    """Update the material's color ramps with dye information.
    Hold Alt to perform a hard reset, recalculating every value on every color ramp from the mtrl file instead of just the ones a dye would affect"""
    bl_idname = "ffgear.update_dyed_ramps"
    bl_label = "Update Color Ramps"
    bl_options = {'REGISTER', 'UNDO'}

    hard_reset: bpy.props.BoolProperty(
        name="Perform Hard Reset",
        description="Recalculate every value on every color ramp in the material, based on what's in the mtrl file. When this is off values that can't be dyed will be left alone",
        default=False
    )

    @classmethod
    def poll(cls, context):
        # Poll checking context for when the operator is called from the UI
        return (hasattr(context, 'material') and
                context.material is not None and
                hasattr(context.material, 'ffgear') and
                context.material.ffgear.mtrl_filepath != "")

    # classmethod for direct updates when called from elsewhere (properties.py, mainly)
    @classmethod
    def perform_update_on_material(cls, material, hard_reset=False):
        """
        Performs the core ramp update logic on a specifically provided material.

        Args:
            material (bpy.types.Material): The material to update.
            hard_reset (bool): Whether to perform a hard reset.

        Returns:
            bool: True if successful, False otherwise.
        """

        logger.debug(f"CALL: perform_update_on_material (color-ramp update, used externally or with the update ramps button) on: {material.name}")

        if not material:
            logger.error("Error in perform_update_on_material: No material provided.")
            return False
        if not hasattr(material, 'ffgear') or not material.ffgear.mtrl_filepath:
            logger.error(f"Error in perform_update_on_material: Material '{material.name}' lacks prerequisites (ffgear props or mtrl path).")
            return False

        logger.debug(f"Updating ramps for '{material.name}' (Hard Reset: {hard_reset}).")
        mtrl_filepath = bpy.path.abspath(material.ffgear.mtrl_filepath)

        try:
            # Read MTRL data
            mtrl_data = mtrl_handler.read_mtrl_file(mtrl_filepath)

            if not mtrl_data:
                logger.error(f"Failed to read MTRL file for {material.name}")
                return False

            # Update color ramps
            success = update_color_ramps(material, mtrl_data, hard_reset)

            return success

        except Exception as e:
            logger.exception(f"Error during ramp update for {material.name}: {str(e)}")
            return False


    def execute(self, context):
        # Standard execute calls the classmethod using the context material
        cont_mat = context.material
        cont_props = cont_mat.ffgear
        logger.debug(f"Executing update operator for context material: {cont_mat.name}")

        other_mats = cont_props.linked_materials
        is_linked = cont_props.link_dyes and len(other_mats) > 0
        if is_linked:
            mats_to_update = {cont_mat}.union({item.mat for item in cont_props.linked_materials if item.mat}) # Creates a Set with the other linked mats
        else:
            mats_to_update = {cont_mat}
        
        logger.debug(f"Updating these materials' color ramps: {mats_to_update}")
        
        total_mats = len(mats_to_update)
        successes = 0
        for mat in mats_to_update:
            try:
                successes += 1 if self.perform_update_on_material(mat, self.hard_reset) else 0 # Does this syntax work? It seems to
            except Exception as e:
                logger.exception(f"Exception when updating color ramps for {mat.name}: {e}")
        if successes == total_mats:
            self.report({'INFO'}, "Color ramps updated successfully")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, f"Failed to update color ramps for at least one material in {mats_to_update}")
            return {'CANCELLED'}

    def invoke(self, context, event):
        # Store alt key state for hard_reset
        self.hard_reset = True if event.alt else False
        # Call execute directly
        return self.execute(context)




#¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤#
# REGISTER AND UNREGISTER
#¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤#

def register():
    bpy.utils.register_class(FFGearOpenMTRLBrowser)
    bpy.utils.register_class(FFGearMeddleSetup)
    bpy.utils.register_class(FFGearFetchMtrlTextures)
    bpy.utils.register_class(FFGearFetchMeddleTextures)
    bpy.utils.register_class(FFGearOpenDiffuseTextureBrowser)
    bpy.utils.register_class(FFGearOpenIDTextureBrowser)
    bpy.utils.register_class(FFGearOpenMaskTextureBrowser)
    bpy.utils.register_class(FFGearOpenNormalTextureBrowser)
    bpy.utils.register_class(FFGearAutoMaterial)
    bpy.utils.register_class(FFGearUpdateDyedRamps)
    bpy.utils.register_class(FFGearCopyTexturePaths)
    # bpy.utils.register_class(FFGearUpdateAllRamps)
    bpy.utils.register_class(FFGearGetDyesFromMeddle)

def unregister():
    bpy.utils.unregister_class(FFGearGetDyesFromMeddle)
    # bpy.utils.unregister_class(FFGearUpdateAllRamps)
    bpy.utils.unregister_class(FFGearCopyTexturePaths)
    bpy.utils.unregister_class(FFGearUpdateDyedRamps)
    bpy.utils.unregister_class(FFGearAutoMaterial)
    bpy.utils.unregister_class(FFGearOpenNormalTextureBrowser)
    bpy.utils.unregister_class(FFGearOpenMaskTextureBrowser)
    bpy.utils.unregister_class(FFGearOpenIDTextureBrowser)
    bpy.utils.unregister_class(FFGearOpenDiffuseTextureBrowser)
    bpy.utils.unregister_class(FFGearFetchMeddleTextures)
    bpy.utils.unregister_class(FFGearFetchMtrlTextures)
    bpy.utils.unregister_class(FFGearMeddleSetup)
    bpy.utils.unregister_class(FFGearOpenMTRLBrowser)