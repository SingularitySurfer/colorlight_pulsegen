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

from liteeth.phy.ecp5rgmii import LiteEthPHYRGMII
from litex.build.generic_platform import *
from litex.boards.platforms import genesys2

from litex.soc.interconnect.csr import *

# IOs ----------------------------------------------------------------------------------------------

_gpios = [
    ("gpio", 0, Pins("j4:0"), IOStandard("LVCMOS33")),
    ("gpio", 1, Pins("j4:1"), IOStandard("LVCMOS33")),
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
        self.dacval = CSRStorage(16, description="DAC value")
        self.inp = Signal((16))
        self.out = Signal()
        ###
        accu = Signal(17)
        self.comb += self.inp.eq(self.dacval.storage)
        self.sync += [
            accu.eq(accu[:-1] + self.inp),
            self.out.eq(accu[-1])
        ]


# ColorLite ----------------------------------------------------------------------------------------

class ColorLite(SoCMini, AutoCSR):
    def __init__(self, with_etherbone=True, ip_address=None, mac_address=None):
        platform     = colorlight_5a_75b.Platform(revision="7.0")
        sys_clk_freq = int(125e6)

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


        # Led --------------------------------------------------------------------------------------
        #self.submodules.led = GPIOOut(platform.request("user_led_n"))
        #self.add_csr("led")

        # Pulsegen RAM -----------------------------------------------------------------------------
        self.add_ram("pgen_ram", 0x10000000, 1024)
        port = self.pgen_ram.mem.get_port()
        self.specials += port


        # DAC --------------------------------------------------------------------------------------
        self.submodules.dac = DAC()
        outp = platform.request("gpio", 1)
        led = platform.request("user_led_n")
        self.comb += [
            port.adr.eq(self.dac.inp),
            outp.eq(self.dac.out),
            led.eq(port.dat_r[0]),
            #led.eq(self.dac.inp[0]),
        ]
        self.add_csr("dac")



# Build -------------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="pulsegen test using LiteX and colorlite")
    parser.add_argument("--build",       action="store_true",      help="build bitstream")
    parser.add_argument("--load",        action="store_true",      help="load bitstream")
    parser.add_argument("--flash",       action="store_true",      help="flash bitstream")
    parser.add_argument("--ip-address",  default="192.168.1.20",   help="Ethernet IP address of the board.")
    parser.add_argument("--mac-address", default="0x726b895bc2e2", help="Ethernet MAC address of the board.")
    args = parser.parse_args()

    soc     = ColorLite(ip_address=args.ip_address, mac_address=int(args.mac_address, 0))
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
