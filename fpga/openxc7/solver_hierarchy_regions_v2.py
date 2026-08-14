"""Overlapping XC7A100T hierarchy regions for the shared-terminal solver.

KCL and RHS may use the left and center DSP columns.  The tube, chord, and
terminal-current engines may use the center and right DSP columns.  Sharing
the center column leaves 80 sites of DSP-placement slack for each group while
preventing nonlinear arithmetic from spreading into the far-left column.
"""


KCL_REGION = "solver_kcl_left_center"
NONLINEAR_REGION = "solver_nonlinear_center_right"

ctx.createRectangularRegion(KCL_REGION, 0, 0, 100, 207)
ctx.createRectangularRegion(NONLINEAR_REGION, 61, 0, 147, 207)

kcl_tokens = ("kcl_engine", "rhs_engine")
nonlinear_tokens = (
    "tube_engine",
    "terminal_current_engine",
    "chord_engine",
)
constrained = {KCL_REGION: 0, NONLINEAR_REGION: 0}

for raw_name, _cell in ctx.cells:
    name = raw_name.replace("\\", "")
    if any(token in name for token in kcl_tokens):
        ctx.constrainCellToRegion(raw_name, KCL_REGION)
        constrained[KCL_REGION] += 1
    elif any(token in name for token in nonlinear_tokens):
        ctx.constrainCellToRegion(raw_name, NONLINEAR_REGION)
        constrained[NONLINEAR_REGION] += 1

if constrained[KCL_REGION] == 0 or constrained[NONLINEAR_REGION] == 0:
    raise RuntimeError(
        "solver hierarchy floorplan matched no packed cells: "
        f"{constrained}"
    )

print(
    "V2 solver overlapping regions: "
    f"{constrained[KCL_REGION]} KCL/RHS cells, "
    f"{constrained[NONLINEAR_REGION]} nonlinear cells"
)
