// Board bring-up and the two switchable supply rails.
#pragma once

#include "esp_err.h"

namespace board {

// Call once at start-up, before anything else on the board is used: drives SENS_EN high
// (sensor rail on, as its pull-up already holds it), QWIIC_EN low (Qwiic rail off) and puts
// the internal pull-down on the BMP580 interrupt line, which floats until the BMP580 is set up.
esp_err_t init();

// Sensor rail +3V3_SENS (SHT45, SCD41, SGP41, BMP580 and their bus pull-ups).
// Before switching it off, delete the sensor I2C bus driver: switching off also turns SDA/SCL
// into plain inputs, so the pins cannot feed the unpowered sensors. After switching it on,
// the sensors need their start-up time (SCD41: 1 s) before the first command.
esp_err_t set_sensor_rail(bool on);
bool sensor_rail_on();

// Qwiic rail +3V3_QWIIC (connector and its bus pull-ups), off by default. Same rule as above
// for the Qwiic bus driver.
esp_err_t set_qwiic_rail(bool on);
bool qwiic_rail_on();

}  // namespace board
