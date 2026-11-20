// The sensor task: sole owner of the sensor I2C bus, runs on a fixed 1 s tick
// (docs/firmware/architecture.md).
#pragma once

#include "esp_err.h"

namespace sensors {

// Starts the task. Call once, after board::init().
// Waits for the sensors' power-up time, opens the bus on the low-power I2C controller, logs an
// address scan, then every second reads the SHT45, BMP580 and SGP41 (VOC and NOx index) and every 5 minutes
// takes an SCD41 single shot.
esp_err_t start_task();

}  // namespace sensors
