import bpy
import bmesh
import math
import mathutils
from mathutils import Vector, geometry
from mathutils.bvhtree import BVHTree


def get_socket_vertices(prosthetic_obj, evaluate_modifiers=True):
    """
    Get all vertices from the InnerSocket material faces.
    If evaluate_modifiers is True, evaluates modifiers (like SocketFit) to get deformed positions.
    Returns a list of (vertex_index, world_position) tuples.
    """
    mesh = prosthetic_obj.data
    mat_name = "InnerSocket"

    try:
        socket_mat_index = prosthetic_obj.material_slots.find(mat_name)
    except ValueError:
        raise ValueError(f"Prosthetic is missing the '{mat_name}' material.")

    if socket_mat_index == -1:
        raise ValueError(f"Prosthetic is missing the '{mat_name}' material.")

    # Get world matrix for transforming vertices
    world_matrix = prosthetic_obj.matrix_world

    # Collect all vertices from InnerSocket faces
    socket_vertices = []
    vertex_indices = set()

    # Get vertex positions (with or without modifiers)
    eval_mesh = None
    eval_world_matrix = None
    if evaluate_modifiers:
        # Check if SocketFit modifier exists and is visible
        has_socketfit = "SocketFit" in prosthetic_obj.modifiers
        socketfit_visible = prosthetic_obj.modifiers["SocketFit"].show_viewport if has_socketfit else False

        if has_socketfit and not socketfit_visible:
            print("Warning: SocketFit modifier exists but is not visible in viewport. Measurements will use undeformed geometry.")

        # Use depsgraph to evaluate modifiers (only visible modifiers are evaluated)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        eval_obj = prosthetic_obj.evaluated_get(depsgraph)
        eval_mesh = eval_obj.data
        eval_world_matrix = eval_obj.matrix_world

        print(f"Evaluating with modifiers: {len(eval_mesh.vertices)} vertices in evaluated mesh")

    for face in mesh.polygons:
        if face.material_index == socket_mat_index:
            for v_idx in face.vertices:
                if v_idx not in vertex_indices:
                    vertex_indices.add(v_idx)
                    # Get vertex position (deformed if modifiers evaluated)
                    if evaluate_modifiers and eval_mesh and v_idx < len(eval_mesh.vertices):
                        # Use evaluated mesh position
                        local_vert = eval_mesh.vertices[v_idx].co
                        world_vert = eval_world_matrix @ local_vert
                    else:
                        # Use original mesh position
                        local_vert = mesh.vertices[v_idx].co
                        world_vert = world_matrix @ local_vert
                    socket_vertices.append((v_idx, world_vert))

    print(f"Found {len(socket_vertices)} socket vertices from InnerSocket material faces")
    return socket_vertices


def build_bvh_tree(obj):
    """
    Build a BVH tree from an object's mesh for efficient nearest point queries.
    """
    # Ensure we're in object mode
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    
    # Create bmesh from object
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.transform(obj.matrix_world)
    
    # Build BVH tree
    bvh = BVHTree.FromBMesh(bm)
    
    bm.free()
    return bvh


