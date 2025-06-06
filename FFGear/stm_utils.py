from enum import Enum
from typing import List, Dict, Optional
import struct
import os
import logging

logging.basicConfig()
logger = logging.getLogger('FFGear.stm')
logger.setLevel(logging.INFO)

###¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤###
### Code heavily inspired by how the xivModdingFramework and TexTools reads the .stm format ###
### https://github.com/TexTools/xivModdingFramework                                         ###
###¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤###


#¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤#
# FOUNDATIONAL STUFF
#¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤#

class StainingTemplate(Enum):
    ENDWALKER = 0
    DAWNTRAIL = 1


class StainingTemplateArrayType(Enum):
    SINGLETON = 0
    ONE_TO_ONE = 1
    INDEXED = 2


PAINT_FILE_PATHS = {
    StainingTemplate.ENDWALKER: "bucket_of_paint.dyes",
    StainingTemplate.DAWNTRAIL: "bucket_of_newer_paint.dyes"
}


def half_to_float(half: int) -> float:
    """Convert a 16-bit half-precision float to a 32-bit float"""
    sign = (half >> 15) & 0x1
    exp = (half >> 10) & 0x1F
    mantissa = half & 0x3FF

    if exp == 0:
        if mantissa == 0:
            return 0.0 if sign == 0 else -0.0
        else:
            num = (float(mantissa) / 1024.0) * (2 ** -14)
            return num if sign == 0 else -num
    elif exp == 31:
        if mantissa == 0:
            return float('inf') if sign == 0 else float('-inf')
        else:
            return float('nan')

    result = (1.0 + (float(mantissa) / 1024.0)) * (2 ** (exp - 15))
    return result if sign == 0 else -result



class Half:
    def __init__(self, raw_value: int = 0):
        self.value = raw_value

    @staticmethod
    def from_raw_value(raw_value: int):
        return Half(raw_value)

    def __str__(self):
        result = half_to_float(self.value)
        return f"{result:.4f}"

    def to_float(self) -> float:
        """Convert Half to float value"""
        return half_to_float(self.value)
   

def values_to_dict(values: Optional[List[Half]]) -> Optional[Dict[str, float]]:
    """Convert Half values to dictionary format"""
    if not values:
        return None
    if len(values) == 1:
        return {"value": values[0].to_float()}
    return {
        "R": values[0].to_float(),
        "G": values[1].to_float(),
        "B": values[2].to_float()
    }


