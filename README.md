# ntrip-to-serial

Forward RTCM3 corrections from an NTRIP caster to a serial port as MAVLink
`GPS_RTCM_DATA` messages.  Any MAVLink-speaking autopilot (ArduPilot, PX4, …)
can then inject the corrections directly into its GNSS receiver.

## Installation

Clone the source tree and run

```
uv sync
```

## Usage

```
uv run ntrip-to-serial --host <caster> --mountpoint <MOUNT> --serial-port <device>
```

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | *(required)* | NTRIP caster hostname or IP |
| `--port` | `2101` | NTRIP caster TCP port |
| `--mountpoint` | *(required)* | NTRIP mountpoint |
| `--username` | — | NTRIP username (optional) |
| `--password` | — | NTRIP password (optional) |
| `--serial-port` | *(required)* | Serial device (e.g. `/dev/ttyUSB0`) |
| `--baud-rate` | `115200` | Serial baud rate |
| `--system-id` | `255` | MAVLink source system ID |
| `--component-id` | `190` | MAVLink source component ID |
| `-v, --verbose` | — | Print each RTCM message type |
| `--burst-delay` | `0.0` | Delay in seconds between consecutive MAVLink frames in the same burst. Only applied when the frame payload exceeds 100 bytes. |

### Examples

```bash
# Plain (no auth)
ntrip-to-serial --host rtk2go.com --mountpoint MyBase \
    --serial-port /dev/ttyUSB0

# With authentication, custom baud rate and verbose logging
ntrip-to-serial --host caster.example.com --mountpoint RTCM3 \
    --username alice --password secret \
    --serial-port /dev/ttyACM0 --baud-rate 57600 --verbose
```

## How it works

1. A TCP connection is opened to the NTRIP caster and a standard NTRIP request
   is sent (supporting both NTRIPv1 *ICY* and NTRIPv2 HTTP/1.1 chunked responses
   as well as optional Basic authentication).
2. [`pyrtcm`](https://github.com/semuconsulting/pyrtcm) parses the raw byte
   stream into individual RTCM3 packets.
3. Each packet is sliced into one or more
   [`GPS_RTCM_DATA`](https://mavlink.io/en/messages/common.html#GPS_RTCM_DATA)
   MAVLink messages (max 180 bytes of payload per message; packets up to 720 bytes
   are fragmented across up to four frames).
4. The packed MAVLink frames are written to the serial port via
   [`pymavlink`](https://github.com/ArduPilot/pymavlink) /
   [`pyserial`](https://github.com/pyserial/pyserial).

## License

MIT
