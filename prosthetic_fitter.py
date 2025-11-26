import bpy
import mathutils
from mathutils import Vector
from bpy.props import BoolProperty, FloatProperty, PointerProperty

_tracker_handler = None


class ProstheticScaleTrackerProps(bpy.types.PropertyGroup):
    """Holds the last-known scale factors so they can be reused."""

    initialized: BoolProperty(name="Initialized", default=False)
    baseline_wrist_bu: FloatProperty(name="Baseline Wrist (BU)", default=0.0, precision=4)
    baseline_palm_bu: FloatProperty(name="Baseline Palm (BU)", default=0.0, precision=4)
    scale_x_factor: FloatProperty(name="Scale X Factor", default=1.0, precision=6)
    scale_y_factor: FloatProperty(name="Scale Y Factor", default=1.0, precision=6)
    scale_z_factor: FloatProperty(name="Scale Z Factor", default=1.0, precision=6)
    scale_x_percent: FloatProperty(name="Scale X %", default=100.0, subtype='PERCENTAGE', precision=3)
    scale_y_percent: FloatProperty(name="Scale Y %", default=100.0, subtype='PERCENTAGE', precision=3)
    scale_z_percent: FloatProperty(name="Scale Z %", default=100.0, subtype='PERCENTAGE', precision=3)


def ensure_tracker_defaults(tracker: ProstheticScaleTrackerProps):
    """Guarantee the tracker has sane defaults before new values are written."""
    if tracker and not tracker.initialized:
        tracker.scale_x_percent = tracker.scale_y_percent = tracker.scale_z_percent = 100.0
        tracker.scale_x_factor = tracker.scale_y_factor = tracker.scale_z_factor = 1.0
        tracker.initialized = True


def update_scale_tracker(scale_xy, scale_z, prosthetic_obj, wrist_dist, palm_len):
    """Persist the latest scale factors so other parts can reuse them."""
    scene = bpy.context.scene
    tracker = getattr(scene, "prosthetic_scale_tracker", None)
    if not tracker:
        return

    ensure_tracker_defaults(tracker)

    tracker.baseline_wrist_bu = prosthetic_obj.get("baseline_wrist_bu", wrist_dist)
    tracker.baseline_palm_bu = prosthetic_obj.get("baseline_palm_bu", palm_len)
    tracker.scale_x_factor = scale_xy
    tracker.scale_y_factor = scale_xy
    tracker.scale_z_factor = scale_z
    tracker.scale_x_percent = scale_xy * 100.0
    tracker.scale_y_percent = scale_xy * 100.0
    tracker.scale_z_percent = scale_z * 100.0


def record_prosthetic_baselines(prosthetic_obj, wrist_dist, palm_len):
    """Store the original prosthetic measurements for future reference."""
    if "baseline_wrist_bu" not in prosthetic_obj:
        prosthetic_obj["baseline_wrist_bu"] = wrist_dist
    if "baseline_palm_bu" not in prosthetic_obj:
        prosthetic_obj["baseline_palm_bu"] = palm_len


def _ensure_prosthetic_baseline_scale(prosthetic_obj, factor=1.0):
    """
    Store the object's baseline scale so tracker updates can compare against it.
    Factor represents the percent (as 1.0 == 100%) we want the tracker to read
    at the current scale.
    """
    if not prosthetic_obj:
        return

    eps = 1e-8
    safe_factor = factor if abs(factor) > eps else 1.0
    baseline = []
    for axis, value in enumerate(prosthetic_obj.scale):
        baseline_value = value / safe_factor if abs(safe_factor) > eps else value
        baseline.append(max(baseline_value, eps))

    prosthetic_obj["tracker_baseline_scale"] = tuple(baseline)