class StainingTemplateEntry:
    def __init__(self, data: bytes, offset: int, template_type: StainingTemplate, old_format: bool):
        """
        Initializes a StainingTemplateEntry, parsing dye data based on format version.

        Args:
            data: The raw byte data of the STM file.
            offset: The starting offset for this specific template entry within the data.
            template_type: The type of template (ENDWALKER or DAWNTRAIL).
            old_format: Boolean indicating if the file uses the older 128-dye format.
        """
        self.entries: List[List[List[Half]]] = []
        array_ends = []
        start = offset

        item_count = 5 if template_type == StainingTemplate.ENDWALKER else 12
        num_dyes = 128 if old_format else 254

        for i in range(item_count):
            # Ensure we don't read past the end of the data when getting array ends
            if offset + 2 > len(data):
                 logger.error(f"INIT Error: Attempted to read array end offset beyond data length for item {i}. Offset={offset}, DataLen={len(data)}")
                 array_ends.append(0)
                 offset += 2 # Still increment offset conceptually, though value is invalid
                 continue

            array_ends.append(struct.unpack_from("<H", data, offset)[0])
            offset += 2
            self.entries.append([]) # Initialize empty list for this entry offset

        header_size = item_count * 2
        last_offset = 0

        for x in range(item_count):
            # Ensure 'x' is within the bounds of the initialized 'entries' and 'array_ends' lists
            if x >= len(self.entries) or x >= len(array_ends):
                 logger.error(f"INIT Error: Index 'x' ({x}) is out of bounds for entries/array_ends lists (len={len(self.entries)}/{len(array_ends)}). Skipping property offset.")
                 continue # Skip processing for this invalid index

            element_size = 3 if x < 3 else 1
            default_entry = [Half() for _ in range(element_size)]

            current_end = array_ends[x]
            array_size = 0
            array_type = None

            if current_end < last_offset:
                 logger.warning(f"INIT Warning: Invalid array end offset detected for property offset {x}: end ({current_end}) < start ({last_offset}). Treating as empty.")
                 # Fill half_data with defaults directly
                 half_data = [default_entry for _ in range(num_dyes)]
                 array_type = None # Explicitly mark as having no specific type/data
            else:
                # Calculate size only if offsets are valid
                array_size = (current_end - last_offset) // element_size
                array_type = StainingTemplateArrayType.ONE_TO_ONE # Default assumption
                index_start = 0
                half_data = [] # Initialize half_data for this iteration

                if array_size == 0:
                    logger.debug(f"INIT: No dye data for property offset {x} (array_size is 0). Filling half_data with defaults.")
                    half_data = [default_entry for _ in range(num_dyes)]
                    array_type = None # No specific data type, already filled
                elif array_size == 1:
                    array_type = StainingTemplateArrayType.SINGLETON
                    # Read the single data entry
                    offset_start = start + header_size + (last_offset * 2)
                    # Add boundary checks for reading data
                    if offset_start + (element_size * 2) > len(data):
                         logger.error(f"INIT Error: Attempted to read Singleton data beyond data length for property offset {x}. Offset={offset_start}, DataLen={len(data)}")
                         half_data = [default_entry] # Use default if read fails
                    else:
                         halfs = []
                         element_start = offset_start
                         for j in range(element_size):
                             raw_value = struct.unpack_from("<H", data, element_start + (j * 2))[0]
                             halfs.append(Half.from_raw_value(raw_value))
                         half_data.append(halfs)
                else:
                    # Potential INDEXED or ONE_TO_ONE
                    total_bytes = (current_end - last_offset) * 2
                    rem_bytes = total_bytes - num_dyes

                    # Check for INDEXED pattern (requires space for index table + at least one data element)
                    # Ensure rem_bytes is positive and results in at least one element
                    if rem_bytes >= (element_size * 2): # Need at least enough bytes for one element after index table
                         actual_data_size = rem_bytes // 2 // element_size
                         if actual_data_size > 0: # Check if calculated size is valid
                              array_type = StainingTemplateArrayType.INDEXED
                              index_start = start + header_size + (last_offset * 2) + rem_bytes
                              array_start = last_offset
                              offset_start = start + header_size + (array_start * 2)

                              # Add boundary checks before reading index table and data
                              if index_start + num_dyes > len(data):
                                   logger.error(f"INIT Error: Attempted to read INDEXED index table beyond data length for property offset {x}. IndexStart={index_start}, DataLen={len(data)}")
                                   # Handle error: Fill half_data with defaults.
                                   half_data = [default_entry for _ in range(num_dyes)]
                                   array_type = None # Mark as failed/defaulted
                              elif offset_start + (actual_data_size * element_size * 2) > len(data):
                                   logger.error(f"INIT Error: Attempted to read INDEXED data values beyond data length for property offset {x}. OffsetStart={offset_start}, DataLen={len(data)}")
                                   half_data = [default_entry for _ in range(num_dyes)]
                                   array_type = None # Mark as failed/defaulted
                              else:
                                   # Read the unique Half float values
                                   for i in range(actual_data_size):
                                       halfs = []
                                       element_start = offset_start + ((i * 2) * element_size)
                                       for j in range(element_size):
                                           raw_value = struct.unpack_from("<H", data, element_start + (j * 2))[0]
                                           halfs.append(Half.from_raw_value(raw_value))
                                       half_data.append(halfs)
                         else:
                              # Not enough remaining bytes for even one element, treat as ONE_TO_ONE
                              array_type = StainingTemplateArrayType.ONE_TO_ONE
                              logger.debug(f"INIT: Calculated 0 actual data size for potential INDEXED at offset {x}. Treating as ONE_TO_ONE.")
                    else:
                         # Not enough bytes for index table + data, assume ONE_TO_ONE
                         array_type = StainingTemplateArrayType.ONE_TO_ONE

                    # Handle ONE_TO_ONE reading (if not successfully processed as INDEXED)
                    if array_type == StainingTemplateArrayType.ONE_TO_ONE:
                         array_start = last_offset
                         offset_start = start + header_size + (array_start * 2)
                         # Add boundary check before reading data
                         if offset_start + (array_size * element_size * 2) > len(data):
                              logger.error(f"INIT Error: Attempted to read ONE_TO_ONE data beyond data length for property offset {x}. OffsetStart={offset_start}, DataLen={len(data)}")
                              half_data = [default_entry for _ in range(num_dyes)] # Fill with defaults on error
                              array_type = None # Mark as failed/defaulted
                         else:
                              # Read all entries directly
                              for i in range(array_size):
                                   halfs = []
                                   element_start = offset_start + ((i * 2) * element_size)
                                   for j in range(element_size):
                                       raw_value = struct.unpack_from("<H", data, element_start + (j * 2))[0]
                                       halfs.append(Half.from_raw_value(raw_value))
                                   half_data.append(halfs)


                # ============================ #
                # Process based on Array Type (only if array_type is set)
                # ============================ #
                if array_type == StainingTemplateArrayType.INDEXED:
                    n_array = []
                    unique_value_count = len(half_data)
                    # Boundary check for reading index data
                    if index_start + num_dyes > len(data):
                         logger.error(f"INIT Error: Attempting to read index data out of bounds in INDEXED processing for offset {x}. IndexStart={index_start}, DataLen={len(data)}")
                         # Fill n_array with defaults as recovery
                         n_array = [default_entry for _ in range(num_dyes)]
                    else:
                         for i in range(num_dyes):
                             try:
                                 index = data[index_start + i]
                                 if index == 255 or index == 0:
                                     n_array.append(default_entry)
                                     continue
                                 if 0 < index <= unique_value_count:
                                     n_array.append(half_data[index - 1])
                                 else:
                                     logger.warning(f"INIT Warning: Invalid dye index {index} encountered for property offset {x} at dye {i}. Max unique value index: {unique_value_count}. Using default.")
                                     n_array.append(default_entry)
                             except IndexError: # Should be less likely with boundary check above, but keep for safety
                                 logger.error(f"INIT IndexError accessing index data at {index_start + i} or half_data with index {index-1} for property offset {x}", exc_info=True)
                                 n_array.append(default_entry)
                             except Exception as ex:
                                 logger.error(f"INIT Unexpected error processing indexed dye data for property offset {x}: {ex}", exc_info=True)
                                 raise ex # Re-raise unexpected
                    half_data = n_array

                elif array_type == StainingTemplateArrayType.SINGLETON:
                    if len(half_data) == 1:
                         first_entry = half_data[0] # Store the single entry
                         # Create a new list with the required number of copies
                         half_data = [first_entry for _ in range(num_dyes)]
                    else:
                         logger.warning(f"INIT Warning: Expected 1 entry for Singleton property offset {x}, found {len(half_data)}. Padding with defaults.")
                         half_data = [default_entry for _ in range(num_dyes)]

                # ============================ #
                # Final Padding/Truncating (only if array_type was set)
                # ============================ #
                if array_type is not None:
                    if len(half_data) < num_dyes:
                        logger.debug(f"INIT: Property offset {x} has {len(half_data)} entries after processing, expected {num_dyes}. Padding with defaults.")
                        half_data.extend([default_entry for _ in range(num_dyes - len(half_data))])
                    elif len(half_data) > num_dyes:
                        logger.warning(f"INIT Warning: Property offset {x} has {len(half_data)} entries after processing, expected {num_dyes}. Truncating.")
                        half_data = half_data[:num_dyes]

            # ============================ #
            # Debug logging
            # ============================ #

            logger.debug(f"INIT: Before extend for offset {x}: array_size={array_size}, array_type={array_type}, len(half_data)={len(half_data)}")

            # Store the final data for this property offset
            # Ensure self.entries[x] exists and is empty before extending
            if x < len(self.entries):
                 if not self.entries[x]: # Check if it's empty
                      self.entries[x].extend(half_data)
                 else:
                      # This case should not happen if logic is correct (list should be empty)
                      logger.error(f"INIT Error: Target list self.entries[{x}] was not empty before extend. Overwriting. Length was {len(self.entries[x])}")
                      self.entries[x] = half_data # Overwrite if not empty (potential data loss)
                 logger.debug(f"INIT: After extend for offset {x}: len(self.entries[{x}])={len(self.entries[x])}")
            else:
                 # This case should not happen due to earlier check 'if x >= len(self.entries)'
                 logger.error(f"INIT Error: Index 'x' ({x}) became invalid before extend operation.")

            # Update last_offset for the next iteration
            last_offset = current_end


    def get_data(self, offset: int, dye_id: int = 0) -> Optional[List[Half]]:
        """Get data for specific offset and dye ID"""
        # Check offset validity first
        if offset >= len(self.entries):
            logger.warning(f"GET_DATA Warning: Attempted to access invalid property offset: {offset}. Max offset: {len(self.entries)-1}")
            return None
        if dye_id < 0:
             logger.warning(f"GET_DATA Warning: Attempted to access negative dye_id: {dye_id}. Using dye_id 0 instead.")
             dye_id = 0 # Treat negative dye ID as 0

        current_len = len(self.entries[offset])
        logger.debug(f"GET_DATA: Checking bounds for offset {offset}, dye_id {dye_id}. Current len(self.entries[{offset}]) = {current_len}")

        # Check if the requested dye_id is within the bounds of the specific list for this offset
        if dye_id < current_len:
            return self.entries[offset][dye_id]
        else:
            # This means the list for this offset doesn't have an entry for the requested dye_id
            logger.warning(f"GET_DATA Warning: Dye ID {dye_id} out of bounds for property offset {offset} (max index: {current_len - 1}). Returning default.")
            # Determine element size to return correct default structure
            element_size = 3 if offset < 3 else 1
            return [Half() for _ in range(element_size)]


