// BOOT/user button: polled every 10 ms, events delivered through a queue.
#pragma once

#include <optional>

#include "esp_err.h"
#include "freertos/FreeRTOS.h"

#include "board/button_logic.h"

namespace board::button {

// Starts polling the button. Call once.
esp_err_t init();

// Waits up to `timeout` for the next short or long press.
std::optional<ButtonEvent> wait(TickType_t timeout);

}  // namespace board::button
