// Keeping the VOC algorithm's learned baseline across software resets, so the VOC index does not
// start learning the room again after every update, crash or settings change. Pure, tested on the PC.
//
// Sensirion's rules (sensirion_gas_index_algorithm.h): the state may be saved once the algorithm
// has run for 3 hours, and restored only after an interruption of at most 10 minutes. NOx has
// no saved state; it learns again after each reboot.
//
// The sensor task keeps a copy in RTC memory, written every second: it survives a software reset
// (update, crash, watchdog, restart after saving settings), not a power cut, and is restored at
// once at start. After a power cut the algorithm learns again.
#pragma once

#include <cstdint>
#include <optional>
#include <type_traits>

#include "sensors/gas_index.h"

namespace sensors {

inline constexpr uint32_t kVocMatureSamples = 3 * 3600;  // 3 h of 1 s samples
inline constexpr int64_t kVocMaxGapS = 10 * 60;

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

private:
    uint32_t samples_ = 0;
};

}  // namespace sensors