# The TEMPLATE_MAPPINGS for endwalker in particular may be incorrect, but so far they haven't broken anything so I'm keeping it like this
class StainingTemplateFile:
    TEMPLATE_MAPPINGS = {
        StainingTemplate.ENDWALKER: {
            0: "diffuse",
            1: "specular",
            2: "emissive",
            3: "specular_power",
            4: "metalness"
        },
        StainingTemplate.DAWNTRAIL: {
            0: "diffuse",
            1: "specular",
            2: "emissive",
            3: "specular_power",
            4: "metalness",
            5: "roughness",
            6: "sheen_rate",
            7: "sheen_tint_rate",
            8: "sheen_aperture",
            9: "unknown_9",
            10: "unknown_10",
            11: "unknown_11"
        }
    }

    def __init__(self, data: bytes, template_type: StainingTemplate):
        """
        Initializes the StainingTemplateFile, parsing the header and template entries.

        Args:
            data: The raw byte data of the STM file.
            template_type: The type of template (ENDWALKER or DAWNTRAIL).
        """
        self.template_type = template_type
        self.templates: Dict[int, StainingTemplateEntry] = {} # Store templates by ID

        # --- Format Detection Logic ---
        header = struct.unpack_from("<H", data, 0)[0] # Offset 0: Unknown header value
        version = struct.unpack_from("<H", data, 2)[0] # Offset 2: Version number
        entry_count = struct.unpack_from("<H", data, 4)[0] # Offset 4: Number of template entries
        unknown = struct.unpack_from("<H", data, 6)[0] # Offset 6: Unknown header value

        # MODIFIED: Determine if the file uses the old format (128 dyes, 2-byte keys/offsets)
        # or the new format (254 dyes, 4-byte keys/offsets) based on C# diff logic.
        old_format = False
        if template_type == StainingTemplate.DAWNTRAIL and version < 0x201:
            # Dawntrail files use version number
            old_format = True
            logger.debug(f"Detected old Dawntrail STM format (Version: {version:#04x})")
        elif template_type == StainingTemplate.ENDWALKER:
            # Endwalker files use a heuristic (check bytes at 0x0A, 0x0B)
            # This assumes the header structure (first 8 bytes) is consistent.
            # Check if data is long enough before accessing indices 10 and 11.
            if len(data) > 11 and (data[10] != 0x00 or data[11] != 0x00):
                 old_format = True
                 logger.debug("Detected old Endwalker STM format (Heuristic check)")
            # else:
                 # logger.debug("Detected new Endwalker STM format (Heuristic check)")
        # else:
             # logger.debug(f"Detected new Dawntrail STM format (Version: {version:#04x})")


        # --- Read Template IDs and Offsets ---
        entry_offsets = {} # Dictionary to store {template_id: data_offset}
        keys = []          # List to maintain the order of template IDs
        offset = 8         # Start reading after the initial 8-byte header

        # Determine format strings and sizes based on detected format
        key_fmt = "<H" if old_format else "<I"
        key_size = 2 if old_format else 4
        offset_fmt = "<H" if old_format else "<I"
        offset_size = 2 if old_format else 4
        header_entry_size = key_size + offset_size # Size of ID + Offset pair in header

        logger.debug(f"Reading {entry_count} templates using {'old (2-byte)' if old_format else 'new (4-byte)'} format.")

        # Read template IDs
        for i in range(entry_count):
            if offset + key_size > len(data):
                logger.error(f"Error reading template keys: Reached end of file unexpectedly at index {i}/{entry_count}, offset {offset}.")
                break
            key = struct.unpack_from(key_fmt, data, offset)[0]
            entry_offsets[key] = 0 # Initialize offset value
            keys.append(key)
            offset += key_size

        # Calculate the end of the header section (where actual template data begins)
        # The header contains IDs and their corresponding offsets.
        end_of_header = 8 + (entry_count * header_entry_size) # Start offset + size of all ID/Offset pairs

        # Read template data offsets
        for i in range(entry_count):
            if i >= len(keys): # Check if we broke early during key reading
                break
            if offset + offset_size > len(data):
                 logger.error(f"Error reading template offsets: Reached end of file unexpectedly at index {i}/{entry_count}, offset {offset}.")
                 break
            raw_offset = struct.unpack_from(offset_fmt, data, offset)[0]
            # Calculate the absolute offset in the file data
            # Offset is relative to the end of the header and scaled by 2 (since offsets seem to be in Half units)
            absolute_offset = (raw_offset * 2) + end_of_header
            entry_offsets[keys[i]] = absolute_offset
            offset += offset_size

        # --- Create StainingTemplateEntry Objects ---
        logger.debug(f"Loading {len(entry_offsets)} template entries...")
        loaded_count = 0
        for key, value in entry_offsets.items():
            try:
                # MODIFIED: Pass the old_format flag to the entry constructor
                entry = StainingTemplateEntry(data, value, template_type, old_format)
                # Key should always be treated as an integer
                self.templates[int(key)] = entry
                loaded_count += 1
            except Exception as e:
                logger.error(f"Failed to parse template entry for key {key} at offset {value}: {e}", exc_info=True)

        logger.debug(f"Successfully loaded {loaded_count} templates for {template_type.name} ({'old' if old_format else 'new'} format).")


    def get_template(self, key: int) -> Optional[StainingTemplateEntry]:
        """Get template by ID"""
        # Ensure key is int
        key_int = int(key)
        if key_int in self.templates:
            # logger.debug(f"Found template {key_int} in {self.template_type.name} file")
            return self.templates[key_int]
        logger.warning(f"Template {key_int} not found in {self.template_type.name} file")
        return None

    def get_entry_names(self) -> List[str]:
        """Get list of entry names based on template type"""
        return list(self.TEMPLATE_MAPPINGS[self.template_type].values())


