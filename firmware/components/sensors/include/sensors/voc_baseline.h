// Keeping the VOC algorithm's learned baseline across reboots, so the VOC index does not start
// learning the room again after every update, crash or power cut. Pure, tested on the PC.
//
// Sensirion's rules (sensirion_gas_index_algorithm.h): the state may be saved once the algorithm
// has run for 3 hours, and restored only after an interruption of at most 10 minutes. NOx has
// no saved state; it learns again after each reboot.
//
// The sensor task keeps two copies:
// - in RTC memory, written every second: survives a software reset (update, crash, watchdog,
//   restart after saving settings), not a power cut. Restored at once at start.
// - in flash (NVS), written every 5 minutes together with the wall-clock time: survives a power
//   cut. Restored once the clock is set, if it was written at most 10 minutes before.
#pragma once

#include <cstdint>
#include <optional>
#include <type_traits>

#include "sensors/gas_index.h"

namespace sensors {

inline constexpr uint32_t kVocMatureSamples = 3 * 3600;  // 3 h of 1 s samples
inline constexpr int64_t kVocMaxGapS = 10 * 60;
inline constexpr int64_t kVocFlashSaveS = 5 * 60;
// A wall-clock time before this (2026-01-01 00:00 UTC) means the clock has not been set yet.
inline constexpr int64_t kClockValidFromUnixS = 1'767'225'600;

constexpr bool clock_valid(int64_t unix_s) { return unix_s >= kClockValidFromUnixS; }

// A state the algorithm can have produced: both values positive.
constexpr bool plausible(const GasIndexState &s) { return s.mean > 0 && s.std > 0; }

// The copy in RTC memory. After some resets RTC memory holds garbage that can look valid, so it
// carries a magic number and a checksum. Plain words without initialisers: a constructor would
// clear it at every start, before the firmware could read it.
struct RtcVocBaseline {
    uint32_t magic;
    int32_t mean;
    int32_t std;
    uint32_t check;
};
static_assert(std::is_trivially_default_constructible_v<RtcVocBaseline>);

RtcVocBaseline seal(const GasIndexState &state);
// The state, if the copy is intact and plausible.
std::optional<GasIndexState> unseal(const RtcVocBaseline &copy);

// The copy in flash, with the wall-clock time it was written. Stored as it is in memory; a copy of
// another size (from a firmware with another layout) is ignored.
struct FlashVocBaseline {
    GasIndexState state;
    int64_t saved_unix_s = 0;
};
static_assert(sizeof(FlashVocBaseline) == 16);

// Whether a flash copy may be restored at `now_unix_s`: the clock is set, the copy is plausible
// and was written at most kVocMaxGapS before (and not in the future).
bool restorable(const FlashVocBaseline &copy, int64_t now_unix_s);

// Counts how long the algorithm has been learning, and says when its state may be kept.
class VocBaselineKeeper {
public:
    // One sample processed by the VOC algorithm.
    void sample()
    {
        if (samples_ < kVocMatureSamples) {
            ++samples_;
        }
    }

    // The algorithm continues from a saved state: it is as good as one that ran for 3 hours.
    void restored() { samples_ = kVocMatureSamples; }

    // The state may be saved (3 hours of learning, or restored from a saved one).
    bool mature() const { return samples_ >= kVocMatureSamples; }

    // Whether to write the flash copy now: mature, the clock set, and kVocFlashSaveS since the
    // last write (or none yet).
    bool flash_save_due(int64_t now_unix_s) const
    {
        if (!mature() || !clock_valid(now_unix_s)) {
            return false;
        }
        return !flash_saved_ || now_unix_s - last_flash_save_s_ >= kVocFlashSaveS || now_unix_s < last_flash_save_s_;
    }

    void flash_saved(int64_t now_unix_s)
    {
        flash_saved_ = true;
        last_flash_save_s_ = now_unix_s;
    }

private:
    uint32_t samples_ = 0;
    bool flash_saved_ = false;
    int64_t last_flash_save_s_ = 0;
};

}  // namespace sensors
