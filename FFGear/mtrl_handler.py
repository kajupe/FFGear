import struct
import math
import logging
from . import helpers
from io import BytesIO
from enum import Flag, Enum
from typing import List, Optional, Dict, Any

# Level is a threshold, errors have to be WARNING or higher to be pushed through. I think it goes DEBUG < INFO < WARNING < ERROR < CRITICAL
logging.basicConfig()
logger = logging.getLogger('FFGear.mtrl')
logger.setLevel(logging.INFO)

###¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤###
### Code heavily inspired by how the xivModdingFramework and TexTools reads the .mtrl format ###
### https://github.com/TexTools/xivModdingFramework                                          ###
###¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤###

class MaterialFlags(Flag):
    HideBackfaces = 0x1
    Bit1 = 0x2
    Bit2 = 0x4
    Bit3 = 0x8
    EnableTranslucency = 0x10
    Bit5 = 0x20
    Bit6 = 0x40
    Bit7 = 0x80
    Bit8 = 0x100
    Bit9 = 0x200
    Bit10 = 0x400
    Bit11 = 0x800
    Bit12 = 0x1000
    Bit13 = 0x2000
    Bit14 = 0x4000
    Bit15 = 0x8000
    Bit16 = 0x10000
    Bit17 = 0x20000
    Bit18 = 0x40000
    Bit19 = 0x80000
    Bit20 = 0x100000
    Bit21 = 0x200000
    Bit22 = 0x400000
    Bit23 = 0x800000
    Bit24 = 0x1000000
    Bit25 = 0x2000000
    Bit26 = 0x4000000
    Bit27 = 0x8000000
    Bit28 = 0x10000000
    Bit29 = 0x20000000
    Bit30 = 0x40000000
    Bit31 = 0x80000000


DYE_FLAGS = {
    # Byte 1 flags (0-7)
    'dye_diffuse': (0, 0),
    'dye_specular': (0, 1),
    'dye_emissive': (0, 2),
    'dye_emissive_unknown': (0, 3),
    'dye_metallic': (0, 4),
    'dye_roughness': (0, 5),
    'dye_sheen_rate': (0, 6),
    'dye_sheen_aperture': (0, 7),
    # Byte 2 flags (8-15)
    'dye_sheen_tint_rate': (1, 0),
    'dye_anisotropy': (1, 1),
    'dye_sphere_map_id': (1, 2),
    'dye_sphere_map_opacity': (1, 3)
}


class ColorsetType(Enum):
    """How big is each possible version of colorset data"""
    ENDWALKER = 512  # bytes (16 rows)
    DAWNTRAIL = 2048 # bytes (32 rows)


def extract_dye_flags(byte1: int, byte2: int) -> Dict[str, bool]:
    """Extracts boolean dye flags from two bytes of data into a dictionary for easier lookup."""
    flags = {}
    bytes_array = [byte1, byte2]
    for flag_name, (byte_idx, bit_idx) in DYE_FLAGS.items():
        flags[flag_name] = bool(bytes_array[byte_idx] & (1 << bit_idx))
    return flags


# Math yoinked from Penumbra. Handles the tile material transformation values. I hate this.
def decompose_tile_matrix(uu: float, uv: float, vu: float, vv: float) -> Dict[str, float]:
    """
    Decomposes a 2x2 tile transformation matrix into scale, rotation, and shear.
    Assumes matrix elements uu, uv, vu, vv correspond to [a, b], [c, d].

    Returns:
        Dict[str, float]: Contains 'scale_x', 'scale_y', 'rotation_deg', 'shear_deg'.
    """
    a, b, c, d = uu, uv, vu, vv # Standard matrix notation

    # Prevent precision errors, if it's *close* to zero it's probably zero
    if abs(a) < 1e-9 and abs(c) < 1e-9:
        logger.warning("Matrix decomposition ran into a near-zero first column. Results could be inaccurate.")
        rotation_rad = 0.0
    else:
        rotation_rad = math.atan2(c, a)

    cos_rot = math.cos(rotation_rad)
    sin_rot = math.sin(rotation_rad)

    # Apply inverse rotation: M' = R^T * M
    m_prime_00 = cos_rot * a + sin_rot * c
    m_prime_01 = cos_rot * b + sin_rot * d
    m_prime_11 = -sin_rot * b + cos_rot * d

    # Extract Scale
    scale_x = m_prime_00
    scale_y = m_prime_11

    # Extract Shear
    shear_rad = 0.0
    if abs(scale_y) > 1e-6 and abs(m_prime_01) > 1e-6:
        try:
            tan_shear = m_prime_01 / scale_y
            shear_rad = math.atan(tan_shear)
        except ValueError:
             logger.warning(f"ValueError during shear calculation (atan). Inputs: m_prime_01={m_prime_01}, scale_y={scale_y}")
             shear_rad = 0.0
    elif abs(m_prime_01) > 1e-6:
         logger.warning(f"Near-zero scale_y ({scale_y:.4f}) with non-zero shear component ({m_prime_01:.4f}). Shear calculation skipped.")

    # Convert angles to degrees
    rotation_deg = math.degrees(rotation_rad)
    shear_deg = math.degrees(shear_rad)

    # Invert it to stay in line with Penumbra, less confusing
    shear_deg = -shear_deg

    return {
        'scale_x': scale_x,
        'scale_y': scale_y,
        'rotation_deg': rotation_deg,
        'shear_deg': shear_deg
    }


