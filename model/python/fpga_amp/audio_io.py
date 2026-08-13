"""Dependency-free integer-PCM WAV I/O for deterministic audio regressions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import wave

import numpy as np
from numpy.typing import NDArray


FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class WavData:
    """Decoded PCM samples normalized to [-1, 1), always frame-by-channel."""

    samples: FloatArray
    sample_rate_hz: int
    sample_width_bits: int

    @property
    def frame_count(self) -> int:
        return int(self.samples.shape[0])

    @property
    def channel_count(self) -> int:
        return int(self.samples.shape[1])


def _decode_pcm(payload: bytes, sample_width_bytes: int) -> FloatArray:
    if sample_width_bytes == 1:
        values = np.frombuffer(payload, dtype=np.uint8).astype(np.int16) - 128
        return values.astype(np.float64) / 128.0
    if sample_width_bytes == 2:
        values = np.frombuffer(payload, dtype="<i2")
        return values.astype(np.float64) / float(1 << 15)
    if sample_width_bytes == 3:
        octets = np.frombuffer(payload, dtype=np.uint8)
        if octets.size % 3:
            raise ValueError("24-bit PCM payload is not a whole number of samples")
        triplets = octets.reshape(-1, 3).astype(np.int32)
        unsigned = triplets[:, 0] | (triplets[:, 1] << 8) | (triplets[:, 2] << 16)
        values = np.where(unsigned & 0x800000, unsigned - (1 << 24), unsigned)
        return values.astype(np.float64) / float(1 << 23)
    if sample_width_bytes == 4:
        values = np.frombuffer(payload, dtype="<i4")
        return values.astype(np.float64) / float(1 << 31)
    raise ValueError(f"unsupported PCM width: {8 * sample_width_bytes} bits")


def read_pcm_wav(path: str | Path) -> WavData:
    """Read uncompressed integer PCM without silently changing channels."""

    source = Path(path)
    with wave.open(str(source), "rb") as handle:
        if handle.getcomptype() != "NONE":
            raise ValueError(f"compressed WAV is unsupported: {handle.getcomptype()}")
        channel_count = handle.getnchannels()
        sample_rate_hz = handle.getframerate()
        sample_width_bytes = handle.getsampwidth()
        frame_count = handle.getnframes()
        payload = handle.readframes(frame_count)

    decoded = _decode_pcm(payload, sample_width_bytes)
    expected_samples = frame_count * channel_count
    if decoded.size != expected_samples:
        raise ValueError(
            f"WAV payload contains {decoded.size} samples; expected {expected_samples}"
        )
    return WavData(
        samples=decoded.reshape(frame_count, channel_count),
        sample_rate_hz=sample_rate_hz,
        sample_width_bits=8 * sample_width_bytes,
    )


def _encode_pcm(values: NDArray[np.int64], sample_width_bits: int) -> bytes:
    if sample_width_bits == 16:
        return values.astype("<i2").tobytes()
    if sample_width_bits == 24:
        unsigned = np.bitwise_and(values, (1 << 24) - 1).astype(np.uint32)
        octets = np.empty((values.size, 3), dtype=np.uint8)
        octets[:, 0] = unsigned & 0xFF
        octets[:, 1] = (unsigned >> 8) & 0xFF
        octets[:, 2] = (unsigned >> 16) & 0xFF
        return octets.tobytes()
    if sample_width_bits == 32:
        return values.astype("<i4").tobytes()
    raise ValueError("output PCM width must be 16, 24, or 32 bits")


def write_pcm_wav(
    path: str | Path,
    samples: FloatArray,
    sample_rate_hz: int,
    *,
    sample_width_bits: int = 24,
) -> dict[str, int]:
    """Write integer PCM and report, rather than hide, clipped samples."""

    if sample_rate_hz <= 0:
        raise ValueError("sample rate must be positive")
    if sample_width_bits not in (16, 24, 32):
        raise ValueError("output PCM width must be 16, 24, or 32 bits")
    values = np.asarray(samples, dtype=np.float64)
    if values.ndim == 1:
        values = values[:, np.newaxis]
    if values.ndim != 2 or values.shape[0] == 0 or values.shape[1] == 0:
        raise ValueError("samples must contain at least one frame and channel")
    if not np.all(np.isfinite(values)):
        raise ValueError("WAV samples must all be finite")

    scale = 1 << (sample_width_bits - 1)
    integer_min = -scale
    integer_max = scale - 1
    positive_limit = integer_max / float(scale)
    clipped_count = int(np.count_nonzero((values < -1.0) | (values > positive_limit)))
    bounded = np.clip(values, -1.0, positive_limit)
    quantized = np.rint(bounded * scale).astype(np.int64)
    quantized = np.clip(quantized, integer_min, integer_max)

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(destination), "wb") as handle:
        handle.setnchannels(values.shape[1])
        handle.setsampwidth(sample_width_bits // 8)
        handle.setframerate(sample_rate_hz)
        handle.writeframes(_encode_pcm(quantized.reshape(-1), sample_width_bits))
    return {
        "frame_count": int(values.shape[0]),
        "channel_count": int(values.shape[1]),
        "sample_width_bits": sample_width_bits,
        "clipped_sample_count": clipped_count,
    }