def _sync_tracker_with_prosthetic(scene, force=False):
    """Continuously reflects the Prosthetic object's current scale in the tracker."""
    tracker = getattr(scene, "prosthetic_scale_tracker", None)
    prosthetic_obj = bpy.data.objects.get("Prosthetic")
    if not tracker or not prosthetic_obj:
        return

    ensure_tracker_defaults(tracker)

    baseline = prosthetic_obj.get("tracker_baseline_scale")
    if not baseline:
        _ensure_prosthetic_baseline_scale(prosthetic_obj)
        baseline = prosthetic_obj.get("tracker_baseline_scale")

    if not baseline:
        return

    eps = 1e-8
    bx, by, bz = (baseline[0] or eps, baseline[1] or eps, baseline[2] or eps)
    fx = prosthetic_obj.scale.x / bx
    fy = prosthetic_obj.scale.y / by
    fz = prosthetic_obj.scale.z / bz

    # Avoid churning values if nothing changed
    if not force:
        if (
            abs(tracker.scale_x_factor - fx) < 1e-4
            and abs(tracker.scale_y_factor - fy) < 1e-4
            and abs(tracker.scale_z_factor - fz) < 1e-4
        ):
            return

    tracker.scale_x_factor = fx
    tracker.scale_y_factor = fy
    tracker.scale_z_factor = fz
    tracker.scale_x_percent = fx * 100.0
    tracker.scale_y_percent = fy * 100.0
    tracker.scale_z_percent = fz * 100.0


def _tracker_depsgraph_handler(scene, depsgraph):
    """Blender handler hook to keep the tracker live."""
    try:
        _sync_tracker_with_prosthetic(scene)
    except Exception as exc:  # pragma: no cover - handler safety
        print(f"[HandFit] Tracker update failed: {exc}")


def _register_tracker_handler():
    global _tracker_handler
    if _tracker_handler is not None:
        return
    bpy.app.handlers.depsgraph_update_post.append(_tracker_depsgraph_handler)
    _tracker_handler = _tracker_depsgraph_handler


def _unregister_tracker_handler():
    global _tracker_handler
    if _tracker_handler and _tracker_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_tracker_handler)
    _tracker_handler = None


def get_scene_objects():
    scan_obj = bpy.data.objects.get("HandScan")
    prosthetic_obj = bpy.data.objects.get("Prosthetic")
    if not scan_obj: raise ValueError("Scene error: Could not find 'HandScan'.")
    if not prosthetic_obj: raise ValueError("Scene error: Could not find 'Prosthetic'.")
    return scan_obj, prosthetic_obj

def get_landmarks(scan_obj, prosthetic_obj):
    landmark_names = [
        "Hand_Wrist_L", "Hand_Wrist_R", "Hand_Palm",
        "Prosthetic_Wrist_L", "Prosthetic_Wrist_R", "Prosthetic_Palm"
    ]
    landmarks = {}
    for name in landmark_names:
        obj = bpy.data.objects.get(name)
        if not obj: raise ValueError(f"Scene error: Could not find landmark '{name}'.")
        landmarks[name] = obj.matrix_world.translation
    return landmarks


def auto_create_socket_vg(prosthetic_obj):
    vg_name = "Socket_VG"
    mat_name = "InnerSocket"
    mesh = prosthetic_obj.data
    try:
        socket_mat_index = prosthetic_obj.material_slots.find(mat_name)
    except ValueError:
        raise ValueError(f"Preparation error: Prosthetic is missing the '{mat_name}' material.")
    if vg_name in prosthetic_obj.vertex_groups:
        prosthetic_obj.vertex_groups.remove(prosthetic_obj.vertex_groups[vg_name])
    socket_vg = prosthetic_obj.vertex_groups.new(name=vg_name)
    verts_to_assign = [v_idx for face in mesh.polygons if face.material_index == socket_mat_index for v_idx in face.vertices]
    socket_vg.add(list(set(verts_to_assign)), 1.0, 'REPLACE')
    print(f"Automatically created and assigned '{vg_name}' vertex group.")


