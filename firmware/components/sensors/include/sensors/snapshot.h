// What the sensor task hands over for publishing: the readings since the last snapshot, condensed.
// Pure, tested on the PC. The sensor task adds every reading; the app task takes a snapshot once
// per publish interval, which starts the next window (docs/firmware/architecture.md, "Handover").
#pragma once

#include <cstdint>
#include <optional>

namespace sensors {

// Integer mean, rounded half away from zero.
class Mean {
public:
    void add(int32_t value)
    {
        sum_ += value;
        ++count_;
    }
    std::optional<int32_t> value() const
    {
        if (count_ == 0) {
            return std::nullopt;
        }
        const int64_t half = count_ / 2;
        const int64_t rounded = sum_ >= 0 ? (sum_ + half) / count_ : (sum_ - half) / count_;
        return static_cast<int32_t>(rounded);
    }
    uint32_t count() const { return count_; }

private:
    int64_t sum_ = 0;
    uint32_t count_ = 0;
};

// Fields are empty when there is nothing to report: no reading in the window, a CO2 value too old,
// or a gas index still in its start-up blackout. A consumer leaves them out instead of sending 0.
struct SensorSnapshot {
    std::optional<int32_t> temperature_mc;     // mean, SHT45
    std::optional<int32_t> humidity_mpercent;  // mean, SHT45
    std::optional<int32_t> pressure_milli_pa;  // mean, BMP580
    std::optional<uint16_t> co2_ppm;           // latest SCD41 single shot
    std::optional<uint32_t> co2_age_s;         // its age: the only value older than the window
    std::optional<int32_t> voc_index;          // latest in the window
    std::optional<int32_t> nox_index;          // latest in the window
    uint32_t sht45_samples = 0;
    uint32_t bmp580_samples = 0;
};

class SnapshotBuilder {
public:
    // A CO2 value older than this is not reported: two 5-minute shots missed in a row.
    static constexpr uint32_t kCo2MaxAgeS = 11 * 60;

    void add_temperature_humidity(int32_t temperature_mc, int32_t humidity_mpercent)
    {
        temperature_.add(temperature_mc);
        humidity_.add(humidity_mpercent);
    }
    void add_pressure(int32_t pressure_milli_pa) { pressure_.add(pressure_milli_pa); }
    void set_co2(uint16_t ppm, uint32_t now_s)
    {
        co2_ = ppm;
        co2_time_s_ = now_s;
    }
    // Index 0 means "still starting" and is not reported.
    void set_gas_index(int32_t voc, int32_t nox)
    {
        voc_ = voc > 0 ? std::optional<int32_t>(voc) : std::nullopt;
        nox_ = nox > 0 ? std::optional<int32_t>(nox) : std::nullopt;
    }

    // The window's values; starts the next window. CO2 carries over between windows (it comes only
    // every 5 minutes), the rest does not.
    SensorSnapshot take(uint32_t now_s)
    {
        SensorSnapshot s;
        s.temperature_mc = temperature_.value();
        s.humidity_mpercent = humidity_.value();
        s.pressure_milli_pa = pressure_.value();
        s.sht45_samples = temperature_.count();
        s.bmp580_samples = pressure_.count();
        if (co2_ && now_s - co2_time_s_ <= kCo2MaxAgeS) {
            s.co2_ppm = co2_;
            s.co2_age_s = now_s - co2_time_s_;
        }
        s.voc_index = voc_;
        s.nox_index = nox_;

        temperature_ = {};
        humidity_ = {};
        pressure_ = {};
        voc_.reset();
        nox_.reset();
        return s;
    }

private:
    Mean temperature_;
    Mean humidity_;
    Mean pressure_;
    std::optional<uint16_t> co2_;
    uint32_t co2_time_s_ = 0;
    std::optional<int32_t> voc_;
    std::optional<int32_t> nox_;
};

}  // namespace sensors
