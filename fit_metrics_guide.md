# Fit Quality Metrics Guide

This guide explains how to use the **Fit Quality Metrics** feature to evaluate the geometric accuracy of your prosthetic fitting using RMSE (Root Mean Square Error) and a visual heat map.

## Overview

The Fit Quality Metrics system measures how well the inner socket of the prosthetic conforms to the hand scan surface. It provides:

- **RMSE Score**: A single numerical value representing the overall fit accuracy
- **Distance Statistics**: Minimum, maximum, and mean distances between surfaces
- **Volumetric Congruency**: Quantifies the liner volume (air gap between limb and prosthetic)
- **Heat Map Visualization**: Color-coded representation of fit quality across the socket

## Prerequisites

Before using the metrics:

1. Complete the prosthetic fitting workflow (landmarks positioned, "Fit Prosthetic to Scan" executed)
2. Ensure both `HandScan` and `Prosthetic` objects exist in your scene
3. The prosthetic must have the `InnerSocket` material assigned to the socket faces

## How to Use

### Step 1: Access the Panel

1. Open the 3D Viewport sidebar by pressing `N`
2. Navigate to the **HandFit** tab
3. Find the **Fit Quality Metrics** panel

### Step 2: Calculate Metrics

1. Click the **"Calculate Fit Metrics (RMSE & Heat Map)"** button
2. Wait for the calculation to complete (usually a few seconds)
3. The results will appear in the panel

### Step 3: Interpret Results

#### RMSE Score

The RMSE (Root Mean Square Error) is displayed in millimeters:

| RMSE Value | Interpretation |
|------------|----------------|
| < 1.0 mm   | Excellent fit  |
| 1.0 - 2.0 mm | Good fit     |
| 2.0 - 5.0 mm | Acceptable fit |
| > 5.0 mm   | Poor fit - consider adjustments |

#### Distance Statistics

- **Minimum**: The closest point between the socket and hand scan
- **Maximum**: The furthest point (identifies problem areas)
- **Mean**: Average distance across all socket vertices

#### Volumetric Congruency

The **Liner Volume** represents the total "empty space" or air gap between the hand scan and the prosthetic socket. This is the space available for the soft liner material.

**How it's calculated:**
- A Boolean Subtraction operation is performed: `Prosthetic Socket - Hand Scan`
- The resulting volume represents the liner space
- Displayed in cubic centimeters (cm³)

**Interpretation:**

| Volume Change | Meaning |
|---------------|---------|
| Consistent volume across patients | Good standardization with same offset |
| Large spikes in volume | "Dead space" - socket too loose in areas |
| Very low or near-zero volume | Pressure points - socket too tight |

**Usage:**
- Compare volumes across different patient scans using the same socket offset
- Helps ensure consistent liner thickness
- Identifies areas where fit may be too loose or too tight
- Use in conjunction with RMSE and heat map for complete fit assessment

### Step 4: View the Heat Map

1. Click **"View Heat Map"** to switch to Material Preview mode
2. The prosthetic will display colors indicating **"Material Added"** - the gap that the shrinkwrap must fill

#### Color Legend (Absolute Thresholds)

The heat map uses fixed millimeter thresholds for consistent clinical interpretation:

| Color  | Gap Distance | Meaning |
|--------|--------------|---------|
| 🔵 Blue | 0 - 2 mm | **Excellent fit** - Minimal material added. The original model fits the scan perfectly. |
| 🟢 Green | 2 - 5 mm | **Moderate fit** - Acceptable gap, reasonable material added. |
| 🟡 Yellow/Orange | 5 - 8 mm | **Poor fit** - Significant gap, considerable material added by shrinkwrap. |
| 🔴 Red | > 8 mm | **Very poor fit** - Extreme gap. The shrinkwrap must stretch significantly to fill. Consider a different model size. |

#### Clinical Interpretation

