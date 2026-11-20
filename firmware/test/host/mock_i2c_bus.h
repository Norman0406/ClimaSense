// GoogleMock stand-in for the sensor bus. Unconfigured calls succeed (a default-constructed
// I2cResult has a value); tests set ON_CALL/EXPECT_CALL for what they check.
#pragma once

#include <algorithm>
#include <cstdint>
#include <initializer_list>
#include <ostream>
#include <span>
#include <vector>

#include <gmock/gmock.h>

#include "sensors/i2c_bus.h"

namespace sensors {
// Readable results in GoogleMock's messages ("ok", "NACK", "timeout") instead of raw bytes.
inline void PrintTo(I2cError error, std::ostream *os) { *os << to_string(error); }
inline void PrintTo(const I2cResult &result, std::ostream *os)
{
    *os << (result ? "ok" : to_string(result.error()));
}
}  // namespace sensors

class MockI2cBus : public sensors::I2cBus {
public:
    MOCK_METHOD(sensors::I2cResult, probe, (uint8_t address), (override));
    MOCK_METHOD(sensors::I2cResult, write, (uint8_t address, std::span<const uint8_t> data), (override));
    MOCK_METHOD(sensors::I2cResult, read, (uint8_t address, std::span<uint8_t> data), (override));
    MOCK_METHOD(sensors::I2cResult, write_read,
                (uint8_t address, std::span<const uint8_t> tx, std::span<uint8_t> rx), (override));
};

// Matches a byte span with exactly these bytes, e.g. write(0x44, Bytes({0xFD})).
inline auto Bytes(std::initializer_list<uint8_t> bytes)
{
    return ::testing::Truly([expected = std::vector<uint8_t>(bytes)](std::span<const uint8_t> data) {
        return std::ranges::equal(data, expected);
    });
}
