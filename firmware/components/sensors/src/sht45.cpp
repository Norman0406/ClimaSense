#include "sensors/sht45.h"

#include <algorithm>
#include <array>

#include "sensors/sensirion.h"

namespace sensors {

namespace {

// value = offset + span * raw / 65535, in milli-units, rounded to nearest.
int32_t scale(uint16_t raw, int32_t offset_milli, int32_t span_milli)
{
    const int64_t scaled = (static_cast<int64_t>(span_milli) * raw + 65535 / 2) / 65535;
    return offset_milli + static_cast<int32_t>(scaled);
}

}  // namespace

int32_t Sht45::temperature_mc(uint16_t raw) { return scale(raw, -45'000, 175'000); }

int32_t Sht45::humidity_mpercent(uint16_t raw)
{
    // The formula gives -6..119 %; values outside 0..100 % are physically meaningless and,
    // per the datasheet, are to be clamped.
    // Type named explicitly: int32_t is long on the ESP32 but int on the PC.
    return std::clamp<int32_t>(scale(raw, -6'000, 125'000), 0, 100'000);
}

SensorResult<void> Sht45::command(uint8_t cmd)
{
    const std::array<uint8_t, 1> tx{cmd};
    return check(bus_.write(kAddress, tx));
}

SensorResult<void> Sht45::soft_reset() { return command(kCmdSoftReset); }

SensorResult<void> Sht45::request_serial() { return command(kCmdReadSerial); }

SensorResult<uint32_t> Sht45::read_serial()
{
    std::array<uint8_t, 6> rx{};
    if (auto r = check(bus_.read(kAddress, rx)); !r) {
        return std::unexpected(r.error());
    }
    std::array<uint16_t, 2> words{};
    if (auto r = sensirion::unpack_words<2>(rx, words); !r) {
        return std::unexpected(r.error());
    }
    return (static_cast<uint32_t>(words[0]) << 16) | words[1];
}

SensorResult<void> Sht45::start_measurement() { return command(kCmdMeasureHighPrecision); }

SensorResult<Sht45Reading> Sht45::read_measurement()
{
    std::array<uint8_t, 6> rx{};
    if (auto r = check(bus_.read(kAddress, rx)); !r) {
        return std::unexpected(r.error());
    }
    std::array<uint16_t, 2> words{};
    if (auto r = sensirion::unpack_words<2>(rx, words); !r) {
        return std::unexpected(r.error());
    }
    return Sht45Reading{temperature_mc(words[0]), humidity_mpercent(words[1])};
}

}  // namespace sensors
