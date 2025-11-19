import bpy
import mathutils
from mathutils import Vector


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