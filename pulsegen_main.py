#!/usr/bin/env python3

# This file is Copyright (c) 2020 Florent Kermarrec <florent@enjoy-digital.fr>
# License: BSD

import os
import argparse
import sys

from migen import *
from migen.genlib.misc import WaitTimer
from migen.genlib.resetsync import AsyncResetSynchronizer

from litex_boards.platforms import colorlight_5a_75b

from litex.soc.cores.clock import *
from litex.soc.cores.spi_flash import ECP5SPIFlash
from litex.soc.cores.gpio import GPIOOut
from litex.soc.integration.soc_core import *
from litex.soc.integration.builder import *
from litex.soc.integration.soc import *
from litex.soc.interconnect import wishbone

from liteeth.phy.ecp5rgmii import LiteEthPHYRGMII
from litex.build.generic_platform import *
from litex.boards.platforms import genesys2

from litex.soc.interconnect.csr import *

from pulsegen import Pulsegen

# IOs ----------------------------------------------------------------------------------------------

_gpios = [
    ("gpio", 0, Pins("j4:0"), IOStandard("LVCMOS33")),
    ("gpio", 1, Pins("j4:1"), IOStandard("LVCMOS33")),
]

_leds = [
    ("g", 0, Pins("j6:5"), IOStandard("LVCMOS33")),
    ("r", 0, Pins("j6:7"), IOStandard("LVCMOS33")),
    ("y", 0, Pins("j6:9"), IOStandard("LVCMOS33")),
]

# CRG ----------------------------------------------------------------------------------------------

class _CRG(Module):
    def __init__(self, platform, sys_clk_freq):
        self.clock_domains.cd_sys    = ClockDomain()
        # # #

        # Clk / Rst
        clk25 = platform.request("clk25")
        rst_n = platform.request("user_btn_n", 0)
        platform.add_period_constraint(clk25, 1e9/25e6)

        # PLL
        self.submodules.pll = pll = ECP5PLL()
        self.comb += pll.reset.eq(~rst_n)
        pll.register_clkin(clk25, 25e6)
        pll.create_clkout(self.cd_sys, sys_clk_freq)


class DAC(Module, AutoCSR):
    """Basic first order sigma-delta DAC running at sys clock"""
    def __init__(self):
        self.inp = Signal(16)
        self.out = Signal()
        ###
        accu = Signal(17)
        self.sync += [
            accu.eq(accu[:-1] + self.inp),
            self.out.eq(accu[-1])
        ]



class Main(SoCMini, AutoCSR):
    def __init__(self, with_etherbone=True, ip_address=None, mac_address=None):
        platform     = colorlight_5a_75b.Platform(revision="7.0")
        sys_clk_freq = int(50e6)

        # SoCMini ----------------------------------------------------------------------------------
        SoCMini.__init__(self, platform, clk_freq=sys_clk_freq)

        # CRG --------------------------------------------------------------------------------------
        self.submodules.crg = _CRG(platform, sys_clk_freq)

        # Etherbone --------------------------------------------------------------------------------
        if with_etherbone:
            self.submodules.ethphy = LiteEthPHYRGMII(
                clock_pads = self.platform.request("eth_clocks"),
                pads       = self.platform.request("eth"))
            self.add_csr("ethphy")
            self.add_etherbone(
                phy         = self.ethphy,
                ip_address  = ip_address,
                mac_address = mac_address,
            )

        # SPIFlash ---------------------------------------------------------------------------------
        self.submodules.spiflash = ECP5SPIFlash(
            pads         = platform.request("spiflash"),
            sys_clk_freq = sys_clk_freq,
            spi_clk_freq = 5e6,
        )
        self.add_csr("spiflash")

        # GPIOs ------------------------------------------------------------------------------------
        platform.add_extension(_gpios)


        # Leds --------------------------------------------------------------------------------------
        platform.add_extension(_leds)
        led = platform.request("user_led_n")
        r = platform.request("r")
        y = platform.request("y")
        g = platform.request("g")


        t = Signal(32)
        # PULSEGEN ---------------------------------------------------------------------------------
        n = 128
        wb = wishbone.Interface()
        self.bus.add_slave("pulsegen", wb, SoCRegion(origin=0x20000000, size=n, mode='rw', cached=False))
        self.submodules.pulsegen = pg = Pulsegen(width_d=16, size_fft=n, r_max=4096)
        self.add_csr("pulsegen")
        self.comb += [
            If((wb.adr[-4:] == 2), pg.fft.x_in_we.eq(wb.we)),  # if in general area in busspace
            pg.fft.x_in.eq(wb.dat_w),
            pg.fft.x_in_adr.eq(wb.adr),
            #pg.fft.x_out_adr.eq(wb.adr),
            wb.dat_r.eq(pg.fft.x_out),
        ]
        self.sync += [
            wb.ack.eq(wb.stb),
        ]






        # DAC --------------------------------------------------------------------------------------
        self.submodules.dac = dac = DAC()
        outp = platform.request("gpio", 1)
        self.comb += [
            dac.inp.eq(pg.out0),
            outp.eq(self.dac.out),
            led.eq(~t[0]),
            y.eq(t[1]),
            r.eq(pg.fft.x_out[0]),
            g.eq(pg.fft.done),
        ]


        self.sync += If(wb.stb, t.eq(wb.adr))



# Build -------------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="pulsegen test using LiteX and colorlite")
    parser.add_argument("--build",       action="store_true",      help="build bitstream")
    parser.add_argument("--load",        action="store_true",      help="load bitstream")
    parser.add_argument("--flash",       action="store_true",      help="flash bitstream")
    parser.add_argument("--ip-address",  default="192.168.1.20",   help="Ethernet IP address of the board.")
    parser.add_argument("--mac-address", default="0x726b895bc2e2", help="Ethernet MAC address of the board.")
    args = parser.parse_args()

    soc     = Main(ip_address=args.ip_address, mac_address=int(args.mac_address, 0))
    builder = Builder(soc, output_dir="build", csr_csv="csr.csv")
    builder.build(build_name="pulsegen", run=args.build)

    if args.load:
        prog = soc.platform.create_programmer()
        prog.load_bitstream(os.path.join(builder.gateware_dir, soc.build_name + ".svf"))

    if args.flash:
        prog = soc.platform.create_programmer()
        os.system("cp bit_to_flash.py build/gateware/")
        os.system("cd build/gateware && ./bit_to_flash.py pulsegen.bit pulsegen.svf.flash")
        prog.load_bitstream(os.path.join(builder.gateware_dir, soc.build_name + ".svf.flash"))

if __name__ == "__main__":
    main()
