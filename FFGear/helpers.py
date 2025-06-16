import string
import requests
import addon_utils
import logging
from typing import Tuple

logging.basicConfig()
logger = logging.getLogger('FFGear.helpers')
logger.setLevel(logging.INFO)

ASCII_LETTERS_SET = set(string.ascii_letters)

repo_release_url = "https://api.github.com/repos/kajupe/FFGear/releases/latest"
repo_release_download_url = "https://github.com/kajupe/FFGear/releases"
current_version = "Unknown"
latest_version = "Unknown"
latest_version_name = "Unknown"



#¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤#
# FUNCTIONS
#¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤#

def compare_strings_for_one_difference(str1: str, str2: str) -> bool:
    """
    Compares two strings and returns True if they differ only by a single
    ASCII letter character (a-z or A-Z).

    Args:
        str1: The first string.
        str2: The second string.

    Returns:
        True if the strings differ only by replacing one letter with another
             (case changes allowed), False otherwise.
    """
    # Length must be equal
    n = len(str1)
    if n != len(str2):
        return False

    # Can't be identical
    if str1 == str2:
        return False

    diff_idx = -1
    diff_count = 0

    # Find the number and index of differences
    for i in range(n):
        if str1[i] != str2[i]:
            diff_count += 1
            if diff_count > 1:
                # More than one difference found, return False early
                return False
            # Store the index of the difference
            diff_idx = i

    # Check if the characters at the differing position are letters
    if (str1[diff_idx] in ASCII_LETTERS_SET and
            str2[diff_idx] in ASCII_LETTERS_SET):
        # The single difference is between two ascii letters
        return True
    else:
        # The single difference is non-ascii
        return False
    

def _get_latest_addon_version() -> dict:
    """
    Returns:
        json-formatted data from the repo request url
    """
    response = requests.get(repo_release_url)
    if response.status_code != 200:
        raise Exception(f"Failed to get latest version: {response.status_code}")
    data = response.json()
    return data


def get_addon_version_and_latest() -> Tuple[str, str]:
    """
    Gets the current and latest version of FFGear as a tuple of strings (current, latest). Version is "Unknown" if none can be found

    Returns:
        tuple of strings (current, latest)
    """
    # VERSION CHECK (code stolen from Meddle Tools, but adjusted a bit)
    global current_version
    global latest_version
    global latest_version_name
    try:
        latest_version_info = _get_latest_addon_version()
        latest_version = latest_version_info["tag_name"]
        latest_version_name = latest_version_info["name"]
        logger.info(f"Latest version: {latest_version}")
    except Exception as e:
        logger.warning(f"Failed to get latest version: {e}")
    try:     
        version_set = False 
        for module in addon_utils.modules():
            if module.bl_info.get("name") == "FFGear":
                current_version = ".".join([str(v) for v in module.bl_info.get("version")])
                version_set = True
                break
        if not version_set:
            current_version = "Unknown"
        logger.info(f"Current version: {current_version}")
    except Exception as e:
        logger.warning(f"Failed to read current version: {e}")

    # return (current_version, latest_version)
    return None