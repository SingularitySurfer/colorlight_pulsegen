# SingularitySurfer 2020


import numpy as np
from migen import *
from misoc.interconnect.stream import Endpoint
from litex.soc.interconnect.csr import *

from Phaser_STFT_Pulsegen.super_interpolator import SuperInterpolator
from Phaser_STFT_Pulsegen.fft_generator_migen import Fft


class Pulsegen(Module, AutoCSR):
    """
     Pulsegen for Colorlight
    """

    def __init__(self, width_d=16, size_fft=128, r_max=4096):

        self.out0 = Signal((width_d, False))  # dac output0

        ###

        self.go = CSRStorage(1, description="start pulsegen")
        self.r = CSRStorage(32, description="interpolation rate", reset=200)
        pos = Signal(int(np.log2(size_fft)))
        slow = Signal(2)
        go = Signal()

        self.submodules.fft = fft = Fft(size_fft, True, width_d, width_d, width_d+2, 18, False)

        self.submodules.inter = inter = SuperInterpolator(width_d, r_max, dsp_arch="lattice")

        self.comb += [
            fft.start.eq(self.go.storage),
            fft.en.eq(1),
            fft.scaling.eq(0xff),
            fft.x_out_adr.eq(pos),
            inter.input.data.eq(fft.x_out),
            inter.r.eq(self.r.storage),
            #self.out0.eq(pos<<7),
            #self.out0.eq(Cat(~fft.x_out[8], fft.x_out[:7], 0x00)),
            self.out0.eq(Cat(inter.output.data0[:15], ~inter.output.data0[15])),
        ]

        self.sync += [
            slow.eq(slow + 1),
            #If((slow[-1] & ~go), go.eq(1)),# fft.x_in_we.eq(1)),
            #If(self.go.storage[0], self.go.storage.eq(0)),
            If(inter.input.ack & fft.done,
               pos.eq(pos+1),
               #If(pos<70, pos.eq(70)),
               #pos.eq(int(np.log2(size_fft))-1),
               )
        ]
    def sim(self):
        for i in range(2000):
            yield
            #x = yield self.out0
            #if x > 700: print(x)

if __name__ == "__main__":
    test = Pulsegen()
    run_simulation(test, test.sim(), vcd_name="pulsegen.vcd")
