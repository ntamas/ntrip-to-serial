"""Write MAVLink GPS_RTCM_DATA messages to a serial port."""

from __future__ import annotations

import serial
from pymavlink.dialects.v20 import common as mavcommon


class SerialMAVLinkWriter:
    """Open a serial port and write GPS_RTCM_DATA MAVLink 2 frames.

    Uses :mod:`pymavlink.dialects.v20` directly so that:

    * All outgoing frames use the MAVLink 2 wire format (start byte ``0xFD``).
    * The MAVLink sequence number (header byte 4) is incremented on every
      sent message, allowing receivers to detect dropped frames.

    Parameters
    ----------
    device:
        Serial port path, e.g. ``/dev/ttyUSB0`` or ``COM3``.
    baud_rate:
        Baud rate, e.g. ``115200``.
    source_system:
        MAVLink source system ID (default 255 = GCS).
    source_component:
        MAVLink source component ID (default 190 = MAV_COMP_ID_GPS).
    """

    def __init__(
        self,
        device: str,
        baud_rate: int = 115200,
        source_system: int = 255,
        source_component: int = 190,
    ) -> None:
        self.device = device
        self.baud_rate = baud_rate
        self.source_system = source_system
        self.source_component = source_component
        self._serial: serial.Serial | None = None
        self._mav: mavcommon.MAVLink | None = None

    def open(self) -> None:
        """Open the serial port."""
        self._serial = serial.Serial(self.device, self.baud_rate, timeout=0)
        self._mav = mavcommon.MAVLink(
            self._serial,
            srcSystem=self.source_system,
            srcComponent=self.source_component,
        )

    def close(self) -> None:
        """Close the serial port."""
        if self._serial is not None:
            self._serial.close()
            self._serial = None
        self._mav = None

    def send(self, msg: mavcommon.MAVLink_gps_rtcm_data_message) -> None:
        """Pack and write a single GPS_RTCM_DATA message to the serial port.

        The MAVLink sequence number is incremented automatically on each call
        so that the receiver can detect any dropped frames.
        """
        if self._mav is None:
            raise RuntimeError("Serial port is not open")
        self._mav.send(msg)

    def __enter__(self) -> "SerialMAVLinkWriter":
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
