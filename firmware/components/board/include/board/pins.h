// ClimaSense revision 1.0 pin map (ESP32-C6-WROOM-1-N8).
// Source of truth: docs/hardware/schematic.md, "ESP32-C6-WROOM-1 pin assignment". Keep both in step.
// Only board.cpp, led.cpp and button.cpp (and later the bus code) should need these directly.
#pragma once

#include <cstdint>

#include "driver/gpio.h"

namespace board::pins {

// Sensor bus: SHT45, SCD41, SGP41, BMP580 and nothing else. IO6/IO7 are the C6's
// low-power I2C pins. Pull-ups (4.7 kOhm) go to the switchable sensor rail +3V3_SENS.
inline constexpr gpio_num_t kI2cSensSda = GPIO_NUM_6;
inline constexpr gpio_num_t kI2cSensScl = GPIO_NUM_7;

// Qwiic connector: own bus, pull-ups (4.7 kOhm) to the switchable rail +3V3_QWIIC.
inline constexpr gpio_num_t kI2cQwiicSda = GPIO_NUM_19;
inline constexpr gpio_num_t kI2cQwiicScl = GPIO_NUM_20;

// Sensor rail enable: high = on. 100 kOhm pull-up, so the rail is on during reset.
inline constexpr gpio_num_t kSensEn = GPIO_NUM_18;
// Qwiic rail enable: high = on. 100 kOhm pull-down, so the rail is off until firmware turns it on.
inline constexpr gpio_num_t kQwiicEn = GPIO_NUM_11;
// Before switching either rail off, stop driving that bus's SDA/SCL: the pull-ups sit on the
// switched rail and driven pins would feed the unpowered devices through their inputs.

// BMP580 interrupt. Floats until the BMP580 is configured: enable the internal pull-down.
inline constexpr gpio_num_t kBmpInt = GPIO_NUM_10;

// RGB status LED, each colour active low. Order is G, R, B on IO21..IO23 (not R, G, B).
inline constexpr gpio_num_t kLedG = GPIO_NUM_21;
inline constexpr gpio_num_t kLedR = GPIO_NUM_22;
inline constexpr gpio_num_t kLedB = GPIO_NUM_23;

// Combined BOOT/user button: low when pressed (10 kOhm pull-up). Strapping pin: held low at
// reset it enters USB download mode.
inline constexpr gpio_num_t kButton = GPIO_NUM_9;

// I2C addresses on the sensor bus.
inline constexpr uint8_t kAddrSht45 = 0x44;
inline constexpr uint8_t kAddrBmp580 = 0x47;  // SDO tied to +3V3_SENS
inline constexpr uint8_t kAddrSgp41 = 0x59;
inline constexpr uint8_t kAddrScd41 = 0x62;

}  // namespace board::pins
