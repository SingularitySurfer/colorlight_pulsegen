#!/usr/bin/env python3

import time
import numpy as np

from litex import RemoteClient

wb = RemoteClient()
wb.open()

# # #

x = np.linspace(0,2 * np.pi, 1000)
sine = (2**15 * np.sin(x)) + 2**15
sine = sine.astype('int').tolist()


print("artistic sine output...")
i = 0
while(1):
    i = (i + 1) % 1000
    wb.regs.dac_dacval.write(sine[i])
    #time.sleep(0.001)

# # #

wb.close()
