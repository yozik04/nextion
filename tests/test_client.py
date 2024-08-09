import asyncio
from unittest.mock import Mock, call

import pytest

from nextion import Nextion
from nextion.client import TouchDataPayload
from nextion.exceptions import CommandFailed
from nextion.protocol.nextion import EventType, NextionProtocol


@pytest.fixture
async def transport() -> Mock:
    return Mock()


@pytest.fixture
def event_handler():
    return Mock()


@pytest.fixture
async def protocol(transport) -> NextionProtocol:
    protocol = NextionProtocol(
        lambda x: None
    )  # Assuming a lambda for the event_message_handler
    protocol.connection_made(transport)
    protocol.write = Mock()

    return protocol


@pytest.fixture
async def client(protocol: NextionProtocol, event_handler) -> Nextion:
    client = Nextion("/dev/ttyS1", 9600, event_handler)
    client._connection = protocol
    protocol.event_message_handler = client._handle_event
    return client


@pytest.mark.parametrize(
    "response_data, expected_result, variable",
    [
        (b"\x71\x01\x00\x00\x00\xff\xff\xff", 1, "sleep"),
        (b"\x71\x01\x00\x00\x00\xff\xff\xff\01\xff\xff\xff\xff\xff\xff", 1, "sleep"),
        (b"\x71\xa5\xff\xff\xff\xff\xff\xff", -91, "var1"),
        (b"\x71\xa5\xff\xff\xff\xff\xff\xff\01\xff\xff\xff\xff\xff\xff", -91, "var1"),
        (b"\x70\x34\x30\xff\xff\xff", "40", "t16.txt"),
        (b"\x70\x34\x30\xff\xff\xff\01\xff\xff\xff\xff\xff\xff", "40", "t16.txt"),
    ],
)
async def test_get(client, protocol, response_data, expected_result, variable):
    protocol.write.side_effect = lambda _: protocol.data_received(response_data)
    result = await client.get(variable)
    protocol.write.assert_called_once_with(f"get {variable}".encode())
    assert result == expected_result


@pytest.mark.parametrize(
    "response_data, expected_result, command",
    [
        (b"\x66\x05\xff\xff\xff", 5, "sendme"),
        (b"\x66\x05\xff\xff\xff\01\xff\xff\xff\xff\xff\xff", 5, "sendme"),
    ],
)
async def test_command(client, protocol, response_data, expected_result, command):
    protocol.write.side_effect = lambda _: protocol.data_received(response_data)
    assert await client.command(command) == expected_result
    protocol.write.assert_called_once_with(command.encode())


async def test_command_failed(client, protocol):
    protocol.write.side_effect = lambda _: protocol.data_received(b"\x03\xff\xff\xff")
    with pytest.raises(CommandFailed):
        await client.command("page 2")


@pytest.mark.parametrize(
    "response_data",
    [
        (b"\x01\xff\xff\xff"),
        (b"\x01\xff\xff\xff\01\xff\xff\xff\xff\xff\xff"),
    ],
)
async def test_wakeup(client, protocol, response_data):
    protocol.write.side_effect = lambda _: protocol.data_received(response_data)
    await client.wakeup()
    protocol.write.assert_called_once_with(b"sleep=0")


@pytest.mark.parametrize(
    "response_data, variable, value",
    [
        (b"\x01\xff\xff\xff", "var.txt", "Hello"),
        (b"\x01\xff\xff\xff", "num.txt", -91),
        (b"\x01\xff\xff\xff", "num.txt", 5.123),
    ],
)
async def test_set_during_sleep(client, protocol, response_data, variable, value):
    protocol.write.side_effect = lambda _: protocol.data_received(response_data)
    await client.set(variable, value)
    protocol.write.assert_not_called()
    await client.wakeup()
    await asyncio.sleep(0)  # Allow background tasks to complete

    expected_value = value
    if isinstance(expected_value, (str, float)):
        expected_value = f'"{expected_value}"'

    protocol.write.assert_has_calls(
        [call(b"sleep=0"), call(f"{variable}={expected_value}".encode())]
    )


async def test_event_handler(client, protocol, event_handler):
    event_handler_called = asyncio.Future()

    def event_handler_called_set_result(*args):
        event_handler_called.set_result(args)

    event_handler.side_effect = event_handler_called_set_result

    protocol.data_received(b"\x65\x01\x03\x01\xff\xff\xff")
    await asyncio.wait_for(event_handler_called, timeout=0.1)
    assert event_handler_called.result() == (
        EventType.TOUCH,
        TouchDataPayload(page_id=1, component_id=3, touch_event=1),
    )


async def test_async_event_handler(client, protocol, event_handler):
    event_handler_called = asyncio.Future()

    async def event_handler_called_set_result(*args):
        event_handler_called.set_result(args)

    event_handler.side_effect = event_handler_called_set_result

    protocol.data_received(b"\x65\x01\x03\x01\xff\xff\xff")
    await asyncio.wait_for(event_handler_called, timeout=0.1)
    assert event_handler_called.result() == (
        EventType.TOUCH,
        TouchDataPayload(page_id=1, component_id=3, touch_event=1),
    )
