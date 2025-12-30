import bpy
import bmesh
from mathutils import Vector
from . import prosthetic_fitter
from . import fit_metrics

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


class PROSTHETIC_OT_CalculateFitMetrics(bpy.types.Operator):
    """
    Calculates RMSE (final fit quality) and creates original gap heat map.
    RMSE: Measures final fit quality (deformed socket to hand distance)
    Heat Map: Shows original gap (before shrinkwrap - evaluates prosthetic model quality)
    """
    bl_idname = "prosthetic.calculate_fit_metrics"
    bl_label = "Calculate Fit Metrics (RMSE & Gap Map)"
    bl_description = "Calculate RMSE and visualize original socket gap (before shrinkwrap)"

    def execute(self, context):
        try:
            handscan_obj = bpy.data.objects.get("HandScan")
            prosthetic_obj = bpy.data.objects.get("Prosthetic")
            
            if not handscan_obj:
                self.report({'ERROR'}, "Could not find 'HandScan' object.")
                return {'CANCELLED'}
            
            if not prosthetic_obj:
                self.report({'ERROR'}, "Could not find 'Prosthetic' object.")
                return {'CANCELLED'}
            
            # Check if SocketFit modifier exists and warn if not visible
            if "SocketFit" in prosthetic_obj.modifiers:
                modifier = prosthetic_obj.modifiers["SocketFit"]
                if not modifier.show_viewport:
                    self.report({'WARNING'}, "SocketFit modifier is disabled! Enable 'Toggle Deformation' for accurate measurements.")
                    return {'CANCELLED'}
                self.report({'INFO'}, "Metrics calculated with SocketFit deformation. Offset: {:.1f}mm".format(modifier.offset * 1000))
            
            # Calculate metrics
            rmse, distances_dict = fit_metrics.calculate_rmse_and_distances(handscan_obj, prosthetic_obj)

            # Create heat map (uses shrinkwrap displacement - actual material added)
            displacement_dict = fit_metrics.calculate_shrinkwrap_displacement(prosthetic_obj)
            fit_metrics.create_heat_map(
                prosthetic_obj,
                displacement_dict,
                threshold_blue=context.scene.heatmap_threshold_blue,
                threshold_green=context.scene.heatmap_threshold_green,
                threshold_yellow=context.scene.heatmap_threshold_yellow
            )
            fit_metrics.setup_heat_map_material(prosthetic_obj)

            # Calculate volumetric congruency (liner volume)
            liner_volume_m3 = fit_metrics.calculate_volumetric_congruency(handscan_obj, prosthetic_obj)
            liner_volume_cm3 = liner_volume_m3 * 1000000.0  # Convert m³ to cm³

            # Apply unit scale calibration if set
            unit_scale = context.scene.fit_unit_scale_factor

            # Store RMSE in scene properties for display
            context.scene.fit_rmse_mm = (rmse * 1000.0) / unit_scale  # Convert to mm with scale
            context.scene.fit_liner_volume_cm3 = liner_volume_cm3 / (unit_scale ** 3)
            context.scene.fit_metrics_calculated = True

            # Get statistics
            distances_list = list(distances_dict.values())
            min_dist = (min(distances_list) * 1000.0) / unit_scale  # mm
            max_dist = (max(distances_list) * 1000.0) / unit_scale  # mm
            mean_dist = (sum(distances_list) / len(distances_list) * 1000.0) / unit_scale  # mm

            context.scene.fit_min_distance_mm = min_dist
            context.scene.fit_max_distance_mm = max_dist
            context.scene.fit_mean_distance_mm = mean_dist

            scale_note = f" (scale: {unit_scale:.3f})" if unit_scale != 1.0 else ""
            self.report(
                {'INFO'},
                f"RMSE: {context.scene.fit_rmse_mm:.3f}mm | Volume: {context.scene.fit_liner_volume_cm3:.2f}cm³ | Range: {min_dist:.3f}-{max_dist:.3f}mm{scale_note}"
            )
            
            # Switch to Material Preview or Solid mode with vertex colors
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    for space in area.spaces:
                        if space.type == 'VIEW_3D':
                            space.shading.type = 'MATERIAL'
                            break
            
            return {'FINISHED'}
            
        except ValueError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"Error calculating metrics: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}