def calculate_and_apply_transform(prosthetic_obj, landmarks):
    """
    Calculates and applies transformations by anchoring the prosthetic's wrist
    to the hand's wrist, ensuring the wrist landmarks align perfectly.
    """
    # Isolate landmark vectors
    h_wl, h_wr, h_p = landmarks["Hand_Wrist_L"], landmarks["Hand_Wrist_R"], landmarks["Hand_Palm"]
    p_wl, p_wr, p_p = landmarks["Prosthetic_Wrist_L"], landmarks["Prosthetic_Wrist_R"], landmarks["Prosthetic_Palm"]

    # 1. DEFINE WRIST CENTERS AND ORIENTATION VECTORS
    hand_wrist_center = (h_wl + h_wr) / 2.0
    pros_wrist_center = (p_wl + p_wr) / 2.0
    
    hand_right_vec = (h_wr - h_wl).normalized()
    hand_fwd_vec = (h_p - hand_wrist_center).normalized()
    
    pros_right_vec = (p_wr - p_wl).normalized()
    pros_fwd_vec = (p_p - pros_wrist_center).normalized()

    # 2. CALCULATE SCALE AND ROTATION
    # XY scale is based on wrist width
    hand_wrist_dist = (h_wr - h_wl).length
    pros_wrist_dist = (p_wr - p_wl).length
    scale_xy = hand_wrist_dist / pros_wrist_dist if pros_wrist_dist != 0 else 1.0

    # Z scale is based on palm length
    hand_palm_len = (h_p - hand_wrist_center).length
    pros_palm_len = (p_p - pros_wrist_center).length
    scale_z = hand_palm_len / pros_palm_len if pros_palm_len != 0 else 1.0

    # Persist the original prosthetic measurements for later tracker usage
    record_prosthetic_baselines(prosthetic_obj, pros_wrist_dist, pros_palm_len)

    # Calculate rotation to align the prosthetic's orientation to the hand's
    rot_diff = pros_right_vec.rotation_difference(hand_right_vec)

    # 3. BUILD THE TRANSFORMATION MATRIX 
    # This process applies scale and rotation around the wrist center, not the object origin.
    
    # Start with a blank matrix
    mat_final = mathutils.Matrix.Identity(4)
    
    # Create matrices for each operation
    mat_trans_to_origin = mathutils.Matrix.Translation(-pros_wrist_center)
    mat_scale = mathutils.Matrix.Scale(scale_xy, 4, (1, 0, 0)) @ mathutils.Matrix.Scale(scale_xy, 4, (0, 1, 0)) @ mathutils.Matrix.Scale(scale_z, 4, (0, 0, 1))
    mat_rot = rot_diff.to_matrix().to_4x4()
    mat_trans_to_target = mathutils.Matrix.Translation(hand_wrist_center)

    # Combine the matrices in the correct order: move to origin, scale, rotate, move to target
    mat_final = mat_trans_to_target @ mat_rot @ mat_scale @ mat_trans_to_origin
    
    # Apply the final combined transformation to the prosthetic
    prosthetic_obj.matrix_world = mat_final @ prosthetic_obj.matrix_world
    
    update_scale_tracker(scale_xy, scale_z, prosthetic_obj, pros_wrist_dist, pros_palm_len)

    print(f"Applied Wrist-Centric Transform: Scale:(XY:{scale_xy:.2f}, Z:{scale_z:.2f})")

# --- Boolean Approach Functions ---

