#%%----------------------------------------------------------------------------
# 4x4 Binary FlipDot Clock - CircuitPython
# Adapted from circle clock for BCD time display (HH:MM format)
#%%----------------------------------------------------------------------------
# General Libraries
import time, gc, os
import rtc
import board
import digitalio
import displayio
import terminalio
import simpleio
import random as r

#RTC Libraries
import adafruit_ds3231

# Display Libraries
from adafruit_display_text import label
import adafruit_displayio_sh1107
from adafruit_display_shapes.rect import Rect
from adafruit_display_shapes.roundrect import RoundRect
from adafruit_display_shapes.circle import Circle
import i2cdisplaybus

# WIFI Libraries
import ssl
import wifi
import socketpool
import adafruit_requests
import adafruit_ntp
import json
import microcontroller

# Web Server Libraries
from adafruit_httpserver import Server, Request, Response, POST

# LED Libraries
import adafruit_dotstar


# Panel Header
# |- SCK      - SCK (IO36)
# |- MOSI     - SDO (IO35)
# |- SS/LATCH - SPI (IO37)
# |- GND

# Use FeatherS2 SPI Port
clockPin = digitalio.DigitalInOut(board.SCK)
dataPin = digitalio.DigitalInOut(board.IO35)
latchPin = digitalio.DigitalInOut(board.IO37)
oePin = digitalio.DigitalInOut(board.IO18)

clockPin.direction = digitalio.Direction.OUTPUT
dataPin.direction = digitalio.Direction.OUTPUT
latchPin.direction = digitalio.Direction.OUTPUT
oePin.direction = digitalio.Direction.OUTPUT

# disable outputs (or True, depending on your OE polarity)
clockPin.value = False
dataPin.value = False
latchPin.value = False
oePin.value = False

# OE Clarity
OE_ENABLE  = True
OE_DISABLE = False
oePin.value = OE_DISABLE

# Display mode: "24h" or "12h"
display_mode = "24h"

# Track last displayed time for change detection
lastTimeShown = None

# Relay Setup
relayPrechargeS = 0.20   # seconds to let 24V rails charge
relayHoldS      = 0.08   # seconds to keep rails up after last flip

# Flipdot timing (seconds between actuations, allows capacitor recharge)
flipdotDelay = 0.5

flipPwrIsOn = False
flipPwrOffAtS = 0.0

# Init Time Variables
secOld = 255
minOld = 255
hrOld  = 255

# Web Server Variables
server = None
action_log = []
LOG_MAX = 50
start_time = 0
last_wifi_sync_time = "Never"

# HTML Dashboard - loaded from index.html file
INDEX_HTML_FILE = "/index.html"

# Timezone table: (key, display_name, utc_offset_minutes, dst_rule)
# dst_rule: None=no DST, "US"=US rules, "EU"=EU rules, "AU"=AU rules, "NZ"=NZ rules
TIMEZONES = (
    ("US/Hawaii",    "Hawaii",             -600, None),
    ("US/Alaska",    "Alaska",             -540, "US"),
    ("US/Pacific",   "Pacific (LA)",       -480, "US"),
    ("US/Mountain",  "Mountain (Denver)",  -420, "US"),
    ("US/Arizona",   "Arizona",            -420, None),
    ("US/Central",   "Central (Chicago)",  -360, "US"),
    ("US/Eastern",   "Eastern (New York)", -300, "US"),
    ("EU/London",    "London",                0, "EU"),
    ("EU/Paris",     "Paris",               +60, "EU"),
    ("EU/Berlin",    "Berlin",              +60, "EU"),
    ("EU/Moscow",    "Moscow",             +180, None),
    ("AS/Dubai",     "Dubai",              +240, None),
    ("AS/Mumbai",    "Mumbai",             +330, None),
    ("AS/Singapore", "Singapore",          +480, None),
    ("AS/Tokyo",     "Tokyo",              +540, None),
    ("OC/Sydney",    "Sydney",             +600, "AU"),
    ("OC/Auckland",  "Auckland",           +720, "NZ"),
    ("UTC",          "UTC",                   0, None),
)


#%%----------------------------------------------------------------------------
def getBit(value, bitIdx):
    # Return bit mask of value at bitIdx.
    return value & (1 << bitIdx)

#%%----------------------------------------------------------------------------
def setBit(value, bitIdx):
    # Return value with bitIdx set to 1.
    return value | (1 << bitIdx)

#%%----------------------------------------------------------------------------
def clrBit(value, bitIdx):
    # Return value with bitIdx cleared to 0.
    return value & ~(1 << bitIdx)

#%%----------------------------------------------------------------------------
def writeBit(value, bitIdx, bitValue):
    # Set/clear bitIdx in value based on bitValue.
    if bitValue == 1:  # setBit
        output = value | (1 << bitIdx)
    else:  # clear Bit
        output = value & ~(1 << bitIdx)
    return output

#%%----------------------------------------------------------------------------
def log_action(msg):
    # Add timestamped entry to action log.
    global action_log
    try:
        t = rtc.datetime
        ts = "{:02}:{:02}:{:02}".format(t.tm_hour, t.tm_min, t.tm_sec)
    except:
        ts = "??:??:??"
    action_log.insert(0, {"ts": ts, "msg": msg})
    if len(action_log) > LOG_MAX:
        action_log.pop()
    print("[LOG]", ts, msg)

#%%----------------------------------------------------------------------------
def get_uptime():
    # Return uptime in seconds since start.
    global start_time
    return int(time.monotonic() - start_time)