class PROSTHETIC_OT_ViewHeatMap(bpy.types.Operator):
    """
    Switches viewport shading to show the heat map.
    """
    bl_idname = "prosthetic.view_heat_map"
    bl_label = "View Heat Map"
    bl_description = "Switch to material preview to view the fit quality heat map"

    def execute(self, context):
        prosthetic_obj = bpy.data.objects.get("Prosthetic")
        if not prosthetic_obj:
            self.report({'ERROR'}, "Could not find 'Prosthetic' object.")
            return {'CANCELLED'}

        # Switch to Material Preview mode
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        space.shading.type = 'MATERIAL'
                        # Enable color attribute display if available
                        if hasattr(space.shading, 'color_type'):
                            space.shading.color_type = 'MATERIAL'
                        break

        self.report({'INFO'}, "Switched to Material Preview. Ensure 'FitQuality_HeatMap' material is assigned.")
        return {'FINISHED'}


class PROSTHETIC_OT_RefreshHeatMap(bpy.types.Operator):
    """
    Refreshes the heat map with current threshold settings without recalculating metrics.
    """
    bl_idname = "prosthetic.refresh_heat_map"
    bl_label = "Refresh Heat Map"
    bl_description = "Update heat map colors using current threshold settings"

    def execute(self, context):
        try:
            handscan_obj = bpy.data.objects.get("HandScan")
            prosthetic_obj = bpy.data.objects.get("Prosthetic")

            if not handscan_obj:
                self.report({'ERROR'}, "Could not find 'HandScan' object.")
                return {'CANCELLED'}

            if not prosthetic_obj:
                self.report({'ERROR'}, "Could not find 'Prosthetic' object.")
                return {'CANCELLED'}

            # Get thresholds from scene properties
            threshold_blue = context.scene.heatmap_threshold_blue
            threshold_green = context.scene.heatmap_threshold_green
            threshold_yellow = context.scene.heatmap_threshold_yellow

            # Recalculate shrinkwrap displacement (actual material added)
            displacement_dict = fit_metrics.calculate_shrinkwrap_displacement(prosthetic_obj)

            # Create heat map with custom thresholds
            fit_metrics.create_heat_map(
                prosthetic_obj,
                displacement_dict,
                threshold_blue=threshold_blue,
                threshold_green=threshold_green,
                threshold_yellow=threshold_yellow
            )
            fit_metrics.setup_heat_map_material(prosthetic_obj)

            self.report({'INFO'}, f"Heat map updated with thresholds: Blue≤{threshold_blue}mm, Green≤{threshold_green}mm, Yellow≤{threshold_yellow}mm")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Error refreshing heat map: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}


