# Nextion serial client [![Build](https://github.com/yozik04/nextion/actions/workflows/test.yml/badge.svg)](https://github.com/yozik04/nextion/actions/workflows/test.yml) [![PyPI](https://img.shields.io/pypi/v/nextion)](https://pypi.org/project/nextion/)

Lightweight asyncio library for controlling [Nextion](https://nextion.tech/) HMI displays over a serial port. Requires Python 3.11+.

## Installation

```bash
pip install nextion
```

## Quick start

```python
import asyncio
import logging

from nextion import EventType, Nextion


async def event_handler(type_, data):
    if type_ == EventType.STARTUP:
        print("Display has booted up")
    elif type_ == EventType.TOUCH:
        print(f"Component {data.component_id} touched on page {data.page_id}")


async def main():
    client = Nextion("/dev/ttyS1", 9600, event_handler)
    device_info = await client.connect()
    print(f"Connected to {device_info.model}")

    await client.set("t0.txt", "Hello")
    await client.set("n0.val", 42)
    print(await client.get("t0.txt"))

    await client.command("page 1")

    await asyncio.Event().wait()  # keep running to receive events


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
```

## Constructor

```python
Nextion(
    url: str,                      # serial port, e.g. "/dev/ttyUSB0" or "COM3"
    baud_rate: int | None = None,  # tried first; other supported rates are probed if it fails
    event_handler=...,             # sync or async callable(type_: EventType, data); logs events by default
    reconnect_attempts: int = 3,   # retries for a command that times out
    encoding: str = "ascii",       # text encoding used on the serial line
)
```

Supported baud rates: 2400, 4800, 9600, 19200, 38400, 57600, 115200, 230400.

## API

| Member | Description |
|---|---|
| `await connect()` | Find the display, enable command responses (`bkcmd=3`) and return `DeviceInfo` (`address`, `model`, `firmware_version`, `serial_number`, `flash_size`). |
| `await disconnect()` / `await reconnect()` | Close or reopen the serial connection. |
| `await get(key)` | Read an attribute, e.g. `get("t0.txt")` returns `str`, `get("n0.val")` returns `int`. |
| `await set(key, value)` | Assign a `str` or `int` attribute. While the display sleeps the assignment is deferred until wake-up and `None` is returned; pass `do_not_defer=True` to send it anyway. |
| `await command(cmd)` | Send any [instruction](https://nextion.tech/instruction-set/), e.g. `command("page 1")`. Returns returned data, or `True` on success. |
| `await sleep()` / `await wakeup()` | Put the display to sleep or wake it up. |
| `sleeping` | Whether the display is currently asleep. |
| `await dim(value)` | Set backlight brightness, 0–100. |
| `device_info` | `DeviceInfo` from the last successful `connect()`. |
| `encoding` | Get or set the text encoding (see below). |
| `await upload_firmware(file, upload_baud=None)` | Upload a `.tft` file opened in binary mode. |

`get`, `set` and `command` accept a `timeout` in seconds (default 0.5).

### Errors

All exceptions are importable from `nextion`:

- `CommandFailed` – the display rejected the instruction; `code` holds the return code.
- `CommandTimeout` – no response after all reconnect attempts.
- `ConnectionFailed` – the display could not be reached at any baud rate, or the client is not connected.

### Encoding

`encoding` only changes how text is encoded on the serial line; it must match the character set selected in your Nextion project and be covered by its fonts. It can be changed at any time. For example, to show a degree sign in an `iso-8859-1` project:

```python
client.encoding = "latin-1"
await client.set("t0.txt", "21°C")
```

## Events

The event handler is called for every event sent by the display:

| `EventType` | Data | Data attributes |
|---|---|---|
| `TOUCH` | `TouchDataPayload` | `page_id`, `component_id`, `touch_event` |
| `TOUCH_COORDINATE` | `TouchCoordinateDataPayload` | `x`, `y`, `touch_event` |
| `TOUCH_COORDINATE_IN_SLEEP` | `TouchCoordinateDataPayload` | `x`, `y`, `touch_event` |
| `AUTO_SLEEP` | `None` | – |
| `AUTO_WAKE` | `None` | – |
| `STARTUP` | `None` | – |
| `SD_CARD_UPGRADE` | `None` | – |

`touch_event` is `1` for press and `0` for release. Touch events are only sent for components with **Send Component ID** enabled in the Nextion Editor.

## Firmware upload

Installing the package adds the `nextion-fw-upload` command (or run `python -m nextion.console_scripts.upload_firmware`):

```bash
nextion-fw-upload /dev/ttyUSB0 project.tft --baud 9600 --upload_baud 115200
```

```
usage: nextion-fw-upload [-h] [-b {2400,4800,9600,19200,38400,57600,115200,230400}]
                         [-ub {2400,4800,9600,19200,38400,57600,115200,230400}] [-v]
                         device file

positional arguments:
  device                device serial port
  file                  firmware file *.tft

options:
  -h, --help            show this help message and exit
  -b, --baud {2400,4800,9600,19200,38400,57600,115200,230400}
                        baud rate
  -ub, --upload_baud {2400,4800,9600,19200,38400,57600,115200,230400}
                        upload baud rate
  -v, --verbose         output debug messages
```

`--baud` is the display's current baud rate (probed if omitted); `--upload_baud` is the rate used for the transfer (default 115200). If uploads fail, try a lower `--upload_baud`.

Empty firmware files are rejected before sending any upload commands to the display.

## Resources

- [Nextion Instruction Set](https://nextion.tech/instruction-set/)
- [Nextion Upload Protocol v1.2](https://nextion.tech/2026/07/07/nextion-upload-protocol-v1-2/)
