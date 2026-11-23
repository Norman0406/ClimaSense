#include "ble/sightings.h"

#include <cstring>

namespace ble {

namespace {

bool same_eid(const Sighting &entry, const FhnFrame &frame)
{
    return entry.eid_len == frame.eid_len && std::memcmp(entry.eid.data(), frame.eid.data(), frame.eid_len) == 0;
}

void record(Sighting &entry, const FhnFrame &frame, int8_t rssi, uint32_t now_s)
{
    entry.type = frame.type;
    entry.flags = frame.flags;
    if (entry.count == 0 || entry.rssi == kRssiUnknown || (rssi != kRssiUnknown && rssi > entry.rssi)) {
        entry.rssi = rssi;
    }
    if (entry.count < UINT16_MAX) {
        ++entry.count;
    }
    entry.last_s = now_s;
}

}  // namespace

bool SightingTable::add(const FhnFrame &frame, int8_t rssi, uint32_t now_s)
{
    if (frame.eid_len == 0 || frame.eid_len > kMaxEidBytes) {
        return false;
    }
    Sighting *free_entry = nullptr;
    Sighting *stalest = nullptr;  // among those not heard in this window
    for (Sighting &entry : entries_) {
        if (entry.eid_len == 0) {
            if (free_entry == nullptr) {
                free_entry = &entry;
            }
        } else if (same_eid(entry, frame)) {
            const bool forgotten = now_s - entry.last_s >= kForgetAfterS;
            record(entry, frame, rssi, now_s);
            return forgotten;
        } else if (entry.count == 0 && (stalest == nullptr || entry.last_s < stalest->last_s)) {
            stalest = &entry;
        }
    }
    Sighting *target = free_entry != nullptr ? free_entry : stalest;
    if (target == nullptr) {
        ++dropped_;  // every entry was heard in this window: no room for another tag
        return false;
    }
    *target = Sighting{};
    target->eid = frame.eid;
    target->eid_len = frame.eid_len;
    record(*target, frame, rssi, now_s);
    return true;
}

void SightingTable::take_report(uint32_t now_s, Report &report)
{
    report.count = 0;
    report.window_s = now_s - window_start_s_;
    report.dropped = dropped_;
    for (Sighting &entry : entries_) {
        if (entry.eid_len == 0) {
            continue;
        }
        if (entry.count > 0) {
            report.heard[report.count++] = entry;
            entry.count = 0;
        }
        if (now_s - entry.last_s >= kForgetAfterS) {
            entry = Sighting{};
        }
    }
    window_start_s_ = now_s;
    dropped_ = 0;
}

}  // namespace ble
