"""Grows the VRAM BAR of Arc B580s on boards whose BIOS has no Resizable BAR support.

The BIOS sizes the BAR and every bridge window above it to the card's 256 MiB default, and the kernel can't
grow them later: the card's own switch port has a BAR that pins its parent window in place. Setting the size in
config space, then removing and rescanning the whole root port, makes the kernel lay that port out from scratch.
"""

import signal
import struct
import time
from pathlib import Path

PCI = Path("/sys/bus/pci")
CLAIMS = Path("/var/lib/kubelet/plugins/gpu.intel.com/preparedClaims.json")
VENDOR, DEVICE = "0x8086", "0xe20b"  # Arc B580
BAR = 2  # the VRAM
BRIDGE = "0x0604"  # class

COMMAND = 0x04
MEMORY_SPACE = 1 << 1
EXTENDED_CAPABILITIES = 0x100
REBAR = 0x15  # capability ID
REBAR_CONTROL = 0x08  # of the first entry, BAR2's on the B580
REBAR_SIZE = 0x3F00  # field of the control register: 2^n MiB


def read(dev, name):
    return (dev / name).read_text().strip()


def config(dev, offset, fmt="I", value=None):
    with open(dev / "config", "r+b") as f:
        f.seek(offset)
        if value is None:
            return struct.unpack("<" + fmt, f.read(struct.calcsize(fmt)))[0]
        f.write(struct.pack("<" + fmt, value))


def bar_mib(dev):
    start, end, _ = read(dev, "resource").splitlines()[BAR].split()
    return (int(end, 16) - int(start, 16) + 1) >> 20


def endpoints(under):
    return [d for d in (PCI / "devices").iterdir() if under in d.resolve().parents and not read(d, "class").startswith(BRIDGE)]


def rebar_control(dev):
    offset = EXTENDED_CAPABILITIES
    while offset:
        header = config(dev, offset)
        if header & 0xFFFF == REBAR:
            return offset + REBAR_CONTROL
        offset = header >> 20


for dev in sorted((PCI / "devices").iterdir()):
    if (read(dev, "vendor"), read(dev, "device")) != (VENDOR, DEVICE):
        continue
    size = int(read(dev, f"resource{BAR}_resize"), 16).bit_length() - 1  # bit n: 2^n MiB
    if bar_mib(dev) >= 1 << size:
        print(f"{dev.name}: BAR{BAR} is already {bar_mib(dev)} MiB")
        continue

    root = next(p for p in dev.resolve().parents if p.parent.name.startswith("pci"))
    card = dev.resolve().parent.parent  # its own switch port
    if others := [d.name for d in endpoints(root) if card not in d.resolve().parents]:
        print(f"{dev.name}: root port {root.name} also serves {', '.join(others)}, leaving it alone")
        continue

    device = f'"DeviceName":"{dev.name.replace(":", "-").replace(".", "-")}-{DEVICE}"'
    while CLAIMS.exists() and device in CLAIMS.read_text():
        print(f"{dev.name}: waiting for the pod holding it to finish")
        time.sleep(10)

    print(f"{dev.name}: growing BAR{BAR} from {bar_mib(dev)} MiB to {1 << size} MiB through root port {root.name}")
    for d in endpoints(card):
        if (d / "driver").exists():
            (d / "driver/unbind").write_text(d.name)
    # stop decoding memory, or the new size overlaps whatever sits above the old BAR
    config(dev, COMMAND, "H", config(dev, COMMAND, "H") & ~MEMORY_SPACE)
    control = rebar_control(dev)
    config(dev, control, value=config(dev, control) & ~REBAR_SIZE | size << 8)
    (PCI / "devices" / root.name / "remove").write_text("1")
    (PCI / "rescan").write_text("1")
    time.sleep(5)
    # not retried on failure: a restart would only take the root port down again
    print(f"{dev.name}: BAR{BAR} is now {bar_mib(dev)} MiB")

signal.pause()
