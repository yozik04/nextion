import argparse
import asyncio
import logging

from nextion.client import Nextion


async def upload(args):
    nextion = Nextion(args.device, args.baud)
    await nextion.connect()

    try:
        await nextion.upload_firmware(args.file)
    except:
        logging.exception("Failed to upload firmware")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("device", help="device serial port")
    parser.add_argument("baud", type=int, help="baud rate")
    parser.add_argument("file", help="firmware file *.tft")

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)-8s %(name)-15s %(message)s",
    )

    args = parser.parse_args()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(upload(args))


if __name__ == "__main__":
    main()