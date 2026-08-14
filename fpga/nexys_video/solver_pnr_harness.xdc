# Timing-only harness pins from Digilent's Nexys Video master XDC.
# The board oscillator is 100 MHz.  The open P&R command independently asks
# for the design's required 98.304 MHz timing; this harness is not a bitstream
# top and does not establish the eventual audio-clock generation circuit.
set_property LOC R4 [get_ports fabric_clk]
set_property IOSTANDARD LVCMOS33 [get_ports fabric_clk]

set_property LOC G4 [get_ports reset]
set_property IOSTANDARD LVCMOS15 [get_ports reset]

set_property LOC T14 [get_ports activity]
set_property IOSTANDARD LVCMOS25 [get_ports activity]
