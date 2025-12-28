import bpy
import bmesh
from mathutils import Vector
from . import prosthetic_fitter

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
            prosthetic_fitter.run_fitting_process()
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

# --- THE UI PANEL CLASSES (NOW SEPARATED) ---

# 1. TRACKER PANEL
class PROSTHETIC_PT_TrackerPanel(bpy.types.Panel):
    """Section 1: Live prosthetic scale tracker."""

    bl_label = "Prosthetic Scale Tracker"
    bl_idname = "PROSTHETIC_PT_tracker_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'HandFit'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        tracker = getattr(scene, "prosthetic_scale_tracker", None)
        if not tracker:
            layout.label(text="Tracker unavailable. Reload add-on.", icon='ERROR')
            return
        # Do not mutate tracker from draw; just read
        prosthetic_fitter.ensure_tracker_defaults(tracker, mutate=False)

        col = layout.column(align=True)
        col.label(text=f"X: {tracker.scale_x_percent:.2f}% ({tracker.scale_x_factor:.4f}x)")
        col.label(text=f"Y: {tracker.scale_y_percent:.2f}% ({tracker.scale_y_factor:.4f}x)")
        col.label(text=f"Z: {tracker.scale_z_percent:.2f}% ({tracker.scale_z_factor:.4f}x)")

        layout.separator()
        baseline = layout.column()
        baseline.label(text=f"Baseline wrist: {tracker.baseline_wrist_bu:.4f} BU")
        baseline.label(text=f"Baseline palm:  {tracker.baseline_palm_bu:.4f} BU")

        layout.separator()
        layout.prop(scene, "prosthetic_tracker_baseline_percent", text="Manual Baseline (%)")
        layout.operator("prosthetic.set_tracker_baseline", icon='FILE_REFRESH')

        layout.separator()
        layout.operator("prosthetic.apply_tracked_scale", icon='MOD_SIMPLEDEFORM')


# 2. MASTER MODEL SETUP PANEL
class PROSTHETIC_PT_MasterSetupPanel(bpy.types.Panel):
    bl_label = "Master Model Setup"
    bl_idname = "PROSTHETIC_PT_master_setup_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'HandFit'
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        box = layout.box()
        box.label(text="Step 1: Define Inner Socket Area", icon='HAND')
        
        col = box.column(align=True)
        col.label(text="Option A: Automatic (Recommended)")
        col.label(text="- Select one inner face, then click:")
        col.prop(scene, "selection_threshold", text="Threshold")
        col.operator(PROSTHETIC_OT_SelectSocket.bl_idname)
        
        col = box.column(align=True)
        col.label(text="Option B: Manual")
        col.label(text="- Use 'C' (Circle Select) or other tools.")
        
        box.separator()
        box.label(text="Step 2: Assign Material", icon='MATERIAL')
        box.operator(PROSTHETIC_OT_AssignSocketMaterial.bl_idname)

# 3. WORKFLOW PANEL
class PROSTHETIC_PT_WorkflowPanel(bpy.types.Panel):
    bl_label = "Patient Fitting Workflow"
    bl_idname = "PROSTHETIC_PT_workflow_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'HandFit'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        box = layout.box()
        box.label(text="Step 1: Setup", icon='TOOL_SETTINGS')
        box.operator(PROSTHETIC_OT_CreateLandmarks.bl_idname)

        box = layout.box()
        box.label(text="Step 2: Execution", icon='PLAY')
        box.operator(PROSTHETIC_OT_FitObject.bl_idname)

        prosthetic_obj = bpy.data.objects.get("Prosthetic")
        if prosthetic_obj and "SocketFit" in prosthetic_obj.modifiers:
            modifier = prosthetic_obj.modifiers["SocketFit"]
            
            sub_box = layout.box()
            sub_box.label(text="Step 3: Adjustments", icon='MODIFIER')
            sub_box.prop(modifier, "show_viewport", text="Toggle Deformation")
            sub_box.prop(scene, "socket_offset_mm", text="Socket Offset (mm)")

            sub_box = layout.box()
            sub_box.label(text="Step 4: Finalize", icon='CHECKMARK')
            sub_box.operator(PROSTHETIC_OT_ApplyFit.bl_idname, text="Apply Fit On Prosthetic")
            sub_box.operator(PROSTHETIC_OT_BakeFitToNewObject.bl_idname, text="Create Fitted Copy")


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
    PROSTHETIC_PT_TrackerPanel,           
    PROSTHETIC_PT_MasterSetupPanel,       
    PROSTHETIC_PT_WorkflowPanel,         
)

def register():
    bpy.utils.register_class(prosthetic_fitter.ProstheticScaleTrackerProps)
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.prosthetic_scale_tracker = bpy.props.PointerProperty(type=prosthetic_fitter.ProstheticScaleTrackerProps)

    bpy.types.Scene.socket_offset_mm = bpy.props.FloatProperty(
        name="Socket Offset",
        description="Gap for liner in millimeters",
        default=3.0, min=0.0, max=1000000.0, soft_max=1000.0,
        update=update_offset
    )
    bpy.types.Scene.selection_threshold = bpy.props.FloatProperty(
        name="Selection Threshold",
        description="Angle to use for 'Select Similar by Normal'",
        default=0.1, min=0.0, max=1.0
    )
    bpy.types.Scene.prosthetic_tracker_baseline_percent = bpy.props.FloatProperty(
        name="Baseline %", description="Original prosthetic wrist width as a percentage of target", default=100.0, precision=1, subtype='PERCENTAGE'
    )
    prosthetic_fitter._register_tracker_handler()
    
def unregister():
    prosthetic_fitter._unregister_tracker_handler()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    if hasattr(bpy.types.Scene, "prosthetic_scale_tracker"):
        del bpy.types.Scene.prosthetic_scale_tracker
    if hasattr(bpy.types.Scene, 'socket_offset_mm'):
        del bpy.types.Scene.socket_offset_mm
    if hasattr(bpy.types.Scene, 'selection_threshold'):
        del bpy.types.Scene.selection_threshold
    if hasattr(bpy.types.Scene, 'prosthetic_tracker_baseline_percent'):
        del bpy.types.Scene.prosthetic_tracker_baseline_percent
    bpy.utils.unregister_class(prosthetic_fitter.ProstheticScaleTrackerProps)
   