import bpy
import importlib
import sys
from .prosthetic_fitter import run_fitting_process
from bpy_extras.io_utils import ImportHelper

# --- OPERATORS ---

class PROSTHETIC_OT_LoadHandScan(bpy.types.Operator, ImportHelper):
    bl_idname = "prosthetic.load_hand_scan"
    bl_label = "Load Hand Scan STL"
    bl_options = {'REGISTER', 'UNDO'}
    filename_ext = ".stl"
    filter_glob: bpy.props.StringProperty(default="*.stl", options={'HIDDEN'})

    def execute(self, context):
        try:
            import os
            base = os.path.splitext(os.path.basename(self.filepath))[0]
            ext = os.path.splitext(self.filepath)[1].lower()
            if base != "hand_scan" or ext != ".stl":
                self.report({'ERROR'}, "File must be named 'hand_scan.stl'.")
                return {'CANCELLED'}
            before = set(bpy.data.objects)
            bpy.ops.import_mesh.stl(filepath=self.filepath)
            after = set(bpy.data.objects)
            new_objs = list(after - before)
            if not new_objs:
                self.report({'ERROR'}, "No object imported from STL.")
                return {'CANCELLED'}
            imported_obj = new_objs[0]
            imported_obj.name = "HandScan"
            self.report({'INFO'}, f"Imported '{self.filepath}' as 'HandScan'.")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Import failed: {e}")
            return {'CANCELLED'}

class PROSTHETIC_OT_LoadProsthetic(bpy.types.Operator, ImportHelper):
    bl_idname = "prosthetic.load_prosthetic"
    bl_label = "Load Prosthetic STL"
    bl_options = {'REGISTER', 'UNDO'}
    filename_ext = ".stl"
    filter_glob: bpy.props.StringProperty(default="*.stl", options={'HIDDEN'})

    def execute(self, context):
        try:
            import os
            base = os.path.splitext(os.path.basename(self.filepath))[0]
            ext = os.path.splitext(self.filepath)[1].lower()
            if base != "Prosthetic" or ext != ".stl":
                self.report({'ERROR'}, "File must be named 'Prosthetic.stl'.")
                return {'CANCELLED'}
            before = set(bpy.data.objects)
            bpy.ops.import_mesh.stl(filepath=self.filepath)
            after = set(bpy.data.objects)
            new_objs = list(after - before)
            if not new_objs:
                self.report({'ERROR'}, "No object imported from STL.")
                return {'CANCELLED'}
            imported_obj = new_objs[0]
            imported_obj.name = "Prosthetic"
            self.report({'INFO'}, f"Imported '{self.filepath}' as 'Prosthetic'.")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Import failed: {e}")
            return {'CANCELLED'}

class PROSTHETIC_OT_CreateLandmarks(bpy.types.Operator):
    """Creates the set of 6 required landmark empties"""
    bl_idname = "prosthetic.create_landmarks"
    bl_label = "Create Landmarks"

    def execute(self, context):
        scan_obj = bpy.data.objects.get("HandScan")
        prosthetic_obj = bpy.data.objects.get("Prosthetic")
        if not scan_obj or not prosthetic_obj:
            self.report({'ERROR'}, "Name objects 'HandScan' and 'Prosthetic'.")
            return {'CANCELLED'}
        landmarks_to_create = {
            "Hand_Wrist_L": scan_obj, "Hand_Wrist_R": scan_obj, "Hand_Palm": scan_obj,
            "Prosthetic_Wrist_L": prosthetic_obj, "Prosthetic_Wrist_R": prosthetic_obj, "Prosthetic_Palm": prosthetic_obj,
        }
        for name, parent_obj in landmarks_to_create.items():
            if not bpy.data.objects.get(name):
                new_empty = bpy.data.objects.new(name, None)
                new_empty.location = parent_obj.location
                new_empty.parent = parent_obj
                context.scene.collection.objects.link(new_empty)
        self.report({'INFO'}, "Created landmark Empties.")
        return {'FINISHED'}

class PROSTHETIC_OT_FitObject(bpy.types.Operator):
    """The main operator that runs the entire fitting script"""
    bl_idname = "prosthetic.fit_object"
    bl_label = "Fit Prosthetic to Scan"

    def execute(self, context):
        run_fitting_process()
        # Set the initial value of our custom mm slider to match the script's default (3mm)
        context.scene.socket_offset_mm = 3.0
        return {'FINISHED'}