#%%----------------------------------------------------------------------------
# NVM Storage for Timezone (index 0 = timezone index into TIMEZONES tuple)
# NVM byte 1 = display mode (0=24h, 1=12h)
#%%----------------------------------------------------------------------------
def load_timezone_nvm():
    # Load timezone key from NVM. Returns key string or default.
    try:
        tz_index = microcontroller.nvm[0]
        if tz_index < len(TIMEZONES):
            return TIMEZONES[tz_index][0]
    except Exception as e:
        print("NVM read error:", e)
    return os.getenv("TIMEZONE", "US/Eastern")

#%%----------------------------------------------------------------------------
def save_timezone_nvm(tz_key):
    # Save timezone key to NVM. Returns True on success.
    for i, tz in enumerate(TIMEZONES):
        if tz[0] == tz_key:
            try:
                microcontroller.nvm[0] = i
                print("Timezone saved to NVM: index", i, tz_key)
                return True
            except Exception as e:
                print("NVM write error:", e)
                return False
    return False

#%%----------------------------------------------------------------------------
def load_display_mode_nvm():
    # Load display mode from NVM byte 1. Returns "12h" or "24h".
    try:
        stored = microcontroller.nvm[1]
        return "12h" if stored == 1 else "24h"
    except Exception as e:
        print("NVM display mode read error:", e)
    return "24h"

#%%----------------------------------------------------------------------------
def save_display_mode_nvm(mode):
    # Save display mode to NVM byte 1.
    try:
        microcontroller.nvm[1] = 1 if mode == "12h" else 0
        print("Display mode saved to NVM:", mode)
        return True
    except Exception as e:
        print("NVM display mode write error:", e)
        return False

#%%----------------------------------------------------------------------------
# DST Calculation Functions
#%%----------------------------------------------------------------------------
def nth_weekday(year, month, weekday, n):
    # Find nth occurrence of weekday in month.
    # weekday: 0=Monday, 6=Sunday. n: 1=first, 2=second, -1=last.
    if n == -1:
        # Last occurrence - find last day of month
        if month == 12:
            next_month_start = time.mktime((year + 1, 1, 1, 0, 0, 0, 0, 0, -1))
        else:
            next_month_start = time.mktime((year, month + 1, 1, 0, 0, 0, 0, 0, -1))
        last_day_epoch = next_month_start - 86400
        last_day = time.localtime(last_day_epoch)
        day = last_day.tm_mday
        wday = last_day.tm_wday
        diff = (wday - weekday) % 7
        return day - diff
    else:
        # Find first day of month's weekday
        first_epoch = time.mktime((year, month, 1, 0, 0, 0, 0, 0, -1))
        first = time.localtime(first_epoch)
        first_wday = first.tm_wday
        diff = (weekday - first_wday) % 7
        first_occurrence = 1 + diff
        return first_occurrence + (n - 1) * 7

#%%----------------------------------------------------------------------------
def is_dst_us(year, month, day, hour):
    # US DST: 2nd Sunday March 2am -> 1st Sunday November 2am
    if month < 3 or month > 11:
        return False
    if month > 3 and month < 11:
        return True
    dst_start_day = nth_weekday(year, 3, 6, 2)   # 2nd Sunday March
    dst_end_day = nth_weekday(year, 11, 6, 1)    # 1st Sunday November
    if month == 3:
        return day > dst_start_day or (day == dst_start_day and hour >= 2)
    if month == 11:
        return day < dst_end_day or (day == dst_end_day and hour < 2)
    return False

#%%----------------------------------------------------------------------------
def is_dst_eu(year, month, day, hour):
    # EU DST: Last Sunday March 1am UTC -> Last Sunday October 1am UTC
    if month < 3 or month > 10:
        return False
    if month > 3 and month < 10:
        return True
    dst_start_day = nth_weekday(year, 3, 6, -1)  # Last Sunday March
    dst_end_day = nth_weekday(year, 10, 6, -1)   # Last Sunday October
    if month == 3:
        return day > dst_start_day or (day == dst_start_day and hour >= 1)
    if month == 10:
        return day < dst_end_day or (day == dst_end_day and hour < 1)
    return False

#%%----------------------------------------------------------------------------
def is_dst_au(year, month, day, hour):
    # AU DST: 1st Sunday October 2am -> 1st Sunday April 3am (Southern Hemisphere)
    dst_start_day = nth_weekday(year, 10, 6, 1)  # 1st Sunday October
    dst_end_day = nth_weekday(year, 4, 6, 1)     # 1st Sunday April
    # Southern hemisphere: DST is Oct-Apr
    if month > 10 or month < 4:
        return True
    if month > 4 and month < 10:
        return False
    if month == 10:
        return day > dst_start_day or (day == dst_start_day and hour >= 2)
    if month == 4:
        return day < dst_end_day or (day == dst_end_day and hour < 3)
    return False

#%%----------------------------------------------------------------------------
def is_dst_nz(year, month, day, hour):
    # NZ DST: Last Sunday September 2am -> 1st Sunday April 3am
    dst_start_day = nth_weekday(year, 9, 6, -1)  # Last Sunday September
    dst_end_day = nth_weekday(year, 4, 6, 1)     # 1st Sunday April
    if month > 9 or month < 4:
        return True
    if month > 4 and month < 9:
        return False
    if month == 9:
        return day > dst_start_day or (day == dst_start_day and hour >= 2)
    if month == 4:
        return day < dst_end_day or (day == dst_end_day and hour < 3)
    return False

#%%----------------------------------------------------------------------------
def get_timezone_offset(tz_key):
    # Return base UTC offset in minutes for timezone key.
    for tz in TIMEZONES:
        if tz[0] == tz_key:
            return tz[2]
    return 0  # Default to UTC

