// Sensirion SGP41 VOC and NOx sensor. Pure logic on top of I2cBus, tested on the PC.
//
// Delivers raw signals; GasIndex (gas_index.h) turns them into the VOC and NOx index. Must be
// read once a second without gaps, each time with the current humidity and temperature for
// compensation. After power-up it needs conditioning: for the first 10 s, the conditioning
// command instead of the measurement (never longer, the datasheet warns it can damage the
// sensor). As with the SHT45, each command and its read are separate calls; the caller waits
// kCommandMs in between. Commands, arguments and waits from Sensirion's embedded-i2c-sgp41
// driver.
#pragma once

#include <cstdint>

#include "sensors/i2c_bus.h"
#include "sensors/sensor_error.h"

namespace sensors {

struct Sgp41Raw {
    uint16_t voc;
    uint16_t nox;
};

class Sgp41 {
public:
    static constexpr uint8_t kAddress = 0x59;

    static constexpr uint16_t kCmdConditioning = 0x2612;
    static constexpr uint16_t kCmdMeasureRaw = 0x2619;
    static constexpr uint16_t kCmdGetSerialNumber = 0x3682;

    static constexpr uint32_t kCommandMs = 50;  // conditioning and measurement
    static constexpr uint32_t kSerialMs = 1;
    static constexpr uint32_t kConditioningSeconds = 10;

    // Compensation values when no humidity/temperature reading is available: 50 %RH, 25 C.
    static constexpr uint16_t kDefaultHumidityTicks = 0x8000;
    static constexpr uint16_t kDefaultTemperatureTicks = 0x6666;

    explicit Sgp41(I2cBus &bus) : bus_(bus) {}

    // Compensation arguments: the inverse of the SHT4x conversion formulas, clamped.
    static uint16_t humidity_ticks(int32_t humidity_mpercent);   // 0..100 % -> 0..65535
    static uint16_t temperature_ticks(int32_t temperature_mc);   // -45..130 C -> 0..65535

    // Conditioning (first 10 s): start_conditioning(), wait kCommandMs, read_conditioning().
    SensorResult<void> start_conditioning(uint16_t humidity_ticks, uint16_t temperature_ticks);
    SensorResult<uint16_t> read_conditioning();  // raw VOC signal, not used for the index

    // Measurement: start_measurement(), wait kCommandMs, read_measurement().
    SensorResult<void> start_measurement(uint16_t humidity_ticks, uint16_t temperature_ticks);
    SensorResult<Sgp41Raw> read_measurement();

    // Serial number: request_serial(), wait kSerialMs, read_serial().
    SensorResult<void> request_serial();
    SensorResult<uint64_t> read_serial();  // 48 bits

private:
    SensorResult<void> command_with_args(uint16_t cmd, uint16_t humidity_ticks, uint16_t temperature_ticks);

    I2cBus &bus_;
};

}  // namespace sensors
