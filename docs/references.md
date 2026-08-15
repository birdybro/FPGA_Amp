# Annotated engineering references

Sources are grouped by the decision they support. Scanned manufacturer material
is treated as primary even when a third-party archive hosts the scan. A web
article describing a historical circuit is provenance for that circuit, not a
general authority on tube physics. Links were checked 2026-08-15.

## Open FPGA implementation flow

- YosysHQ, [nextpnr](https://github.com/YosysHQ/nextpnr). The upstream README
  identifies the Project-X-Ray-backed Xilinx 7-series backend as experimental.
  The [pinned device-generator source](https://github.com/YosysHQ/nextpnr/blob/4d235150266df2fa5c2c6102c67aa16ff34e6469/himbaechel/uarch/xilinx/CMakeLists.txt)
  explicitly supports both `xc7a100t` and `xc7a200t`, while the backend exposes
  only a `DEFAULT` timing grade. These facts support using the flow for
  reproducible placement/routing evidence while withholding qualified `-1`
  speed-grade signoff claims.
- F4PGA, [Project X-Ray](https://github.com/f4pga/prjxray) and
  [prjxray-db](https://github.com/f4pga/prjxray-db). These are the open 7-series
  bitstream documentation/tooling and device database consumed by nextpnr. The
  checked database contains `artix7/xc7a100tcsg324-1`, the exact provisional
  Arty A7-100T part.
- trabucayre, [openFPGALoader](https://github.com/trabucayre/openFPGALoader)
  and its [official board compatibility
  list](https://trabucayre.github.io/openFPGALoader/compatibility/board.html).
  The upstream command documentation distinguishes volatile SRAM loading from
  `-f` flash writes, and the compatibility table lists the Artix-7 Nexys Video
  as `nexysVideo` with both SRAM and flash support. These sources fix the open
  programmer profile and support offering SRAM-only bring-up before any
  persistent flash operation.
- Digilent,
  [Arty-A7-100 master XDC](https://github.com/Digilent/digilent-xdc/blob/master/Arty-A7-100-Master.xdc).
  Primary board-source provenance for the E3 oscillator, D9 button, and H5 LED
  locations used by the timing-only solver harness. Those three pins do not
  define the eventual converter daughterboard or audio clock circuit.
- AMD, [Artix 7 FPGA product table](https://www.amd.com/en/products/adaptive-socs-and-fpgas/fpga/artix-7.html).
  Primary manufacturer resource counts support the controlled capacity
  comparison: XC7A100T has 240 DSP slices, while XC7A200T has 740. More hard
  blocks do not imply timing closure, so the repository still measures the
  complete placed hierarchy.
- Digilent,
  [Nexys Video master XDC](https://github.com/Digilent/digilent-xdc/blob/master/Nexys-Video-Master.xdc).
  Primary board-source provenance for the R4 oscillator, active-low G4
  `CPU_RESETN` input,
  and T14 LED used by the XC7A200T timing-only harness. This pin subset is not a
  production-board constraint set or an audio-clock implementation.
- AMD, [*7 Series FPGAs Clocking Resources User Guide
  (UG472)*](https://www.amd.com/content/dam/xilinx/support/documents/user_guides/ug472_7Series_Clocking.pdf).
  Primary primitive documentation for `MMCME2_BASE`, the legal MMCM
  multiplier/divider controls, and `CLKOUT0_DIVIDE_F` eighth-step fractional
  output division. It supports the two-stage exact 100 MHz -> 12.288 MHz ->
  49.152 MHz board-clock implementation; the checked open route and FASM are
  separate evidence that the backend encoded those settings.
- Digilent, [*Nexys Video Reference
  Manual*](https://digilent.com/reference/_media/reference/programmable-logic/nexys-video/nexys-video_rm.pdf).
  Primary board documentation for the 100 MHz oscillator and ADAU1761 wiring:
  U6 MCLK, T5 BCLK, U5 shared LRCLK, T4 ADC data, W6 DAC data, and V5/W5 I2C.
  This prevents the board wrapper from inventing separate ADC and DAC LRCLK
  pins and establishes that codec register configuration is mandatory.
- Analog Devices, [*ADAU1761 Data Sheet, Rev.
  F*](https://www.analog.com/media/en/technical-documentation/data-sheets/ADAU1761.pdf).
  Primary codec source for 12.288 MHz operation in the 48 kHz family, shared
  BCLK/LRCLK serial-port constraints, I2S timing, and control-port setup. The
  FPGA is the serial-clock main device for initial bring-up; the implemented
  I2C sequence derives register meanings and clock-role choices from this
  source. Passing digital simulation is not evidence of physical codec setup.
- Digilent, [Nexys Video DMA audio support source at commit
  `6797909`](https://github.com/Digilent/Nexys-Video/blob/679790988e2792748e968f09de65233198a5c3c5/sw/src/Nexys-Video-DMA/src/audio/audio.c),
  2023-07-26. This board-specific primary implementation corroborates the
  seven-bit codec address `0x3b` and the proven analog mixer/line-output route.
  Its PLL and codec-generated BCLK/LRCLK choices are intentionally not copied:
  this project provides exact MCLK/BCLK/LRCLK from FPGA logic and therefore
  programs the ADAU1761 serial port as subordinate.

## Product eARC, front-panel, and motor-control platform

- HDMI Licensing Administrator,
  [*Enhanced Audio Return Channel*](https://www.hdmi.org/spec21sub/enhancedaudioreturnchannel),
  [adopter overview](https://www.hdmi.org/adopter/index), and
  [licensed-product clarification](https://www.hdmi.org/adopter/enforcement).
  The first source establishes the public eARC purpose and high-rate audio
  context. The licensing sources establish that specification access belongs
  to adopters and that a finished product must itself meet adopter/compliance
  requirements even when it contains licensed components. They support the
  explicit production gate in `product_hardware_spec.md`; public pages are not
  treated as enough information to design a compliant connector network.
- Lattice Semiconductor,
  [SiI9437/SiI9438 product page](https://www.latticesemi.com/Products/ASSPs/HDMI21eARC)
  and [receiver/transmitter data
  brief](https://www.latticesemi.com/-/media/LatticeSemi/Documents/DataSheets/SiI-DB-02013-B.ashx?document_id=52242).
  Primary device evidence for the provisional audio-only receiver: SiI9437 is
  the audio-device eARC/ARC receiver, exposes four I2S outputs plus IEC 60958,
  and describes up to eight-channel 24-bit/192 kHz transport. V1 deliberately
  advertises only two-channel LPCM and keeps selection conditional on current
  lifecycle, supply, full documentation, software terms, and licensed
  reference-design access.
- Analog Devices,
  [ADV7671A product page](https://www.analog.com/en/products/adv7671a.html).
  Primary contingency source for a full 48 Gbit/s HDMI transceiver that can
  configure its transmit-side interface as an eARC receiver and expose
  eight-channel 24-bit/192 kHz audio. The same page states HDMI 2.1 and HDCP 2.x
  adopter requirements for purchase/sampling. Its video/HDCP/API burden is why
  it is not the baseline audio-only architecture.
- Texas Instruments,
  [SRC4392 product page](https://www.ti.com/product/SRC4392) and
  [data sheet](https://www.ti.com/lit/ds/symlink/src4392.pdf); Analog Devices,
  [AD1896 product page](https://www.analog.com/en/products/ad1896.html) and
  [data sheet](https://www.analog.com/media/en/technical-documentation/data-sheets/AD1896.pdf).
  Primary sources for the provisional TV-to-local-clock boundary. SRC4392 is
  active, host-controlled, two-channel, 24-bit, and rated through 216 kHz;
  AD1896 is a production, hardware-configured 24-bit stereo alternative through
  192 kHz. Device headline performance is not accepted in lieu of board-level
  passband, residual, relock, latency, and transient measurements.
- STMicroelectronics,
  [STM32H743/753 product family](https://www.st.com/en/microcontrollers-microprocessors/stm32h743-753.html).
  Primary source for the provisional front-panel MCU class: LTDC, external
  memory interface, Ethernet MAC, timers/ADCs, up to 2 MiB flash/1 MiB RAM, and
  the H753 security accelerators. The UI remains outside FPGA audio deadlines
  and must build with an open compiler toolchain.
- Newhaven Display,
  [NHD-5.0-800480AF-ASXP-CTP product
  page](https://newhavendisplay.com/5-0-inch-ips-capacitive-tft-display/).
  Primary candidate source for the 5-inch, 800 x 480, 24-bit RGB IPS LCD with
  capacitive FT5426G I2C touch, cover glass, 3.3 V logic, high-brightness
  backlight, and EMI-shielded FPC. It supports the mechanical/electrical
  baseline, not a lifecycle or thermal qualification claim.
- Bourns,
  [PRM16 motorized rotary potentiometer](https://www.bourns.com/products/potentiometers/product-detail/commercial-panel-controls/prm16)
  and [PRM16 data
  sheet](https://www.bourns.com/docs/Product-Datasheets/PRM16.pdf).
  Primary prototype-mechanism source. It supports manual and motorized rotation
  but publishes 15,000-cycle life, which motivates a separate 100,000-cycle
  production qualification and prevents presenting this prototype selection as
  a high-life production solution. Its tracks sense position only; they never
  carry product audio.
- Texas Instruments,
  [DRV8874 product page](https://www.ti.com/product/DRV8874) and
  [data sheet](https://www.ti.com/lit/ds/symlink/drv8874.pdf).
  Primary source for the provisional motor H-bridge: bidirectional drive,
  current regulation, proportional current feedback, sleep, and fault output.
  The selected mechanism sets the current limit; the driver's maximum current
  is not treated as a motor requirement.
- Grayhill, [Series 62H optical encoder](https://grayhill.com/products/rotational-controls/optical-encoders/high-torque-haptic-rotary-encoder/62h/),
  and Bourns, [EM14 optical
  encoder](https://www.bourns.com/products/encoders/product-detail/optical-encoders/em14).
  Primary candidates for metal-shaft/bushing, quadrature, push-capable physical
  controls with published long life. Detent torque/resolution still require a
  front-panel human-factors trial with production knob inertia.

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
  frequency. OPA1656 is the Rev-A dual-channel JFET-input prototype choice; its
  electrical table's 4.3 nV/√Hz at 1 kHz and 6 fA/√Hz typical values define the
  conservative white-noise calculation, while 2.9 nV/√Hz at 10 kHz explains the
  different headline value. This is not a measured board result.
- Texas Instruments, [OPA1632 data sheet](https://www.ti.com/lit/ds/symlink/opa1632.pdf).
  Supplies the fully differential amplifier pin map, common-mode interface, and
  the PCM4202 drive/filter topology adapted by the Rev-A EVT board.
- Texas Instruments, [TPS7A39 data sheet](https://www.ti.com/lit/ds/symlink/tps7a39.pdf)
  and [TPS7A20 data sheet](https://www.ti.com/lit/ds/symlink/tps7a20.pdf).
  Supply the package pin maps, feedback equations, stability capacitors, and
  operating limits for the local bipolar and ADC post-regulators.
- AKM, [AK5572EN](https://www.akm.com/global/en/products/audio/audio-adc/ak5572en/);
  TI, [PCM4202 data sheet](https://www.ti.com/lit/ds/symlink/pcm4202.pdf) and
  [TAA5242](https://www.ti.com/product/TAA5242). Current official product pages
  and data sheets supply ADC dynamic-range, interface, and availability
  candidates. PCM4202 is the Rev-A EVT choice; its exact DBR pin map, 6 Vpp
  differential full scale, 116 dB unweighted 48 kHz dynamic range, master-mode
  strap table, 512-fS SCKI, 128-fS BCK, reference bypass, VCOM restriction, and
  high-pass-disable polarity define the board and its verifier.
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
