"""Host-side codec and guarded client for the FPGA_Amp control ABI.

The RTL SPI transport exchanges one fixed 80-bit mode-0 transaction.  The
first five bytes carry the request and the final five clock out the response::

    request  = write/address byte + big-endian 32-bit data
    response = status byte + big-endian 32-bit read data

This module deliberately has no dependency on a particular USB/SPI adapter.
Board software supplies a callable that performs one full-duplex ten-byte
transfer, keeping framing and register semantics independently testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, IntFlag
from typing import Protocol


SPI_FRAME_BYTES = 10
DIAGNOSTIC_WORD_COUNT = 22
IDENTITY = 0x4650_4741
ABI_VERSION = 0x0001_0001


class Register(IntEnum):
    IDENTITY = 0x00
    ABI_VERSION = 0x01
    CAPABILITIES = 0x02
    STATUS = 0x03
    CONTROL = 0x04
    SNAPSHOT_SEQUENCE = 0x05
    CALIBRATION_ATTEMPTED = 0x06
    CALIBRATION_ACCEPTED = 0x07
    ADC_CALIBRATION_SHADOW = 0x08
    DAC_CALIBRATION_SHADOW = 0x09
    CALIBRATION_COMMAND = 0x0A
    ADC_CALIBRATION_ACTIVE = 0x0B
    DAC_CALIBRATION_ACTIVE = 0x0C
    STICKY_STATUS = 0x0D
    DIAGNOSTIC_BASE = 0x20


class Capability(IntFlag):
    SNAPSHOT = 1 << 0
    CALIBRATION = 1 << 1
    MUTE = 1 << 2
    DIAGNOSTIC_CLEAR = 1 << 3


class LiveStatus(IntFlag):
    MUTE_REQUEST = 1 << 0
    OUTPUT_MUTED = 1 << 1
    OUTPUT_RAMPING = 1 << 2
    CALIBRATION_BUSY = 1 << 3
    SNAPSHOT_VALID = 1 << 4
    SNAPSHOT_BUSY = 1 << 5
    SNAPSHOT_CAPTURE_AVAILABLE = 1 << 6


class StickyStatus(IntFlag):
    BUS_ERROR = 1 << 0
    CALIBRATION_REJECTED = 1 << 1
    CALIBRATION_INVALID = 1 << 2
    CALIBRATION_UNSAFE = 1 << 3
    SNAPSHOT_TIMEOUT = 1 << 4


class ControlCommand(IntFlag):
    MUTE_REQUEST = 1 << 0
    SNAPSHOT = 1 << 1
    CLEAR_DIAGNOSTICS = 1 << 2
    CLEAR_LOCAL_STICKIES = 1 << 3


class FullDuplexTransfer(Protocol):
    def __call__(self, transmitted: bytes) -> bytes:
        """Exchange one complete ten-byte SPI frame."""


class ControlProtocolError(RuntimeError):
    """Malformed transport response or incompatible control ABI."""


class RegisterBusError(ControlProtocolError):
    """The FPGA register bank rejected a well-formed SPI transaction."""


class CalibrationRejectedError(ControlProtocolError):
    """The atomic calibration guard did not accept the requested pair."""


@dataclass(frozen=True)
class SpiResponse:
    status: int
    data: int


@dataclass(frozen=True)
class CalibrationCommitResult:
    attempted_sequence: int
    accepted_sequence: int


def _require_unsigned(value: int, width: int, name: str) -> None:
    if not isinstance(value, int) or not 0 <= value < (1 << width):
        raise ValueError(f"{name} must be an unsigned {width}-bit integer")


def encode_spi_request(write: bool, word_address: int, data: int = 0) -> bytes:
    """Encode the request half and five response clocks of one SPI frame."""

    _require_unsigned(word_address, 7, "word_address")
    _require_unsigned(data, 32, "data")
    command = (0x80 if write else 0x00) | word_address
    return bytes((command,)) + data.to_bytes(4, "big") + bytes(5)


def decode_spi_response(received: bytes) -> SpiResponse:
    """Decode the response half of one full-duplex SPI frame."""

    if len(received) != SPI_FRAME_BYTES:
        raise ControlProtocolError(
            f"SPI transfer returned {len(received)} bytes; expected {SPI_FRAME_BYTES}"
        )
    return SpiResponse(status=received[5], data=int.from_bytes(received[6:10], "big"))


class SpiControlClient:
    """Typed operations over the protocol-neutral FPGA register bank."""

    def __init__(self, transfer: FullDuplexTransfer):
        self._transfer = transfer

    def transact(self, write: bool, word_address: int, data: int = 0) -> SpiResponse:
        transmitted = encode_spi_request(write, word_address, data)
        response = decode_spi_response(bytes(self._transfer(transmitted)))
        if response.status & 0x01:
            raise RegisterBusError(
                f"register transaction failed at word address 0x{word_address:02x}"
            )
        if response.status & 0xFE:
            raise ControlProtocolError(
                f"unsupported SPI response status 0x{response.status:02x}"
            )
        return response

    def read(self, register: int | Register) -> int:
        return self.transact(False, int(register)).data

    def write(self, register: int | Register, data: int) -> None:
        self.transact(True, int(register), data)

    def verify_compatibility(self) -> None:
        identity = self.read(Register.IDENTITY)
        abi_version = self.read(Register.ABI_VERSION)
        capabilities = Capability(self.read(Register.CAPABILITIES))
        if identity != IDENTITY:
            raise ControlProtocolError(f"unexpected FPGA identity 0x{identity:08x}")
        if abi_version != ABI_VERSION:
            raise ControlProtocolError(
                f"unsupported control ABI 0x{abi_version:08x}; "
                f"expected 0x{ABI_VERSION:08x}"
            )
        required = (
            Capability.SNAPSHOT
            | Capability.CALIBRATION
            | Capability.MUTE
            | Capability.DIAGNOSTIC_CLEAR
        )
        if capabilities & required != required:
            raise ControlProtocolError(
                f"missing required capabilities 0x{int(required & ~capabilities):x}"
            )

    def set_mute(self, muted: bool) -> None:
        self.write(
            Register.CONTROL,
            int(ControlCommand.MUTE_REQUEST) if muted else 0,
        )

    def snapshot(self, muted: bool, poll_limit: int = 8) -> int:
        """Capture and return a new diagnostic-snapshot sequence number.

        The mute level is explicit because every CONTROL write also owns bit 0;
        no host-side cached state can silently change it.
        """

        if poll_limit < 1:
            raise ValueError("poll_limit must be positive")
        previous_sequence = self.read(Register.SNAPSHOT_SEQUENCE)
        command = ControlCommand.SNAPSHOT
        if muted:
            command |= ControlCommand.MUTE_REQUEST
        self.write(Register.CONTROL, int(command))
        for _ in range(poll_limit):
            status = LiveStatus(self.read(Register.STATUS))
            if not status & LiveStatus.SNAPSHOT_BUSY:
                break
        else:
            raise ControlProtocolError("diagnostic snapshot remained busy")
        completed_sequence = self.read(Register.SNAPSHOT_SEQUENCE)
        expected_sequence = min(previous_sequence + 1, 0xFFFF_FFFF)
        if completed_sequence != expected_sequence:
            sticky = StickyStatus(self.read(Register.STICKY_STATUS))
            if sticky & StickyStatus.SNAPSHOT_TIMEOUT:
                raise ControlProtocolError("diagnostic snapshot timed out")
            raise ControlProtocolError(
                "diagnostic snapshot completed without advancing its sequence"
            )
        return completed_sequence

    def clear_diagnostics(self, muted: bool, clear_local_stickies: bool = False) -> None:
        command = ControlCommand.CLEAR_DIAGNOSTICS
        if muted:
            command |= ControlCommand.MUTE_REQUEST
        if clear_local_stickies:
            command |= ControlCommand.CLEAR_LOCAL_STICKIES
        self.write(Register.CONTROL, int(command))

    def read_diagnostic_word(self, index: int) -> int:
        if not isinstance(index, int) or not 0 <= index < DIAGNOSTIC_WORD_COUNT:
            raise ValueError(
                f"diagnostic index must be within 0..{DIAGNOSTIC_WORD_COUNT - 1}"
            )
        return self.read(int(Register.DIAGNOSTIC_BASE) + index)

    def commit_calibration(
        self,
        input_peak_volts_q24: int,
        output_reciprocal_q24: int,
        poll_limit: int = 4,
    ) -> CalibrationCommitResult:
        """Commit the positive Q8.24 ADC/DAC pair while output is muted."""

        for name, value in (
            ("input_peak_volts_q24", input_peak_volts_q24),
            ("output_reciprocal_q24", output_reciprocal_q24),
        ):
            if not isinstance(value, int) or not 0 < value < (1 << 31):
                raise ValueError(f"{name} must be positive signed Q8.24")
        if poll_limit < 1:
            raise ValueError("poll_limit must be positive")

        status = LiveStatus(self.read(Register.STATUS))
        if not status & LiveStatus.OUTPUT_MUTED or status & LiveStatus.OUTPUT_RAMPING:
            raise CalibrationRejectedError("output must be fully muted before commit")
        self.write(Register.ADC_CALIBRATION_SHADOW, input_peak_volts_q24)
        self.write(Register.DAC_CALIBRATION_SHADOW, output_reciprocal_q24)
        self.write(Register.CALIBRATION_COMMAND, 1)

        for _ in range(poll_limit):
            status = LiveStatus(self.read(Register.STATUS))
            if not status & LiveStatus.CALIBRATION_BUSY:
                break
        else:
            raise ControlProtocolError("calibration commit remained busy")

        attempted = self.read(Register.CALIBRATION_ATTEMPTED)
        accepted = self.read(Register.CALIBRATION_ACCEPTED)
        result = CalibrationCommitResult(attempted, accepted)
        if accepted != attempted:
            raise CalibrationRejectedError(
                f"calibration attempt {attempted} was not accepted (last {accepted})"
            )
        return result
