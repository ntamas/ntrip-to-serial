"""Slice raw RTCM3 bytes into GPS_RTCM_DATA MAVLink messages.

GPS_RTCM_DATA (message ID 233) carries at most 180 bytes of RTCM payload per
frame.  Larger RTCM packets (up to 720 bytes) must be fragmented across up to
four frames.  The ``flags`` field encodes:

    bit  0      : 1 = fragmented message
    bits 1-2    : fragment ID (0-3)
    bits 3-7    : sequence number (0-31, wraps)

References
----------
https://mavlink.io/en/messages/common.html#GPS_RTCM_DATA
"""

from __future__ import annotations

from typing import Iterator

from pymavlink.dialects.v20 import common as mavcommon

_MAX_FRAG_LEN = 180  # bytes per GPS_RTCM_DATA data field
_MAX_TOTAL_LEN = _MAX_FRAG_LEN * 4  # 720 bytes maximum RTCM payload


def rtcm_to_mavlink_messages(
    raw: bytes,
    sequence: int,
) -> Iterator[mavcommon.MAVLink_gps_rtcm_data_message]:
    """Yield one or more :class:`MAVLink_gps_rtcm_data_message` objects for *raw*.

    Parameters
    ----------
    raw:
        Raw bytes of a single RTCM3 packet (preamble + payload + CRC).
    sequence:
        Monotonically increasing counter maintained by the caller (only the
        low 5 bits are used, wrapping at 32).
    """
    if len(raw) > _MAX_TOTAL_LEN:
        raise ValueError(
            f"RTCM packet is {len(raw)} bytes; GPS_RTCM_DATA supports at most "
            f"{_MAX_TOTAL_LEN} bytes"
        )

    seq5 = sequence & 0x1F  # 5-bit sequence number

    if len(raw) <= _MAX_FRAG_LEN:
        # Single unfragmented message.
        flags = seq5 << 3
        yield _make_msg(flags, raw)
        return

    # Fragmented: split into chunks of up to 180 bytes.
    for frag_id, offset in enumerate(range(0, len(raw), _MAX_FRAG_LEN)):
        chunk = raw[offset : offset + _MAX_FRAG_LEN]
        flags = (seq5 << 3) | ((frag_id & 0x3) << 1) | 1
        yield _make_msg(flags, chunk)


def _make_msg(flags: int, payload: bytes) -> mavcommon.MAVLink_gps_rtcm_data_message:
    data = bytearray(payload) + bytearray(_MAX_FRAG_LEN - len(payload))
    return mavcommon.MAVLink_gps_rtcm_data_message(
        flags=flags,
        len=len(payload),
        data=data,
    )
