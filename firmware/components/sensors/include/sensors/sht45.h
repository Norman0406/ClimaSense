// Sensirion SHT45 temperature and humidity sensor. Pure logic on top of I2cBus, tested on the PC.
//
// A measurement takes two calls with a wait in between, so the caller decides how to wait
// (the sensor task sleeps; the tests do not): start_measurement(), wait kMeasureMs,
// read_measurement(). Commands, timing and formulas: SHT4x datasheet, cross-checked against
// Sensirion's embedded-i2c-sht4x driver.
#pragma once

#include <cstdint>

#include "sensors/i2c_bus.h"
#include "sensors/sensor_error.h"

namespace sensors {

struct Sht45Reading {
    int32_t temperature_mc;      // milli-degrees Celsius
    int32_t humidity_mpercent;   // milli-percent relative humidity, clamped to 0..100 %
};

class Sht45 {
public:
    static constexpr uint8_t kAddress = 0x44;

    static constexpr uint8_t kCmdMeasureHighPrecision = 0xFD;
    static constexpr uint8_t kCmdReadSerial = 0x89;
    static constexpr uint8_t kCmdSoftReset = 0x94;

    // Waits after a command before the response can be read (as in Sensirion's driver;
    // the datasheet's maximum for a high-precision measurement is 8.3 ms).
    static constexpr uint32_t kMeasureMs = 10;
    static constexpr uint32_t kSerialMs = 10;
    static constexpr uint32_t kResetMs = 10;

    explicit Sht45(I2cBus &bus) : bus_(bus) {}

    SensorResult<void> soft_reset();

    // Serial number: request_serial(), wait kSerialMs, read_serial().
    SensorResult<void> request_serial();
    SensorResult<uint32_t> read_serial();

    // Measurement (high repeatability): start_measurement(), wait kMeasureMs, read_measurement().
    // Reading too early gives SensorError::Nack: the SHT45 does not acknowledge while measuring.
    SensorResult<void> start_measurement();
    SensorResult<Sht45Reading> read_measurement();

    // Datasheet conversion formulas, rounded to the nearest milli-unit.
    static int32_t temperature_mc(uint16_t raw);
    static int32_t humidity_mpercent(uint16_t raw);  // clamped to 0..100000

private:
    SensorResult<void> command(uint8_t cmd);

    I2cBus &bus_;
};

}  // namespace sensors