def calculate_rmse_and_distances(handscan_obj, prosthetic_obj, evaluate_modifiers=True):
    """
    Calculate RMSE between HandScan mesh and InnerSocket vertices.
    If evaluate_modifiers is True, evaluates modifiers (like SocketFit) for accurate measurement.
    Returns (rmse_value, distances_dict) where distances_dict maps vertex_index -> distance
    All distances are in Blender Units (meters by default).
    """
    # Get Blender scene unit scale
    unit_scale = bpy.context.scene.unit_settings.scale_length
    print(f"Scene unit scale: {unit_scale} (1 BU = {unit_scale}m)")

    # Get socket vertices (with modifiers evaluated if requested)
    socket_vertices = get_socket_vertices(prosthetic_obj, evaluate_modifiers=evaluate_modifiers)

    if not socket_vertices:
        raise ValueError("No InnerSocket vertices found. Ensure InnerSocket material is assigned.")

    # Build BVH tree for HandScan
    handscan_bvh = build_bvh_tree(handscan_obj)
    
    # Calculate distances
    distances = []
    distances_dict = {}
    
    for v_idx, world_pos in socket_vertices:
        # Find nearest point on HandScan mesh
        location, _normal, _face_index, distance = handscan_bvh.find_nearest(world_pos)

        if location is None:
            # Fallback: use distance to nearest vertex
            min_dist = float('inf')
            for vert in handscan_obj.data.vertices:
                vert_world = handscan_obj.matrix_world @ vert.co
                dist = (world_pos - vert_world).length
                if dist < min_dist:
                    min_dist = dist
            distance = min_dist

        distances.append(distance)
        distances_dict[v_idx] = distance

    # Calculate RMSE
    if distances:
        squared_distances = [d * d for d in distances]
        mean_squared = sum(squared_distances) / len(squared_distances)
        rmse = math.sqrt(mean_squared)

        # Debug output
        print(f"\nRMSE Calculation: {len(distances)} vertices measured")
        print(f"  Min distance: {min(distances):.6f} BU = {min(distances)*1000:.3f}mm")
        print(f"  Max distance: {max(distances):.6f} BU = {max(distances)*1000:.3f}mm")
        print(f"  Mean distance: {(sum(distances)/len(distances)):.6f} BU = {(sum(distances)/len(distances))*1000:.3f}mm")
        print(f"  RMSE: {rmse:.6f} BU = {rmse*1000:.3f}mm")
        print(f"  Distance range: {(max(distances)-min(distances))*1000:.3f}mm")
    else:
        rmse = 0.0

    return rmse, distances_dict


def distance_to_color_material_added(distance, threshold_blue=2.0, threshold_green=5.0, threshold_yellow=8.0, unit_scale=1000.0):
    """
    Maps original gap distance to a heat map color.
    This represents the "void" that the Shrinkwrap modifier must fill with material.

    Color Logic (based on clinical interpretation):
    - Blue (0-threshold_blue): Excellent fit, minimal material added. The original model fits the scan perfectly.
    - Green/Yellow (threshold_blue-threshold_green): Moderate material added. Acceptable gap.
    - Yellow/Orange (threshold_green-threshold_yellow): Poor base fit, significant material added.
    - Red (>threshold_yellow): Extreme gap. The shrinkwrap must "stretch" the mesh significantly.

    Args:
        distance: Gap distance in Blender Units (meters)
        threshold_blue: Upper limit for blue color (mm), default 2.0
        threshold_green: Upper limit for green color (mm), default 5.0
        threshold_yellow: Upper limit for yellow/orange color (mm), default 8.0
        unit_scale: Scale factor to convert BU to mm (default 1000.0)

    Returns:
        RGBA tuple (0.0-1.0 range)
    """
    gap_mm = (distance * 1000.0) / unit_scale  # Convert Blender Units to mm with scale

    # Define thresholds for color transition
    if gap_mm <= threshold_blue:
        # Blue (Tight fit - excellent, minimal material added)
        return (0.0, 0.4, 1.0, 1.0)
    elif gap_mm <= threshold_green:
        # Blue to Green transition (Moderate gap)
        t = (gap_mm - threshold_blue) / (threshold_green - threshold_blue) if threshold_green > threshold_blue else 0.0
        return (0.0, 0.4 + (0.6 * t), 1.0 - (0.5 * t), 1.0)
    elif gap_mm <= threshold_yellow:
        # Green to Red transition (Poor base fit)
        t = (gap_mm - threshold_green) / (threshold_yellow - threshold_green) if threshold_yellow > threshold_green else 0.0
        return (t, 1.0 - t, 0.0, 1.0)
    else:
        # Solid Red (Extreme gap - very poor model fit)
        return (1.0, 0.0, 0.0, 1.0)


