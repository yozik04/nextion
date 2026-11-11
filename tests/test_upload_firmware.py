import subprocess
import sys
import textwrap


def test_main_without_current_event_loop(tmp_path):
    firmware = tmp_path / "display.tft"
    firmware.write_bytes(b"firmware")

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            textwrap.dedent("""
                import asyncio
                from unittest.mock import AsyncMock, patch

                from nextion.console_scripts.upload_firmware import main

                asyncio.set_event_loop(None)
                with patch("nextion.console_scripts.upload_firmware.Nextion") as factory:
                    client = factory.return_value
                    client.connect = AsyncMock()
                    client.upload_firmware = AsyncMock()

                    main()

                    factory.assert_called_once_with(
                        "/dev/test", 9600, reconnect_attempts=1
                    )
                    client.connect.assert_awaited_once_with()
                    client.upload_firmware.assert_awaited_once()
                    file, baud = client.upload_firmware.await_args.args
                    assert file.read() == b"firmware"
                    assert baud == 115200
                    file.close()
                """),
            "/dev/test",
            "-b",
            "9600",
            str(firmware),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stdout + result.stderr
