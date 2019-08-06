#!/usr/bin/env python3

import serial
import io

ser = serial.Serial(
    port='/dev/ttyS1',
    baudrate = 9600,
    timeout=1
)
sio = io.BufferedRWPair(ser, ser)

#command=b'boiler_top.txt="20"'
command="connect"
end=b'\xff\xff\xff'
sio.write(command.encode()+end)
sio.flush()
while(1):
    r=sio.read()
    if(r):
        print(r)
