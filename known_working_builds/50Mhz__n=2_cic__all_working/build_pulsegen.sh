# Autogenerated by LiteX / git: b84a858b
set -e
yosys -l pulsegen.rpt pulsegen.ys
nextpnr-ecp5 --json pulsegen.json --lpf pulsegen.lpf --textcfg pulsegen.config      --25k --package CABGA256 --speed 6 --timing-allow-fail  --seed 1
ecppack pulsegen.config --svf pulsegen.svf --bit pulsegen.bit --bootaddr 0 