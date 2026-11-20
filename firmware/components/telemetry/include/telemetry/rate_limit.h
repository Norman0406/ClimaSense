// At most N events per window (fixed windows). Pure, tested on the PC. Keeps a fault that logs in a
// loop from flooding the broker with log messages.
#pragma once

#include <cstdint>

namespace telemetry {

class RateLimiter {
public:
    RateLimiter(uint32_t max_per_window, uint32_t window_s) : max_(max_per_window), window_s_(window_s) {}

    // True if one more event may go out now.
    bool allow(uint32_t now_s)
    {
        if (!started_ || now_s - window_start_ >= window_s_) {
            started_ = true;
            window_start_ = now_s;
            count_ = 0;
        }
        if (count_ < max_) {
            ++count_;
            return true;
        }
        return false;
    }

private:
    uint32_t max_;
    uint32_t window_s_;
    bool started_ = false;
    uint32_t window_start_ = 0;
    uint32_t count_ = 0;
};

}  // namespace telemetry