def create_heat_map(prosthetic_obj, distances_dict, colormap_name="FitQuality", threshold_blue=2.0, threshold_green=5.0, threshold_yellow=8.0):
    """
    Create a vertex color heat map on the prosthetic object based on distances.

    Metric Definition: Measures the distance from the original (undeformed) socket
    vertices to the HandScan surface. This represents the "void" that the Shrinkwrap
    modifier must fill with material.

    Color Logic:
    - Blue: Minimal distance (0mm - threshold_blue). The original model fits the scan perfectly;
            very little material is added.
    - Green/Yellow: Moderate distance (threshold_blue - threshold_green). Acceptable gap.
    - Yellow/Orange: Large distance (threshold_green - threshold_yellow). Poor fit, significant gap.
    - Red: Very large distance (>threshold_yellow). There is a significant gap between the scan
           and the prosthetic; the shrinkwrap must "stretch" the mesh, adding significant material.

    Args:
        prosthetic_obj: The prosthetic mesh object
        distances_dict: Dictionary mapping vertex indices to distances (in BU/meters)
        colormap_name: Name for the color attribute
        threshold_blue: Upper limit for blue color (mm), default 2.0
        threshold_green: Upper limit for green color (mm), default 5.0
        threshold_yellow: Upper limit for yellow/orange color (mm), default 8.0
    """
    # Get unit scale factor from scene settings
    unit_scale = bpy.context.scene.fit_unit_scale_factor if hasattr(bpy.context.scene, 'fit_unit_scale_factor') else 1000.0

    mesh = prosthetic_obj.data

    # Ensure we're in object mode
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    # Ensure Color Attribute exists (create if needed, reuse if exists)
    if colormap_name not in mesh.color_attributes:
        mesh.color_attributes.new(name=colormap_name, type='BYTE_COLOR', domain='POINT')
    color_attr = mesh.color_attributes[colormap_name]

    # Normalize distances for color mapping
    if not distances_dict:
        return

    distances_list = list(distances_dict.values())
    min_dist = min(distances_list)
    max_dist = max(distances_list)
    dist_range = max_dist - min_dist
    mean_dist = sum(distances_list) / len(distances_list)

    # Get socket offset for reference
    socket_offset = 0.003  # Default 3mm
    if "SocketFit" in prosthetic_obj.modifiers:
        socket_offset = prosthetic_obj.modifiers["SocketFit"].offset

    print(f"\n=== HEAT MAP GENERATION (Material Added) ===")
    print(f"Visualizing: Original socket gap (distance before shrinkwrap)")
    print(f"Socket offset setting: {socket_offset*1000:.1f}mm")
    print(f"Gap range: {min_dist*1000:.3f}mm to {max_dist*1000:.3f}mm (Δ = {dist_range*1000:.3f}mm)")
    print(f"Mean gap: {mean_dist*1000:.3f}mm (avg material to be added)")

    # Initialize all vertices to neutral gray (non-socket vertices)
    for i in range(len(mesh.vertices)):
        color_attr.data[i].color = (0.2, 0.2, 0.2, 1.0)

    # Apply specific heat map colors to Socket vertices using absolute thresholds
    color_samples = []
    for v_idx, dist in distances_dict.items():
        if v_idx < len(mesh.vertices):
            color = distance_to_color_material_added(dist, threshold_blue, threshold_green, threshold_yellow, unit_scale)
            color_attr.data[v_idx].color = color
            # Collect some samples for debugging (apply unit scale for display)
            if len(color_samples) < 10:
                color_samples.append((v_idx, (dist * 1000) / unit_scale, color))

    # Update mesh
    mesh.update()

    print(f"\nHeat map '{colormap_name}' created successfully!")
    print(f"Color Legend (Absolute Thresholds):")
    print(f"  Blue (0-{threshold_blue}mm): Excellent fit - minimal material added")
    print(f"  Green ({threshold_blue}-{threshold_green}mm): Moderate fit - acceptable material added")
    print(f"  Yellow/Orange ({threshold_green}-{threshold_yellow}mm): Poor fit - significant material added")
    print(f"  Red (>{threshold_yellow}mm): Very poor fit - extreme gap, major material added")

    # Debug: Show actual color assignments
    print(f"\n  Sample color assignments (first 10 vertices):")
    for v_idx, dist_mm, color in color_samples:
        color_name = "BLUE" if color[2] > 0.5 else ("GREEN" if color[1] > 0.5 else ("RED" if color[0] > 0.5 else "YELLOW"))
        print(f"    Vertex {v_idx}: {dist_mm:.3f}mm → {color_name} {color}")

    print(f"\n→ Blue areas = Good model selection (socket close to hand)")
    print(f"→ Red areas = Poor model selection (consider different size)")


