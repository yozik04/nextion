# Nextion serial client [![Build Status](https://travis-ci.org/yozik04/nextion.svg?branch=master)](https://travis-ci.org/yozik04/nextion)
Lightweight Python 3.5+ async library to control Nextion displays.

## Installation
### Pypi
`pip3 install nextion`

## Simple usage:
```python
import asyncio
import logging
import random

from nextion import Nextion, EventType

class App:
    def __init__(self):
        self.client = Nextion('/dev/ttyS1', 9600, self.event_handler)
    
    # Note: async event_handler can be used only in versions 1.8.0+ (versions 1.8.0+ supports both sync and async versions)
    async def event_handler(self, type_, data):
        if type_ == EventType.STARTUP:
            print('We have booted up!')
        elif type_ == EventType.TOUCH:
            print('A button (id: %d) was touched on page %d' % (data.component_id, data.page_id))
    
        logging.info('Event %s data: %s', type, str(data))
        
        print(await self.client.get('field1.txt'))
    
    async def run(self):
        await self.client.connect()
    
        # await client.sleep()
        # await client.wakeup()
    
        # await client.command('sendxy=0')
    
        print(await self.client.get('sleep'))
        print(await self.client.get('field1.txt'))
    
        await self.client.set('field1.txt', "%.1f" % (random.randint(0, 1000) / 10))
        await self.client.set('field2.txt', "%.1f" % (random.randint(0, 1000) / 10))
        
        await self.client.set('field3.txt', random.randint(0, 100))
    
        print('finished')

if __name__ == '__main__':
    logging.basicConfig(
        format='%(asctime)s - %(levelname)s - %(message)s',
        level=logging.DEBUG,
        handlers=[
            logging.StreamHandler()
        ])
    loop = asyncio.get_event_loop()
    app = App()
    asyncio.ensure_future(app.run())
    loop.run_forever()
```

### Nextion constructor parameters
```
url: str # serial dev
baudrate: int # baud rate
event_handler: typing.Callable[[EventType, any], None] # Event handler function
loop=asyncio.get_event_loop() # your own event loop
reconnect_attempts: int = 3 # how many times to try to retry command in case of failure
encoding: str = 'ascii' # Nextion encoding
```

### Nextion parameters
#### Encoding
You can update encoding on fly (This changes encoding of serial communication only):

`client.encoding = 'latin-1'`

Get current set encoding (Not fetched from the device)

`print(client.encoding)`

## Event handling

```event_handler``` method in the example above will be called on every event comming from the display.

| EventType        | Data                       | Data attributes                    |
|------------------|----------------------------|------------------------------------|
| TOUCH            | TouchDataPayload           | page_id, component_id, touch_event |
| TOUCH_COORDINATE | TouchCoordinateDataPayload | x, y, touch_event                  |
| TOUCH_IN_SLEEP   | TouchCoordinateDataPayload | x, y, touch_event                  |
| AUTO_SLEEP       | None                       | -                                  |
| AUTO_WAKE        | None                       | -                                  |
| STARTUP          | None                       | -                                  |
| SD_CARD_UPGRADE  | None                       | -                                  |

For some components in the Nextion Editor you need to check `Send Component ID` for required event.

# Firmware uploading
If you installed the library you should have `nextion-fw-upload` command in your PATH.
```bash
nextion-fw-upload -h
```

Otherwise use next command in the root of the project: 
```bash
python -m nextion.console_scripts.upload_firmware -h
```

Usage (check with option `-h`)
```
usage: nextion-fw-upload [-h]
                         [-b {2400,4800,9600,19200,38400,57600,115200,230400}]
                         [-ub {2400,4800,9600,19200,38400,57600,115200,230400}]
                         [-v]
                         device file

positional arguments:
  device                device serial port
  file                  firmware file *.tft

optional arguments:
  -h, --help            show this help message and exit
  -b {2400,4800,9600,19200,38400,57600,115200,230400}, --baud {2400,4800,9600,19200,38400,57600,115200,230400}
                        baud rate
  -ub {2400,4800,9600,19200,38400,57600,115200,230400}, --upload_baud {2400,4800,9600,19200,38400,57600,115200,230400}
                        upload baud rate
  -v, --verbose         output debug messages
```

# Additional resources:
- https://www.itead.cc/wiki/Nextion_Instruction_Set
- [PyPI](https://pypi.org/project/nextion/)
