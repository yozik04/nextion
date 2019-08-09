import pytest

from nextion import Nextion

@pytest.mark.asyncio
async def test_connect():
    client = Nextion('/dev/ttyS1', 9600)
    await client.connect()