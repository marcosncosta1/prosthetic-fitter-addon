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
    
    print(f"Created solid object: '{filler_obj.name}'")
    return filler_obj


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