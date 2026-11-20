#include "sensors/scd41.h"

#include <algorithm>
#include <array>

#include "sensors/sensirion.h"

namespace sensors {

namespace {

int32_t scale(uint16_t raw, int32_t offset_milli, int32_t span_milli)
{
    const int64_t scaled = (static_cast<int64_t>(span_milli) * raw + 65535 / 2) / 65535;
    return offset_milli + static_cast<int32_t>(scaled);
}

}  // namespace

int32_t Scd41::temperature_mc(uint16_t raw) { return scale(raw, -45'000, 175'000); }

int32_t Scd41::humidity_mpercent(uint16_t raw) { return scale(raw, 0, 100'000); }

SensorResult<void> Scd41::command(uint16_t cmd)
{
    const std::array<uint8_t, 2> tx{static_cast<uint8_t>(cmd >> 8), static_cast<uint8_t>(cmd & 0xFF)};
    return check(bus_.write(kAddress, tx));
}

SensorResult<void> Scd41::command_with_arg(uint16_t cmd, uint16_t arg)
{
    std::array<uint8_t, 5> tx{static_cast<uint8_t>(cmd >> 8), static_cast<uint8_t>(cmd & 0xFF)};
    sensirion::pack_word(arg, std::span<uint8_t, 3>(tx.data() + 2, 3));
    return check(bus_.write(kAddress, tx));
}

template <std::size_t N>
SensorResult<void> Scd41::read_words(uint16_t cmd, std::array<uint16_t, N> &words)
{
    if (auto r = command(cmd); !r) {
        return r;
    }
    delay_ms_(kCommandMs);
    std::array<uint8_t, 3 * N> rx{};
    if (auto r = check(bus_.read(kAddress, rx)); !r) {
        return r;
    }
    return sensirion::unpack_words<N>(rx, words);
}

SensorResult<void> Scd41::stop_periodic_measurement() { return command(kCmdStopPeriodic); }

SensorResult<uint64_t> Scd41::read_serial()
{
    std::array<uint16_t, 3> w{};
    if (auto r = read_words(kCmdGetSerialNumber, w); !r) {
        return std::unexpected(r.error());
    }
    return (static_cast<uint64_t>(w[0]) << 32) | (static_cast<uint64_t>(w[1]) << 16) | w[2];
}

SensorResult<bool> Scd41::automatic_self_calibration_enabled()
{
    std::array<uint16_t, 1> w{};
    if (auto r = read_words(kCmdGetAscEnabled, w); !r) {
        return std::unexpected(r.error());
    }
    return w[0] != 0;
}

SensorResult<void> Scd41::set_ambient_pressure(int32_t pressure_milli_pa)
{
    // The argument is in hPa (Pa / 100), rounded.
    const int32_t pa = std::clamp<int32_t>((pressure_milli_pa + 500) / 1000, kMinPressurePa, kMaxPressurePa);
    const auto hpa = static_cast<uint16_t>((pa + 50) / 100);
    if (auto r = command_with_arg(kCmdSetAmbientPressure, hpa); !r) {
        return r;
    }
    delay_ms_(kCommandMs);
    return {};
}

SensorResult<void> Scd41::start_single_shot() { return command(kCmdMeasureSingleShot); }

SensorResult<bool> Scd41::data_ready()
{
    std::array<uint16_t, 1> w{};
    if (auto r = read_words(kCmdGetDataReady, w); !r) {
        return std::unexpected(r.error());
    }
    return (w[0] & 0x07FF) != 0;
}

SensorResult<Scd41Reading> Scd41::read_measurement()
{
    std::array<uint16_t, 3> w{};
    if (auto r = read_words(kCmdReadMeasurement, w); !r) {
        return std::unexpected(r.error());
    }
    return Scd41Reading{w[0], temperature_mc(w[1]), humidity_mpercent(w[2])};
}

}  // namespace sensors
