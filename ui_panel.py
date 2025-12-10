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
            # Ensure the object is active for the operator
            bpy.context.view_layer.objects.active = prosthetic_obj
            prosthetic_obj.select_set(True)
            bpy.ops.object.modifier_apply(modifier="SocketFit")
            self.report({'INFO'}, "Fit has been applied. Prosthetic is now an independent object.")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Could not find 'Prosthetic' object or 'SocketFit' modifier.")
            return {'CANCELLED'}


class PROSTHETIC_OT_BakeFitToNewObject(bpy.types.Operator):
    """
    Creates a new object that corresponds ONLY to the SocketFit
    shrinkwrap region (the deformed inner socket), as seen when
    "Toggle Deformation" is enabled, without altering the original
    Prosthetic object.
    """
    bl_idname = "prosthetic.bake_fit_to_new_object"
    bl_label = "Create Socket Shrinkwrap Object"

    def execute(self, context):
        src_obj = bpy.data.objects.get("Prosthetic")
        if not src_obj or "SocketFit" not in src_obj.modifiers:
            self.report({'ERROR'}, "Could not find 'Prosthetic' object with 'SocketFit' modifier.")
            return {'CANCELLED'}

        # Ensure we're in Object Mode for duplication / modifier application
        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode='OBJECT')

        # Duplicate object and its mesh data, linking to the same collections.
        result_obj = src_obj.copy()
        result_obj.data = src_obj.data.copy()
        if src_obj.users_collection:
            for col in src_obj.users_collection:
                col.objects.link(result_obj)
        else:
            context.scene.collection.objects.link(result_obj)
        result_obj.name = src_obj.name + "_SocketResult"

        # Make the new object active and apply the SocketFit modifier on it.
        for o in context.view_layer.objects:
            o.select_set(False)
        bpy.context.view_layer.objects.active = result_obj
        result_obj.select_set(True)

        if "SocketFit" not in result_obj.modifiers:
            self.report(
                {'WARNING'},
                "Duplicate object did not inherit 'SocketFit' modifier; "
                "shrinkwrap result could not be baked."
            )
            return {'CANCELLED'}

        # Apply the SocketFit modifier so the mesh is actually deformed.
        bpy.ops.object.modifier_apply(modifier="SocketFit")

        # Now trim the mesh down to JUST the socket region that the
        # shrinkwrap acted on (InnerSocket / Socket_VG), so the
        # resulting object contains only the interior fitted shape.

        # Prefer isolating by InnerSocket material; fall back to Socket_VG vertex group.
        inner_mat_index = result_obj.material_slots.find("InnerSocket")
        used_strategy = None

        if inner_mat_index != -1:
            # Use material selection
            if bpy.ops.object.mode_set.poll():
                bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='DESELECT')
            result_obj.active_material_index = inner_mat_index
            bpy.ops.object.material_slot_select()
            # Invert selection and delete everything that is NOT the socket
            bpy.ops.mesh.select_all(action='INVERT')
            bpy.ops.mesh.delete(type='FACE')
            bpy.ops.object.mode_set(mode='OBJECT')
            used_strategy = "material"
        else:
            # Try vertex group
            vg = result_obj.vertex_groups.get("Socket_VG")
            if vg:
                if bpy.ops.object.mode_set.poll():
                    bpy.ops.object.mode_set(mode='EDIT')
                bpy.ops.mesh.select_all(action='DESELECT')
                bpy.ops.mesh.select_mode(type='VERT')
                bpy.ops.object.vertex_group_set_active(group=vg.name)
                bpy.ops.object.vertex_group_select()
                bpy.ops.mesh.select_all(action='INVERT')
                bpy.ops.mesh.delete(type='VERT')
                bpy.ops.object.mode_set(mode='OBJECT')
                used_strategy = "vertex_group"

        if not used_strategy:
            self.report(
                {'WARNING'},
                "Shrinkwrap was baked, but could not isolate the socket-only mesh "
                "(no 'InnerSocket' material or 'Socket_VG' vertex group found)."
            )
            return {'FINISHED'}

        self.report(
            {'INFO'},
            f"Created '{result_obj.name}' containing only the SocketFit "
            "shrinkwrap region (no outer prosthetic shell)."
        )

        return {'FINISHED'}

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
            sub_box.operator("prosthetic.apply_fit", text="Apply Fit On Prosthetic")
            sub_box.operator("prosthetic.bake_fit_to_new_object", text="Create Fitted Copy")

# --- CUSTOM PROPERTY & REGISTRATION ---
def update_offset(self, context):
    prosthetic_obj = bpy.data.objects.get("Prosthetic")
    if prosthetic_obj and "SocketFit" in prosthetic_obj.modifiers:
        prosthetic_obj.modifiers["SocketFit"].offset = context.scene.socket_offset_mm / 1000.0
classes = (
    PROSTHETIC_OT_CreateLandmarks,
    PROSTHETIC_OT_FitObject,
    PROSTHETIC_OT_ApplyFit, 
    PROSTHETIC_OT_BakeFitToNewObject,
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
        default=3.0, min=0.0, max=1000000.0, soft_max=1000.0, #unit='LENGTH',
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