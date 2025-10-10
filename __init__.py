# This file tells Blender that the folder is a loadable add-on.

bl_info = {
    "name": "Prosthetic Fitter",
    "author": "Marcos Costa (ZHAW)",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "View3D > Sidebar > Fitter Tab",
    "description": "Automates the fitting of a prosthetic to a hand scan. Developed at ZHAW.",
    "category": "Object",
}

# Import everything from our other files so Blender knows about them.
# The '.' before the name means "from the same folder".
from . import prosthetic_fitter
from . import ui_panel

def register():
    ui_panel.register()

def unregister():
    ui_panel.unregister()

if __name__ == "__main__":
    register()