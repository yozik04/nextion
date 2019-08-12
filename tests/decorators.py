import asyncio

import asynctest

from nextion.client import Nextion, NextionProtocol


def with_client(func):
    @asynctest.patch('serial_asyncio.create_serial_connection')
    async def wrapper(cls, create_serial_connection):
        client = Nextion('/dev/ttyS1', 9600)

        protocol_mock = asynctest.create_autospec(NextionProtocol)
        protocol_mock.wait_connection = asynctest.CoroutineMock()
        protocol_mock.read = asynctest.create_autospec(asyncio.Queue)
        protocol_mock.read_no_wait = asynctest.mock.Mock(side_effect=asyncio.QueueEmpty)
        create_serial_connection.return_value = None, protocol_mock
        await func(cls, client, protocol_mock)

    return wrapper
