import argparse
import asyncio
import logging

from nextion.client import Nextion
from nextion.constants import BAUDRATES


async def upload(args):
    nextion = Nextion(args.device, args.baud, reconnect_attempts=1)
    await nextion.connect()

    try:
        await nextion.upload_firmware(args.file, args.upload_baud)
    except:
        logging.exception("Failed to upload firmware")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("device", help="device serial port")
    parser.add_argument(
        "-b", "--baud", type=int, default=None, help="baud rate", choices=BAUDRATES
    )
    parser.add_argument(
        "-ub",
        "--upload_baud",
        type=int,
        default=115200,
        help="upload baud rate",
        choices=BAUDRATES,
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="output debug messages"
    )
    parser.add_argument(
        "file", type=argparse.FileType("br"), help="firmware file *.tft"
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)-15s %(message)s",
    )

    loop = asyncio.get_event_loop()
    loop.run_until_complete(upload(args))


if __name__ == "__main__":
    main()
