# Nextion serial client
Lightweight Python 3.5+ async library to control Nextion displays.

# Simple usage:
```python
async def run():
    client = Nextion('/dev/ttyS1', 9600)
    await client.connect()

    # await client.sleep(True)

    # await client.command('sendxy=0')

    print(await client.get('sleep'))
    print(await client.get('field1.txt'))

    await client.set('field1.txt', "%.1f" % (random.randint(0, 1000) / 10))
    await client.set('field2.txt', "%.1f" % (random.randint(0, 1000) / 10))
    
    await client.set('field3.txt', random.randint(0, 100))

    print('finished')

if __name__ == '__main__':
    logging.basicConfig(
        format='%(asctime)s - %(levelname)s - %(message)s',
        level=logging.DEBUG,
        handlers=[
            logging.StreamHandler()
        ])
    loop = asyncio.get_event_loop()
    asyncio.ensure_future(run())
    loop.run_forever()
```

# Additional resources:
https://www.itead.cc/wiki/Nextion_Instruction_Set
