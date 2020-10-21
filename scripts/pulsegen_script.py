#!/usr/bin/env python3

import time
import numpy as np

from litex import RemoteClient

wb = RemoteClient()
wb.open()

print("Pulsegen Output...")


n = 128  # fft size
r = 200  # interpolation rate
width_d = 16  # data width

data = [0] * n
data[7] = 16000
data[6] = -8000
data[8] = -8000
#data[8] = 8000

data = [(int(_.real) | int(_.imag) << width_d) & (1 << width_d*2)-1 for _ in data]

wb.write(0x20000000, data)

wb.write(0x00001810, r)

wb.write(0x00001800, 0)
wb.write(0x00001800, 1)



wb.close()