# Global cache for STM data
_stm_cache = None
_template_cache = {}



#¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤#
# FUNCTIONS
#¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤#

def get_template_values(template_id: int, dye_index: int, template_type: StainingTemplate, is_legacy: bool = False) -> Optional[Dict]:
    """
    Get cached template values or compute them
    
    Args:
        template_id: Template ID to process
        dye_index: Dye index to use
        template_type: Which template format to use
        is_legacy: Whether to force Endwalker STM for legacy shaders
    """
    # Force Endwalker template type for legacy shaders
    effective_type = StainingTemplate.ENDWALKER if is_legacy else template_type
    
    cache_key = f"{effective_type.value}_{template_id}_{dye_index}"
    if cache_key in _template_cache:
        return _template_cache[cache_key]
        
    stm_file = get_stm_cache(effective_type)
    if not stm_file:
        return None
        
    template = stm_file.get_template(template_id)
    if not template:
        return None

    result = {}
    entry_names = stm_file.get_entry_names()
    
    for i, entry_name in enumerate(entry_names):
        data = template.get_data(i, dye_index)
        result[entry_name] = values_to_dict(data)
        
    _template_cache[cache_key] = result
    return result


def get_stm_cache(intended_template_type: StainingTemplate) -> Optional[StainingTemplateFile]:
    """
    Gets the StainingTemplateFile from cache or loads it.
    Uses the intended_template_type to find the file path, but the actual
    type is determined by the file header during loading.
    """
    global _stm_cache

    if intended_template_type not in _stm_cache or _stm_cache[intended_template_type] == None: # If we've never loaded it before, or if we did try before but failed
        # File not in cache, attempt to load
        _stm_cache[intended_template_type] = None # Mark as attempted
        try:
            # Construct path relative to this script's parent's parent directory
            # Adjust this path logic if necessary for your project structure
            script_dir = os.path.dirname(os.path.realpath(__file__))
            # Example: If script is in 'Project/FFGear/utils/stm_utils.py',
            # addon_dir might be 'Project/FFGear'
            addon_dir = os.path.dirname(script_dir) # Adjust if needed
            assets_dir = os.path.join(addon_dir, "FFGear", "assets") # Assuming assets is sibling to utils
            
            # Get the expected filename based on the *intended* type
            stm_filename = PAINT_FILE_PATHS.get(intended_template_type)
            if not stm_filename:
                 logger.error(f"No file path defined for template type {intended_template_type.name}")
                 return None

            stm_path = os.path.join(assets_dir, stm_filename)

            if os.path.exists(stm_path):
                logger.debug(f"Loading STM file: {stm_path} for intended type {intended_template_type.name}")
                with open(stm_path, 'rb') as f:
                    file_data = f.read()
                # Parse the file - constructor determines actual type
                loaded_file = StainingTemplateFile(file_data, intended_template_type)
                # Store the loaded file in the cache under the intended key
                _stm_cache[intended_template_type] = loaded_file
                logger.debug(f"Successfully loaded and parsed. Actual type: {loaded_file.template_type.name}")
            else:
                logger.error(f"STM file not found at expected path: {stm_path}")

        except ValueError as e:
            logger.error(f"Failed to parse STM file {stm_path}: {e}")
            _stm_cache[intended_template_type] = None # Ensure cache reflects load failure
        except Exception as e:
            logger.error(f"An unexpected error occurred loading STM file {stm_path}: {e}", exc_info=True)
            _stm_cache[intended_template_type] = None

    # Return the cached object (which might be None if loading failed)
    return _stm_cache.get(intended_template_type)


