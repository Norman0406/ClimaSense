// Status LED colour to PWM duty: gamma correction and per-colour brightness balance.
// Pure logic, no ESP-IDF dependencies, so it is tested on the PC (firmware/test/host).
#pragma once

#include <cstdint>

namespace board {

struct Rgb {
    uint8_t r = 0;
    uint8_t g = 0;
    uint8_t b = 0;
};

namespace colour {
inline constexpr Rgb kOff{0, 0, 0};
inline constexpr Rgb kRed{255, 0, 0};
inline constexpr Rgb kGreen{0, 255, 0};
inline constexpr Rgb kBlue{0, 0, 255};
inline constexpr Rgb kWhite{255, 255, 255};
}  // namespace colour

struct Duty {
    uint32_t r = 0;
    uint32_t g = 0;
    uint32_t b = 0;
};

// PWM resolution: 10 bit.
inline constexpr uint32_t kDutyMax = 1023;

// Luminous intensity of each colour at full duty, in any common unit. Only the ratios matter:
// each channel is scaled down to the weakest one, so equal values look about equally bright.
struct LedBalance {
    float r;
    float g;
    float b;
};

// Estimate for the Everlight 19-337 with the board's resistors (red 330 R, green and blue 100 R),
// from the datasheet curves, +-30 % (docs/hardware/schematic.md). To be checked by eye on the board.
inline constexpr LedBalance kBoardBalance{13.0f, 21.0f, 8.0f};  // mcd

inline constexpr float kGamma = 2.2f;

// Duty per channel for a colour at a brightness (255 = full), with gamma correction.
Duty to_duty(Rgb colour, uint8_t brightness, const LedBalance &balance = kBoardBalance);

}  // namespace board