def create_socket_filler(prosthetic_obj):
    """
    Creates a solid 'filler' object from the faces assigned to the 'InnerSocket' material.
    """
    print("Creating Socket Filler...")
    
    # Ensure we are in Object Mode to start
    if bpy.context.object:
        bpy.ops.object.mode_set(mode='OBJECT')
        
    # Deselect all
    bpy.ops.object.select_all(action='DESELECT')
    
    # Select Prosthetic and make active
    bpy.context.view_layer.objects.active = prosthetic_obj
    prosthetic_obj.select_set(True)
    
    # Enter Edit Mode
    bpy.ops.object.mode_set(mode='EDIT')
    
    # Select faces with "InnerSocket" material
    bpy.ops.mesh.select_all(action='DESELECT')
    
    try:
        mat_idx = prosthetic_obj.material_slots.find("InnerSocket")
        if mat_idx == -1:
            raise ValueError("Material 'InnerSocket' not found on Prosthetic.")
            
        # We need to select faces by material index. 
        # Using bmesh is more robust but for simple selection this works:
        bpy.context.object.active_material_index = mat_idx
        bpy.ops.object.material_slot_select()
        
    except Exception as e:
        bpy.ops.object.mode_set(mode='OBJECT')
        raise e

    # Duplicate selected faces
    bpy.ops.mesh.duplicate()
    
    # Separate to a new object
    bpy.ops.mesh.separate(type='SELECTED')
    
    # Return to Object Mode
    bpy.ops.object.mode_set(mode='OBJECT')
    
    # Identify the new object (it will be selected)
    selected_objects = bpy.context.selected_objects
    filler_obj = None
    for obj in selected_objects:
        if obj != prosthetic_obj:
            filler_obj = obj
            break
            
    if not filler_obj:
        raise RuntimeError("Failed to create Socket Filler object.")
        
    # Rename and setup filler
    filler_obj.name = "Socket_Filler"
    
    # Clean up the filler mesh (Cap holes to make it solid)
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = filler_obj
    filler_obj.select_set(True)
    
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    
    # Fill holes (Cap the open end)
    # Fills all edges, creating a solid volume
    bpy.ops.mesh.fill_holes() 
    
    # Recalculate normals to be sure they point out
    bpy.ops.mesh.normals_make_consistent(inside=False)
    
    bpy.ops.object.mode_set(mode='OBJECT')
    
    configure_socket_filler(filler_obj)
    print(f"Created solid object: '{filler_obj.name}'")
    return filler_obj


def get_socket_filler():
    return bpy.data.objects.get("Socket_Filler")


def _ensure_socket_filler_modifiers(filler_obj):
    """Guarantee the filler has the modifiers we expect for live tuning."""
    solid = filler_obj.modifiers.get("SocketFiller_Solid")
    if not solid:
        solid = filler_obj.modifiers.new(name="SocketFiller_Solid", type='SOLIDIFY')
        solid.use_even_offset = True
        solid.offset = 1.0
        solid.thickness = 0.003
        solid.show_in_editmode = True

    displace = filler_obj.modifiers.get("SocketFiller_Displace")
    if not displace:
        displace = filler_obj.modifiers.new(name="SocketFiller_Displace", type='DISPLACE')
        displace.mid_level = 0.0
        displace.strength = 0.0
        displace.direction = 'NORMAL'

    return solid, displace


def configure_socket_filler(filler_obj, scene=None):
    """Applies visibility and modifier settings from the current scene."""
    if not filler_obj:
        return

    if scene is None:
        scene = bpy.context.scene

    solid, displace = _ensure_socket_filler_modifiers(filler_obj)

    if scene:
        thickness = getattr(
            scene,
            "socket_filler_thickness_m",
            getattr(scene, "socket_filler_thickness_mm", 0.003),
        )
        push = getattr(
            scene,
            "socket_filler_push_m",
            getattr(scene, "socket_filler_push_mm", 0.0),
        )
        visible = getattr(scene, "socket_filler_visible", False)

        solid.thickness = thickness
        displace.strength = push

        filler_obj.hide_viewport = not visible
        filler_obj.hide_render = not visible


def update_socket_filler_visibility(self, context):
    filler_obj = get_socket_filler()
    if not filler_obj:
        return
    visible = context.scene.socket_filler_visible
    filler_obj.hide_viewport = not visible
    filler_obj.hide_render = not visible


def update_socket_filler_thickness(self, context):
    filler_obj = get_socket_filler()
    if not filler_obj:
        return
    solid, _ = _ensure_socket_filler_modifiers(filler_obj)
    solid.thickness = context.scene.socket_filler_thickness_m


def update_socket_filler_push(self, context):
    filler_obj = get_socket_filler()
    if not filler_obj:
        return
    _, displace = _ensure_socket_filler_modifiers(filler_obj)
    displace.strength = context.scene.socket_filler_push_m


