// GoogleMock stand-in for the sensor bus. Unconfigured calls succeed (a default-constructed
// I2cResult has a value); tests set ON_CALL/EXPECT_CALL for what they check.
#pragma once

#include <cstdint>
#include <span>

#include <gmock/gmock.h>

#include "sensors/i2c_bus.h"

class MockI2cBus : public sensors::I2cBus {
public:
    MOCK_METHOD(sensors::I2cResult, probe, (uint8_t address), (override));
    MOCK_METHOD(sensors::I2cResult, write, (uint8_t address, std::span<const uint8_t> data), (override));
    MOCK_METHOD(sensors::I2cResult, read, (uint8_t address, std::span<uint8_t> data), (override));
    MOCK_METHOD(sensors::I2cResult, write_read,
                (uint8_t address, std::span<const uint8_t> tx, std::span<uint8_t> rx), (override));
};
