# CircuitPython Libraries for ESP32 FlipDot Binary Clock

This folder contains the required CircuitPython libraries for the FeatherS3.

## Required Libraries

Download these from the [Adafruit CircuitPython Bundle](https://circuitpython.org/libraries) for **CircuitPython 10.x**.

Copy the following files/folders to this `lib/` directory:

### Core Libraries (folders)
- `adafruit_display_text/` - Text rendering for displays
- `adafruit_display_shapes/` - Shape drawing (rect, circle, roundrect)
- `adafruit_httpserver/` - HTTP server framework

### Driver Libraries (single .mpy files)
- `adafruit_ds3231.mpy` - DS3231 RTC module driver
- `adafruit_dotstar.mpy` - DotStar RGB LED control
- `adafruit_displayio_sh1107.mpy` - SH1107 OLED display driver
- `adafruit_requests.mpy` - HTTP requests library
- `adafruit_ntp.mpy` - NTP time synchronization
- `adafruit_connection_manager.mpy` - Connection pooling (dependency of adafruit_requests)

### Bus Libraries
- `i2cdisplaybus.mpy` - I2C display bus driver (may be built-in on CP 10.x)

## Bundle Download

1. Go to https://circuitpython.org/libraries
2. Download the **Bundle for Version 10.x**
3. Extract the zip file
4. Copy the required libraries listed above from the `lib/` folder in the bundle to this folder

## Verification

After copying, your `lib/` folder should contain:
```
lib/
├── adafruit_connection_manager.mpy
├── adafruit_display_shapes/
│   ├── __init__.mpy
│   ├── circle.mpy
│   ├── rect.mpy
│   └── roundrect.mpy
├── adafruit_display_text/
│   ├── __init__.mpy
│   ├── label.mpy
│   └── ...
├── adafruit_displayio_sh1107.mpy
├── adafruit_dotstar.mpy
├── adafruit_ds3231.mpy
├── adafruit_httpserver/
│   ├── __init__.mpy
│   └── ...
├── adafruit_ntp.mpy
├── adafruit_requests.mpy
├── i2cdisplaybus.mpy (if not built-in)
└── README.md
```

## Notes

- Use `.mpy` compiled files for better memory efficiency
- The FeatherS3 has sufficient flash for these libraries
- Some libraries (like `i2cdisplaybus`) may be built into CircuitPython 10.x core
