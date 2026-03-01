# ESP32 FlipDot Binary Clock

A 4x4 BCD (Binary-Coded Decimal) flip-dot clock driven by an **Unexpected Maker FeatherS3** running **CircuitPython 10.0.3**. Displays time in binary format across 4 columns representing H1, H2, M1, M2 digits.

## Features

- **BCD Time Display**: 4 columns showing hours and minutes in binary (0-9 per column)
- **WiFi & NTP Sync**: Automatic time synchronization via NTP
- **Web Interface**: Full control dashboard accessible via browser
- **Timezone Support**: Multiple US timezones with automatic DST handling
- **12h/24h Mode**: Toggle between display formats
- **OLED Status**: Local display showing time, IP, and status
- **RTC Backup**: DS3231 maintains time during power loss
- **Animations**: Demo, chase, chaos, count, and debug patterns

## Hardware Architecture

### Panel Design (FlipDotBinF)

The display panel contains 16 flip-dots arranged in a 4x4 matrix:

```
Column:   0 (H1)   1 (H2)   2 (M1)   3 (M2)
         +------+ +------+ +------+ +------+
Bit 3:   |  8   | |  8   | |  8   | |  8   |  (Weight: 8)
         +------+ +------+ +------+ +------+
Bit 2:   |  4   | |  4   | |  4   | |  4   |  (Weight: 4)
         +------+ +------+ +------+ +------+
Bit 1:   |  2   | |  2   | |  2   | |  2   |  (Weight: 2)
         +------+ +------+ +------+ +------+
Bit 0:   |  1   | |  1   | |  1   | |  1   |  (Weight: 1)
         +------+ +------+ +------+ +------+
```

### Shift Register Chain

8x 74HC4094 shift registers daisy-chained (directly coupled, no latch):

```
ESP32 Data --> U7 --> U8 --> U5 --> U6 --> U3 --> U4 --> U1 --> U2
              |_________|   |_________|   |_________|   |_________|
               Column 3      Column 2      Column 1      Column 0
                 (M2)          (M1)          (H2)          (H1)
```

Total: 64 bits (8 registers x 8 bits)

### Per-Dot Control (3 bits each)

Each flip-dot requires 3 control signals:

| Signal | Function | MOSFET |
|--------|----------|--------|
| SUPPLY | Enable H-bridge power | DMG6602SVT (P+N complementary) |
| SET | Flip dot to "on" (yellow) | DMG3402L (N-ch) |
| RESET | Flip dot to "off" (black) | DMG3402L (N-ch) |

### Bit Mapping (per column, 12 bits)

```python
# Row 0 (bottom, weight 1)
supBits = [0, 3, 6, 9]   # Supply enable for rows 0-3
setBits = [1, 4, 7, 10]  # Set (flip to yellow) for rows 0-3
resBits = [2, 5, 8, 11]  # Reset (flip to black) for rows 0-3
```

Layout per column (bits 0-11):
```
Row 0: [SUP0, SET0, RES0] = bits 0, 1, 2
Row 1: [SUP1, SET1, RES1] = bits 3, 4, 5
Row 2: [SUP2, SET2, RES2] = bits 6, 7, 8
Row 3: [SUP3, SET3, RES3] = bits 9, 10, 11
```

## Controller Board (FlipDotMasterC)

The original Arduino controller includes:

- **MCU**: ATmega328P (Arduino compatible)
- **RTC**: DS3231 with CR1220 backup battery
- **Power**: 24V input with boost converter for flip-dot drive
- **Interface**: Grove connectors for panel connection

### FeatherS3 Pinout

For CircuitPython 10.0.3 on the Unexpected Maker FeatherS3:

| Signal | ESP32 Pin | Function |
|--------|-----------|----------|
| SCK (Clock) | IO36 (`board.SCK`) | Shift register clock |
| MOSI (Data) | IO35 (`board.IO35`) | Serial data out |
| Latch | IO37 | Latch shift register outputs |
| OE | IO18 | Output enable (directly controlled by IC) |
| 24V Relay | IO11 | High-voltage power control |
| Button A | IO1 | Wipe/refresh display |
| Button B | IO38 | +1 hour |
| Button C | IO33 | +1 minute |
| OLED SDA | IO3 | I2C data |
| OLED SCL | IO4 | I2C clock |