#%%----------------------------------------------------------------------------
def calculate_dst_offset(tz_key, utc_time):
    # Return DST offset in minutes (60 if active, 0 otherwise).
    tz_entry = None
    for tz in TIMEZONES:
        if tz[0] == tz_key:
            tz_entry = tz
            break
    if not tz_entry or tz_entry[3] is None:
        return 0

    dst_rule = tz_entry[3]
    year = utc_time.tm_year
    month = utc_time.tm_mon
    day = utc_time.tm_mday
    hour = utc_time.tm_hour

    if dst_rule == "US":
        return 60 if is_dst_us(year, month, day, hour) else 0
    elif dst_rule == "EU":
        return 60 if is_dst_eu(year, month, day, hour) else 0
    elif dst_rule == "AU":
        return 60 if is_dst_au(year, month, day, hour) else 0
    elif dst_rule == "NZ":
        return 60 if is_dst_nz(year, month, day, hour) else 0
    return 0


#%%----------------------------------------------------------------------------
def sayHello():
    # Print startup banner plus free RAM and flash stats.
    print("\n4x4 Binary FlipDot Clock")
    print("------------------------\n")

    # Show available memory
    print("Memory Info - gc.mem_free()")
    print("---------------------------")
    print("{} Bytes\n".format(gc.mem_free()))

    flash = os.statvfs('/')
    flash_size = flash[0] * flash[2]
    flash_free = flash[0] * flash[3]
    # Show flash size
    print("Flash - os.statvfs('/')")
    print("---------------------------")
    print("Size: {} Bytes\nFree: {} Bytes\n".format(flash_size, flash_free))

#%%----------------------------------------------------------------------------
def setupButton():
    # Configure 3 pull-up inputs and return button objects.
    butA = digitalio.DigitalInOut(board.IO1)
    butA.direction = digitalio.Direction.INPUT
    butA.pull = digitalio.Pull.UP

    butB = digitalio.DigitalInOut(board.IO38)
    butB.direction = digitalio.Direction.INPUT
    butB.pull = digitalio.Pull.UP

    butC = digitalio.DigitalInOut(board.IO33)
    butC.direction = digitalio.Direction.INPUT
    butC.pull = digitalio.Pull.UP

    return [butA, butB, butC]

#%%----------------------------------------------------------------------------
def setupI2C():
    # Initialize and return I2C bus object.
    i2c = board.I2C()
    return i2c

#%%----------------------------------------------------------------------------
def setupRTC(i2c):
    # Create and return DS3231 RTC on the provided I2C bus.
    rtc = adafruit_ds3231.DS3231(i2c)
    return rtc

#%%----------------------------------------------------------------------------
def setHrs():
    # Increment RTC hour by 1 (wrap 0-23) and update screen.
    ucStatus.text = "+1 Hrs"
    t = rtc.datetime

    newHrs = t.tm_hour + 1
    if newHrs > 23:
        newHrs = 0

    rtc.datetime = time.struct_time(
        (t.tm_year, t.tm_mon, t.tm_mday, newHrs, t.tm_min, 0, 0, 0, -1)
    )
    screenUpdate()

#%%----------------------------------------------------------------------------
def setMins():
    # Increment RTC minute by 1 (wrap 0-59) and update screen.
    ucStatus.text = "+1 Mins"
    t = rtc.datetime

    newMins = t.tm_min + 1
    if newMins > 59:
        newMins = 0

    rtc.datetime = time.struct_time(
        (t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, newMins, 0, 0, 0, -1)
    )
    screenUpdate()

#%%----------------------------------------------------------------------------
def setupFlipdotPower():
    # Configure flipdot relay control pin and return it.
    pwr = digitalio.DigitalInOut(board.IO11)
    pwr.direction = digitalio.Direction.OUTPUT
    pwr.value = False  # flipdot power OFF by default
    return pwr

#%%----------------------------------------------------------------------------
def flipsPower(on: bool):
    # Turn flipdot relay on/off with precharge delay on enable.
    global flipPwrIsOn

    if on:
        if not flipPwrIsOn:
            pwr.value = True
            flipPwrIsOn = True
            time.sleep(relayPrechargeS)
    else:
        if flipPwrIsOn:
            pwr.value = False
            flipPwrIsOn = False

#%%----------------------------------------------------------------------------
def extendFlipPowerWindow():
    # Push relay off deadline out by relayHoldS seconds.
    global flipPwrOffAtS
    nowS = time.monotonic()
    offAtS = nowS + relayHoldS
    if offAtS > flipPwrOffAtS:
        flipPwrOffAtS = offAtS

#%%----------------------------------------------------------------------------
def serviceFlipPowerWindow():
    # Turn relay off when window expires; reset cache.
    global flipPwrOffAtS
    if flipPwrIsOn and (time.monotonic() >= flipPwrOffAtS):
        flipsPower(False)
        invalidateFlipCache()

#%%----------------------------------------------------------------------------
def invalidateFlipCache():
    # Force next flip update by invalidating oldData cache.
    global oldData
    oldData = [255, 255, 255, 255]

#%%----------------------------------------------------------------------------
def setFlips(dataIn, flagXOR, managePower=True, forceFull=False, doPrecharge=False):
    # Compute/shift flipdot data with optional power management flags.
    if forceFull:
        flagXOR = 1

    if managePower:
        flipsPower(True)
        extendFlipPowerWindow()
        if doPrecharge:
            time.sleep(relayPrechargeS)

    regData = setFlipsCore(dataIn, flagXOR)

    if managePower:
        extendFlipPowerWindow()

    return regData

