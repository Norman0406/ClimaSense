// When the sensor task switches the sensor rail off and on to recover a hung sensor or bus
// (docs/firmware/architecture.md). Pure, tested on the PC.
//
// A sensor counts as stuck after kStuckReadings failed readings in a row (kStuckShots for the
// SCD41, which measures every 5 minutes), and the bus when it could not be opened. The first
// recovery comes at once; each further one waits for a pause that doubles, from 2 minutes up to
// 4 hours, so that a sensor that is broken for good does not cost the others a restart every few
// seconds. Once every sensor has worked for an hour, the pause starts at 2 minutes again.
#pragma once

#include <algorithm>
#include <cstdint>

namespace sensors {

class RailRecovery {
public:
    static constexpr uint32_t kStuckReadings = 10;  // SHT45, BMP580, SGP41: 10 s at 1 Hz
    static constexpr uint32_t kStuckShots = 2;      // SCD41: two shots, up to 10 minutes
    static constexpr uint32_t kFirstPauseS = 2 * 60;
    static constexpr uint32_t kMaxPauseS = 4 * 3600;
    static constexpr uint32_t kSettledS = 3600;

    // Call once a tick. `stuck`: a sensor or the bus counts as stuck. `all_working`: no sensor
    // is failing at the moment. True: recover now.
    bool due(uint32_t now_s, bool stuck, bool all_working)
    {
        if (!all_working) {
            working_ = false;
        } else if (!working_) {
            working_ = true;
            working_since_s_ = now_s;
        } else if (now_s - working_since_s_ >= kSettledS) {
            pause_s_ = kFirstPauseS;
        }

        if (!stuck || (count_ > 0 && static_cast<int32_t>(now_s - next_allowed_s_) < 0)) {
            return false;
        }
        ++count_;
        next_allowed_s_ = now_s + pause_s_;
        pause_s_ = std::min(pause_s_ * 2, kMaxPauseS);
        return true;
    }

    // Recoveries since start.
    uint32_t count() const { return count_; }
    // The earliest time (in the caller's seconds) of the next recovery, valid once count() > 0.
    uint32_t next_allowed_s() const { return next_allowed_s_; }

private:
    uint32_t count_ = 0;
    uint32_t next_allowed_s_ = 0;
    uint32_t pause_s_ = kFirstPauseS;
    bool working_ = false;
    uint32_t working_since_s_ = 0;
};

}  // namespace sensors
