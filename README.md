# Prosthetic Fitter - Blender Addon

A Blender addon that automates the fitting of prosthetic devices to hand scans using landmark-based alignment and socket conforming techniques.

## Features

- **Automatic Landmark Creation**: Creates 6 required landmark empties for hand and prosthetic alignment
- **Wrist-Centric Alignment**: Aligns prosthetic to hand scan based on wrist landmarks and palm orientation
- **Socket Conforming**: Uses Shrinkwrap modifier to conform the prosthetic socket to the hand geometry
- **Dimension-Aware Scaling**: Tracks wrist width and palm length from landmarks to automatically scale the prosthetic to each patient's anatomy (separate XY and Z scaling)
- **Interactive Adjustments**: Real-time socket offset adjustment with millimeter precision
- **Professional UI**: Clean, step-by-step interface in Blender's 3D View sidebar (`HandFit` tab)

## Installation

1. Download or clone this repository
2. In Blender, go to `Edit > Preferences > Add-ons`
3. Click `Install...` and select the `prosthetic_fitter_addon` folder (make sure the folder is zipped/compressed)
4. Enable the addon by checking the box next to "Prosthetic Fitter"

## Usage

### Prerequisites

Before using the addon, ensure your Blender scene contains:

1. **HandScan object**: Your 3D hand scan
2. **Prosthetic object**: The prosthetic device to be fitted
3. **InnerSocket material**: The prosthetic must have a material named "InnerSocket" for the socket area

You access all controls through the `HandFit` panel in the 3D View sidebar (`N` key) under the **HandFit** tab.

### Step-by-Step Process

1. **Setup** (Step 1):
   - Click "Create Landmarks" to automatically create the 6 required landmark empties
   - The landmarks will be positioned at the object origins and parented to their respective objects

2. **Position Landmarks** (Manual):
   - Move the landmark empties to their correct positions:
     - `Hand_Wrist_L` and `Hand_Wrist_R`: Left and right wrist points (define wrist width)
     - `Hand_Palm`: Palm center point (defines palm length / forward direction)
     - `Prosthetic_Wrist_L` and `Prosthetic_Wrist_R`: Corresponding prosthetic wrist points
     - `Prosthetic_Palm`: Corresponding prosthetic palm point

3. **Execution** (Step 2):
   - Click "Fit Prosthetic to Scan" to run the automated fitting process
   - The addon will:
     - Create a vertex group for the socket area
     - Calculate scale and rotation based on landmark positions
     - Apply wrist-centric transformation
     - Add a Shrinkwrap modifier for socket conforming

4. **Adjustments** (Step 3):
   - Use the "Socket Offset (mm)" slider to adjust the gap between prosthetic and hand
   - Default offset is 3mm for liner space
   - Adjustments are applied in real-time

5. **Finalize** (Step 4):
   - Click "Apply and Finalize Fit" to make the transformation permanent
   - This removes the modifier and makes the prosthetic an independent object

## Technical Details

### Alignment Algorithm

The addon uses a wrist-centric alignment approach:

1. **Wrist Center Calculation**: Finds the midpoint between left and right wrist landmarks
2. **Scale Calculation**: 
   - XY scale based on wrist width ratio
   - Z scale based on palm length ratio
3. **Rotation Calculation**: Aligns prosthetic orientation to hand orientation
4. **Transformation Matrix**: Applies scale and rotation around the wrist center, not object origin

In practice, this means the three hand landmarks (`Hand_Wrist_L`, `Hand_Wrist_R`, `Hand_Palm`) act as a compact **dimension tracking system**, encoding wrist width and palm length so that each prosthetic is automatically scaled to the patient's anatomy.

### Socket Conforming

- Uses Blender's Shrinkwrap modifier
- Targets the hand scan object
- Applies only to vertices in the "Socket_VG" vertex group
- Automatically created from faces using the "InnerSocket" material

## Requirements

- Blender 2.80 or later
- Python 3.7+ (included with Blender)

## File Structure

```
prosthetic_fitter_addon/
├── __init__.py              # Addon metadata and registration
├── prosthetic_fitter.py     # Core fitting algorithms
├── ui_panel.py             # User interface and operators
└── README.md               # This file
```

## Troubleshooting

### Common Issues

1. **"Could not find 'HandScan' or 'Prosthetic'"**
   - Ensure objects are named exactly "HandScan" and "Prosthetic"

2. **"Could not find landmark"**
   - Run "Create Landmarks" first
   - Ensure landmarks are positioned correctly

3. **"Missing 'InnerSocket' material"**
   - Add a material named "InnerSocket" to the prosthetic
   - Apply it to the faces that should be part of the socket

4. **Poor fitting results**
   - Check landmark positioning accuracy
   - Ensure landmarks represent the same anatomical points on both objects
   - Verify the prosthetic geometry is suitable for the target hand

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for bugs and feature requests.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

Developed as part of the VT1 (Virtual Technologies) project at ZHAW - Zurich University of Applied Sciences. This work contributes to prosthetic fitting applications in medical and assistive technology contexts.

**Institution**: ZHAW School of Engineering - Center for Artificial Intelligenc (CAI). 
**Program**: Virtual Technologies (VT1)  
**Academic Year**: Fall 2025