#%%----------------------------------------------------------------------------
def setFlipsCore(dataIn, flagXOR):
    # Build 4x12-bit register words and shift them to hardware.
    global oldData

    try:
        oldData
    except NameError:
        oldData = [255, 255, 255, 255]

    supBits = [0, 3, 6, 9]
    setBits = [1, 4, 7, 10]
    resBits = [2, 5, 8, 11]

    xorData = [0, 0, 0, 0]
    regData = [0, 0, 0, 0]

    colData = [dataIn[3], dataIn[2], dataIn[1], dataIn[0]]

    for i in range(0, 4):
        xorData[i] = colData[i] ^ oldData[i]
        for j in range(0, 4):
            xorIdx = getBit(xorData[i], j)
            dotIdx = getBit(colData[i], j)

            if xorIdx == 1 or flagXOR == 1:
                regData[i] = setBit(regData[i], supBits[j])
                if dotIdx == 0:
                    regData[i] = clrBit(regData[i], setBits[j])
                    regData[i] = setBit(regData[i], resBits[j])
                else:
                    regData[i] = setBit(regData[i], setBits[j])
                    regData[i] = clrBit(regData[i], resBits[j])
            else:
                regData[i] = clrBit(regData[i], supBits[j])
                regData[i] = clrBit(regData[i], setBits[j])
                regData[i] = clrBit(regData[i], resBits[j])

    shiftData(regData)
    oldData = colData
    return regData

#%%----------------------------------------------------------------------------
def setupLed():
    # Configure onboard LED pin and return LED object.
    led = digitalio.DigitalInOut(board.LED)
    led.direction = digitalio.Direction.OUTPUT
    return led

#%%----------------------------------------------------------------------------
def setupScreen(i2c):
    # Init OLED and return screen group + label/status objects.
    blk = 0x000000
    wht = 0xFFFFFF
    displayio.release_displays()
    display_bus = i2cdisplaybus.I2CDisplayBus(i2c, device_address=0x3C)

    screenWidth  = 128
    screenHeight = 64
    screenBorder = 2
    screenRadius = 5

    display = adafruit_displayio_sh1107.SH1107(
        display_bus, width=screenWidth, height=screenHeight
    )

    screen = displayio.Group()
    display.root_group = screen

    rect = RoundRect(
        int(screenBorder/2), int(screenBorder/2),
        screenWidth-screenBorder, screenHeight-screenBorder,
        screenRadius, fill=None, outline=wht, stroke=1
    )
    screen.append(rect)

    timeArea = label.Label(terminalio.FONT, text="HH:MM", color=wht)
    timeArea.anchor_point = (0.5, 0.5)
    timeArea.anchored_position = (64, 9)
    screen.append(timeArea)

    ucStatus = label.Label(terminalio.FONT, text=" Startup", color=wht)
    ucStatus.anchor_point = (0.5, 0.5)
    ucStatus.anchored_position = (64, 27)
    screen.append(ucStatus)

    circleRadius = 4
    wifiCircle = Circle(120, 8, circleRadius, fill=None, outline=wht, stroke=1)
    screen.append(wifiCircle)

    wifiStatus = label.Label(terminalio.FONT, text="No WiFi", color=wht)
    wifiStatus.anchor_point = (0.5, 0.5)
    wifiStatus.anchored_position = (64, 44)
    screen.append(wifiStatus)

    wifiAddress = label.Label(terminalio.FONT, text="000.000.00.00", color=wht)
    wifiAddress.anchor_point = (0.5, 0.5)
    wifiAddress.anchored_position = (64, 54)
    screen.append(wifiAddress)

    return [screen, timeArea, ucStatus, wifiCircle, wifiStatus, wifiAddress]

#%%----------------------------------------------------------------------------
def screenUpdate():
    # Refresh OLED time text and blink the onboard LED.
    t = rtc.datetime
    timeArea.text = "{:02}:{:02}:{:02}".format(t.tm_hour, t.tm_min, t.tm_sec)
    print(timeArea.text)
    ucStatus.text = " "
    led.value = not led.value

#%%----------------------------------------------------------------------------
def hour24ToHour12(hour24):
    # Convert 24h hour to 12h range (1-12).
    hour12 = hour24 % 12
    if hour12 == 0:
        hour12 = 12
    return hour12

#%%----------------------------------------------------------------------------
def timeDisplay(hour, minute, use_12h=False):
    """
    Convert HH:MM to 4-column BCD data [H1, H2, M1, M2].
    Matches Arduino format: sprintf(buffer, "%02d%02d", hour, minute)
    """
    if use_12h:
        hour = hour24ToHour12(hour)

    # Format as HHMM string
    time_str = "{:02d}{:02d}".format(hour, minute)

    # Column order: H1, H2, M1, M2 (left to right on physical display)
    col_data = [
        ord(time_str[0]) & 0x0F,  # H1 (column 0)
        ord(time_str[1]) & 0x0F,  # H2 (column 1)
        ord(time_str[2]) & 0x0F,  # M1 (column 2)
        ord(time_str[3]) & 0x0F,  # M2 (column 3)
    ]
    return col_data

#%%----------------------------------------------------------------------------
def timeUpdate(forceAll=False):
    """Update flipdot display with current time in BCD format."""
    global lastTimeShown, display_mode

    t = rtc.datetime
    use_12h = (display_mode == "12h")
    data = timeDisplay(t.tm_hour, t.tm_min, use_12h)

    # Format time string for logging
    time_str = "{:02d}{:02d}".format(
        hour24ToHour12(t.tm_hour) if use_12h else t.tm_hour,
        t.tm_min
    )

    flipsPower(True)
    try:
        if forceAll:
            # Force blank first, then set time
            setFlips([0, 0, 0, 0], 1, managePower=False)
            time.sleep(flipdotDelay)
            setFlips(data, 1, managePower=False)
            time.sleep(flipdotDelay)
        else:
            # Differential update (XOR-based)
            setFlips(data, 0, managePower=False)
    finally:
        extendFlipPowerWindow()

    lastTimeShown = time_str
    log_action("Display: " + time_str)

