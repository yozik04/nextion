import binascii

import asynctest

from tests.decorators import with_client


class TestClient(asynctest.TestCase):
    @with_client
    async def testConnect(self, client, protocol):
        connect_return = binascii.unhexlify(
            '636f6d6f6b20312c36372d302c4e5834383237543034335f303131522c3133302c36313438382c453436383543423335423631333633362c3136373737323136')

        protocol.queue.get = asynctest.CoroutineMock(side_effect=[connect_return, b'', b'\01', b''])
        await client.connect()

    @with_client
    async def test_get(self, client, protocol):
        client.connection = protocol

        response_data = binascii.unhexlify('7101000000')

        protocol.queue.get = asynctest.CoroutineMock(side_effect=[response_data, b'\01', b''])

        result = await client.get('sleep')
        protocol.write.assert_called_once_with('get sleep')

        assert result == True