// The last resort when the device stays offline: a restart after an hour without the connection
// it is set up for (the MQTT broker if one is set, else the Wi-Fi network). Reconnecting is
// normally done by the Wi-Fi station and the MQTT client themselves (net/backoff.h); this only
// catches a network stack or driver that has stopped trying. A device whose router is off for
// longer restarts once an hour, which costs nothing: it has nowhere to send its values, and the
// VOC baseline survives the restart. Pure, tested on the PC.
#pragma once

#include <cstdint>

namespace net {

class OfflineGuard {
public:
    static constexpr uint32_t kRestartAfterS = 60 * 60;

    // Call regularly. `online`: connected as configured, or nothing configured to connect to
    // (ota::trial_healthy). `paused`: the setup portal is open or an update runs, which is not a
    // time to restart and counts as online. True: restart now.
    bool restart_due(uint32_t uptime_s, bool online, bool paused)
    {
        if (online || paused) {
            last_online_s_ = uptime_s;
            return false;
        }
        return uptime_s - last_online_s_ >= kRestartAfterS;
    }

private:
    uint32_t last_online_s_ = 0;
};

}  // namespace net