#%%----------------------------------------------------------------------------
# Animation Functions (adapted for 4x4 binary display - no motor)
#%%----------------------------------------------------------------------------
def anim_demo():
    # Demo: count through BCD digits 0-9 on each column
    flipsPower(True)
    try:
        # Count 0-9 on all columns simultaneously
        for n in range(10):
            setFlips([n, n, n, n], 1, managePower=False)
            time.sleep(0.2)
        # Show 12:00
        setFlips(timeDisplay(12, 0, False), 1, managePower=False)
        time.sleep(0.3)
        # Blank
        setFlips([0, 0, 0, 0], 1, managePower=False)
        time.sleep(0.2)
    finally:
        extendFlipPowerWindow()
    # Restore actual time
    timeUpdate(forceAll=True)

def anim_chase():
    # Chase pattern: light columns left-to-right
    flipsPower(True)
    try:
        for col in range(4):
            data = [0, 0, 0, 0]
            data[col] = 15  # All dots in column
            setFlips(data, 1, managePower=False)
            time.sleep(0.2)
        # Reverse
        for col in range(3, -1, -1):
            data = [0, 0, 0, 0]
            data[col] = 15
            setFlips(data, 1, managePower=False)
            time.sleep(0.2)
        # Blank
        setFlips([0, 0, 0, 0], 1, managePower=False)
        time.sleep(0.1)
    finally:
        extendFlipPowerWindow()
    timeUpdate(forceAll=True)

def anim_chaos():
    # Random chaos: random dot patterns
    flipsPower(True)
    try:
        for _ in range(20):
            data = [r.randint(0, 15) for _ in range(4)]
            setFlips(data, 1, managePower=False)
            time.sleep(0.08)
    finally:
        extendFlipPowerWindow()
    timeUpdate(forceAll=True)

def anim_sync():
    # Binary counting: count 0-15 on all columns
    flipsPower(True)
    try:
        for n in range(16):
            setFlips([n, n, n, n], 1, managePower=False)
            time.sleep(0.15)
        setFlips([0, 0, 0, 0], 1, managePower=False)
    finally:
        extendFlipPowerWindow()
    timeUpdate(forceAll=True)

#%%----------------------------------------------------------------------------
def setupDot():
    # Initialize DotStar and define global color constants.
    numPixels = 1
    dotstar = adafruit_dotstar.DotStar(
        board.APA102_SCK, board.APA102_MOSI, numPixels,
        brightness=1.0, auto_write=True
    )

    global RED, YELLOW, ORANGE, GREEN, TEAL, CYAN, BLUE, PURPLE, MAGENTA, WHITE
    RED     = (255, 0, 0)
    YELLOW  = (200, 255, 0)
    ORANGE  = (255, 40, 0)
    GREEN   = (0, 255, 0)
    TEAL    = (0, 255, 120)
    CYAN    = (0, 255, 255)
    BLUE    = (0, 0, 255)
    PURPLE  = (180, 0, 255)
    MAGENTA = (255, 0, 20)
    WHITE   = (255, 255, 255)

    return dotstar

#%%----------------------------------------------------------------------------
def setDotstar(color, brightness):
    # Set DotStar color and brightness.
    dotstar[0] = (color[0], color[1], color[2], brightness)

