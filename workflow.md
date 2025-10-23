Prosthetic Fitting: Complete Workflow
This document outlines the complete process for using the HandFit add-on, from initial model preparation to final export.

## Part 1: One-Time Master File Setup
Do these steps only once for each prosthetic model you have. This creates a "master template" file that has all the repetitive setup (materials and landmarks) pre-completed.

1. Import and Clean the Prosthetic
Open a new, blank Blender file (File > New > General).

Import your base prosthetic STL (File > Import > Stl).

In the Outliner (top-right), rename the object to Prosthetic.

Critical Step: Select the model and apply all transforms by pressing Ctrl + A (or Object > Apply > All Transforms). This prevents scale and rotation problems.

2. Set Up Materials
This is the most important setup step for automation.

Go to the Material Properties tab (red sphere icon).

Create your main material. Rename it to OuterShell.

Click the + button to add a second material slot.

Click "New" and rename this new material to exactly InnerSocket.

Go into Edit Mode (Tab).

Assign OuterShell to the entire model (select all faces, click OuterShell, click "Assign").

Now, select only the inner faces of the socket.

With the inner faces selected, click on OuterShell and then click the "Remove" button.

Click on InnerSocket and then click the "Assign" button.

Verify: Deselect all. Click "Select" on InnerSocket (only inner faces light up). Click "Select" on OuterShell (only outer faces light up).

3. Set Prosthetic Landmarks
Go to your "HandFit" panel (press N in the 3D View).

Click "Create Landmarks". This will fail, but it will create the Prosthetic_ landmarks since the HandScan object doesn't exist yet.

Position the three Prosthetic_ landmarks (...Wrist_L, ...Wrist_R, ...Palm) at their correct default locations on the prosthetic model.

Make sure they are parented to the Prosthetic object.

4. Save the Master File
Save this file as Master_Prosthetic_Template.blend. Your preparation is finished.

## Part 2: Per-Patient Fitting Workflow
This is the fast, day-to-day workflow you will use for every new patient.

Step 1: Open Template and Import Scan
Open your Master_Prosthetic_Template.blend file.

Import the patient's hand scan STL (File > Import > Stl).

In the Outliner, rename the newly imported scan to exactly HandScan.

Step 2: Place Hand Landmarks
Go to the "HandFit" panel.

Click the "Create Landmarks" button. The script will see that the Prosthetic_ landmarks already exist and will only create the three Hand_ landmarks.

Manually drag the three Hand_ landmarks to their correct anatomical locations on the HandScan model:

Hand_Wrist_L and Hand_Wrist_R define the width of the wrist.

Hand_Palm defines the "forward" direction, placed at the base of the residual palm.

Step 3: Execute the Fit
In the "HandFit" panel, click the "Fit Prosthetic to Scan" button.

The prosthetic model will instantly snap to the hand, scale to size, and the inner socket will deform to the hand scan.

Step 4: Fine-Tune the Fit
The "Adjustments" section will now be visible in your panel.

Use the "Socket Offset (mm)" slider to interactively adjust the gap for padding and comfort. A value of 2-3mm is a common starting point.

Note: The script automatically creates the Socket_VG vertex group from your "InnerSocket" material. You no longer need to do this manually.

Step 5: Finalize the Model
Once you are happy with the fit, you must make the changes permanent.

In the "HandFit" panel, click the "Apply and Finalize Fit" button.

This "bakes in" the Shrinkwrap deformation. The modifier is removed, and the prosthetic is now a single, finished mesh ready for export.