class PROSTHETIC_OT_CompareBeforeAfterFit(bpy.types.Operator):
    """
    Compares fit quality before and after SocketFit transformation.
    Shows the improvement gained from the shrinkwrap fitting process.
    """
    bl_idname = "prosthetic.compare_before_after_fit"
    bl_label = "Compare Before/After Fit"
    bl_description = "Measure fit quality before (undeformed) and after (with SocketFit) to show improvement"

    def execute(self, context):
        try:
            handscan_obj = bpy.data.objects.get("HandScan")
            prosthetic_obj = bpy.data.objects.get("Prosthetic")

            if not handscan_obj:
                self.report({'ERROR'}, "Could not find 'HandScan' object.")
                return {'CANCELLED'}

            if not prosthetic_obj:
                self.report({'ERROR'}, "Could not find 'Prosthetic' object.")
                return {'CANCELLED'}

            if "SocketFit" not in prosthetic_obj.modifiers:
                self.report({'ERROR'}, "SocketFit modifier not found! Run 'Fit Prosthetic to Scan' first.")
                return {'CANCELLED'}

            modifier = prosthetic_obj.modifiers["SocketFit"]
            original_visibility = modifier.show_viewport

            unit_scale = context.scene.fit_unit_scale_factor

            print("\n" + "="*60)
            print("BEFORE/AFTER FIT COMPARISON")
            print("="*60)

            # BEFORE: Disable SocketFit and measure
            modifier.show_viewport = False
            print("\n--- BEFORE FIT (SocketFit disabled) ---")
            rmse_before, distances_before = fit_metrics.calculate_rmse_and_distances(handscan_obj, prosthetic_obj)

            # AFTER: Enable SocketFit and measure
            modifier.show_viewport = True
            print("\n--- AFTER FIT (SocketFit enabled) ---")
            rmse_after, distances_after = fit_metrics.calculate_rmse_and_distances(handscan_obj, prosthetic_obj)

            # Restore original state
            modifier.show_viewport = original_visibility

            # Calculate improvement
            rmse_before_mm = (rmse_before * 1000.0) / unit_scale
            rmse_after_mm = (rmse_after * 1000.0) / unit_scale
            improvement_mm = rmse_before_mm - rmse_after_mm
            improvement_pct = (improvement_mm / rmse_before_mm * 100.0) if rmse_before_mm > 0 else 0

            # Get statistics
            distances_before_list = list(distances_before.values())
            distances_after_list = list(distances_after.values())

            mean_before = (sum(distances_before_list) / len(distances_before_list) * 1000.0) / unit_scale
            mean_after = (sum(distances_after_list) / len(distances_after_list) * 1000.0) / unit_scale

            # Store in scene properties
            context.scene.fit_rmse_before_mm = rmse_before_mm
            context.scene.fit_rmse_after_mm = rmse_after_mm
            context.scene.fit_improvement_mm = improvement_mm
            context.scene.fit_improvement_pct = improvement_pct
            context.scene.fit_comparison_done = True

            # Report results
            print("\n" + "="*60)
            print("RESULTS SUMMARY")
            print("="*60)
            print(f"BEFORE Fitting:")
            print(f"  RMSE: {rmse_before_mm:.3f}mm")
            print(f"  Mean Distance: {mean_before:.3f}mm")
            print(f"\nAFTER Fitting:")
            print(f"  RMSE: {rmse_after_mm:.3f}mm")
            print(f"  Mean Distance: {mean_after:.3f}mm")
            print(f"\nIMPROVEMENT:")
            print(f"  RMSE Reduction: {improvement_mm:.3f}mm ({improvement_pct:.1f}%)")
            print("="*60 + "\n")

            self.report(
                {'INFO'},
                f"Improvement: {improvement_mm:.3f}mm ({improvement_pct:.1f}%) | Before: {rmse_before_mm:.3f}mm → After: {rmse_after_mm:.3f}mm"
            )

            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Error comparing fits: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}

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
        box.label(text="Step 2: Fitting Settings", icon='SETTINGS')
        box.prop(scene, "wrist_offset_mm", text="Wrist Clearance (mm)")
        box.label(text="(Gap on each side of wrist)", icon='INFO')

        box = layout.box()
        box.label(text="Step 3: Execution", icon='PLAY')
        box.operator(PROSTHETIC_OT_FitObject.bl_idname)

        prosthetic_obj = bpy.data.objects.get("Prosthetic")
        if prosthetic_obj and "SocketFit" in prosthetic_obj.modifiers:
            modifier = prosthetic_obj.modifiers["SocketFit"]

            sub_box = layout.box()
            sub_box.label(text="Step 4: Adjustments", icon='MODIFIER')
            sub_box.prop(modifier, "show_viewport", text="Toggle Deformation")
            sub_box.prop(scene, "socket_offset_mm", text="Socket Offset (mm)")

            sub_box = layout.box()
            sub_box.label(text="Step 5: Finalize", icon='CHECKMARK')
            sub_box.operator(PROSTHETIC_OT_ApplyFit.bl_idname, text="Apply Fit On Prosthetic")
            sub_box.operator(PROSTHETIC_OT_BakeFitToNewObject.bl_idname, text="Create Fitted Copy")