#%%----------------------------------------------------------------------------
def getWifiTime():
    # Connect WiFi, fetch UTC time via NTP, apply timezone/DST, set RTC.
    global wifiError
    global secOld, minOld, hrOld

    # Get WiFi credentials from settings.toml
    ssid = os.getenv("CIRCUITPY_WIFI_SSID")
    password = os.getenv("CIRCUITPY_WIFI_PASSWORD")
    ntp_server = os.getenv("NTP_SERVER", "pool.ntp.org")

    # Load timezone from NVM or fallback to settings.toml
    timezone = load_timezone_nvm()

    if not ssid or not password:
        print("WiFi credentials missing in settings.toml!")
        return {
            "wifiError": True,
            "rtc_time": rtc.datetime,
            "ipAddress": None,
            "timezone": timezone,
            "dst": None,
            "delta_s": None,
            "msg": "Check settings.toml",
        }

    wifiError = False

    result = {
        "wifiError": False,
        "rtc_time": rtc.datetime,
        "ipAddress": None,
        "timezone": timezone,
        "dst": False,
        "delta_s": None,
        "msg": "Init",
    }

    setDotstar(PURPLE, 0.25)
    wifiCircle.fill = None
    ucStatus.text = "Connecting WiFi"; print("Connecting to WiFi")
    wifiStatus.text = "---"
    wifiAddress.text = "---"
    result["msg"] = "Connecting to WiFi"

    print("Connecting to %s" % ssid)
    try:
        wifi.radio.connect(ssid, password)
    except Exception as e:
        wifiError = True
        result["wifiError"] = True
        result["msg"] = "WiFi Error"
        print("WiFi Error - Could Not Connect:", e)
        ucStatus.text = "WiFi Error"; print("WiFi Error")
        setDotstar(YELLOW, 0.25)
        return result

    ipAddress = wifi.radio.ipv4_address
    result["ipAddress"] = ipAddress

    ucStatus.text = "WiFi Connected"; print("WiFi Available")
    wifiCircle.fill = 0xFFFFFF
    wifiStatus.text = ssid
    wifiAddress.text = str(ipAddress)
    setDotstar(GREEN, 0.25)
    result["msg"] = "WiFi Available"

    try:
        pool = socketpool.SocketPool(wifi.radio)

        ucStatus.text = "NTP Sync"; print("Fetching NTP from", ntp_server)
        result["msg"] = "NTP Sync"

        # Create NTP client and get UTC time
        ntp = adafruit_ntp.NTP(pool, server=ntp_server, tz_offset=0)
        utc_time = ntp.datetime

        # Look up timezone offset and DST
        tz_offset_min = get_timezone_offset(timezone)
        dst_offset_min = calculate_dst_offset(timezone, utc_time)
        total_offset_min = tz_offset_min + dst_offset_min

        result["dst"] = dst_offset_min > 0

        # Apply offset to get local time
        utc_epoch = time.mktime(utc_time)
        local_epoch = utc_epoch + (total_offset_min * 60)
        local_time = time.localtime(local_epoch)

        # Build struct_time for RTC
        local_struct = time.struct_time((
            local_time.tm_year,
            local_time.tm_mon,
            local_time.tm_mday,
            local_time.tm_hour,
            local_time.tm_min,
            local_time.tm_sec,
            local_time.tm_wday,
            local_time.tm_yday,
            1 if result["dst"] else 0
        ))

        rtc_before = rtc.datetime

        WIFI_RESYNC_THRESHOLD_S = 120
        try:
            delta_s = abs(time.mktime(local_struct) - time.mktime(rtc_before))
        except Exception as e:
            print("Delta calc failed:", e)
            delta_s = WIFI_RESYNC_THRESHOLD_S

        result["delta_s"] = delta_s

        rtc.datetime = local_struct
        result["rtc_time"] = rtc.datetime

        if delta_s >= WIFI_RESYNC_THRESHOLD_S:
            print("Time drift %.1fs, resyncing" % delta_s)
            timeUpdate(forceAll=True)
            syncOldTrackers()

        tz_name = timezone
        for tz in TIMEZONES:
            if tz[0] == timezone:
                tz_name = tz[1]
                break
        print("RTC updated via NTP (%s, DST=%s)" % (tz_name, result["dst"]))
        ucStatus.text = "NTP Synced"
        result["msg"] = "RTC update via NTP"

    except Exception as e:
        print("NTP Error:", e)
        setDotstar(YELLOW, 0.25)
        ucStatus.text = "NTP Error"; print("NTP Error")
        result["msg"] = "NTP Error"
        result["wifiError"] = True
        result["rtc_time"] = rtc.datetime

    return result

#%%----------------------------------------------------------------------------
def shiftData(regData):
    # Shift 4 words into registers, latch, then clear outputs.
    oePin.value = OE_ENABLE

    for i in range(0, 4):
        latchPin.value = False
        simpleio.shift_out(dataPin, clockPin, (regData[i] >> 8), msb_first=True)
        simpleio.shift_out(dataPin, clockPin, regData[i], msb_first=True)

    latchPin.value = True
    latchPin.value = False
    time.sleep(0.005)

    for i in range(0, 4):
        latchPin.value = False
        simpleio.shift_out(dataPin, clockPin, 0, msb_first=True)
        simpleio.shift_out(dataPin, clockPin, 0, msb_first=True)

    latchPin.value = True
    latchPin.value = False
    oePin.value = OE_DISABLE

#%%----------------------------------------------------------------------------
def blankDisplay():
    # Run full blank-white-blank sequence and reset flip cache.
    print("Blanking Display")

    flipsPower(True)
    try:
        setFlips([0, 0, 0, 0], 1, managePower=False)
        time.sleep(2.5)

        setFlips([15, 15, 15, 15], 1, managePower=False)
        time.sleep(2.5)

        setFlips([0, 0, 0, 0], 1, managePower=False)
        time.sleep(2.5)
    finally:
        time.sleep(relayHoldS)
        flipsPower(False)
        invalidateFlipCache()

#%%----------------------------------------------------------------------------
def blankToBlack():
    # Quickly force display to black and reset flip cache.
    flipsPower(True)
    try:
        setFlips([0, 0, 0, 0], 1, managePower=False)
        time.sleep(0.05)
    finally:
        time.sleep(relayHoldS)
        flipsPower(False)
        invalidateFlipCache()

#%%----------------------------------------------------------------------------
def playAnimation():
    # Run simple wipe animation frames on flipdots.
    ucStatus.text = "Play Animation"

    wipeLt = [[15,0,0,0],[0,15,0,0],[0,0,15,0],[0,0,0,0]]
    wipeRt = [[0,0,0,15],[0,0,15,0],[0,15,0,0],[15,0,0,0]]
    frames = [wipeLt, wipeRt]

    flipsPower(True)
    try:
        for frame in frames:
            for col in frame:
                setFlips(col, 1, managePower=False)
                time.sleep(0.5)
                led.value = not led.value
    finally:
        time.sleep(relayHoldS)
        flipsPower(False)
        invalidateFlipCache()

#%%----------------------------------------------------------------------------
def syncOldTrackers():
    # Sync secOld/minOld/hrOld to RTC so main loop won't re-trigger updates.
    global secOld, minOld, hrOld
    t = rtc.datetime
    secOld = t.tm_sec
    minOld = t.tm_min
    hrOld  = t.tm_hour