def apply_boolean_fit(filler_obj, scan_obj):
    """
    Applies a Boolean Difference using a proxy of the scan object.
    The proxy handles the offset via a Displace modifier.
    """
    print("Applying Boolean Fit...")
    
    # 1. Create a Proxy of the HandScan for the Boolean operation
    proxy_name = "HandScan_Proxy"
    
    # Check if proxy already exists and delete it
    if bpy.data.objects.get(proxy_name):
        bpy.data.objects.remove(bpy.data.objects[proxy_name], do_unlink=True)
        
    # Duplicate HandScan 
    proxy_obj = scan_obj.copy()
    proxy_obj.data = scan_obj.data.copy()
    proxy_obj.name = proxy_name
    bpy.context.collection.objects.link(proxy_obj)
    
    # Hide the proxy
    proxy_obj.hide_viewport = True
    proxy_obj.hide_render = True
    
    # 2. Add Displace Modifier to Proxy (for Offset/Liner Gap)
    # We use a Displace modifier with no texture to push vertices along normals
    displace_mod = proxy_obj.modifiers.new(name="Offset_Displace", type='DISPLACE')
    displace_mod.mid_level = 0.0 # Absolute displacement
    # Strength will be controlled by the scene property in the UI update function
    displace_mod.strength = bpy.context.scene.socket_offset_mm / 1000.0 
    
    # 3. Add Boolean Modifier to Filler
    bool_mod = filler_obj.modifiers.new(name="Socket_Boolean", type='BOOLEAN')
    bool_mod.operation = 'DIFFERENCE'
    bool_mod.object = proxy_obj
    bool_mod.solver = 'FAST' # 'FAST' is often better for complex scans, 'EXACT' is more robust but slower
    
    print("Boolean modifier applied.")
    return proxy_obj


def create_socket_filler_only():
    """
    Convenience helper for the UI: build the filler mesh without running
    the full fitting/boolean workflow. Intended for quick inspection.
    """
    scan_obj, prosthetic_obj = get_scene_objects()
    scene = bpy.context.scene
    auto_create_socket_vg(prosthetic_obj)
    filler_obj = create_socket_filler(prosthetic_obj)
    if hasattr(scene, "socket_filler_visible"):
        scene.socket_filler_visible = True

    # Make the newly created filler active so users can work on it right away.
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = filler_obj
    filler_obj.select_set(True)

    print("Socket filler ready for inspection. Run full fit to boolean cut.")
    return filler_obj


class PROSTHETIC_OT_apply_tracked_scale(bpy.types.Operator):
    """Applies the stored prosthetic scale factors to the current selection."""

    bl_idname = "prosthetic.apply_tracked_scale"
    bl_label = "Match Selected To Tracker"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        tracker = getattr(context.scene, "prosthetic_scale_tracker", None)

        if not tracker or not tracker.initialized:
            self.report({'WARNING'}, "Tracker has no data yet. Run the fitting process first.")
            return {'CANCELLED'}

        targets = [
            obj for obj in context.selected_objects
            if obj.type in {'MESH', 'CURVE', 'SURFACE', 'FONT', 'META'} and obj.name != "Prosthetic"
        ]

        if not targets:
            self.report({'WARNING'}, "Select at least one non-prosthetic object to scale.")
            return {'CANCELLED'}

        for obj in targets:
            obj.scale.x *= tracker.scale_x_factor
            obj.scale.y *= tracker.scale_y_factor
            obj.scale.z *= tracker.scale_z_factor

        self.report({'INFO'}, f"Applied tracked scale to {len(targets)} object(s).")
        return {'FINISHED'}


class PROSTHETIC_OT_set_tracker_baseline(bpy.types.Operator):
    """Allows the user to start the tracker at a custom percentage scale."""

    bl_idname = "prosthetic.set_tracker_baseline"
    bl_label = "Apply Manual Baseline"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        tracker = getattr(context.scene, "prosthetic_scale_tracker", None)

        if not tracker:
            self.report({'ERROR'}, "Tracker data missing.")
            return {'CANCELLED'}

        prosthetic_obj = bpy.data.objects.get("Prosthetic")
        if not prosthetic_obj:
            self.report({'ERROR'}, "Could not find 'Prosthetic' object.")
            return {'CANCELLED'}

        ensure_tracker_defaults(tracker)

        pct = context.scene.prosthetic_tracker_baseline_percent
        factor = pct / 100.0

        _ensure_prosthetic_baseline_scale(prosthetic_obj, factor)
        _sync_tracker_with_prosthetic(context.scene, force=True)

        self.report({'INFO'}, f"Tracker baseline set to {pct:.2f}%")
        return {'FINISHED'}


