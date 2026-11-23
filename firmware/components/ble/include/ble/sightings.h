// Which Find Hub tags were heard, and how well. Pure, tested on the PC.
//
// A fixed table of the identifiers (EIDs) heard recently. The scanner adds every frame; the app
// task takes a report once per interval, which lists what was heard since the last report and
// starts the next window. An EID stays known for kForgetAfterS after it was last heard, so the
// table can tell a tag that just came into range (worth a message at once) from one that has
// been around.
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>

#include "ble/fhn_frame.h"

namespace ble {

// Tags in range at once. A report with all of them is about 2.6 KB of JSON, which fits the MQTT
// client's 4 KB buffer.
inline constexpr std::size_t kMaxSightings = 24;

// An EID not heard for this long is forgotten; heard again, it counts as new.
inline constexpr uint32_t kForgetAfterS = 120;

inline constexpr int8_t kRssiUnknown = 127;  // as the Bluetooth controller reports it

struct Sighting {
    std::array<uint8_t, kMaxEidBytes> eid{};
    uint8_t eid_len = 0;           // 0: free table entry
    uint8_t type = 0;              // frame type of the latest frame
    std::optional<uint8_t> flags;  // hashed flags of the latest frame
    int8_t rssi = kRssiUnknown;    // strongest in the window, dBm
    uint16_t count = 0;            // frames in the window
    uint32_t last_s = 0;           // when last heard (uptime)

    std::span<const uint8_t> eid_bytes() const { return {eid.data(), eid_len}; }
};

struct Report {
    std::array<Sighting, kMaxSightings> heard{};
    std::size_t count = 0;   // entries used in `heard`
    uint32_t window_s = 0;   // how long the window was
    uint32_t dropped = 0;    // frames of further tags that found no room in the table
};

class SightingTable {
public:
    // Records a frame. True if its EID was not known: never heard, or forgotten since.
    bool add(const FhnFrame &frame, int8_t rssi, uint32_t now_s);

    // Fills `report` with what was heard since the last report; starts the next window and
    // forgets EIDs not heard for kForgetAfterS. (Filled in place: a report is about 1 KB, much
    // for a task's stack.)
    void take_report(uint32_t now_s, Report &report);

private:
    std::array<Sighting, kMaxSightings> entries_{};
    uint32_t window_start_s_ = 0;
    uint32_t dropped_ = 0;
};

}  // namespace ble