#%%----------------------------------------------------------------------------
def setupWebServer(pool):
    # Initialize HTTP server with routes for status and control.
    global server
    server = Server(pool, debug=True)

    @server.route("/")
    def index_route(request: Request):
        with open(INDEX_HTML_FILE, "r") as f:
            html_content = f.read()
        return Response(request, body=html_content, content_type="text/html")

    @server.route("/status.json")
    def status_route(request: Request):
        global display_mode
        try:
            t = rtc.datetime
            time_str = "{:02}:{:02}:{:02}".format(t.tm_hour, t.tm_min, t.tm_sec)
            hr12 = hour24ToHour12(t.tm_hour)
        except:
            time_str = "??:??:??"
            hr12 = 0

        ssid = os.getenv("CIRCUITPY_WIFI_SSID", "Unknown")

        # Load timezone from NVM
        tz = load_timezone_nvm()
        tz_name = tz
        for timezone in TIMEZONES:
            if timezone[0] == tz:
                tz_name = timezone[1]
                break

        # Get current BCD display data
        t = rtc.datetime
        use_12h = (display_mode == "12h")
        current_bcd = timeDisplay(t.tm_hour, t.tm_min, use_12h)

        status = {
            "time": time_str,
            "hour_24": t.tm_hour if t else 0,
            "hour_12": hr12,
            "minute": t.tm_min if t else 0,
            "wifi_connected": wifi.radio.connected,
            "ip_address": str(wifi.radio.ipv4_address) if wifi.radio.connected else "None",
            "ssid": ssid,
            "timezone": tz,
            "timezone_name": tz_name,
            "display_mode": display_mode,
            "current_bcd": current_bcd,
            "current_display": "{:02d}{:02d}".format(
                hr12 if use_12h else t.tm_hour,
                t.tm_min
            ) if t else "0000",
            "last_time_shown": lastTimeShown if lastTimeShown else "----",
            "flipdot_power": flipPwrIsOn,
            "uptime_s": get_uptime(),
            "free_memory": gc.mem_free(),
            "last_wifi_sync": last_wifi_sync_time,
        }
        return Response(request, body=json.dumps(status), content_type="application/json")

    @server.route("/log.json")
    def log_route(request: Request):
        return Response(request, body=json.dumps({"entries": action_log}), content_type="application/json")

    @server.route("/wipe", POST)
    def wipe_route(request: Request):
        log_action("Wipe display triggered via web")
        blankDisplay()
        timeUpdate(forceAll=True)
        return Response(request, body='{"ok":true}', content_type="application/json")

    @server.route("/set_hour", POST)
    def set_hour_route(request: Request):
        log_action("+1 hour via web")
        setHrs()
        timeUpdate(forceAll=True)
        return Response(request, body='{"ok":true}', content_type="application/json")

    @server.route("/set_min", POST)
    def set_min_route(request: Request):
        log_action("+1 minute via web")
        setMins()
        timeUpdate(forceAll=True)
        return Response(request, body='{"ok":true}', content_type="application/json")

    @server.route("/refresh", POST)
    def refresh_route(request: Request):
        log_action("Refresh display via web")
        timeUpdate(forceAll=True)
        return Response(request, body='{"ok":true}', content_type="application/json")

    @server.route("/sync_wifi", POST)
    def sync_wifi_route(request: Request):
        global last_wifi_sync_time
        log_action("WiFi sync triggered via web")
        result = getWifiTime()
        if not result["wifiError"]:
            t = rtc.datetime
            last_wifi_sync_time = "{:02}:{:02}:{:02}".format(t.tm_hour, t.tm_min, t.tm_sec)
        return Response(request, body=json.dumps({"ok": not result["wifiError"]}), content_type="application/json")

    @server.route("/get_timezone")
    def get_timezone_route(request: Request):
        # Return current timezone and list of all available timezones.
        current_tz = load_timezone_nvm()

        tz_list = []
        for tz in TIMEZONES:
            tz_list.append({
                "key": tz[0],
                "name": tz[1],
                "offset": tz[2],
                "dst": tz[3] is not None
            })

        response = {
            "current": current_tz,
            "timezones": tz_list
        }
        return Response(request, body=json.dumps(response), content_type="application/json")

    @server.route("/set_timezone", POST)
    def set_timezone_route(request: Request):
        # Set timezone, save to NVM, and immediately resync clock.
        global last_wifi_sync_time

        try:
            # Parse JSON body
            body = request.body.decode("utf-8") if request.body else "{}"
            data = json.loads(body)
            new_tz = data.get("timezone", "").strip()

            # Validate timezone exists
            valid = False
            tz_name = new_tz
            for tz in TIMEZONES:
                if tz[0] == new_tz:
                    valid = True
                    tz_name = tz[1]
                    break

            if not valid:
                return Response(
                    request,
                    body='{"ok":false,"error":"Invalid timezone"}',
                    content_type="application/json"
                )

            # Save to NVM
            if not save_timezone_nvm(new_tz):
                return Response(
                    request,
                    body='{"ok":false,"error":"Failed to save to NVM"}',
                    content_type="application/json"
                )

            log_action("Timezone set to " + tz_name)

            # Immediately resync with new timezone
            result = getWifiTime()
            if not result["wifiError"]:
                t = rtc.datetime
                last_wifi_sync_time = "{:02}:{:02}:{:02}".format(t.tm_hour, t.tm_min, t.tm_sec)

            return Response(
                request,
                body=json.dumps({"ok": not result["wifiError"], "timezone": new_tz, "name": tz_name}),
                content_type="application/json"
            )

        except Exception as e:
            print("set_timezone error:", e)
            return Response(
                request,
                body='{"ok":false,"error":"Parse error"}',
                content_type="application/json"
            )

    @server.route("/set_display_mode", POST)
    def set_display_mode_route(request: Request):
        # Toggle or set display mode (12h/24h)
        global display_mode

        try:
            body = request.body.decode("utf-8") if request.body else "{}"
            data = json.loads(body)
            new_mode = data.get("mode", "").strip().lower()

            if new_mode not in ["12h", "24h"]:
                # Toggle if no valid mode specified
                new_mode = "24h" if display_mode == "12h" else "12h"

            display_mode = new_mode
            save_display_mode_nvm(new_mode)
            log_action("Display mode set to " + new_mode)

            # Refresh display with new mode
            timeUpdate(forceAll=True)

            return Response(
                request,
                body=json.dumps({"ok": True, "mode": new_mode}),
                content_type="application/json"
            )

        except Exception as e:
            print("set_display_mode error:", e)
            return Response(
                request,
                body='{"ok":false,"error":"Parse error"}',
                content_type="application/json"
            )

    # Animation routes
    @server.route("/anim/demo", POST)
    def anim_demo_route(request: Request):
        log_action("Animation: Demo sequence")
        anim_demo()
        return Response(request, body='{"ok":true}', content_type="application/json")

    @server.route("/anim/chase", POST)
    def anim_chase_route(request: Request):
        log_action("Animation: Chase pattern")
        anim_chase()
        return Response(request, body='{"ok":true}', content_type="application/json")

    @server.route("/anim/chaos", POST)
    def anim_chaos_route(request: Request):
        log_action("Animation: Random chaos")
        anim_chaos()
        return Response(request, body='{"ok":true}', content_type="application/json")

    @server.route("/anim/sync", POST)
    def anim_sync_route(request: Request):
        log_action("Animation: Binary count")
        anim_sync()
        return Response(request, body='{"ok":true}', content_type="application/json")

    return server

