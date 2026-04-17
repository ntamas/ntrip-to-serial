"""Command-line interface for ntrip-to-serial."""

from __future__ import annotations

import signal
import sys
from itertools import count
from typing import Optional

import click
from pyrtcm import RTCMReader
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from ntrip_to_serial.mavlink import rtcm_to_mavlink_messages
from ntrip_to_serial.ntrip import NTRIPClient, NTRIPError
from ntrip_to_serial.serial_writer import SerialMAVLinkWriter

console = Console(stderr=True)


def _status_table(
    host: str,
    mountpoint: str,
    serial_device: str,
    packets: int,
    messages: int,
    bytes_rx: int,
) -> Table:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold cyan", no_wrap=True)
    table.add_column()
    table.add_row("NTRIP source", f"{host}/{mountpoint}")
    table.add_row("Serial port", serial_device)
    table.add_row("RTCM packets forwarded", str(packets))
    table.add_row("MAVLink messages sent", str(messages))
    table.add_row("Bytes received", f"{bytes_rx:,}")
    return table


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--host", required=True, help="NTRIP caster hostname or IP address.")
@click.option("--port", default=2101, show_default=True, help="NTRIP caster TCP port.")
@click.option(
    "--mountpoint", required=True, help="NTRIP mountpoint (without leading '/')."
)
@click.option("--username", default=None, help="NTRIP username (optional).")
@click.option("--password", default=None, help="NTRIP password (optional).")
@click.option(
    "--serial-port",
    required=True,
    help="Serial port device to write MAVLink messages to (e.g. /dev/ttyUSB0).",
)
@click.option(
    "--baud-rate",
    default=115200,
    show_default=True,
    help="Serial port baud rate.",
)
@click.option(
    "--system-id",
    default=255,
    show_default=True,
    help="MAVLink source system ID.",
)
@click.option(
    "--component-id",
    default=190,
    show_default=True,
    help="MAVLink source component ID.",
)
@click.option("-v", "--verbose", is_flag=True, help="Print each RTCM message type.")
def main(
    host: str,
    port: int,
    mountpoint: str,
    username: Optional[str],
    password: Optional[str],
    serial_port: str,
    baud_rate: int,
    system_id: int,
    component_id: int,
    verbose: bool,
) -> None:
    """Forward RTCM3 corrections from an NTRIP server to a serial port.

    The RTCM3 packets are sliced into GPS_RTCM_DATA MAVLink messages before
    being written to the serial port so that any MAVLink-speaking autopilot
    (e.g. ArduPilot / PX4) can inject them directly into its GNSS receiver.

    \b
    Examples
    --------
    ntrip-to-serial --host rtk2go.com --mountpoint MyBase \\
        --serial-port /dev/ttyUSB0

    ntrip-to-serial --host caster.example.com --mountpoint RTCM3 \\
        --username alice --password secret \\
        --serial-port /dev/ttyACM0 --baud-rate 57600 --verbose
    """
    ntrip = NTRIPClient(
        host=host,
        port=port,
        mountpoint=mountpoint,
        username=username,
        password=password,
    )
    writer = SerialMAVLinkWriter(
        device=serial_port,
        baud_rate=baud_rate,
        source_system=system_id,
        source_component=component_id,
    )

    console.print(
        Panel.fit(
            f"[bold]ntrip-to-serial[/bold]\n"
            f"  NTRIP  : [cyan]{host}:{port}[/cyan] / [cyan]{mountpoint}[/cyan]\n"
            f"  Serial : [cyan]{serial_port}[/cyan] @ {baud_rate} baud",
            border_style="green",
        )
    )

    # Connect to NTRIP server.
    console.print(f"Connecting to NTRIP caster [cyan]{host}:{port}[/cyan] …")
    try:
        ntrip.connect()
    except (NTRIPError, OSError) as exc:
        console.print(f"[red]Connection failed:[/red] {exc}")
        sys.exit(1)
    console.print("[green]Connected.[/green]")

    # Open serial port.
    console.print(f"Opening serial port [cyan]{serial_port}[/cyan] …")
    try:
        writer.open()
    except Exception as exc:
        ntrip.close()
        console.print(f"[red]Failed to open serial port:[/red] {exc}")
        sys.exit(1)
    console.print("[green]Serial port open.[/green]")

    # Graceful shutdown on SIGINT / SIGTERM.
    _running = True

    def _shutdown(signum: int, frame: object) -> None:
        nonlocal _running
        _running = False

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # Import RTCMReader is at the top of the module (pyrtcm is a required dep).
    reader = RTCMReader(ntrip.stream, quitonerror=0)

    packets = 0
    messages = 0
    bytes_rx = 0
    seq_counter = count()

    console.print("Forwarding RTCM corrections … (Ctrl-C to stop)\n")

    try:
        with Live(
            _status_table(host, mountpoint, serial_port, 0, 0, 0),
            console=console,
            refresh_per_second=2,
        ) as live:
            for raw, parsed in reader:
                if not _running:
                    break
                if raw is None:
                    continue

                bytes_rx += len(raw)
                seq = next(seq_counter)

                try:
                    mavlink_msgs = list(rtcm_to_mavlink_messages(raw, seq))
                except ValueError as exc:
                    if verbose:
                        console.print(f"[yellow]Skipping oversized packet:[/yellow] {exc}")
                    continue

                for msg in mavlink_msgs:
                    writer.send(msg)
                    messages += 1

                packets += 1

                if verbose:
                    msg_type = parsed.identity if parsed is not None else "?"
                    console.print(
                        f"  [dim]RTCM {msg_type:>8s}[/dim] "
                        f"{len(raw):4d} B → "
                        f"{len(mavlink_msgs)} MAVLink frame(s)"
                    )

                live.update(
                    _status_table(host, mountpoint, serial_port, packets, messages, bytes_rx)
                )

    except Exception as exc:
        console.print(f"\n[red]Error:[/red] {exc}")
        sys.exit(1)
    finally:
        ntrip.close()
        writer.close()

    console.print("\n[green]Done.[/green]")
