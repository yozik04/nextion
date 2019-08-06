import pytest

from nextion.client import Nextion

@pytest.mark.asyncio
async def test_connect():
    client = Nextion('/dev/ttyS1', 9600)
    await client.connect()
    await client.write('connect')
    result = await client.read()

    assert result[:6] == b'comok '