def read_mtrl_file(filepath: str) -> Optional[Dict[str, Any]]:
    """
    Reads a mtrl file, extracts material properties, textures,
    and colorset data (now with proper tile transformations).
    Assumes little-endian byte order.

    Args:
        filepath (str): Path to the .mtrl file.

    Returns:
        mtrl_data (dict): A dictionary containing the parsed data, or None if an error occurs.
    """
    try:
        filepath = helpers.safe_filepath(filepath)
        with open(filepath, 'rb') as f:
            data = f.read()
    except FileNotFoundError:
        logger.error(f"MTRL file not found at: {filepath}")
        return None
    except IOError as e:
        logger.error(f"IOError reading MTRL file {filepath}: {e}")
        return None

    with BytesIO(data) as br:
        try:
            # HEADER
            # Signature (4 bytes, uint)
            signature = struct.unpack('<I', br.read(4))[0]
            if signature != 16973824:
                logger.error(f"Invalid MTRL signature: expected 16973824, got {signature}")
                return None

            # Header fields (ushorts and bytes)
            file_size = struct.unpack('<H', br.read(2))[0]
            color_set_data_size = struct.unpack('<H', br.read(2))[0]
            string_block_size = struct.unpack('<H', br.read(2))[0]
            shader_name_offset = struct.unpack('<H', br.read(2))[0]
            texture_count = struct.unpack('<B', br.read(1))[0]
            map_count = struct.unpack('<B', br.read(1))[0]
            colorset_count = struct.unpack('<B', br.read(1))[0]
            additional_data_size = struct.unpack('<B', br.read(1))[0]


            # TEXTURE INFO
            texture_offsets = []
            texture_flags_from_header = []

            for _ in range(texture_count):
                offset = struct.unpack('<H', br.read(2))[0]
                flags = struct.unpack('<H', br.read(2))[0]
                texture_offsets.append(offset)
                texture_flags_from_header.append(flags)

            # Skip map and colorset info block (4 bytes per entry)
            br.seek((map_count + colorset_count) * 4, 1)
            string_block_start = br.tell()

            # Strings with Texture Paths and the Shader Name
            textures = []
            for i in range(texture_count):
                abs_seek_pos = string_block_start + texture_offsets[i]
                if abs_seek_pos >= br.getbuffer().nbytes:
                     logger.warning(f"Texture {i} offset {texture_offsets[i]} points outside file bounds ({abs_seek_pos}). Skipping.")
                     continue

                br.seek(abs_seek_pos)
                path_bytes = []
                while (char := br.read(1)) != b'\0' and char:
                    path_bytes.append(char)

                textures.append({
                    'path': b''.join(path_bytes).decode('utf-8', errors='replace'),
                    'flags': texture_flags_from_header[i]
                })

            br.seek(string_block_start + shader_name_offset)
            shader_bytes = []
            while (char := br.read(1)) != b'\0' and char:
                shader_bytes.append(char)
            shader_name = b''.join(shader_bytes).decode('utf-8', errors='replace')


            # COLORSET DATA
            br.seek(string_block_start + string_block_size + additional_data_size)
            color_data_start = br.tell()
            colorset_data:List[Dict[str,Any]] = []
            colorset_type = None
            row_count = 0

            if color_set_data_size > 0:
                # Determine format based on size
                if color_set_data_size >= 2048:
                    colorset_type = ColorsetType.DAWNTRAIL; row_count = 32
                elif color_set_data_size >= 512:
                    colorset_type = ColorsetType.ENDWALKER; row_count = 16
                else:
                    logger.warning(f"Unexpected color_set_data_size: {color_set_data_size}. Cannot determine colorset type.")
                    return None

                def read_le_half_float(field_name_debug=""):
                    """Reads 2 bytes, unpacks as little-endian half-float."""
                    raw_bytes = br.read(2)
                    if len(raw_bytes) < 2:
                        raise EOFError(f"Unexpected EOF reading half-float for {field_name_debug}.")
                    value = struct.unpack('<e', raw_bytes)[0]
                    return value

                # Read colorset rows
                for i in range(row_count):
                    # DIFFUSE
                    diffuse_r = read_le_half_float()            # 0
                    diffuse_g = read_le_half_float()            # 1
                    diffuse_b = read_le_half_float()            # 2
                    diffuse_unknown = read_le_half_float()      # 3, Gloss Strength (Legacy)

                    # SPECULAR
                    specular_r = read_le_half_float()           # 4
                    specular_g = read_le_half_float()           # 5
                    specular_b = read_le_half_float()           # 6
                    specular_unknown = read_le_half_float()     # 7, Specular Strength/Power (Legacy)

                    # EMISSIVE
                    emissive_r = read_le_half_float()           # 8
                    emissive_g = read_le_half_float()           # 9
                    emissive_b = read_le_half_float()           # 10
                    emissive_unknown = read_le_half_float()     # 11

                    # SHEEN
                    sheen_rate = read_le_half_float()           # 12
                    sheen_tint_rate = read_le_half_float()      # 13
                    sheen_aperture = read_le_half_float()       # 14, Could also be Sheen Aptitude but whatever
                    sheen_unknown = read_le_half_float()        # 15

                    # PBR
                    roughness = read_le_half_float()            # 16
                    pbr_unknown = read_le_half_float()          # 17
                    metalness = read_le_half_float()            # 18
                    anisotropy_blending = read_le_half_float()  # 19

                    # WEIRD SHIT
                    effect_unknown_r = read_le_half_float()     # 20
                    sphere_map_opacity = read_le_half_float()   # 21
                    effect_unknown_b = read_le_half_float()     # 22
                    effect_unknown_a = read_le_half_float()     # 23

                    # IDs AND STUFF
                    shader_template_id = read_le_half_float()   # 24
                    tile_map_id_raw = read_le_half_float()      # 25
                    tile_map_opacity = read_le_half_float()     # 26
                    sphere_map_id = read_le_half_float()        # 27

                    # RAW TILE TRANSFORM DATA
                    tile_matrix_uu = read_le_half_float()       # 28
                    tile_matrix_uv = read_le_half_float()       # 29
                    tile_matrix_vu = read_le_half_float()       # 30
                    tile_matrix_vv = read_le_half_float()       # 31

                    # Decompose the tile matrix
                    tile_transform = decompose_tile_matrix(
                        tile_matrix_uu, tile_matrix_uv, tile_matrix_vu, tile_matrix_vv
                    )

                    row_data = {
                        'row_number': i + 1,
                        'group': 'A' if i % 2 == 0 else 'B',
                        'diffuse': [diffuse_r, diffuse_g, diffuse_b],
                        'diffuse_unknown': diffuse_unknown,
                        'specular': [specular_r, specular_g, specular_b],
                        'specular_unknown': specular_unknown,
                        'emissive': [emissive_r, emissive_g, emissive_b],
                        'emissive_unknown': emissive_unknown,
                        'sheen_rate': sheen_rate,
                        'sheen_tint_rate': sheen_tint_rate,
                        'sheen_aperture': sheen_aperture,
                        'sheen_unknown': sheen_unknown,
                        'roughness': roughness,
                        'pbr_unknown': pbr_unknown,
                        'metalness': metalness,
                        'anisotropy_blending': anisotropy_blending,
                        'effect_unknown_r': effect_unknown_r,
                        'sphere_map_opacity': sphere_map_opacity,
                        'effect_unknown_b': effect_unknown_b,
                        'effect_unknown_a': effect_unknown_a,
                        'shader_template_id': shader_template_id,
                        'tile_map_id': int(tile_map_id_raw * 64), # Turn it from a 0-1 value into a valid tile ID
                        'tile_map_opacity': tile_map_opacity,
                        'sphere_map_id': sphere_map_id,
                        'tile_scale_x': tile_transform['scale_x'],
                        'tile_scale_y': tile_transform['scale_y'],
                        'tile_rotation_deg': tile_transform['rotation_deg'],
                        'tile_shear_deg': tile_transform['shear_deg'],
                        'tile_matrix_raw': {'uu': tile_matrix_uu, 'uv': tile_matrix_uv, 'vu': tile_matrix_vu, 'vv': tile_matrix_vv}
                    }
                    colorset_data.append(row_data)

                # DYE DATA (If it exists)
                colorset_bytes_read = br.tell() - color_data_start
                remaining_data_after_rows = color_set_data_size - colorset_bytes_read
                expected_dye_bytes = row_count * 4

                if remaining_data_after_rows >= expected_dye_bytes:
                    dye_data = br.read(expected_dye_bytes)
                    num_dye_rows = len(dye_data) // 4
                    for i in range(num_dye_rows):
                        offset = i * 4
                        chunk = dye_data[offset:offset+4]
                        if len(chunk) == 4:
                            # Assume dye data is also little-endian. Surely.
                            b1, b2, b3, b4 = struct.unpack('<BBBB', chunk)
                            # Template uses little-endian short within bytes 3 & 4
                            template_val = struct.unpack('<H', bytes([b3, b4 & 0b11100111]))[0]
                            dye_info = {
                                'channel': ((b4 >> 3) & 0b11) + 1,
                                'template': template_val,
                                'flags': extract_dye_flags(b1, b2), # dye_diffuse, dye_specular, etc
                                'raw_bytes': {'hex': f'{b1:02x} {b2:02x} {b3:02x} {b4:02x}'} # Simplified raw bytes that I don't really know what they're for
                            }
                            if i < len(colorset_data):
                                colorset_data[i]['dye'] = dye_info
                        else:
                            logger.warning(f"Incomplete dye data chunk for row index {i}.")
                elif remaining_data_after_rows > 0:
                    logger.warning(f"Remaining data size ({remaining_data_after_rows}) after colorset rows doesn't match expected dye size ({expected_dye_bytes}). Skipping dye read.")

            # MATERIAL FLAGS
            # Seek relative to start of colorset block + declared size
            flags_offset = color_data_start + color_set_data_size
            br.seek(flags_offset)
            # Skip 6 bytes (shader constants?)
            br.seek(6, 1)
            flags_read_offset = br.tell()
            # Read 4 bytes for flags
            material_flags_value = struct.unpack('<I', br.read(4))[0]
            material_flags = MaterialFlags(material_flags_value)

            # Return dict
            return {
                'colorset_data': colorset_data,
                'material_flags': material_flags,
                'shader_name': shader_name,
                'textures': textures,
                'colorset_type': colorset_type
            }

        except EOFError as e:
            logger.error(f"Error reading MTRL file {filepath}: Reached end of file unexpectedly. {e}")
            return None
        except struct.error as e:
            logger.error(f"Error reading MTRL file {filepath}: Struct unpack error. {e}")
            return None
        except ValueError as e:
             logger.error(f"Error reading MTRL file {filepath}: Value error (likely invalid data). {e}")
             return None
        except Exception as e:
            logger.exception(f"Unexpected error reading MTRL file {filepath}: {e}")
            return None


# Not used for anything anymore I think but good for debugging sometimes
def get_values_by_group(data: List[dict], value_key: str, group: str) -> List:
    """Extract specific values from all rows of a particular group"""
    values = []
    if not data: return values # Handle empty data case
    for row in data:
        # Check if row is a dictionary and has the group key
        if isinstance(row, dict) and row.get('group') == group:
            value = row.get(value_key)
            if value is not None:
                 if isinstance(value, (list, tuple)):
                     values.append(list(value))  # Make sure it's a list just in case
                 else:
                     values.append(value)
    return values
