from __future__ import annotations

from pathlib import Path
import sys
import unittest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "model" / "python"))

from fpga_amp.host_control import (
    ABI_VERSION,
    IDENTITY,
    CalibrationRejectedError,
    ControlProtocolError,
    LiveStatus,
    Register,
    RegisterBusError,
    SpiControlClient,
    decode_spi_response,
    encode_spi_request,
)


class FakeRegisterLink:
    def __init__(self) -> None:
        self.registers = {
            int(Register.IDENTITY): IDENTITY,
            int(Register.ABI_VERSION): ABI_VERSION,
            int(Register.CAPABILITIES): 0xF,
            int(Register.STATUS): int(LiveStatus.OUTPUT_MUTED),
            int(Register.SNAPSHOT_SEQUENCE): 0,
            int(Register.CALIBRATION_ATTEMPTED): 0,
            int(Register.CALIBRATION_ACCEPTED): 0,
        }
        self.requests: list[bytes] = []
        self.error_addresses: set[int] = set()
        self.reject_calibration = False

    def __call__(self, transmitted: bytes) -> bytes:
        self.requests.append(transmitted)
        command = transmitted[0]
        write = bool(command & 0x80)
        address = command & 0x7F
        data = int.from_bytes(transmitted[1:5], "big")
        status = 1 if address in self.error_addresses else 0
        response_data = 0
        if status == 0 and write:
            self.registers[address] = data
            if address == int(Register.CONTROL) and data & 0x2:
                self.registers[int(Register.SNAPSHOT_SEQUENCE)] += 1
            if address == int(Register.CALIBRATION_COMMAND):
                attempted = self.registers[int(Register.CALIBRATION_ATTEMPTED)] + 1
                self.registers[int(Register.CALIBRATION_ATTEMPTED)] = attempted
                if not self.reject_calibration:
                    self.registers[int(Register.CALIBRATION_ACCEPTED)] = attempted
        elif status == 0:
            response_data = self.registers.get(address, 0)
        return bytes(5) + bytes((status,)) + response_data.to_bytes(4, "big")


class HostControlTests(unittest.TestCase):
    def test_request_and_response_wire_order(self) -> None:
        self.assertEqual(
            encode_spi_request(True, 0x09, 0x1234_5678),
            bytes.fromhex("89 12 34 56 78 00 00 00 00 00"),
        )
        response = decode_spi_response(bytes.fromhex("00 00 00 00 00 00 de ad be ef"))
        self.assertEqual(response.status, 0)
        self.assertEqual(response.data, 0xDEAD_BEEF)

    def test_codec_rejects_invalid_ranges_and_lengths(self) -> None:
        with self.assertRaises(ValueError):
            encode_spi_request(False, 0x80)
        with self.assertRaises(ValueError):
            encode_spi_request(False, 0, -1)
        with self.assertRaises(ControlProtocolError):
            decode_spi_response(bytes(9))

    def test_identity_read_write_and_bus_error(self) -> None:
        link = FakeRegisterLink()
        client = SpiControlClient(link)
        client.verify_compatibility()
        client.set_mute(False)
        self.assertEqual(link.requests[-1][:5], bytes.fromhex("84 00 00 00 00"))
        link.error_addresses.add(0x7F)
        with self.assertRaises(RegisterBusError):
            client.read(0x7F)

    def test_snapshot_and_clear_keep_mute_level_explicit(self) -> None:
        link = FakeRegisterLink()
        client = SpiControlClient(link)
        self.assertEqual(client.snapshot(muted=True), 1)
        self.assertEqual(link.requests[-2][:5], bytes.fromhex("84 00 00 00 03"))
        client.clear_diagnostics(muted=False, clear_local_stickies=True)
        self.assertEqual(link.requests[-1][:5], bytes.fromhex("84 00 00 00 0c"))
        with self.assertRaises(ValueError):
            client.read_diagnostic_word(21)

    def test_calibration_commit_is_guarded_and_sequence_checked(self) -> None:
        link = FakeRegisterLink()
        client = SpiControlClient(link)
        result = client.commit_calibration(335_544, 2_097_152)
        self.assertEqual(result.attempted_sequence, 1)
        self.assertEqual(result.accepted_sequence, 1)
        self.assertEqual(link.registers[int(Register.ADC_CALIBRATION_SHADOW)], 335_544)
        self.assertEqual(link.registers[int(Register.DAC_CALIBRATION_SHADOW)], 2_097_152)

        link.reject_calibration = True
        with self.assertRaises(CalibrationRejectedError):
            client.commit_calibration(335_545, 2_097_153)

    def test_calibration_requires_fully_muted_positive_coefficients(self) -> None:
        link = FakeRegisterLink()
        client = SpiControlClient(link)
        link.registers[int(Register.STATUS)] = int(LiveStatus.OUTPUT_RAMPING)
        with self.assertRaises(CalibrationRejectedError):
            client.commit_calibration(1, 1)
        with self.assertRaises(ValueError):
            client.commit_calibration(0, 1)


if __name__ == "__main__":
    unittest.main()
