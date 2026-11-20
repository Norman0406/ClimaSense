// Sensirion SCD41 CO2 sensor (with its own temperature and humidity). Pure logic on top of
// I2cBus, tested on the PC.
//
// Used in single-shot mode every 5 minutes: the interval for which its automatic
// self-calibration (on by default) is tuned. Commands are 16-bit words; responses and
// arguments are Sensirion words with CRC (sensirion.h). Commands that take 1 ms before the
// response can be read wait through the delay function passed in; the long waits (stop:
// 500 ms, single shot: 5 s) are left to the caller, which must not block for them.
// Commands and waits from Sensirion's embedded-i2c-scd4x driver.
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "sensors/i2c_bus.h"
#include "sensors/sensor_error.h"

namespace sensors {

struct Scd41Reading {
    uint16_t co2_ppm;
    int32_t temperature_mc;     // the SCD41's own; it runs warm, the SHT45 is the room's
    int32_t humidity_mpercent;
};

class Scd41 {
public:
    using DelayMs = void (*)(uint32_t ms);

    static constexpr uint8_t kAddress = 0x62;

    static constexpr uint16_t kCmdStopPeriodic = 0x3F86;
    static constexpr uint16_t kCmdMeasureSingleShot = 0x219D;
    static constexpr uint16_t kCmdGetDataReady = 0xE4B8;
    static constexpr uint16_t kCmdReadMeasurement = 0xEC05;
    static constexpr uint16_t kCmdSetAmbientPressure = 0xE000;
    static constexpr uint16_t kCmdGetSerialNumber = 0x3682;
    static constexpr uint16_t kCmdGetAscEnabled = 0x2313;

    static constexpr uint32_t kCommandMs = 1;        // before a response can be read
    static constexpr uint32_t kStopMs = 500;         // after stop_periodic_measurement()
    static constexpr uint32_t kSingleShotMs = 5000;  // after start_single_shot()

    // Range the SCD41 accepts for pressure compensation.
    static constexpr int32_t kMinPressurePa = 70'000;
    static constexpr int32_t kMaxPressurePa = 120'000;

    Scd41(I2cBus &bus, DelayMs delay_ms) : bus_(bus), delay_ms_(delay_ms) {}

    // Leaves periodic mode if the sensor is in it (it keeps running across an ESP32 reset while
    // its supply stays on). Harmless when it is idle. Then wait kStopMs before the next command.
    SensorResult<void> stop_periodic_measurement();

    SensorResult<uint64_t> read_serial();  // 48 bits
    SensorResult<bool> automatic_self_calibration_enabled();

    // Pressure compensation for the next measurements. Clamped to the range the sensor accepts.
    SensorResult<void> set_ambient_pressure(int32_t pressure_milli_pa);

    // Single shot: start_single_shot(), wait kSingleShotMs (without blocking), then
    // data_ready() and read_measurement().
    SensorResult<void> start_single_shot();
    SensorResult<bool> data_ready();
    SensorResult<Scd41Reading> read_measurement();

    // Datasheet conversions, rounded to the nearest milli-unit.
    static int32_t temperature_mc(uint16_t raw);     // -45 + 175 * raw / 65535
    static int32_t humidity_mpercent(uint16_t raw);  // 100 * raw / 65535

private:
    SensorResult<void> command(uint16_t cmd);
    SensorResult<void> command_with_arg(uint16_t cmd, uint16_t arg);
    template <std::size_t N>
    SensorResult<void> read_words(uint16_t cmd, std::array<uint16_t, N> &words);

    I2cBus &bus_;
    DelayMs delay_ms_;
};

}  // namespace sensors
