// Framing shared by the Sensirion sensors (SHT45, SCD41, SGP41): data comes in 16-bit words,
// each followed by a CRC-8. Pure, no ESP-IDF dependencies.
#pragma once

#include <cstddef>
#include <cstdint>
#include <span>

#include "sensors/sensor_error.h"

namespace sensors::sensirion {

// CRC-8, polynomial 0x31, initial value 0xFF, no reflection, no final XOR.
// Datasheet example: crc8({0xBE, 0xEF}) == 0x92.
constexpr uint8_t crc8(std::span<const uint8_t> data)
{
    uint8_t crc = 0xFF;
    for (const uint8_t byte : data) {
        crc ^= byte;
        for (int bit = 0; bit < 8; ++bit) {
            crc = (crc & 0x80) ? static_cast<uint8_t>((crc << 1) ^ 0x31) : static_cast<uint8_t>(crc << 1);
        }
    }
    return crc;
}

// Checks and unpacks a response of N words (3 bytes each: MSB, LSB, CRC) into `words`.
template <std::size_t N>
SensorResult<void> unpack_words(std::span<const uint8_t, 3 * N> response, std::span<uint16_t, N> words)
{
    for (std::size_t i = 0; i < N; ++i) {
        const auto chunk = response.subspan(3 * i, 3);
        if (crc8(chunk.first(2)) != chunk[2]) {
            return std::unexpected(SensorError::Crc);
        }
        words[i] = static_cast<uint16_t>((chunk[0] << 8) | chunk[1]);
    }
    return {};
}

// Packs a word with its CRC, for commands that carry arguments (SCD41, SGP41).
constexpr void pack_word(uint16_t word, std::span<uint8_t, 3> out)
{
    out[0] = static_cast<uint8_t>(word >> 8);
    out[1] = static_cast<uint8_t>(word & 0xFF);
    const uint8_t bytes[2] = {out[0], out[1]};
    out[2] = crc8(bytes);
}

}  // namespace sensors::sensirion
