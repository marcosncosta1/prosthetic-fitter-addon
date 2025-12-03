import bpy
import bmesh  
from .prosthetic_fitter import run_fitting_process

# --- OPERATORS ---

class PROSTHETIC_OT_CreateLandmarks(bpy.types.Operator):
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
    bl_idname = "prosthetic.fit_object"
    bl_label = "Fit Prosthetic to Scan"
    def execute(self, context):
        try:
            run_fitting_process()
            context.scene.socket_offset_mm = 3.0
            return {'FINISHED'}
        except ValueError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

class PROSTHETIC_OT_ApplyFit(bpy.types.Operator):
    bl_idname = "prosthetic.apply_fit"
    bl_label = "Apply and Finalize Fit"
    def execute(self, context):
        prosthetic_obj = bpy.data.objects.get("Prosthetic")
        if prosthetic_obj and "SocketFit" in prosthetic_obj.modifiers:
            bpy.ops.object.modifier_apply(modifier="SocketFit")
            self.report({'INFO'}, "Fit has been applied. Prosthetic is now an independent object.")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Could not find 'Prosthetic' object or 'SocketFit' modifier.")
            return {'CANCELLED'}

class PROSTHETIC_OT_SelectSocket(bpy.types.Operator):
    bl_idname = "prosthetic.select_socket"
    bl_label = "Select Inner Socket by Normal"
    def execute(self, context):
        if not context.active_object or context.mode != 'EDIT_MESH':
            self.report({'ERROR'}, "Must be in Edit Mode with one face selected.")
            return {'CANCELLED'}
        threshold = context.scene.selection_threshold
        try:
            bpy.ops.mesh.select_similar(type='FACE_NORMAL', threshold=threshold)
        except Exception as e:
            self.report({'ERROR'}, f"Selection failed. Make sure you are in Edit Mode with a face selected. {e}")
            return {'CANCELLED'}
        self.report({'INFO'}, "Selection complete.")
        return {'FINISHED'}


class PROSTHETIC_OT_AssignSocketMaterial(bpy.types.Operator):
    """
    Assigns 'InnerSocket' material to the selected faces
    by directly changing the mesh data.
    """
    bl_idname = "prosthetic.assign_socket_material"
    bl_label = "Assign 'InnerSocket' to Selection"

    def execute(self, context):
        obj = context.active_object
        if not obj or context.mode != 'EDIT_MESH':
            self.report({'ERROR'}, "Must be in Edit Mode with faces selected.")
            return {'CANCELLED'}

        # Get the material slot index for "InnerSocket"
        try:
            inner_socket_index = obj.material_slots.find("InnerSocket")
        except ValueError:
            self.report({'ERROR'}, "Material 'InnerSocket' not found. Please create it.")
            return {'CANCELLED'}

        # Get the mesh data using bmesh
        me = obj.data
        bm = bmesh.from_edit_mesh(me)

        # Find selected faces
        selected_faces = [f for f in bm.faces if f.select]

        if not selected_faces:
            self.report({'WARNING'}, "No faces were selected.")
            return {'CANCELLED'}

        # Assign the new material index to all selected faces
        
        for face in selected_faces:
            face.material_index = inner_socket_index
        
        # Update the mesh and free the bmesh data
        bmesh.update_edit_mesh(me)
        bm.free()

        self.report({'INFO'}, f"Assigned 'InnerSocket' to {len(selected_faces)} faces.")
        return {'FINISHED'}


# --- THE UI PANEL CLASS ---
class PROSTHETIC_PT_FittingPanel(bpy.types.Panel):
    bl_label = "HandFit"
    bl_idname = "PROSTHETIC_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'HandFit'
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        box = layout.box()
        box.label(text="Master Model Setup", icon='PRESET')
        box.label(text="Step 1: Make Your Selection (in Edit Mode)")
        col = box.column(align=True)
        col.label(text="Option A: Automatic (Recommended)")
        col.label(text="- Select one inner face, then click:")
        col.prop(scene, "selection_threshold", text="Threshold")
        col.operator("prosthetic.select_socket")
        col = box.column(align=True)
        col.label(text="Option B: Manual")
        col.label(text="- Use 'C' (Circle Select) or other tools.")
        box.label(text="Step 2: Assign Material")
        box.operator("prosthetic.assign_socket_material")
        box = layout.box()
        box.label(text="Patient Fitting Workflow", icon='HAND')
        box.label(text="Step 1: Setup", icon='TOOL_SETTINGS')
        box.operator("prosthetic.create_landmarks")
        box.label(text="Step 2: Execution", icon='PLAY')
        box.operator("prosthetic.fit_object")
        prosthetic_obj = bpy.data.objects.get("Prosthetic")
        if prosthetic_obj and "SocketFit" in prosthetic_obj.modifiers:
            modifier = prosthetic_obj.modifiers["SocketFit"]
            sub_box = box.box()
            sub_box.label(text="Step 3: Adjustments", icon='MODIFIER')
            sub_box.prop(modifier, "show_viewport", text="Toggle Deformation")
            sub_box.prop(scene, "socket_offset_mm", text="Socket Offset (mm)")
            sub_box = box.box()
            sub_box.label(text="Step 4: Finalize", icon='CHECKMARK')
            sub_box.operator("prosthetic.apply_fit")

# --- CUSTOM PROPERTY & REGISTRATION ---
def update_offset(self, context):
    prosthetic_obj = bpy.data.objects.get("Prosthetic")
    if prosthetic_obj and "SocketFit" in prosthetic_obj.modifiers:
        prosthetic_obj.modifiers["SocketFit"].offset = context.scene.socket_offset_mm / 1000.0
classes = (
    PROSTHETIC_OT_CreateLandmarks,
    PROSTHETIC_OT_FitObject,
    PROSTHETIC_OT_ApplyFit, 
    PROSTHETIC_OT_SelectSocket,         
    PROSTHETIC_OT_AssignSocketMaterial, 
    PROSTHETIC_PT_FittingPanel,
)
def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.socket_offset_mm = bpy.props.FloatProperty(
        name="Socket Offset",
        description="Gap for liner in millimeters",
        default=3.0, min=0.0, max=50.0, soft_max=30.0, #unit='LENGTH',
        update=update_offset
    )
    bpy.types.Scene.selection_threshold = bpy.props.FloatProperty(
        name="Selection Threshold",
        description="Angle to use for 'Select Similar by Normal'",
        default=0.1, min=0.0, max=1.0
    )
def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    if hasattr(bpy.types.Scene, 'socket_offset_mm'):
        del bpy.types.Scene.socket_offset_mm
    if hasattr(bpy.types.Scene, 'selection_threshold'):
        del bpy.types.Scene.selection_threshold