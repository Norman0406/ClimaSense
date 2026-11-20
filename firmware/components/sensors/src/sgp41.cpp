#include "sensors/sgp41.h"

#include <algorithm>
#include <array>
#include <span>

#include "sensors/sensirion.h"

namespace sensors {

namespace {

// round(value * 65535 / span), clamped to 0..65535; value and span in milli-units.
uint16_t to_ticks(int64_t value, int64_t span)
{
    const int64_t ticks = (value * 65535 + span / 2) / span;
    return static_cast<uint16_t>(std::clamp<int64_t>(ticks, 0, 65535));
}

}  // namespace

uint16_t Sgp41::humidity_ticks(int32_t humidity_mpercent)
{
    return to_ticks(std::max<int32_t>(humidity_mpercent, 0), 100'000);
}

uint16_t Sgp41::temperature_ticks(int32_t temperature_mc)
{
    return to_ticks(std::max<int64_t>(static_cast<int64_t>(temperature_mc) + 45'000, 0), 175'000);
}

SensorResult<void> Sgp41::command_with_args(uint16_t cmd, uint16_t humidity_ticks, uint16_t temperature_ticks)
{
    std::array<uint8_t, 8> tx{static_cast<uint8_t>(cmd >> 8), static_cast<uint8_t>(cmd & 0xFF)};
    sensirion::pack_word(humidity_ticks, std::span<uint8_t, 3>(tx.data() + 2, 3));
    sensirion::pack_word(temperature_ticks, std::span<uint8_t, 3>(tx.data() + 5, 3));
    return check(bus_.write(kAddress, tx));
}

SensorResult<void> Sgp41::start_conditioning(uint16_t humidity_ticks, uint16_t temperature_ticks)
{
    return command_with_args(kCmdConditioning, humidity_ticks, temperature_ticks);
}

SensorResult<uint16_t> Sgp41::read_conditioning()
{
    std::array<uint8_t, 3> rx{};
    if (auto r = check(bus_.read(kAddress, rx)); !r) {
        return std::unexpected(r.error());
    }
    std::array<uint16_t, 1> w{};
    if (auto r = sensirion::unpack_words<1>(rx, w); !r) {
        return std::unexpected(r.error());
    }
    return w[0];
}

SensorResult<void> Sgp41::start_measurement(uint16_t humidity_ticks, uint16_t temperature_ticks)
{
    return command_with_args(kCmdMeasureRaw, humidity_ticks, temperature_ticks);
}

SensorResult<Sgp41Raw> Sgp41::read_measurement()
{
    std::array<uint8_t, 6> rx{};
    if (auto r = check(bus_.read(kAddress, rx)); !r) {
        return std::unexpected(r.error());
    }
    std::array<uint16_t, 2> w{};
    if (auto r = sensirion::unpack_words<2>(rx, w); !r) {
        return std::unexpected(r.error());
    }
    return Sgp41Raw{w[0], w[1]};
}

SensorResult<void> Sgp41::request_serial()
{
    const std::array<uint8_t, 2> tx{static_cast<uint8_t>(kCmdGetSerialNumber >> 8),
                                    static_cast<uint8_t>(kCmdGetSerialNumber & 0xFF)};
    return check(bus_.write(kAddress, tx));
}

SensorResult<uint64_t> Sgp41::read_serial()
{
    std::array<uint8_t, 9> rx{};
    if (auto r = check(bus_.read(kAddress, rx)); !r) {
        return std::unexpected(r.error());
    }
    std::array<uint16_t, 3> w{};
    if (auto r = sensirion::unpack_words<3>(rx, w); !r) {
        return std::unexpected(r.error());
    }
    return (static_cast<uint64_t>(w[0]) << 32) | (static_cast<uint64_t>(w[1]) << 16) | w[2];
}

}  // namespace sensors