# --- THE MAIN CONTROLLER  ---
def run_fitting_process():
    try:
        scan_obj, prosthetic_obj = get_scene_objects()
        print("Found HandScan and Prosthetic objects.")
        
        # Ensure Socket_VG logic is still valid or if we just need the material
        # The new approach relies on the material "InnerSocket" existing.
        # We can keep auto_create_socket_vg if it helps visualize, but it's not strictly needed for the boolean filler creation
        # which selects by material. Let's keep it for backward compatibility/visuals.
        auto_create_socket_vg(prosthetic_obj)
        
        landmarks = get_landmarks(scan_obj, prosthetic_obj)
        print("Found all required landmarks.")
        
        calculate_and_apply_transform(prosthetic_obj, landmarks)
        
        # --- NEW BOOLEAN LOGIC ---
        # 1. Create the filler object
        filler_obj = create_socket_filler(prosthetic_obj)
        
        # 2. Apply the boolean cut
        apply_boolean_fit(filler_obj, scan_obj)
        
        print("\n--- Fitting Process Completed Successfully ---")
        
    except ValueError as e:
        print(f"ERROR: {e}")
        print("--- Fitting Process Aborted ---")
    except RuntimeError as e:
        print(f"RUNTIME ERROR: {e}")
        print("--- Fitting Process Aborted ---")


classes = (
    ProstheticScaleTrackerProps,
    PROSTHETIC_OT_apply_tracked_scale,
    PROSTHETIC_OT_set_tracker_baseline,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    if not hasattr(bpy.types.Scene, "prosthetic_scale_tracker"):
        bpy.types.Scene.prosthetic_scale_tracker = PointerProperty(type=ProstheticScaleTrackerProps)

    if not hasattr(bpy.types.Scene, "prosthetic_tracker_baseline_percent"):
        bpy.types.Scene.prosthetic_tracker_baseline_percent = FloatProperty(
            name="Tracker Baseline %",
            description="Manual starting percentage for the tracker",
            default=100.0,
            min=1.0,
            max=400.0,
            precision=2,
            subtype='PERCENTAGE'
        )

    if not hasattr(bpy.types.Scene, "socket_filler_visible"):
        bpy.types.Scene.socket_filler_visible = BoolProperty(
            name="Show Socket Filler",
            description="Toggle visibility of the preview filler mesh",
            default=False,
            update=update_socket_filler_visibility,
        )

    if not hasattr(bpy.types.Scene, "socket_filler_thickness_m"):
        bpy.types.Scene.socket_filler_thickness_m = FloatProperty(
            name="Filler Thickness",
            description="Controls the extra volume added to the socket filler",
            default=0.003,
            min=0.0001,
            precision=4,
            unit='LENGTH',
            update=update_socket_filler_thickness,
        )

    if not hasattr(bpy.types.Scene, "socket_filler_push_m"):
        bpy.types.Scene.socket_filler_push_m = FloatProperty(
            name="Filler Push",
            description="Offsets the filler along its normals to tweak height/depth",
            default=0.0,
            min=-0.01,
            precision=4,
            unit='LENGTH',
            update=update_socket_filler_push,
        )

    _register_tracker_handler()


def unregister():
    if hasattr(bpy.types.Scene, "prosthetic_tracker_baseline_percent"):
        del bpy.types.Scene.prosthetic_tracker_baseline_percent

    if hasattr(bpy.types.Scene, "prosthetic_scale_tracker"):
        del bpy.types.Scene.prosthetic_scale_tracker

    for attr in (
        "socket_filler_visible",
        "socket_filler_thickness_m",
        "socket_filler_push_m",
    ):
        if hasattr(bpy.types.Scene, attr):
            delattr(bpy.types.Scene, attr)

    _unregister_tracker_handler()

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()