def get_modified_value(dye_info: Optional[Dict], property_name: str, dye_id: str) -> Optional[List[float]]:
    """Get modified value based on dye settings"""
    if not dye_info or dye_id == '0':
        return None

    dye_index = int(dye_id)
    template_id = dye_info['template']
    # logger.debug(f"Using dye_index: {dye_index}")
    
    if template_id == 0:
        return None

    # Get template type and log it
    template_type = dye_info.get('template_type', StainingTemplate.DAWNTRAIL)
    # logger.debug(f"get_modified_value - Using template type: {template_type.name}")

    template_values = get_template_values(template_id, dye_index, template_type)
    if not template_values:
        logger.warning(f"No template values found for template {template_id} ({template_type.name})")
        return None

    if property_name not in template_values:
        logger.warning(f"Property {property_name} not found in template {template_id}")
        return None

    value_dict = template_values[property_name]
    if not value_dict:
        return None
        
    result = None
    if "value" in value_dict:
        result = value_dict["value"]
    else:
        result = [value_dict["R"], value_dict["G"], value_dict["B"]]
    
    # logger.debug(f"Modified value for {property_name}: {result}")
    return result


def should_apply_dye(dye_flags: Dict, property_name: str, channel: int) -> bool:
    """Determine if dye should be applied based on flags and channel"""
    flag_map = {
        'diffuse': 'dye_diffuse',
        'specular': 'dye_specular', 
        'emissive': 'dye_emissive',
        'roughness': 'dye_roughness',
        'metalness': 'dye_metallic'
    }
    
    flag_name = flag_map.get(property_name)
    if not flag_name:
        return False

    flags = dye_flags.get('flags', {})
    dye_channel = dye_flags.get('channel')
    
    return flags.get(flag_name, False) and dye_channel == channel


def clear_caches():
    """Clear all caches"""
    global _stm_cache, _template_cache
    _stm_cache = {}  # Changed from None to empty dict
    _template_cache.clear()


def register():
    clear_caches()

def unregister():
    clear_caches()