#include "board/led_logic.h"

#include <algorithm>
#include <cmath>

namespace board {

namespace {

// value and brightness 0..255, scale 0..1. The ESP32-C6 has no FPU; this runs only when the
// colour changes, so soft-float is fine.
uint32_t channel_duty(uint8_t value, uint8_t brightness, float scale)
{
    const float level = (static_cast<float>(value) / 255.0f) * (static_cast<float>(brightness) / 255.0f);
    const float duty = std::pow(level, kGamma) * scale * static_cast<float>(kDutyMax);
    return std::min(static_cast<uint32_t>(std::lround(duty)), kDutyMax);
}

}  // namespace

Duty to_duty(Rgb colour, uint8_t brightness, const LedBalance &balance)
{
    const float weakest = std::min({balance.r, balance.g, balance.b});
    return Duty{
        channel_duty(colour.r, brightness, weakest / balance.r),
        channel_duty(colour.g, brightness, weakest / balance.g),
        channel_duty(colour.b, brightness, weakest / balance.b),
    };
}

}  // namespace board
