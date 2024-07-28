from unittest.mock import MagicMock

import pytest

from nextion.protocol import NextionProtocol


@pytest.fixture
def protocol():
    return NextionProtocol(MagicMock())


@pytest.mark.parametrize(
    "input_chunks, expected_packets",
    [
        (
            [b"\x70\x31\x32\xff\xff\xff\x01\xff\xff\xff\xff\xff\xff"],
            [b"\x70\x31\x32", b"\x01", b""],
        ),
        (
            [
                b"\x70\x31\x32\xff\xff",
                b"\xff\x01\xff",
                b"\xff\xff",
                b"\xff\xff\xff",
            ],
            [b"\x70\x31\x32", b"\x01", b""],
        ),
        (
            [b"\x71\xa5\xff\xff\xff\xff\xff\xff\x01\xff\xff\xff\xff\xff\xff"],
            [b"\x71\xa5\xff\xff\xff", b"\x01", b""],
        ),
        (
            [
                b"\x71\xa5\xff",
                b"\xff\xff\xff",
                b"\xff\xff\x01",
                b"\xff\xff",
                b"\xff\xff\xff\xff",
            ],
            [b"\x71\xa5\xff\xff\xff", b"\x01", b""],
        ),
        (
            [b"\x71\xff\xff\xff\x71\xa5\xff\xff\xff\xff\xff\xff"],
            [b"\x71\xa5\xff\xff\xff"],
        ),
    ],
)
def test_data_received(protocol, input_chunks, expected_packets):
    for chunk in input_chunks:
        protocol.data_received(chunk)

    assert len(expected_packets) == protocol.queue.qsize()

    for expected_packet in expected_packets:
        assert expected_packet == protocol.read_no_wait()
