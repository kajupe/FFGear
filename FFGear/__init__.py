from . import icons
from . import preferences
from . import properties
from . import stm_utils
from . import mtrl_handler
from . import operators
from . import ui
from . import auto_updating

import bpy

def register():
    
    # Load Icons First!
    icons.register()

    preferences.register()

    properties.register()
    stm_utils.register()
    operators.register()
    auto_updating.register()
    ui.register()
    

def unregister():
    
    ui.unregister()
    auto_updating.unregister()
    operators.unregister()
    stm_utils.unregister()
    properties.unregister()
    preferences.unregister()
    icons.unregister()

if __name__ == "__main__":
    register()