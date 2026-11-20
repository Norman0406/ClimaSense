// The sensor task: sole owner of the sensor I2C bus, runs on a fixed 1 s tick
// (docs/firmware/architecture.md).
#pragma once

#include "esp_err.h"

namespace sensors {

// Starts the task. Call once, after board::init().
// Waits for the sensors' power-up time, opens the bus on the low-power I2C controller, logs an
// address scan, then reads the SHT45 and BMP580 every second (step 4 adds the SCD41 and SGP41).
esp_err_t start_task();

}  // namespace sensors