def setup_heat_map_material(prosthetic_obj, colormap_name="FitQuality"):
    """
    Create or update a material to display the vertex color heat map.
    Updates the InnerSocket material to show vertex colors.
    """
    mesh = prosthetic_obj.data

    # Check if color attribute exists
    if colormap_name not in mesh.color_attributes:
        print(f"Warning: Color attribute '{colormap_name}' not found.")
        return

    # Find or create InnerSocket material
    mat_name = "InnerSocket"
    mat_slot_index = prosthetic_obj.material_slots.find(mat_name)

    if mat_slot_index == -1:
        print(f"Warning: '{mat_name}' material not found on prosthetic.")
        return

    mat = prosthetic_obj.material_slots[mat_slot_index].material

    if not mat:
        print(f"Warning: Material slot '{mat_name}' is empty.")
        return

    # Enable use_nodes for modern Blender
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    # Clear existing nodes to set up heat map visualization
    nodes.clear()

    # Create nodes
    output_node = nodes.new(type='ShaderNodeOutputMaterial')
    output_node.location = (300, 0)

    principled = nodes.new(type='ShaderNodeBsdfPrincipled')
    principled.location = (0, 0)

    attr_node = nodes.new(type='ShaderNodeAttribute')
    attr_node.location = (-300, 0)
    attr_node.attribute_name = colormap_name

    # Connect nodes
    links.new(attr_node.outputs['Color'], principled.inputs['Base Color'])
    links.new(principled.outputs['BSDF'], output_node.inputs['Surface'])

    print(f"Updated '{mat_name}' material to display heat map '{colormap_name}'")


