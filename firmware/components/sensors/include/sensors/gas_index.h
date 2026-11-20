// C++ wrapper around Sensirion's Gas Index Algorithm (vendor/gas_index_algorithm, fixed-point
// variant, unchanged). One instance per signal: VOC or NOx. Pure, tested on the PC.
#pragma once

#include <cstdint>

extern "C" {
#include "sensirion_gas_index_algorithm.h"
}

namespace sensors {

class GasIndex {
public:
    enum class Kind : uint8_t { Voc, Nox };

    // The algorithm's start-up blackout: index 0 for the first samples after a (re)start.
    static constexpr uint32_t kBlackoutSamples = 46;

    explicit GasIndex(Kind kind)
    {
        GasIndexAlgorithm_init(&params_, kind == Kind::Voc ? GasIndexAlgorithm_ALGORITHM_TYPE_VOC
                                                           : GasIndexAlgorithm_ALGORITHM_TYPE_NOX);
    }

    // Feeds one raw sample; call exactly once per second. Returns 0 during the blackout, then the
    // index: VOC 1..500 (100 = the room's usual), NOx 1..500 (1 = the usual).
    int32_t process(uint16_t sraw)
    {
        int32_t index = 0;
        GasIndexAlgorithm_process(&params_, static_cast<int32_t>(sraw), &index);
        return index;
    }

private:
    GasIndexAlgorithmParams params_{};
};

}  // namespace sensors
