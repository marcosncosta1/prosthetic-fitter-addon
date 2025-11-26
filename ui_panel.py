import bpy
import bmesh
from . import prosthetic_fitter


def _call_run_fitting_process():
    """Wrapper so we don't break if the fitter module signature changes."""
    if hasattr(prosthetic_fitter, "run_fitting_process"):
        return prosthetic_fitter.run_fitting_process()
    raise RuntimeError("prosthetic_fitter.run_fitting_process() is missing.")


def _call_create_socket_filler_only():
    """Optional helper: only available on newer fitter versions."""
    if hasattr(prosthetic_fitter, "create_socket_filler_only"):
        return prosthetic_fitter.create_socket_filler_only()
    # Fall back to the legacy behavior: run the whole fitting process
    # so users on older versions still get a filler created.
    return _call_run_fitting_process()

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


class PROSTHETIC_OT_CreateSocketFiller(bpy.types.Operator):
    bl_idname = "prosthetic.create_socket_filler"
    bl_label = "Create/Show Socket Filler"
    def execute(self, context):
        try:
            _call_create_socket_filler_only()
            return {'FINISHED'}
        except ValueError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}


class PROSTHETIC_OT_FitObject(bpy.types.Operator):
    bl_idname = "prosthetic.fit_object"
    bl_label = "Fit Prosthetic to Scan"
    def execute(self, context):
        try:
            _call_run_fitting_process()
            context.scene.socket_offset_m = 0.003
            return {'FINISHED'}
        except ValueError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

class PROSTHETIC_OT_ApplyFit(bpy.types.Operator):
    bl_idname = "prosthetic.apply_fit"
    bl_label = "Apply and Finalize Fit"
    def execute(self, context):
        filler_obj = bpy.data.objects.get("Socket_Filler")
        proxy_obj = bpy.data.objects.get("HandScan_Proxy")
        
        if filler_obj and "Socket_Boolean" in filler_obj.modifiers:
            # Apply the Boolean modifier
            bpy.context.view_layer.objects.active = filler_obj
            bpy.ops.object.modifier_apply(modifier="Socket_Boolean")
            
            # Clean up the proxy object
            if proxy_obj:
                bpy.data.objects.remove(proxy_obj, do_unlink=True)
                
            self.report({'INFO'}, "Fit applied. 'Socket_Filler' is now final. Proxy removed.")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Could not find 'Socket_Filler' or its boolean modifier.")
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

        prosthetic_fitter.ensure_tracker_defaults(tracker)

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


class PROSTHETIC_PT_MasterSetupPanel(bpy.types.Panel):
    """Section 2: Prepare master prosthetic model."""

    bl_label = "Master Model Setup"
    bl_idname = "PROSTHETIC_PT_master_setup_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'HandFit'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.label(text="Step 1: Make Your Selection (in Edit Mode)")
        col = layout.column(align=True)
        col.label(text="Option A: Automatic (Recommended)")
        col.label(text="- Select one inner face, then click:")
        col.prop(scene, "selection_threshold", text="Threshold")
        col.operator("prosthetic.select_socket")
        col = layout.column(align=True)
        col.label(text="Option B: Manual")
        col.label(text="- Use 'C' (Circle Select) or other tools.")
        layout.label(text="Step 2: Assign Material")
        layout.operator("prosthetic.assign_socket_material")


class PROSTHETIC_PT_WorkflowPanel(bpy.types.Panel):
    """Section 3: Patient fitting workflow."""

    bl_label = "Patient Fitting Workflow"
    bl_idname = "PROSTHETIC_PT_workflow_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'HandFit'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        box = layout.box()
        box.label(text="Step 1: Pre-Fit Inspection", icon='VIEWZOOM')
        box.operator("prosthetic.create_socket_filler")
        filler_controls = box.box()
        filler_controls.label(text="Socket Filler Preview", icon='MESH_CYLINDER')

        if hasattr(scene, "socket_filler_visible"):
            filler_controls.prop(scene, "socket_filler_visible", text="Show Socket Filler")
        else:
            filler_controls.label(text="Reload add-on to access filler controls.", icon='INFO')

        filler_obj = bpy.data.objects.get("Socket_Filler")
        if filler_obj and hasattr(scene, "socket_filler_thickness_m"):
            filler_controls.prop(scene, "socket_filler_thickness_m", text="Volume (m)")
            filler_controls.prop(scene, "socket_filler_push_m", text="Height Adjust (m)")
        else:
            filler_controls.label(text="Create a socket filler to adjust settings.", icon='INFO')

        box.label(text="Step 2: Setup", icon='TOOL_SETTINGS')
        box.operator("prosthetic.create_landmarks")
        box.label(text="Step 3: Execution", icon='PLAY')
        box.operator("prosthetic.fit_object")

        # Check for the new Socket_Filler object
        filler_obj = bpy.data.objects.get("Socket_Filler")
        if filler_obj and "Socket_Boolean" in filler_obj.modifiers:
            modifier = filler_obj.modifiers["Socket_Boolean"]
            sub_box = box.box()
            sub_box.label(text="Step 4: Adjustments", icon='MODIFIER')
            sub_box.prop(modifier, "show_viewport", text="Toggle Cut")
            sub_box.prop(scene, "socket_offset_m", text="Socket Offset (m)")
            sub_box = box.box()
            sub_box.label(text="Step 5: Finalize", icon='CHECKMARK')
            sub_box.operator("prosthetic.apply_fit")

# --- CUSTOM PROPERTY & REGISTRATION ---
def update_offset(self, context):
    # Updates the Displace modifier on the Proxy object
    proxy_obj = bpy.data.objects.get("HandScan_Proxy")
    if proxy_obj and "Offset_Displace" in proxy_obj.modifiers:
        proxy_obj.modifiers["Offset_Displace"].strength = context.scene.socket_offset_m
classes = (
    PROSTHETIC_OT_CreateLandmarks,
    PROSTHETIC_OT_CreateSocketFiller,
    PROSTHETIC_OT_FitObject,
    PROSTHETIC_OT_ApplyFit,
    PROSTHETIC_OT_SelectSocket,
    PROSTHETIC_OT_AssignSocketMaterial,
    PROSTHETIC_PT_TrackerPanel,
    PROSTHETIC_PT_MasterSetupPanel,
    PROSTHETIC_PT_WorkflowPanel,
)
def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.socket_offset_m = bpy.props.FloatProperty(
        name="Socket Offset",
        description="Gap for liner in meters",
        default=0.003, min=0.0, max=0.01, unit='LENGTH',
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
    if hasattr(bpy.types.Scene, 'socket_offset_m'):
        del bpy.types.Scene.socket_offset_m
    if hasattr(bpy.types.Scene, 'selection_threshold'):
        del bpy.types.Scene.selection_threshold