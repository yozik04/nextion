from unittest.mock import call, MagicMock

import pytest

from nextion.protocol import NextionProtocol


@pytest.fixture
async def protocol():
    return NextionProtocol(MagicMock())


@pytest.mark.parametrize(
    "input_chunks, expected_packets",
    [
        ([b"\x00\xff\xff\xff"], [b"\x00"]),
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


@pytest.mark.parametrize("split", range(26))
def test_mixed_packets_at_every_chunk_boundary(protocol, split):
    data = (
        b"\x00\xff\xff\xff"
        b"\x00\x00\x00\xff\xff\xff"
        b"\x71\xff\xff\xff\xff\xff\xff\xff"
        b"\x65\x01\x03\x01\xff\xff\xff"
    )

    protocol.data_received(data[:split])
    protocol.data_received(data[split:])

    assert protocol.read_no_wait() == b"\x00"
    assert protocol.read_no_wait() == b"\x71\xff\xff\xff\xff"
    assert protocol.queue.empty()
    assert protocol.event_message_handler.call_args_list == [
        call(b"\x00\x00\x00"),
        call(b"\x65\x01\x03\x01"),
    ]
    assert protocol.buffer == b""


def test_incomplete_numeric_packet_waits_for_fixed_length(protocol):
    protocol.data_received(b"\x71\xff\xff\xff")

    assert protocol.queue.empty()
    assert protocol.buffer == b"\x71\xff\xff\xff"

    protocol.data_received(b"\xff\xff\xff\xff")

    assert protocol.read_no_wait() == b"\x71\xff\xff\xff\xff"
    assert protocol.buffer == b""


def test_many_malformed_packets_then_partial_response(protocol, caplog):
    malformed = b"\x65\xff\xff\xff" * 1500

    protocol.data_received(malformed + b"\x70ok\xff\xff")

    assert protocol.queue.empty()
    assert protocol.buffer == b"\x70ok\xff\xff"
    assert protocol.dropped_buffer == malformed

    protocol.data_received(b"\xff\x01\xff\xff\xff")

    assert protocol.read_no_wait() == b"\x70ok"
    assert protocol.read_no_wait() == b"\x01"
    assert protocol.queue.empty()
    assert protocol.dropped_buffer == b""
    assert len(caplog.records) == 1
    assert "Junk received. Dropped bytes" in caplog.text
