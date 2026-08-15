# Display-connector footprint audit

This audit separates a drawing-derived land pattern from the remaining
physical-validation work. Dimensions below are millimetres and are enforced by
`verify.py`; changing a connector footprint without updating this evidence and
the regression is an error.

## J2 — Molex 54104-4031

Source: Molex product customer drawing `541041000`, revision B, sheets 1–2,
for the 54104 top-contact family. The 40-circuit row in sheet 1 identifies
material number `541044031` (engineering number 54104-4031) with A = 19.50,
B = 20.65, C = 24.30, and D = 25.50. Sheet 2 supplies the recommended PCB
pattern.

| Feature | Implemented dimension | Drawing basis |
|---|---:|---|
| Signal count | 40 | 40-circuit table row |
| Signal pitch | 0.50 | non-accumulative pitch |
| Signal land | 0.30 x 1.20 | recommended PCB pattern |
| First/last signal centre | -9.75 / +9.75 | 0.5 x (N - 1) |
| Fitting-nail land | 2.40 x 2.40 | recommended PCB pattern |
| Fitting-nail centre X | -11.85 / +11.85 | 0.90 inner offset plus 2.40 land |

The footprint courtyard also covers the 6.55 mm open-actuator depth rather
than only the 5.00 mm locked depth. The footprint is top contact, matching the
Newhaven display recommendation.

## J3 — Molex 52271-0679

Source: Molex product customer drawing `SD-52271-036`, document-part 001,
revision F, sheets 1–2. The 6-circuit row identifies order number 52271-0679
with A = 5.00, B = 7.20, and C = 11.00. Sheet 2 supplies the recommended PCB
pattern.

| Feature | Implemented dimension | Drawing basis |
|---|---:|---|
| Signal count | 6 | 6-circuit table row |
| Signal pitch | 1.00 | recommended pattern |
| Signal land | 0.60 x 2.20 | recommended pattern; +0.60 / -1.60 about datum |
| First/last signal centre | -2.50 / +2.50 | 1.0 x (N - 1) |
| Fitting-nail land | 2.10 x 2.20 | recommended pattern |
| Fitting-nail centre X | -5.65 / +5.65 | 2.10/4.20 offsets from end signal |

The footprint is bottom contact, matching the Newhaven capacitive-touch FPC
recommendation. The courtyard covers the 7.15 mm open-actuator depth.

## Validation status

The KiCad footprints now reproduce the published land dimensions and exact
contact styles, and the board regression checks their pad count, pitch, sizes,
and fitting-nail locations. This closes the provisional-library-substitute
error. It does **not** close these fabrication gates:

- print the footprints 1:1 and physically fit production-lot connectors;
- obtain an assembler DFM/stencil review;
- inspect first-article solder joints and FPC insertion/retention; and
- freeze the enclosure and display-cable bend/strain-relief geometry.

Primary online records:

- [Molex 541044031 product record](https://www.molex.com/en-us/products/part-detail/541044031)
- [Molex 54104 drawing PDF](https://www.molex.com/content/dam/molex/molex-dot-com/products/automated/en-us/salesdrawingpdf/541/54104/541044031_sd.pdf)
- [Molex 522710679 product record](https://www.molex.com/en-us/products/part-detail/522710679)
- [Molex 52271 drawing PDF](https://www.molex.com/content/dam/molex/molex-dot-com/products/automated/en-us/salesdrawingpdf/522/52271/522710679_sd.pdf)
- [Newhaven NHD-5.0-800480AF-ASXP-CTP data sheet](https://newhavendisplay.com/content/specs/NHD-5.0-800480AF-ASXP-CTP.pdf)