# 4. FIT METRICS PANEL
class PROSTHETIC_PT_FitMetricsPanel(bpy.types.Panel):
    bl_label = "Fit Quality Metrics"
    bl_idname = "PROSTHETIC_PT_fit_metrics_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'HandFit'

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        box = layout.box()
        box.label(text="Geometric Accuracy Analysis", icon='GRAPH')

        # Unit scale calibration
        settings_box = box.box()
        settings_box.label(text="Measurement Settings:", icon='SETTINGS')
        settings_box.prop(scene, "fit_unit_scale_factor", text="Unit Scale Factor")
        settings_box.label(text="(Default 1000 = 1 BU = 1mm for CAD)", icon='INFO')
        settings_box.label(text="Use 1.0 if 1 BU = 1m in your file", icon='INFO')

        # Heat map color threshold settings
        settings_box.separator()
        settings_box.label(text="Heat Map Color Thresholds (mm):", icon='COLOR')
        settings_box.prop(scene, "heatmap_threshold_blue", text="Blue (Excellent)")
        settings_box.prop(scene, "heatmap_threshold_green", text="Green (Moderate)")
        settings_box.prop(scene, "heatmap_threshold_yellow", text="Yellow (Poor)")
        settings_box.label(text="Red: Above Yellow threshold", icon='INFO')
        settings_box.label(text="Tip: Check console for actual displacement values", icon='INFO')

        # Check if SocketFit modifier is visible
        prosthetic_obj = bpy.data.objects.get("Prosthetic")
        if prosthetic_obj and "SocketFit" in prosthetic_obj.modifiers:
            modifier = prosthetic_obj.modifiers["SocketFit"]
            if not modifier.show_viewport:
                warning_box = box.box()
                warning_box.alert = True
                warning_box.label(text="Enable 'Toggle Deformation' first!", icon='ERROR')

        # Calculate metrics button
        box.separator()
        box.operator(PROSTHETIC_OT_CalculateFitMetrics.bl_idname, icon='MODIFIER_ON')
        
        # Display results if calculated
        if scene.fit_metrics_calculated:
            box.separator()
            metrics_box = box.box()
            metrics_box.label(text="RMSE (Root Mean Square Error):", icon='INFO')
            metrics_box.label(text=f"{scene.fit_rmse_mm:.3f} mm")

            metrics_box.separator()
            metrics_box.label(text="Distance Statistics:", icon='GRAPH')
            metrics_box.label(text=f"Minimum: {scene.fit_min_distance_mm:.3f} mm")
            metrics_box.label(text=f"Maximum: {scene.fit_max_distance_mm:.3f} mm")
            metrics_box.label(text=f"Mean: {scene.fit_mean_distance_mm:.3f} mm")

            metrics_box.separator()
            metrics_box.label(text="Volumetric Congruency:", icon='MESH_CUBE')
            metrics_box.label(text=f"Liner Volume: {scene.fit_liner_volume_cm3:.2f} cm³")

            box.separator()
            box.label(text="Socket Gap Heat Map:", icon='MATERIAL')
            box.operator(PROSTHETIC_OT_ViewHeatMap.bl_idname, icon='SHADING_RENDERED')
            box.operator(PROSTHETIC_OT_RefreshHeatMap.bl_idname, icon='FILE_REFRESH')

            box.separator()
            info_box = box.box()
            info_box.label(text="Heat Map Shows: Original Gap", icon='INFO')
            info_box.label(text="(Distance before shrinkwrap)", icon='ARROW_LEFTRIGHT')
            info_box.separator()
            info_box.label(text="Color Legend:", icon='COLOR')
            info_box.label(text="Blue = Small gap (good model fit)")
            info_box.label(text="Green = Moderate gap")
            info_box.label(text="Yellow = Large gap")
            info_box.label(text="Red = Very large gap (poor model fit)")
        else:
            box.separator()
            box.label(text="Click 'Calculate Fit Metrics' to analyze", icon='INFO')

        # Before/After Comparison
        box.separator()
        comparison_box = box.box()
        comparison_box.label(text="Fit Improvement Analysis:", icon='SORTSIZE')
        comparison_box.operator(PROSTHETIC_OT_CompareBeforeAfterFit.bl_idname, icon='AUTOMERGE_ON')

        if scene.fit_comparison_done:
            comparison_box.separator()
            results_box = comparison_box.box()
            results_box.label(text="Before Fit (Original):", icon='REMOVE')
            results_box.label(text=f"  RMSE: {scene.fit_rmse_before_mm:.3f} mm")

            results_box.separator()
            results_box.label(text="After Fit (With SocketFit):", icon='CHECKMARK')
            results_box.label(text=f"  RMSE: {scene.fit_rmse_after_mm:.3f} mm")

            results_box.separator()
            improvement_label = results_box.box()
            if scene.fit_improvement_mm > 0:
                improvement_label.alert = False
                improvement_label.label(text=f"Improvement: {scene.fit_improvement_mm:.3f} mm", icon='TRIA_UP')
                improvement_label.label(text=f"({scene.fit_improvement_pct:.1f}% better fit)")
            else:
                improvement_label.alert = True
                improvement_label.label(text="No improvement detected!", icon='ERROR')


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
    PROSTHETIC_OT_CalculateFitMetrics,
    PROSTHETIC_OT_ViewHeatMap,
    PROSTHETIC_OT_RefreshHeatMap,
    PROSTHETIC_OT_CompareBeforeAfterFit,
    PROSTHETIC_PT_TrackerPanel,
    PROSTHETIC_PT_MasterSetupPanel,
    PROSTHETIC_PT_WorkflowPanel,
    PROSTHETIC_PT_FitMetricsPanel,
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
    bpy.types.Scene.wrist_offset_mm = bpy.props.FloatProperty(
        name="Wrist Clearance",
        description="Gap on each side of wrist in millimeters (prevents prosthetic from touching hand during fitting)",
        default=3.0, min=0.0, max=50.0, soft_max=10.0, precision=1
    )
    bpy.types.Scene.selection_threshold = bpy.props.FloatProperty(
        name="Selection Threshold",
        description="Angle to use for 'Select Similar by Normal'",
        default=0.1, min=0.0, max=1.0
    )
    bpy.types.Scene.prosthetic_tracker_baseline_percent = bpy.props.FloatProperty(
        name="Baseline %", description="Original prosthetic wrist width as a percentage of target", default=100.0, precision=1, subtype='PERCENTAGE'
    )
    
    # Fit metrics properties
    bpy.types.Scene.fit_rmse_mm = bpy.props.FloatProperty(
        name="RMSE (mm)", description="Root Mean Square Error in millimeters", default=0.0, precision=3
    )
    bpy.types.Scene.fit_min_distance_mm = bpy.props.FloatProperty(
        name="Min Distance (mm)", description="Minimum distance between surfaces", default=0.0, precision=3
    )
    bpy.types.Scene.fit_max_distance_mm = bpy.props.FloatProperty(
        name="Max Distance (mm)", description="Maximum distance between surfaces", default=0.0, precision=3
    )
    bpy.types.Scene.fit_mean_distance_mm = bpy.props.FloatProperty(
        name="Mean Distance (mm)", description="Mean distance between surfaces", default=0.0, precision=3
    )
    bpy.types.Scene.fit_liner_volume_cm3 = bpy.props.FloatProperty(
        name="Liner Volume (cm³)", description="Volume of the liner space between socket and hand scan", default=0.0, precision=2
    )
    bpy.types.Scene.fit_metrics_calculated = bpy.props.BoolProperty(
        name="Metrics Calculated", description="Whether fit metrics have been calculated", default=False
    )
    bpy.types.Scene.fit_unit_scale_factor = bpy.props.FloatProperty(
        name="Unit Scale Factor",
        description="Scale factor to convert Blender Units to real measurements. 1000.0 = 1 BU = 1mm (common for CAD imports). 1.0 = 1 BU = 1m.",
        default=1000.0, min=0.001, max=10000.0, soft_min=100.0, soft_max=2000.0, precision=1
    )
    bpy.types.Scene.fit_heatmap_absolute_mode = bpy.props.BoolProperty(
        name="Absolute Threshold Mode",
        description="If True, heat map uses absolute thresholds based on socket offset. If False, shows relative variation.",
        default=False
    )

    # Heat map color threshold properties (in mm) - open-ended ranges
    bpy.types.Scene.heatmap_threshold_blue = bpy.props.FloatProperty(
        name="Blue Threshold",
        description="Maximum distance (mm) for blue color (excellent fit)",
        default=2.0, min=0.0, soft_max=10.0, precision=1
    )
    bpy.types.Scene.heatmap_threshold_green = bpy.props.FloatProperty(
        name="Green Threshold",
        description="Maximum distance (mm) for green color (moderate fit)",
        default=5.0, min=0.0, soft_max=20.0, precision=1
    )
    bpy.types.Scene.heatmap_threshold_yellow = bpy.props.FloatProperty(
        name="Yellow Threshold",
        description="Maximum distance (mm) for yellow/orange color (poor fit)",
        default=8.0, min=0.0, soft_max=30.0, precision=1
    )

    # Before/After comparison properties
    bpy.types.Scene.fit_comparison_done = bpy.props.BoolProperty(
        name="Comparison Done", description="Whether before/after comparison has been calculated", default=False
    )
    bpy.types.Scene.fit_rmse_before_mm = bpy.props.FloatProperty(
        name="RMSE Before (mm)", description="RMSE before SocketFit transformation", default=0.0, precision=3
    )
    bpy.types.Scene.fit_rmse_after_mm = bpy.props.FloatProperty(
        name="RMSE After (mm)", description="RMSE after SocketFit transformation", default=0.0, precision=3
    )
    bpy.types.Scene.fit_improvement_mm = bpy.props.FloatProperty(
        name="Improvement (mm)", description="RMSE improvement in mm", default=0.0, precision=3
    )
    bpy.types.Scene.fit_improvement_pct = bpy.props.FloatProperty(
        name="Improvement (%)", description="RMSE improvement percentage", default=0.0, precision=1
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
    if hasattr(bpy.types.Scene, 'wrist_offset_mm'):
        del bpy.types.Scene.wrist_offset_mm
    if hasattr(bpy.types.Scene, 'selection_threshold'):
        del bpy.types.Scene.selection_threshold
    if hasattr(bpy.types.Scene, 'prosthetic_tracker_baseline_percent'):
        del bpy.types.Scene.prosthetic_tracker_baseline_percent
    if hasattr(bpy.types.Scene, 'fit_rmse_mm'):
        del bpy.types.Scene.fit_rmse_mm
    if hasattr(bpy.types.Scene, 'fit_min_distance_mm'):
        del bpy.types.Scene.fit_min_distance_mm
    if hasattr(bpy.types.Scene, 'fit_max_distance_mm'):
        del bpy.types.Scene.fit_max_distance_mm
    if hasattr(bpy.types.Scene, 'fit_mean_distance_mm'):
        del bpy.types.Scene.fit_mean_distance_mm
    if hasattr(bpy.types.Scene, 'fit_liner_volume_cm3'):
        del bpy.types.Scene.fit_liner_volume_cm3
    if hasattr(bpy.types.Scene, 'fit_metrics_calculated'):
        del bpy.types.Scene.fit_metrics_calculated
    if hasattr(bpy.types.Scene, 'fit_unit_scale_factor'):
        del bpy.types.Scene.fit_unit_scale_factor
    if hasattr(bpy.types.Scene, 'fit_heatmap_absolute_mode'):
        del bpy.types.Scene.fit_heatmap_absolute_mode
    if hasattr(bpy.types.Scene, 'heatmap_threshold_blue'):
        del bpy.types.Scene.heatmap_threshold_blue
    if hasattr(bpy.types.Scene, 'heatmap_threshold_green'):
        del bpy.types.Scene.heatmap_threshold_green
    if hasattr(bpy.types.Scene, 'heatmap_threshold_yellow'):
        del bpy.types.Scene.heatmap_threshold_yellow
    if hasattr(bpy.types.Scene, 'fit_comparison_done'):
        del bpy.types.Scene.fit_comparison_done
    if hasattr(bpy.types.Scene, 'fit_rmse_before_mm'):
        del bpy.types.Scene.fit_rmse_before_mm
    if hasattr(bpy.types.Scene, 'fit_rmse_after_mm'):
        del bpy.types.Scene.fit_rmse_after_mm
    if hasattr(bpy.types.Scene, 'fit_improvement_mm'):
        del bpy.types.Scene.fit_improvement_mm
    if hasattr(bpy.types.Scene, 'fit_improvement_pct'):
        del bpy.types.Scene.fit_improvement_pct
    bpy.utils.unregister_class(prosthetic_fitter.ProstheticScaleTrackerProps)
   