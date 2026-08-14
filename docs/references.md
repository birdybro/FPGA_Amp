# Annotated engineering references

Sources are grouped by the decision they support. Scanned manufacturer material
is treated as primary even when a third-party archive hosts the scan. A web
article describing a historical circuit is provenance for that circuit, not a
general authority on tube physics. Links were checked 2026-08-12.

## Frozen V1 circuit and equalization

- Kevin Kennedy, [“Single Tube Phono Stage”](https://www.kta-hifi.net/projects/pre_page/ots_preamp/ots11.html)
  and [source schematic](https://www.kta-hifi.net/projects/pre_page/ots_preamp/1tbpre.pdf),
  1998. This is the exact historical artifact selected for V1. It fixes B+,
  resistor/capacitor values, topology, and reference load. The project does not
  assume its RIAA accuracy; ngspice measures it.
- RIAA Engineering Bulletin E1,
  [*Dimensional Standards—Disc Records*](https://www.bostonaudiosociety.org/pdf/RIAA%20Bulletins%20E1%20%26%20E4_1978%20LP%20dimensional%20standards.pdf),
  1978. Primary source for 3180, 318, and 75 µs replay constants and the
  tabulated response regression vector.
- H. J. Leak / Mullard applications lineage,
  [*Mullard Circuits for Audio Amplifiers*](https://primary-audio.com/articles/Mullard-Circuits-for-Audio-Amplifiers.pdf).
  Provides historically credible valve-amplifier/RIAA context, power-supply,
  phase-inverter, EL84, and EL34 circuits. It is future integrated-amplifier
  research, not the source of V1 values.

## Tubes and characteristic data

- General Electric, [12AX7/ECC83 ET-T509B data](https://frank.pocnet.net/sheets/093/1/12AX7.pdf).
  Manufacturer characteristic families and nominal amplification factor. The
  checked CSV is an approximate digitization of page 3 with ±0.05 mA reading
  uncertainty.
- RCA, [*Receiving Tube Manual RC-30*](https://www.worldradiohistory.com/BOOKSHELF-ARH/Technology/RCA-Books/RCA-Receiving-Tube-Manual-1975-RC-30.pdf),
  1975. Primary ratings and curves for the 12AX7, 12AU7, 12AT7, 6V6, 6L6 and
  related American types. This is the first reference for later triode and
  beam-power libraries.
- Mullard,
  [*Valves for Audio Equipment* archive entry](https://frank.pocnet.net/other/Mullard/).
  Manufacturer material covering ECC83, EF86, EL84, and EL34. It will constrain
  future pentode screen-grid and operating-region work.
- Philips ECC83 sheets are indexed in the
  [Philips/Mullard data archive](https://frank.pocnet.net/sheetsE.html).
  These provide an independent European-manufacturer cross-check for ECC81,
  ECC82, ECC83, and later EL-series models. Exact sheets will be frozen with
  each new model asset rather than treating equivalent type names as identical.

KT66/KT88 and production-tube variation remain research debt. No parameter set
for those types is claimed from modern reissue marketing data.

## Analytical and digital tube models

- Norman Koren, [“Improved Vacuum-Tube Models for SPICE”](https://www.i-t.com/blog/updating-norman-korens-tube-amplifier-design/improved-vacuum-tube-models-for-spice/).
  Primary author exposition of the triode equation, 12AX7 parameter set,
  capacitances, and rough positive-grid extension used by both ngspice and
  Python. Koren explicitly limits confidence in the grid-current estimate.
- Kurt James Werner, virtual-analog literature should not be conflated with a
  tube transfer curve alone. The implementation instead follows coupled nodal
  equations and keeps solver residuals observable.
- T. Dempwolf and U. Zölzer,
  [“A physically-motivated triode model for circuit simulations”](https://dafx.de/paper-archive/2009/papers/paper_29.pdf),
  DAFx-09. Academic alternative to Koren with explicit parameter fitting and a
  useful path for future model-error comparisons.
- J. Pakarinen and D. T. Yeh,
  [“A Review of Digital Techniques for Modeling Vacuum-Tube Guitar Amplifiers”](https://www.effectrode.com/wp-content/uploads/2018/08/a_review_of_digital_techniques_for_modeling_guitar_amplifiers.pdf),
  *Computer Music Journal* 33(2), 2009. Survey supporting the separation of
  static nonlinear, circuit-based, state-space, and wave-digital approaches;
  also identifies transformers, feedback, and power supplies as coupled system
  behavior rather than optional coloration.

## Circuit formulation and nonlinear solution

- C.-W. Ho, A. Ruehli, and P. Brennan,
  [“The Modified Nodal Approach to Network Analysis”](https://research.ibm.com/publications/the-modified-nodal-approach-to-network-analysis),
  *IEEE Transactions on Circuits and Systems*, 1975. Basis for the coupled KCL
  formulation and the future generalization to voltage-source/inductor stamps.
- L. W. Nagel and D. O. Pederson,
  [*SPICE (Simulation Program with Integrated Circuit Emphasis)*](https://www2.eecs.berkeley.edu/Pubs/TechRpts/1973/22871.html),
  UC Berkeley ERL-M382, 1973. Primary provenance for SPICE's nonlinear
  nodal/transient reference role.
- A. Fettweis, “Wave Digital Filters: Theory and Practice,”
  [DOI 10.1109/PROC.1986.13458](https://doi.org/10.1109/PROC.1986.13458),
  *Proceedings of the IEEE*, 1986. Authoritative WDF foundation. WDF remains a
  candidate where passivity and modular one-port structure reduce solver cost;
  V1 currently uses MNA because the historical network maps transparently and
  supplies direct ngspice node comparisons.

| Method | Strength | V1 limitation/decision |
|---|---|---|
| full Newton MNA | direct physical topology, arbitrary coupling | matrix solve and derivatives cost hardware; float reference selected |
| fixed-point iteration | predictable datapath | convergence weaker around strong nonlinear feedback; rejected as sole reference |
| WDF | passivity and efficient linear network updates | multiport/triode adaptation requires careful topology transforms; retain for study |
| 2-D LUT + interpolation | bounded latency and reproducible error | memory-heavy and only represents the device, not circuit state; selected tube primitive |
| piecewise polynomial | potentially lower BRAM | coefficient/range proof and positive-grid accuracy still open |
| black-box waveshaper | cheap | cannot reproduce loading, capacitor state, grid current, or supply interaction; rejected |

## Cartridge, input noise, and converters

- Audio-Technica,
  [AT-VM95 series user manual](https://www.audio-technica.co.jp/pdf/support/AT-VM95E_UM.pdf).
  Primary nominal source: 4.0 mV output, 485 Ω DC resistance, 550 mH inductance,
  47 kΩ termination, and 100–200 pF recommended total capacitance.
- Texas Instruments,
  [AN-346 *High-Performance Audio Applications of the LM833*](https://www.ti.com/lit/an/snoa586d/snoa586d.pdf).
  Supports treating MM inductance, total capacitance, and termination as a
  resonant electrical network and provides phono-noise design context.
- Analog Devices,
  [ADA4625-1 data sheet](https://www.analog.com/media/en/technical-documentation/data-sheets/ada4625-1.pdf);
  Texas Instruments, [OPA1656](https://www.ti.com/lit/ds/symlink/opa1656.pdf) and
  [OPA210](https://www.ti.com/lit/ds/symlink/opa210.pdf) data sheets. These supply
  the voltage/current-noise assumptions in `analyze_frontend.py`. The JFET parts
  win the present MM calculation because cartridge impedance rises with
  frequency; this is a requirements study, not a released schematic.
- AKM, [AK5572EN](https://www.akm.com/global/en/products/audio/audio-adc/ak5572en/);
  TI, [PCM4202](https://www.ti.com/product/PCM4202/part-details/PCM4202DBR) and
  [TAA5242](https://www.ti.com/product/TAA5242). Current official product pages
  supply ADC dynamic-range, interface, and availability candidates.
- TI, [PCM5242](https://www.ti.com/product/PCM5242) and
  [PCM1792A](https://www.ti.com/product/PCM1792A/part-details/PCM1792ADB);
  AKM, [AK4493S announcement/specification](https://www.akm.com/global/en/about-us/news/2022/20220207-ak4493sak4490r/).
  Current DAC candidates spanning integrated voltage output through higher-
  performance external-I/V designs. PCB selection awaits measured clock,
  headroom, and output-stage requirements.

## Audio measurement procedures

- SMPTE, [Recommended Practice document index](https://www.smpte.org/standards/document-index/RP),
  entry for RP 120, *Measurement of Intermodulation Distortion in Motion-Picture
  Audio Systems*, and DOI
  [10.5594/SMPTE.RP120.2005](https://doi.org/10.5594/SMPTE.RP120.2005).
  This establishes the authoritative procedure identity and scope. The complete
  normative text is not redistributed by this repository, so the regression is
  deliberately called an RP-120-style frequency/ratio profile rather than a
  conformance implementation.
- Audio Precision,
  [Portable One Dual Domain Specifications](https://www.audioprecision.com/fileadmin-ap/technical-library/P-1_DD_Specifications.pdf),
  Appendix G. This primary analyzer-manufacturer specification identifies the
  commonly implemented 60 Hz + 7 kHz or 250 Hz + 8 kHz stimulus, 4:1 LF:HF
  ratio, and amplitude-modulation-product measurement associated with
  SMPTE/DIN IMD. It supports the V1 60 Hz/7 kHz profile and sideband analysis;
  it does not substitute for RP 120 calibration or uncertainty requirements.
- IEC, [IEC 60268-3:2018](https://webstore.iec.ch/en/publication/32788),
  *Sound system equipment – Part 3: Amplifiers*. This is the current amplifier
  characteristic/measurement-method reference for future physical line and
  power-amplifier qualification. V1 does not claim IEC conformance.