def calculate_volumetric_congruency(handscan_obj, prosthetic_obj, evaluate_modifiers=True):
    """
    Calculate the liner volume by performing a boolean subtraction between
    the prosthetic socket and the hand scan. This represents the "empty space"
    or air gap available for the soft liner.

    Parameters:
    - handscan_obj: The HandScan mesh object
    - prosthetic_obj: The Prosthetic mesh object
    - evaluate_modifiers: If True, evaluates modifiers (like SocketFit) before calculation

    Returns:
    - liner_volume: Volume in cubic meters (convert to cm³ or mm³ for display)
    """
    # Ensure we're in object mode
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    # Store original active object
    original_active = bpy.context.view_layer.objects.active
    original_selection = [obj for obj in bpy.context.selected_objects]

    try:
        # Deselect all
        for obj in bpy.context.selected_objects:
            obj.select_set(False)

        # Create temporary duplicate of prosthetic for boolean operation
        prosthetic_temp = prosthetic_obj.copy()
        prosthetic_temp.data = prosthetic_obj.data.copy()
        prosthetic_temp.name = "TempProsthetic_BoolOp"
        bpy.context.collection.objects.link(prosthetic_temp)

        # If evaluate_modifiers is True, apply the SocketFit modifier to temp object
        if evaluate_modifiers and "SocketFit" in prosthetic_temp.modifiers:
            # Check if modifier is visible in viewport
            if not prosthetic_temp.modifiers["SocketFit"].show_viewport:
                print("Warning: SocketFit modifier not visible, volumetric calculation will use undeformed geometry")
            else:
                bpy.context.view_layer.objects.active = prosthetic_temp
                prosthetic_temp.select_set(True)
                bpy.ops.object.modifier_apply(modifier="SocketFit")
                prosthetic_temp.select_set(False)
                print("Applied SocketFit modifier for volumetric calculation")

        # Create temporary duplicate of handscan
        handscan_temp = handscan_obj.copy()
        handscan_temp.data = handscan_obj.data.copy()
        handscan_temp.name = "TempHandScan_BoolOp"
        bpy.context.collection.objects.link(handscan_temp)

        # Add boolean modifier to prosthetic temp to subtract handscan
        bool_mod = prosthetic_temp.modifiers.new(name="LinerVolumeBool", type='BOOLEAN')
        bool_mod.operation = 'DIFFERENCE'
        bool_mod.object = handscan_temp
        bool_mod.solver = 'FAST'

        # Apply the boolean modifier
        bpy.context.view_layer.objects.active = prosthetic_temp
        prosthetic_temp.select_set(True)

        try:
            bpy.ops.object.modifier_apply(modifier="LinerVolumeBool")
        except RuntimeError as e:
            print(f"Warning: Boolean operation failed: {e}")
            # Clean up and return 0
            bpy.data.objects.remove(prosthetic_temp, do_unlink=True)
            bpy.data.objects.remove(handscan_temp, do_unlink=True)
            return 0.0

        # Calculate volume of the resulting mesh
        bm = bmesh.new()
        bm.from_mesh(prosthetic_temp.data)
        bm.transform(prosthetic_temp.matrix_world)

        # Calculate volume
        volume = bm.calc_volume(signed=False)

        bm.free()

        # Clean up temporary objects
        bpy.data.objects.remove(prosthetic_temp, do_unlink=True)
        bpy.data.objects.remove(handscan_temp, do_unlink=True)

        # Restore original selection and active object
        for obj in original_selection:
            if obj and obj.name in bpy.data.objects:
                obj.select_set(True)
        if original_active and original_active.name in bpy.data.objects:
            bpy.context.view_layer.objects.active = original_active

        return volume

    except Exception as e:
        print(f"Error calculating volumetric congruency: {e}")
        import traceback
        traceback.print_exc()

        # Clean up any remaining temp objects
        for obj_name in ["TempProsthetic_BoolOp", "TempHandScan_BoolOp"]:
            if obj_name in bpy.data.objects:
                bpy.data.objects.remove(bpy.data.objects[obj_name], do_unlink=True)

        # Restore original selection and active object
        for obj in original_selection:
            if obj and obj.name in bpy.data.objects:
                obj.select_set(True)
        if original_active and original_active.name in bpy.data.objects:
            bpy.context.view_layer.objects.active = original_active

        return 0.0


