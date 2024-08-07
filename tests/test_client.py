import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from nextion import Nextion
from nextion.client import TouchDataPayload
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
    protocol.read = AsyncMock()
    protocol.read_no_wait = Mock(side_effect=asyncio.QueueEmpty)
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
        ([b"\x71\x01\x00\x00\x00"], 1, "sleep"),
        ([b"\x71\x01\x00\x00\x00", b"\01", b""], 1, "sleep"),
        ([b"\x71\xa5\xff\xff\xff"], -91, "var1"),
        ([b"\x71\xa5\xff\xff\xff", b"\01", b""], -91, "var1"),
        ([b"\x70\x34\x30"], "40", "t16.txt"),
        ([b"\x70\x34\x30", b"\01", b""], "40", "t16.txt"),
    ],
)
async def test_get(client, protocol, response_data, expected_result, variable):
    protocol.read.side_effect = response_data
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
    protocol.read.side_effect = [response_data]
    assert await client.command(command) == expected_result
    protocol.write.assert_called_once_with(command.encode())


@pytest.mark.parametrize(
    "response_data, variable, value",
    [
        (b"\x01\xff\xff\xff", "sleep", 1),
        (b"\x01\xff\xff\xff\01\xff\xff\xff\xff\xff\xff", "sleep", 1),
    ],
)
async def test_set(client, protocol, response_data, variable, value):
    protocol.data_received(response_data)
    assert await client.set(variable, value) is True
    protocol.write.assert_called_once_with(f"{variable}={value}".encode())


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
