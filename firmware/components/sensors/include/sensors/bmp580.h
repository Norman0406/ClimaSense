// Bosch BMP580 pressure sensor. Pure logic on top of I2cBus, tested on the PC.
//
// Register-based (write the register address, repeated start, read), no checksums. Used in
// forced mode: one measurement per start_measurement(), after which the sensor returns to
// standby by itself; read_measurement() checks that before reading the data. As with the
// SHT45, the caller waits between the calls. Registers, values and sequences are taken from
// Bosch's BMP5_SensorAPI (bmp5_defs.h, bmp5.c).
#pragma once

#include <cstdint>

#include "sensors/i2c_bus.h"
#include "sensors/sensor_error.h"

namespace sensors {

struct Bmp580Reading {
    int32_t temperature_mc;     // milli-degrees Celsius (die temperature, not the room's)
    int32_t pressure_milli_pa;  // milli-pascal (101325000 = 1013.25 hPa)
};

class Bmp580 {
public:
    static constexpr uint8_t kAddress = 0x47;  // SDO tied high on the board

    // Registers
    static constexpr uint8_t kRegChipId = 0x01;
    static constexpr uint8_t kRegTempData = 0x1D;  // 3 bytes temperature, then 3 bytes pressure
    static constexpr uint8_t kRegIntStatus = 0x27;
    static constexpr uint8_t kRegStatus = 0x28;
    static constexpr uint8_t kRegOsrConfig = 0x36;
    static constexpr uint8_t kRegOdrConfig = 0x37;
    static constexpr uint8_t kRegCmd = 0x7E;

    // Values
    static constexpr uint8_t kChipIdA = 0x50;  // Bosch's API accepts both IDs of the BMP58x family
    static constexpr uint8_t kChipIdB = 0x51;
    static constexpr uint8_t kCmdSoftReset = 0xB6;
    static constexpr uint8_t kIntStatusResetDone = 0x10;  // power-on / soft reset complete
    static constexpr uint8_t kStatusNvmReady = 0x02;
    static constexpr uint8_t kStatusNvmError = 0x04;
    static constexpr uint8_t kOdrPowerModeMask = 0x03;    // 0 standby, 1 normal, 2 forced
    static constexpr uint8_t kOdrForced = 0x02;
    static constexpr uint8_t kOdrRateMask = 0x7C;
    static constexpr uint8_t kOdrDeepStandbyDisabled = 0x80;

    // Pressure enabled, pressure oversampling 16x (4 << 3), temperature 2x (1).
    static constexpr uint8_t kOsrConfig = 0x40 | (4 << 3) | 1;

    static constexpr uint32_t kResetMs = 3;     // 2 ms in Bosch's API
    static constexpr uint32_t kMeasureMs = 40;  // generous; read_measurement() checks completion

    explicit Bmp580(I2cBus &bus) : bus_(bus) {}

    // Start-up: soft_reset(), wait kResetMs, check_after_reset(), configure().
    SensorResult<void> soft_reset();
    // Checks the chip ID, that the reset completed and that the calibration memory (NVM) is
    // ready without error. Returns the chip ID.
    SensorResult<uint8_t> check_after_reset();
    // Sets oversampling and puts the sensor in standby (deep standby disabled).
    SensorResult<void> configure();

    // Measurement: start_measurement(), wait kMeasureMs, read_measurement().
    // read_measurement() gives SensorError::NotReady while the sensor is still measuring.
    SensorResult<void> start_measurement();
    SensorResult<Bmp580Reading> read_measurement();

    // Conversions (Bosch's API: temperature raw / 2^16 degrees C, pressure raw / 2^6 Pa).
    static int32_t temperature_mc(uint32_t raw24);       // raw24 is 24-bit two's complement
    static int32_t pressure_milli_pa(uint32_t raw24);

private:
    SensorResult<void> write_reg(uint8_t reg, uint8_t value);
    SensorResult<uint8_t> read_reg(uint8_t reg);

    I2cBus &bus_;
    uint8_t odr_config_ = kOdrDeepStandbyDisabled;  // ODR_CONFIG in standby, as written by configure()
};

}  // namespace sensors
