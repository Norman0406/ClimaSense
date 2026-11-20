// Errors of the sensor drivers. Pure, no ESP-IDF dependencies.
#pragma once

#include <cstdint>
#include <expected>

#include "sensors/i2c_bus.h"

namespace sensors {

enum class SensorError : uint8_t {
    Nack,     // the sensor did not acknowledge (absent, busy, or measurement not finished)
    Timeout,  // the bus hung
    Bus,      // other bus or driver failure
    Crc,      // the response arrived but its checksum is wrong
};

constexpr const char *to_string(SensorError error)
{
    switch (error) {
    case SensorError::Nack:    return "NACK";
    case SensorError::Timeout: return "bus timeout";
    case SensorError::Bus:     return "bus error";
    case SensorError::Crc:     return "CRC mismatch";
    }
    return "?";
}

constexpr SensorError to_sensor_error(I2cError error)
{
    switch (error) {
    case I2cError::Nack:    return SensorError::Nack;
    case I2cError::Timeout: return SensorError::Timeout;
    case I2cError::Other:   return SensorError::Bus;
    }
    return SensorError::Bus;
}

template <typename T>
using SensorResult = std::expected<T, SensorError>;

// Turns a bus result into a sensor result.
inline SensorResult<void> check(I2cResult result)
{
    if (!result) {
        return std::unexpected(to_sensor_error(result.error()));
    }
    return {};
}

}  // namespace sensors
