import bpy
from .prosthetic_fitter import run_fitting_process

# --- OPERATORS ---

class PROSTHETIC_OT_CreateLandmarks(bpy.types.Operator):
    """Creates the set of 6 required landmark empties"""
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
    """The main operator that runs the entire fitting script"""
    bl_idname = "prosthetic.fit_object"
    bl_label = "Fit Prosthetic to Scan"

    def execute(self, context):
        run_fitting_process()
        # Set the initial value of our custom mm slider
        context.scene.socket_offset_mm = 3.0
        return {'FINISHED'}

class PROSTHETIC_OT_ApplyFit(bpy.types.Operator):
    """Applies the SocketFit modifier to make the change permanent"""
    bl_idname = "prosthetic.apply_fit"
    bl_label = "Apply and Finalize Fit"

    def execute(self, context):
        prosthetic_obj = bpy.data.objects.get("Prosthetic")
        if prosthetic_obj and "SocketFit" in prosthetic_obj.modifiers:
            # Ensure the object is active for the operator
            bpy.context.view_layer.objects.active = prosthetic_obj
            bpy.ops.object.modifier_apply(modifier="SocketFit")
            self.report({'INFO'}, "Fit has been applied. Prosthetic is now an independent object.")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Could not find 'Prosthetic' object or 'SocketFit' modifier.")
            return {'CANCELLED'}

# --- THE UI PANEL CLASS ---

class PROSTHETIC_PT_FittingPanel(bpy.types.Panel):
    """Creates a Panel in the 3D View's Sidebar"""
    bl_label = "HandFit"
    bl_idname = "PROSTHETIC_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'HandFit'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # Step 1: Setup
        box = layout.box()
        box.label(text="Step 1: Setup", icon='TOOL_SETTINGS')
        box.operator("prosthetic.create_landmarks")

        # Step 2: Execution
        box = layout.box()
        box.label(text="Step 2: Execution", icon='PLAY')
        box.operator("prosthetic.fit_object")

        # Conditional section that appears after the fit is run
        prosthetic_obj = bpy.data.objects.get("Prosthetic")
        if prosthetic_obj and "SocketFit" in prosthetic_obj.modifiers:
            
            # Get a reference to the modifier
            modifier = prosthetic_obj.modifiers["SocketFit"]

            # Step 3: Adjustments
            box = layout.box()
            box.label(text="Step 3: Adjustments", icon='MODIFIER')
            
            # Checkbox to toggle the modifier on/off
            box.prop(modifier, "show_viewport", text="Toggle Deformation")
            
            # Slider for the offset
            box.prop(scene, "socket_offset_mm", text="Socket Offset (mm)")

            # Step 4: Finalize
            box = layout.box()
            box.label(text="Step 4: Finalize", icon='CHECKMARK')
            box.operator("prosthetic.apply_fit")

# --- CUSTOM PROPERTY & REGISTRATION ---

def update_offset(self, context):
    """This function is triggered whenever the user changes the "socket_offset_mm" slider"""
    prosthetic_obj = bpy.data.objects.get("Prosthetic")
    if prosthetic_obj and "SocketFit" in prosthetic_obj.modifiers:
        # Convert the millimeter value from the UI to meters for Blender
        prosthetic_obj.modifiers["SocketFit"].offset = context.scene.socket_offset_mm / 1000.0

# A list of all our classes to register
classes = (
    PROSTHETIC_OT_CreateLandmarks,
    PROSTHETIC_OT_FitObject,
    PROSTHETIC_OT_ApplyFit, 
    PROSTHETIC_PT_FittingPanel,
)

def register():
    """This function is required by __init__.py to register the add-on"""
    for cls in classes:
        bpy.utils.register_class(cls)
    # Define our custom property and link it to the update function
    bpy.types.Scene.socket_offset_mm = bpy.props.FloatProperty(
        name="Socket Offset",
        description="Gap for liner in millimeters",
        default=3.0,
        min=0.0,
        max=100.0,
        unit='LENGTH',
        update=update_offset
    )

def unregister():
    """This function is required by __init__.py to unregister the add-on"""
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    # Delete our custom property when the add-on is disabled
    del bpy.types.Scene.socket_offset_mm