#%%----------------------------------------------------------------------------
# Setup Functions
#%%----------------------------------------------------------------------------
# Startup Stuff
start_time = time.monotonic()
sayHello()

# Load display mode from NVM
display_mode = load_display_mode_nvm()
print("Display mode:", display_mode)

# Setup Leds
led = setupLed()
dotstar = setupDot()
setDotstar(YELLOW,0.5)

# Setup Clock and Buttons
i2c = setupI2C()
rtc = setupRTC(i2c)
butA,butB,butC = setupButton()
t = rtc.datetime

# Re-sync old trackers to current time so loop doesn't fight you
syncOldTrackers()

# Setup the Display
[screen, timeArea, ucStatus, wifiCircle, wifiStatus, wifiAddress] = setupScreen(i2c)
ucStatus.text = "Start Up"

# Setup the Relay for the Dots
pwr = setupFlipdotPower()

# Play Startup Animation
ucStatus.text = "Blanking Display"
blankDisplay()
time.sleep(1.0)

# Show the Current RTC Time
ucStatus.text = "Show Time"
time.sleep(1.0)
timeUpdate(forceAll=True)
screenUpdate()

# Connect to Wifi
ucStatus.text = "Connecting to Wifi"
wifi_status = getWifiTime()
print(
    wifi_status["msg"],
    "ok=", (not wifi_status["wifiError"]),
    "ip=", wifi_status["ipAddress"],
    "tz=", wifi_status["timezone"],
    "dst=", wifi_status["dst"],
    "delta_s=", wifi_status["delta_s"],
)

# Start Web Server if WiFi connected
if not wifi_status["wifiError"]:
    ucStatus.text = "Starting Web Server"
    t = rtc.datetime
    last_wifi_sync_time = "{:02}:{:02}:{:02}".format(t.tm_hour, t.tm_min, t.tm_sec)
    log_action("Clock started")
    log_action("WiFi connected: " + str(wifi_status["ipAddress"]))
    try:
        pool = socketpool.SocketPool(wifi.radio)
        server = setupWebServer(pool)
        clock_web_port = int(os.getenv("CLOCK_WEB_PORT", "80"))
        server.start(str(wifi.radio.ipv4_address), port=clock_web_port)
        print("Web server started at http://{}:{}".format(wifi.radio.ipv4_address, clock_web_port))
        log_action("Web server started")
    except Exception as e:
        print("Web server failed to start:", e)
        server = None

#%%----------------------------------------------------------------------------
# Main Loop
#%%----------------------------------------------------------------------------
print("Starting Main Loop")

while True:
    # Poll web server for incoming requests
    if server:
        try:
            server.poll()
        except Exception as e:
            print("Server poll error:", e)

    t = rtc.datetime

    # Perform Screen Update Every Second
    secTest = t.tm_sec
    if secOld != secTest:
        screenUpdate()
        secOld = secTest

    # Perform Flipdot Update Every Minute
    minTest = t.tm_min
    if minOld != minTest:
        timeUpdate()
        minOld = minTest

    # Begin Button Testing
    didManualUpdate = False   # Track whether a button caused a time/mech change

    if butA.value == 0:
        print("Button A - Full Refresh")
        blankDisplay()
        timeUpdate(forceAll=True)
        didManualUpdate = True

    elif butB.value == 0:
        setHrs()              # Increment RTC hour
        timeUpdate(forceAll=True)
        didManualUpdate = True

    elif butC.value == 0:
        setMins()             # Increment RTC minute
        timeUpdate(forceAll=True)
        didManualUpdate = True

    else:
        serviceFlipPowerWindow()  # Handle delayed flipdot power-off
        time.sleep(0.1)           # Idle delay to limit loop rate

    if didManualUpdate:
        syncOldTrackers()     # Prevent main loop from re-triggering updates
