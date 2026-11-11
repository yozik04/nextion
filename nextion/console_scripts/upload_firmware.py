import argparse
import asyncio
import logging
import sys

from nextion.client import Nextion
from nextion.constants import BAUD_RATES


async def upload(args):
    with open(args.file, "rb") as file:
        nextion = Nextion(args.device, args.baud, reconnect_attempts=1)
        await nextion.connect()
        try:
            await nextion.upload_firmware(file, args.upload_baud)
        finally:
            await nextion.disconnect()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("device", help="device serial port")
    parser.add_argument(
        "-b", "--baud", type=int, default=None, help="baud rate", choices=BAUD_RATES
    )
    parser.add_argument(
        "-ub",
        "--upload_baud",
        type=int,
        default=115200,
        help="upload baud rate",
        choices=BAUD_RATES,
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="output debug messages"
    )
    parser.add_argument("file", help="firmware file *.tft")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)-15s %(message)s",
    )

    try:
        asyncio.run(upload(args))
    except Exception:
        logging.exception("Failed to upload firmware")
        sys.exit(1)


if __name__ == "__main__":
    main()