class PROSTHETIC_OT_ApplyFit(bpy.types.Operator):
    """Applies the SocketFit modifier to make the change permanent"""
    bl_idname = "prosthetic.apply_fit"
    bl_label = "Apply and Finalize Fit"

    def execute(self, context):
        prosthetic_obj = bpy.data.objects.get("Prosthetic")
        if prosthetic_obj and "SocketFit" in prosthetic_obj.modifiers:
            for obj in context.selected_objects:
                obj.select_set(False)
            prosthetic_obj.select_set(True)
            bpy.context.view_layer.objects.active = prosthetic_obj
            bpy.ops.object.modifier_apply(modifier="SocketFit")
            self.report({'INFO'}, "Fit has been applied.")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Could not find 'Prosthetic' object or 'SocketFit' modifier.")
            return {'CANCELLED'}

# --- NEW RELOAD OPERATOR ---
class PROSTHETIC_OT_ReloadAddon(bpy.types.Operator):
    """Reloads the entire add-on to reflect script changes"""
    bl_idname = "prosthetic.reload_addon"
    bl_label = "Reload Add-on (Dev)"

    def execute(self, context):
        addon_name = __package__
        loaded_modules = [mod for name, mod in sys.modules.items() if name.startswith(addon_name)]
        for mod in loaded_modules:
            importlib.reload(mod)
        self.report({'INFO'}, f"Reloaded add-on: {addon_name}")
        return {'FINISHED'}


# --- THE UI PANEL CLASS ---
class PROSTHETIC_PT_FittingPanel(bpy.types.Panel):
    """Creates a Panel in the 3D View's Sidebar"""
    bl_label = "HandFit"
    bl_idname = "PROSTHETIC_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'HandFit'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # Step 0: Imports
        box = layout.box()
        box.label(text="Step 0: Load Models", icon='FILE_FOLDER')
        row = box.row(align=True)
        row.operator("prosthetic.load_hand_scan", icon='MESH_DATA')
        row.operator("prosthetic.load_prosthetic", icon='MESH_CUBE')

        # Step 1: Setup
        box = layout.box()
        box.label(text="Step 1: Setup", icon='TOOL_SETTINGS')
        box.operator("prosthetic.create_landmarks")

        # Step 2: Execution
        box = layout.box()
        box.label(text="Step 2: Execution", icon='PLAY')
        box.operator("prosthetic.fit_object")

        # Conditional section that appears after the fit is run
        prosthetic_obj = bpy.data.objects.get("Prosthetic")
        if prosthetic_obj and "SocketFit" in prosthetic_obj.modifiers:
            box = layout.box()
            box.label(text="Step 3: Adjustments", icon='MODIFIER')
            box.prop(scene, "socket_offset_mm", text="Socket Offset (mm)")

            box = layout.box()
            box.label(text="Step 4: Finalize", icon='CHECKMARK')
            box.operator("prosthetic.apply_fit")

        # --- Developer Section ---
        dev_box = layout.box()
        dev_box.label(text="Developer Tools", icon='SCRIPTPLUGINS')
        dev_box.operator("prosthetic.reload_addon")

# --- CUSTOM PROPERTY & REGISTRATION ---

def update_offset(self, context):
    prosthetic_obj = bpy.data.objects.get("Prosthetic")
    if prosthetic_obj and "SocketFit" in prosthetic_obj.modifiers:
        prosthetic_obj.modifiers["SocketFit"].offset = context.scene.socket_offset_mm / 1000.0

classes = (
    PROSTHETIC_OT_LoadHandScan,
    PROSTHETIC_OT_LoadProsthetic,
    PROSTHETIC_OT_CreateLandmarks,
    PROSTHETIC_OT_FitObject,
    PROSTHETIC_OT_ApplyFit,
    PROSTHETIC_OT_ReloadAddon, # Added the reload operator
    PROSTHETIC_PT_FittingPanel,
)

def unregister_previous():
    for cls in reversed(classes):
        if hasattr(bpy.types, cls.__name__):
            bpy.utils.unregister_class(cls)

def register():
    unregister_previous() # Helper for stable reloading
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.socket_offset_mm = bpy.props.FloatProperty(
        name="Socket Offset",
        description="Gap for liner in millimeters",
        default=3.0,
        min=0.0,
        max=10.0,
        unit='LENGTH',
        update=update_offset
    )

def unregister():
    for cls in reversed(classes):
        if hasattr(bpy.types, cls.__name__):
            bpy.utils.unregister_class(cls)
    if hasattr(bpy.types.Scene, 'socket_offset_mm'):
        del bpy.types.Scene.socket_offset_mm