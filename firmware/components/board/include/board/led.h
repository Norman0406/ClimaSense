// RGB status LED on three LEDC PWM channels.
#pragma once

#include <cstdint>

#include "esp_err.h"

#include "board/led_logic.h"

namespace board::led {

// Sets up the PWM timer and channels with the LED off. Call once.
esp_err_t init();

// Shows a colour at a brightness (255 = full). Gamma-corrected and colour-balanced
// (see led_logic.h). Not thread-safe: call it from one task.
esp_err_t set(Rgb colour, uint8_t brightness = 255);

inline esp_err_t off() { return set(colour::kOff, 0); }

}  // namespace board::led
