#------------------------------------------------------------------------------
# boot.py - Runs before code.py, before USB is configured
# Target: Unexpected Maker FeatherS3 (ESP32-S3) + CircuitPython 10.0.3
# Clears shift registers immediately to ensure supply bits are off
#------------------------------------------------------------------------------
import board
import digitalio
import simpleio

# Configure shift register control pins
clockPin = digitalio.DigitalInOut(board.SCK)
dataPin = digitalio.DigitalInOut(board.IO35)
latchPin = digitalio.DigitalInOut(board.IO37)
oePin = digitalio.DigitalInOut(board.IO18)

clockPin.direction = digitalio.Direction.OUTPUT
dataPin.direction = digitalio.Direction.OUTPUT
latchPin.direction = digitalio.Direction.OUTPUT
oePin.direction = digitalio.Direction.OUTPUT

# Set safe initial states
clockPin.value = False
dataPin.value = False
latchPin.value = False
oePin.value = False  # OE disabled (outputs high-Z)

# Configure 24V relay pin - ensure power is OFF
pwr = digitalio.DigitalInOut(board.IO11)
pwr.direction = digitalio.Direction.OUTPUT
pwr.value = False  # Relay OFF (active-high relay)

# Clear shift registers - shift 64 bits of zeros through all 8 registers
for _ in range(8):
    latchPin.value = False
    simpleio.shift_out(dataPin, clockPin, 0, msb_first=True)
latchPin.value = True
latchPin.value = False

# Deinit shift register pins so code.py can reinitialize them
# NOTE: Relay pin (pwr) is NOT deinit'd - keeps driving LOW to prevent relay activation
clockPin.deinit()
dataPin.deinit()
latchPin.deinit()
oePin.deinit()
# pwr stays configured as OUTPUT LOW until code.py takes over
