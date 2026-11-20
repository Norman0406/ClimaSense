#include "sensors/bmp580.h"

#include <array>

namespace sensors {

namespace {

uint32_t le24(const uint8_t *p)
{
    return static_cast<uint32_t>(p[0]) | (static_cast<uint32_t>(p[1]) << 8) | (static_cast<uint32_t>(p[2]) << 16);
}

}  // namespace

int32_t Bmp580::temperature_mc(uint32_t raw24)
{
    // Sign-extend the 24-bit value, then raw * 1000 / 65536, rounded half away from zero.
    const int32_t raw = (raw24 & 0x800000u) ? static_cast<int32_t>(raw24 | 0xFF000000u)
                                            : static_cast<int32_t>(raw24 & 0x00FFFFFFu);
    const int64_t scaled = static_cast<int64_t>(raw) * 1000;
    return static_cast<int32_t>((scaled + (scaled >= 0 ? 32768 : -32768)) / 65536);
}

int32_t Bmp580::pressure_milli_pa(uint32_t raw24)
{
    // raw / 64 Pa = raw * 1000 / 64 mPa = raw * 125 / 8 mPa, rounded.
    const int64_t scaled = static_cast<int64_t>(raw24 & 0x00FFFFFFu) * 125;
    return static_cast<int32_t>((scaled + 4) / 8);
}

SensorResult<void> Bmp580::write_reg(uint8_t reg, uint8_t value)
{
    const std::array<uint8_t, 2> tx{reg, value};
    return check(bus_.write(kAddress, tx));
}

SensorResult<uint8_t> Bmp580::read_reg(uint8_t reg)
{
    const std::array<uint8_t, 1> tx{reg};
    std::array<uint8_t, 1> rx{};
    if (auto r = check(bus_.write_read(kAddress, tx, rx)); !r) {
        return std::unexpected(r.error());
    }
    return rx[0];
}

SensorResult<void> Bmp580::soft_reset() { return write_reg(kRegCmd, kCmdSoftReset); }

SensorResult<uint8_t> Bmp580::check_after_reset()
{
    const auto chip_id = read_reg(kRegChipId);
    if (!chip_id) {
        return std::unexpected(chip_id.error());
    }
    if (*chip_id != kChipIdA && *chip_id != kChipIdB) {
        return std::unexpected(SensorError::UnexpectedId);
    }
    // Reading INT_STATUS also clears it.
    const auto int_status = read_reg(kRegIntStatus);
    if (!int_status) {
        return std::unexpected(int_status.error());
    }
    if ((*int_status & kIntStatusResetDone) == 0) {
        return std::unexpected(SensorError::NotReady);
    }
    const auto status = read_reg(kRegStatus);
    if (!status) {
        return std::unexpected(status.error());
    }
    if ((*status & kStatusNvmReady) == 0 || (*status & kStatusNvmError) != 0) {
        return std::unexpected(SensorError::NotReady);
    }
    return *chip_id;
}

SensorResult<void> Bmp580::configure()
{
    if (auto r = write_reg(kRegOsrConfig, kOsrConfig); !r) {
        return r;
    }
    // Keep the rate bits as they are (unused in forced mode), select standby and disable deep
    // standby, which would otherwise be entered from standby.
    const auto odr = read_reg(kRegOdrConfig);
    if (!odr) {
        return std::unexpected(odr.error());
    }
    odr_config_ = static_cast<uint8_t>((*odr & kOdrRateMask) | kOdrDeepStandbyDisabled);
    return write_reg(kRegOdrConfig, odr_config_);
}

SensorResult<void> Bmp580::start_measurement()
{
    // From standby (where the sensor returns after every forced measurement) to forced.
    return write_reg(kRegOdrConfig, static_cast<uint8_t>(odr_config_ | kOdrForced));
}

SensorResult<Bmp580Reading> Bmp580::read_measurement()
{
    const auto odr = read_reg(kRegOdrConfig);
    if (!odr) {
        return std::unexpected(odr.error());
    }
    if ((*odr & kOdrPowerModeMask) != 0) {
        return std::unexpected(SensorError::NotReady);  // still measuring
    }
    const std::array<uint8_t, 1> tx{kRegTempData};
    std::array<uint8_t, 6> rx{};
    if (auto r = check(bus_.write_read(kAddress, tx, rx)); !r) {
        return std::unexpected(r.error());
    }
    return Bmp580Reading{temperature_mc(le24(&rx[0])), pressure_milli_pa(le24(&rx[3]))};
}

}  // namespace sensors