def calculate_shrinkwrap_displacement(prosthetic_obj):
    """
    Calculate the actual displacement caused by the shrinkwrap modifier.
    This directly measures how much material was added at each vertex.

    Returns:
    - displacement_dict: Dictionary mapping vertex_index -> displacement distance (in BU/meters)

    The displacement represents the actual material added by shrinkwrap:
    - Large displacement = lots of material added = poor original model fit
    - Small displacement = little material added = good original model fit
    """
    # Get unit scale factor from scene settings
    unit_scale = bpy.context.scene.fit_unit_scale_factor if hasattr(bpy.context.scene, 'fit_unit_scale_factor') else 1000.0

    # Get socket vertices in ORIGINAL positions (WITHOUT modifiers)
    original_vertices = get_socket_vertices(prosthetic_obj, evaluate_modifiers=False)

    # Get socket vertices in DEFORMED positions (WITH modifiers)
    deformed_vertices = get_socket_vertices(prosthetic_obj, evaluate_modifiers=True)

    # Create dictionaries for easy lookup
    original_dict = {v_idx: pos for v_idx, pos in original_vertices}
    deformed_dict = {v_idx: pos for v_idx, pos in deformed_vertices}

    # Calculate displacement for each vertex
    displacement_dict = {}
    displacements = []

    for v_idx in original_dict.keys():
        if v_idx in deformed_dict:
            original_pos = original_dict[v_idx]
            deformed_pos = deformed_dict[v_idx]
            displacement = (deformed_pos - original_pos).length
            displacement_dict[v_idx] = displacement
            displacements.append(displacement)

    # Debug output with detailed vertex examples
    if displacements:
        print(f"\n=== SHRINKWRAP DISPLACEMENT ANALYSIS (Material Added) ===")
        print(f"Unit scale: {unit_scale} (1 BU = {1000/unit_scale:.6f}m = {1000000/unit_scale:.3f}mm)")
        print(f"Socket vertices analyzed: {len(displacements)}")

        # Apply unit scale for proper mm conversion
        min_mm = (min(displacements) * 1000) / unit_scale
        max_mm = (max(displacements) * 1000) / unit_scale
        mean_mm = (sum(displacements) / len(displacements) * 1000) / unit_scale
        range_mm = (max(displacements) - min(displacements)) * 1000 / unit_scale

        print(f"\n  Min displacement: {min_mm:.3f}mm (least material added)")
        print(f"  Max displacement: {max_mm:.3f}mm (most material added)")
        print(f"  Mean displacement: {mean_mm:.3f}mm (avg material added)")
        print(f"  Displacement range: {range_mm:.3f}mm")

        # Show some example vertices with their actual displacement values
        print(f"\n  Sample vertex displacements (first 10 vertices):")
        for v_idx, disp in list(displacement_dict.items())[:10]:
            disp_mm = (disp * 1000) / unit_scale
            print(f"    Vertex {v_idx}: {disp_mm:.3f}mm")

        print(f"\nHeat Map Interpretation:")
        print(f"  Blue areas = Small displacement (socket already close to hand, good model)")
        print(f"  Red areas = Large displacement (socket far from hand, poor model)")
        print(f"  → Shows actual material added by shrinkwrap")

    return displacement_dict