- **Blue areas**: The original prosthetic model is very close to the hand scan. Good model selection.
- **Red areas**: Large gap between original model and hand scan. The shrinkwrap modifier adds significant material here.
- **Use case**: Helps determine if you've selected the correct "Master Model" size before finalizing the fit.

## Technical Details

### What is Measured

**Geometric Accuracy (RMSE & Distance Statistics):**
- The system compares each vertex from the `InnerSocket` material faces against the `HandScan` mesh surface
- Distances are calculated using Blender's BVH (Bounding Volume Hierarchy) tree for performance
- If the `SocketFit` modifier is active, the deformed positions are used for measurement

**Volumetric Congruency (Liner Volume):**
- A Boolean Subtraction operation is performed between the prosthetic socket and hand scan
- The resulting mesh volume represents the liner space (air gap)
- Calculation handles modifier evaluation to measure the actual fitted state
- Uses Blender's BMesh volume calculation for accurate results

### Data Storage

- **Vertex Colors**: Stored as a color attribute named `FitQuality` on the prosthetic mesh
- **Material**: A shader named `FitQuality_HeatMap` is created to display the colors
- **Scene Properties**: RMSE and statistics are stored in scene properties for display

### Modifier Handling

The metrics system evaluates modifiers by default:
- If `SocketFit` shrinkwrap is active, measurements reflect the deformed socket position
- This gives you accurate metrics even before applying the modifier

## Tips for Better Results

1. **Run after fitting**: Always calculate metrics after running the fitting process
2. **Check before finalizing**: Use metrics to verify fit quality before applying modifiers
3. **Adjust and re-measure**: If results are poor, adjust socket offset and recalculate
4. **Compare settings**: Try different socket offset values and compare RMSE scores

## Troubleshooting

### "Could not find 'HandScan' object"
- Ensure your hand scan mesh is named exactly `HandScan`

### "Could not find 'Prosthetic' object"
- Ensure your prosthetic mesh is named exactly `Prosthetic`

### "No InnerSocket vertices found"
- Assign the `InnerSocket` material to the socket faces of your prosthetic
- Use the **Master Model Setup** panel to define the inner socket area

### Heat map not visible
1. Ensure viewport is in **Material Preview** or **Rendered** mode
2. Check that the `FitQuality_HeatMap` material is assigned to the prosthetic
3. Try clicking "View Heat Map" again

### RMSE seems too high
- Verify landmark placement is accurate
- Check that socket offset value is appropriate (default: 3mm)
- Ensure the prosthetic model is suitable for the target hand size

## API Reference

For developers, the `fit_metrics.py` module provides:

```python
from . import fit_metrics

# Calculate RMSE and distances
rmse, distances_dict = fit_metrics.calculate_rmse_and_distances(handscan_obj, prosthetic_obj)

# Calculate volumetric congruency (liner volume)
liner_volume_m3 = fit_metrics.calculate_volumetric_congruency(handscan_obj, prosthetic_obj)
liner_volume_cm3 = liner_volume_m3 * 1000000.0  # Convert to cm³

# Create heat map visualization
fit_metrics.create_heat_map(prosthetic_obj, distances_dict)

# Full calculation with visualization
rmse, distances_dict = fit_metrics.calculate_fit_metrics(handscan_obj, prosthetic_obj)
```

### Key Functions

| Function | Description |
|----------|-------------|
| `get_socket_vertices(obj, evaluate_modifiers)` | Get InnerSocket vertices in world space |
| `build_bvh_tree(obj)` | Build BVH tree for efficient nearest-point queries |
| `calculate_rmse_and_distances(hand, prosthetic)` | Calculate RMSE and per-vertex distances |
| `calculate_volumetric_congruency(hand, prosthetic)` | Calculate liner volume via Boolean subtraction |
| `create_heat_map(obj, distances_dict)` | Apply vertex colors based on distances |
| `setup_heat_map_material(obj)` | Create shader to display vertex colors |
| `calculate_fit_metrics(hand, prosthetic)` | Complete workflow: RMSE + heat map |

