# Overshield projected-shadow regression

The Mac ANGLE renderer could draw two long dark bands through the floor from
Downrush's overshield. Picking up the item removed the bands. The same renderer
also produced an incorrect extended pattern around the stock Blood Gulch
overshield.

This was reproduced with an isolated fixed camera. Turning off
`rasterizer_environment_shadows` removed the bands without removing the item.
The compiled Downrush overshield's equipment, model, collision, shaders and
bitmaps matched the stock Blood Gulch dependency tags byte for byte: 15
non-sound tags matched. The imported map and stock data were not changed.

## Cause and correction

Xbox projected shadows request `D3DTADDRESS_BORDER`. On this Mac, ANGLE reports
no border-clamp extension, and the shared GLES adapter substituted
`GL_CLAMP_TO_EDGE`. An opaque edge texel could therefore stretch outside the
shadow texture instead of sampling the requested border color.

The native adapter now generates a border-sampling shader helper for affected
single-level 2D textures. It honors U/V addressing independently, the requested
RGBA border color, point filtering, and the half-texel border blend for linear
filtering. Linear Xbox texture coordinates are scaled before the border test.
Border color is included in the cached draw-uniform inputs.

The existing hardware-extension path is preserved. This change does not add
fallback support for mipmapped, anisotropic, cube or 3D border samplers; those
require separately validated sampling footprints. No game rules, item tags,
map placement, simulation timing or display settings are changed.

## Verification

`python3 -m unittest tools.test_texture_border -v` compiles the production
shader helper and performs 36,504 offscreen ANGLE/Metal pixel comparisons.
Cases cover independent border axes, nonblack RGBA borders, corners, outside
coordinates, point/linear and mixed min/mag filtering, LOD transitions/bias and
Xbox coordinate scaling. Capability/type gates are also checked. The test
requires the local Mac ANGLE dependencies and Metal access.

Five existing presentation, geometry-cache and visibility-query tests passed,
and the native Mac build succeeded. Fixed-camera Downrush and stock Blood Gulch
runs with the corrected guest removed the extended artifacts while shadows
remained enabled. Both completed without rendering/runtime faults.

Local evidence is in
`build/community-maps/overshield-render-20261002/`: `baseline/` contains the
initial reproduction and shadow-disable isolation, the `downrush-before/`,
`downrush-after/`, `stock-before/` and `stock-after/` folders contain matched
camera captures, and `probe.py` records the isolated reproduction procedure.
The asset comparison is in
`build/community-maps/overshield-audit-20261002/comparison.json`.

These focused checks verify this renderer defect. They do not establish full
Xbox rendering parity or a performance improvement.