def calculate_original_socket_distances(handscan_obj, prosthetic_obj):
    """
    Calculate the distance from ORIGINAL (undeformed) socket vertices to the HandScan surface.
    This shows where material will be added by the shrinkwrap - the "gap" that needs filling.

    Returns:
    - distances_dict: Dictionary mapping vertex_index -> distance from original socket to hand scan (in BU/meters)

    The distance represents the original gap between socket and hand (before shrinkwrap):
    - Large distance = big gap, lots of material will be added = poor original model fit
    - Small distance = small gap, little material will be added = good original model fit
    """
    # Get socket vertices in ORIGINAL positions (WITHOUT modifiers evaluated)
    socket_vertices = get_socket_vertices(prosthetic_obj, evaluate_modifiers=False)

    if not socket_vertices:
        raise ValueError("No InnerSocket vertices found. Ensure InnerSocket material is assigned.")

    # Build BVH tree for HandScan
    handscan_bvh = build_bvh_tree(handscan_obj)

    # Calculate distances from ORIGINAL socket positions to hand scan
    distances = []
    distances_dict = {}
    penetrating_count = 0  # Count vertices inside the hand scan

    for v_idx, world_pos in socket_vertices:
        # Find nearest point on HandScan mesh
        location, normal, face_index, distance = handscan_bvh.find_nearest(world_pos)

        if location is None:
            # Fallback: use distance to nearest vertex
            min_dist = float('inf')
            for vert in handscan_obj.data.vertices:
                vert_world = handscan_obj.matrix_world @ vert.co
                dist = (world_pos - vert_world).length
                if dist < min_dist:
                    min_dist = dist
            distance = min_dist
        else:
            # Check if socket vertex is INSIDE or OUTSIDE the hand scan
            # Vector from nearest point on hand scan to socket vertex
            to_socket = world_pos - location

            # Dot product with surface normal tells us which side we're on
            # Normal points outward from hand surface
            # If dot > 0: socket is outside hand (gap exists - material will be added)
            # If dot < 0: socket is inside hand (penetrating - already too close)
            dot = to_socket.dot(normal)

            if dot < 0:
                # Socket vertex is INSIDE the hand scan (penetrating)
                # This means original socket was too close or overlapping
                # Shrinkwrap moved INWARD (removed material) - very good fit
                # Treat as zero gap (will show as blue - excellent fit)
                distance = 0.0
                penetrating_count += 1
            # else: distance is already the gap we need to fill (socket outside hand)

        distances.append(distance)
        distances_dict[v_idx] = distance

    # Debug output
    if distances:
        outside_count = len(distances) - penetrating_count
        penetrating_pct = (penetrating_count / len(distances) * 100.0) if len(distances) > 0 else 0

        print(f"\n=== ORIGINAL SOCKET GAP ANALYSIS (Before Shrinkwrap) ===")
        print(f"Socket vertices analyzed: {len(distances)}")
        print(f"  Vertices OUTSIDE hand: {outside_count} ({100-penetrating_pct:.1f}%) - gap exists")
        print(f"  Vertices INSIDE hand: {penetrating_count} ({penetrating_pct:.1f}%) - penetrating (very close fit)")
        print(f"\n  Min gap: {min(distances)*1000:.3f}mm (tightest area)")
        print(f"  Max gap: {max(distances)*1000:.3f}mm (loosest area)")
        print(f"  Mean gap: {(sum(distances)/len(distances))*1000:.3f}mm (avg material to add)")
        print(f"  Gap range: {(max(distances)-min(distances))*1000:.3f}mm")
        print(f"\nHeat Map Interpretation:")
        print(f"  Blue areas = Small/zero gap (socket close to or inside hand, good model)")
        print(f"  Red areas = Large gap (socket far from hand, poor model)")
        print(f"  → Shows where shrinkwrap will add material")
        print(f"  → Penetrating vertices (inside hand) show as blue (excellent fit)")

    return distances_dict


def calculate_fit_metrics(handscan_obj, prosthetic_obj, evaluate_modifiers=True):
    """
    Main function to calculate RMSE and create heat map visualization.

    RMSE: Measures final fit quality (distance from deformed socket to hand scan)
    Heat Map: Shows ORIGINAL gap (distance before shrinkwrap - material that will be added)
              Uses absolute mm thresholds for clinical interpretation.

    The heat map shows where material will be added by shrinkwrap.
    This evaluates the quality of the original prosthetic MODEL design.

    Color Logic:
    - Blue (0-2mm): Excellent fit, minimal material added
    - Green (2-5mm): Moderate fit, acceptable material added  
    - Yellow/Orange (5-8mm): Poor fit, significant material added
    - Red (>8mm): Very poor fit, extreme gap

    If evaluate_modifiers is True, evaluates modifiers for accurate RMSE measurement.
    Returns RMSE value in meters (convert to mm for display).
    """
    # Calculate RMSE (final fit quality - deformed socket to hand distance)
    rmse, distances_dict = calculate_rmse_and_distances(handscan_obj, prosthetic_obj, evaluate_modifiers=evaluate_modifiers)

    # Calculate ORIGINAL socket gap (before shrinkwrap) for heat map
    original_gap_dict = calculate_original_socket_distances(handscan_obj, prosthetic_obj)

    # Create heat map based on ORIGINAL GAP (material to be added)
    # Uses absolute thresholds for consistent clinical interpretation
    create_heat_map(prosthetic_obj, original_gap_dict, colormap_name="FitQuality")

    # Setup material for visualization (updates InnerSocket shader nodes)
    setup_heat_map_material(prosthetic_obj)

    return rmse, distances_dict

