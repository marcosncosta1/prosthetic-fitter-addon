bl_info = {
    "name": "Prosthetic Fitter",
    "author": "Marcos Costa (ZHAW)",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "View3D > Sidebar > Fitter Tab",
    "description": "Automates the fitting of a prosthetic to a hand scan. Developed at ZHAW.",
    "category": "Object",
}


from . import prosthetic_fitter
from . import ui_panel

def register():
    ui_panel.register()

def unregister():
    ui_panel.unregister()

if __name__ == "__main__":
    register()