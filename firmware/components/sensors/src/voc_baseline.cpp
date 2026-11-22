#include "sensors/voc_baseline.h"

#include <initializer_list>

namespace sensors {

namespace {

constexpr uint32_t kMagic = 0x564F4331;  // "VOC1"

// FNV-1a over the three words.
uint32_t checksum(uint32_t magic, const GasIndexState &s)
{
    uint32_t hash = 2166136261u;
    for (const uint32_t word : {magic, static_cast<uint32_t>(s.mean), static_cast<uint32_t>(s.std)}) {
        for (int shift = 0; shift < 32; shift += 8) {
            hash ^= (word >> shift) & 0xFFu;
            hash *= 16777619u;
        }
    }
    return hash;
}

}  // namespace

RtcVocBaseline seal(const GasIndexState &state)
{
    return RtcVocBaseline{kMagic, state.mean, state.std, checksum(kMagic, state)};
}

std::optional<GasIndexState> unseal(const RtcVocBaseline &copy)
{
    const GasIndexState state{copy.mean, copy.std};
    if (copy.magic != kMagic || copy.check != checksum(copy.magic, state) || !plausible(state)) {
        return std::nullopt;
    }
    return state;
}

}  // namespace sensors
