import asyncio
import sys
from unittest.mock import AsyncMock, patch

import pytest

from nextion.console_scripts.upload_firmware import main


@pytest.fixture
def firmware(tmp_path):
    firmware = tmp_path / "display.tft"
    firmware.write_bytes(b"firmware")
    return firmware


@pytest.fixture
def nextion(firmware, monkeypatch):
    monkeypatch.setattr(
        sys, "argv", ["nextion-fw-upload", "/dev/test", "-b", "9600", str(firmware)]
    )
    # Python 3.14 has no implicit event loop; main() must not rely on one.
    asyncio.set_event_loop(None)

    with patch("nextion.console_scripts.upload_firmware.Nextion") as factory:
        client = factory.return_value
        client.connect = AsyncMock()
        client.upload_firmware = AsyncMock()
        client.disconnect = AsyncMock()
        yield factory


def test_main_uploads_firmware(nextion, firmware):
    main()

    nextion.assert_called_once_with("/dev/test", 9600, reconnect_attempts=1)
    client = nextion.return_value
    client.connect.assert_awaited_once_with()
    file, baud = client.upload_firmware.await_args.args
    assert file.name == str(firmware)
    assert file.closed
    assert baud == 115200
    client.disconnect.assert_awaited_once_with()


def test_main_exits_with_error_when_upload_fails(nextion):
    client = nextion.return_value
    client.upload_firmware.side_effect = OSError("no reply")

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
    client.disconnect.assert_awaited_once_with()