## Web Interface

Access the dashboard at `http://<device-ip>/`

### Endpoints

| Route | Method | Description |
|-------|--------|-------------|
| `/` | GET | Main dashboard |
| `/status.json` | GET | Current status (time, BCD, WiFi, etc.) |
| `/log.json` | GET | Activity log |
| `/refresh` | POST | Force display update |
| `/wipe` | POST | Blank display then refresh |
| `/set_hour` | POST | Increment hour |
| `/set_min` | POST | Increment minute |
| `/sync_wifi` | POST | Force NTP sync |
| `/set_display_mode` | POST | Toggle 12h/24h |
| `/set_timezone` | POST | Change timezone |
| `/get_timezone` | GET | List available timezones |
| `/anim/demo` | POST | Run demo animation |
| `/anim/chase` | POST | Run chase animation |
| `/anim/chaos` | POST | Run chaos animation |
| `/anim/sync` | POST | Run count animation |
| `/anim/debug` | POST | Count 1-8 on each column |

## Installation

### 1. Install CircuitPython

Install [CircuitPython 10.0.3](https://circuitpython.org/board/unexpectedmaker_feathers3/) on your FeatherS3.

### 2. Copy Libraries

Copy the entire `lib/` folder from this repository to the root of your CIRCUITPY drive. See `lib/README.md` for the complete list of required libraries from the [CircuitPython Bundle](https://circuitpython.org/libraries).

Required libraries:
- `adafruit_ds3231.mpy` - RTC driver
- `adafruit_dotstar.mpy` - Onboard LED
- `adafruit_displayio_sh1107.mpy` - OLED display
- `adafruit_display_text/` - Text rendering
- `adafruit_display_shapes/` - Shape drawing
- `adafruit_httpserver/` - Web server
- `adafruit_requests.mpy` - HTTP client
- `adafruit_ntp.mpy` - Time sync
- `adafruit_connection_manager.mpy` - Connection pooling

### 3. Configure WiFi

Create `settings.toml` with your WiFi credentials:
```toml
CIRCUITPY_WIFI_SSID = "YOUR_WIFI_SSID"
CIRCUITPY_WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"
```

### 4. Copy Application Files

- Copy `code-binaryclock.py` to `/code.py`
- Copy `index.html` to `/index.html`
- Copy `boot.py` to `/boot.py`

### 5. Power On

The clock will connect to WiFi and sync time via NTP automatically.

## File Structure

```
ESP32-FlipDotBinaryClock/
├── boot.py               # Early boot shift register clearing
├── code-binaryclock.py   # Main CircuitPython code (copy as code.py)
├── index.html            # Web dashboard
├── settings.toml         # WiFi & NTP config (create from template)
├── lib/                  # CircuitPython libraries
│   └── README.md         # Library installation guide
├── Arduino/              # Original Arduino firmware (reference)
├── PCB/
│   ├── FlipDotMasterC.PDF      # Controller schematic
│   └── FlipDotBinF_Panel-*.TXT # Panel design files
└── README.md
```

## How It Works

### Time to BCD Conversion

```python
def timeDisplay(hour, minute, use_12h=False):
    if use_12h:
        hour = hour24ToHour12(hour)
    time_str = "{:02d}{:02d}".format(hour, minute)
    col_data = [
        ord(time_str[0]) & 0x0F,  # H1 (tens of hours)
        ord(time_str[1]) & 0x0F,  # H2 (ones of hours)
        ord(time_str[2]) & 0x0F,  # M1 (tens of minutes)
        ord(time_str[3]) & 0x0F,  # M2 (ones of minutes)
    ]
    return col_data
```

Example: 14:37 becomes `[1, 4, 3, 7]`

### Flip-Dot Actuation

1. Enable 24V relay
2. Build 64-bit shift data (3 bits per dot x 16 dots + padding)
3. For each dot needing change:
   - Set SUPPLY bit high
   - Set either SET (yellow) or RESET (black) bit high
4. Shift out data, pulse latch
5. Hold for ~50ms actuation time
6. Clear all bits, shift out zeros
7. Disable relay after timeout

## License

MIT License

## Credits

Adapted from circle clock project for flip-dot binary display.
Hardware design based on original Arduino FlipDotMaster controller.
