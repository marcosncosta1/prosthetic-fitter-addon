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


def _safe_call(module, func_name):
    func = getattr(module, func_name, None)
    if func is None:
        print(f"[HandFit] WARNING: '{module.__name__}' has no attribute '{func_name}'.")
        return
    func()


def register():
    _safe_call(prosthetic_fitter, "register")
    _safe_call(ui_panel, "register")


def unregister():
    _safe_call(ui_panel, "unregister")
    _safe_call(prosthetic_fitter, "unregister")

if __name__ == "__main__":
    register()