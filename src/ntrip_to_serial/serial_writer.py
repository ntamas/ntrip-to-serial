"""Write MAVLink GPS_RTCM_DATA messages to a serial port."""

from __future__ import annotations

from pymavlink import mavutil
from pymavlink.dialects.v20 import common as mavcommon


class SerialMAVLinkWriter:
    """Open a serial port as a MAVLink connection and write GPS_RTCM_DATA frames.

    Parameters
    ----------
    device:
        Serial port path, e.g. ``/dev/ttyUSB0`` or ``COM3``.
    baud_rate:
        Baud rate, e.g. ``115200``.
    source_system:
        MAVLink source system ID (default 255 = GCS).
    source_component:
        MAVLink source component ID (default 0).
    """

    def __init__(
        self,
        device: str,
        baud_rate: int = 115200,
        source_system: int = 255,
        source_component: int = 0,
    ) -> None:
        self.device = device
        self.baud_rate = baud_rate
        self.source_system = source_system
        self.source_component = source_component
        self._conn: mavutil.mavserial | None = None

    def open(self) -> None:
        """Open the serial port."""
        self._conn = mavutil.mavserial(
            self.device,
            baud=self.baud_rate,
            source_system=self.source_system,
            source_component=self.source_component,
        )

    def close(self) -> None:
        """Close the serial port."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def send(self, msg: mavcommon.MAVLink_gps_rtcm_data_message) -> None:
        """Pack and write a single GPS_RTCM_DATA message to the serial port."""
        if self._conn is None:
            raise RuntimeError("Serial port is not open")
        buf = msg.pack(self._conn.mav)
        self._conn.write(buf)

    def __enter__(self) -> "SerialMAVLinkWriter":
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
