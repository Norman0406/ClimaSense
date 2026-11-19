// The sensor task: sole owner of the sensor I2C bus, runs on a fixed 1 s tick
// (docs/firmware/architecture.md).
#pragma once

#include "esp_err.h"

namespace sensors {

// Starts the task. Call once, after board::init().
// Step 3: waits for the sensors' power-up time, opens the bus on the low-power I2C controller
// and logs an address scan. The 1 s tick runs but does nothing yet.
esp_err_t start_task();

}  // namespace sensors
