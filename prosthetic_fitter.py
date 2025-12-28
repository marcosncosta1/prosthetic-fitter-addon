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


def ensure_tracker_defaults(tracker: ProstheticScaleTrackerProps, mutate: bool = True):
    """
    Guarantee the tracker has sane defaults.
    When called from UI draw, set mutate=False to avoid write restrictions.
    """
    if not tracker or tracker.initialized:
        return
    if not mutate:
        return
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

# --- Conform_socket function ---
def conform_socket(prosthetic_obj, scan_obj):
    bpy.context.view_layer.objects.active = prosthetic_obj
    prosthetic_obj.select_set(True)
    modifier_name = "SocketFit"
    for mod in prosthetic_obj.modifiers:
        if mod.name == modifier_name:
            prosthetic_obj.modifiers.remove(mod)
    shrinkwrap_mod = prosthetic_obj.modifiers.new(name=modifier_name, type='SHRINKWRAP')
    shrinkwrap_mod.target = scan_obj
    shrinkwrap_mod.vertex_group = "Socket_VG"
    # shrinkwrap_mod.offset = 0.003  original offset
    shrinkwrap_mod.offset = bpy.context.scene.socket_offset_mm / 1000.0
    print(f"Successfully applied '{modifier_name}' modifier.")

# --- THE MAIN CONTROLLER  ---
def run_fitting_process():
    try:
        scan_obj, prosthetic_obj = get_scene_objects()
        print("Found HandScan and Prosthetic objects.")
        auto_create_socket_vg(prosthetic_obj)
        landmarks = get_landmarks(scan_obj, prosthetic_obj)
        print("Found all required landmarks.")
        calculate_and_apply_transform(prosthetic_obj, landmarks)
        conform_socket(prosthetic_obj, scan_obj)
        print("\n--- Fitting Process Completed Successfully ---")
    except ValueError as e:
        print(f"ERROR: {e}")
        print("--- Fitting Process Aborted ---")