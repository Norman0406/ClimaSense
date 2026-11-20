// Pause before the next Wi-Fi connection attempt: 1 s, 2 s, 4 s ... up to 60 s, back to 1 s
// once connected. Keeps the radio (and its heat) quiet while the router is away. Pure, tested
// on the PC.
#pragma once

#include <algorithm>
#include <cstdint>

namespace net {

class ReconnectBackoff {
public:
    static constexpr uint32_t kFirstMs = 1'000;
    static constexpr uint32_t kMaxMs = 60'000;

    // The pause before the next attempt; each call doubles the following one.
    uint32_t next_ms()
    {
        const uint32_t delay = current_;
        current_ = std::min(current_ * 2, kMaxMs);
        return delay;
    }

    void reset() { current_ = kFirstMs; }

private:
    uint32_t current_ = kFirstMs;
};

}  // namespace net
