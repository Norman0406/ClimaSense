#include <cstdint>
#include <cstdlib>
#include <optional>

#include <gtest/gtest.h>

#include "sensors/gas_index.h"
#include "sensors/voc_baseline.h"

using sensors::GasIndex;
using sensors::GasIndexState;
using sensors::kVocMatureSamples;
using sensors::kVocMaxGapS;
using sensors::RtcVocBaseline;
using sensors::seal;
using sensors::unseal;
using sensors::VocBaselineKeeper;

namespace {

constexpr GasIndexState kState{1'234'567, 89'012};

// A raw VOC signal around `mean` with a slow wobble and some noise, one sample a second.
uint16_t signal(uint32_t t, int32_t mean)
{
    const int32_t wobble = static_cast<int32_t>((t / 60) % 40) - 20;  // +-20 over 40 minutes
    const int32_t noise = static_cast<int32_t>((t * 2654435761u) >> 28) - 8;  // -8..7
    return static_cast<uint16_t>(mean + wobble + noise);
}

}  // namespace

TEST(VocBaselineRtc, SealedStateComesBackUnchanged)
{
    const std::optional<GasIndexState> back = unseal(seal(kState));
    ASSERT_TRUE(back.has_value());
    EXPECT_EQ(*back, kState);
}

TEST(VocBaselineRtc, GarbageIsRejected)
{
    EXPECT_FALSE(unseal(RtcVocBaseline{}).has_value());  // cleared

    RtcVocBaseline copy = seal(kState);
    copy.mean ^= 1;  // one bit flipped
    EXPECT_FALSE(unseal(copy).has_value());

    copy = seal(kState);
    copy.magic ^= 0x100;
    EXPECT_FALSE(unseal(copy).has_value());

    copy = seal(kState);
    copy.check += 1;
    EXPECT_FALSE(unseal(copy).has_value());
}

TEST(VocBaselineRtc, ImplausibleStateIsRejectedEvenWithAValidChecksum)
{
    EXPECT_FALSE(unseal(seal(GasIndexState{0, 100})).has_value());
    EXPECT_FALSE(unseal(seal(GasIndexState{100, -1})).has_value());
}

TEST(VocBaselineKeeper, MatureAfterThreeHoursOfSamples)
{
    VocBaselineKeeper keeper;
    for (uint32_t i = 0; i + 1 < kVocMatureSamples; ++i) {
        keeper.sample();
    }
    EXPECT_FALSE(keeper.mature());
    keeper.sample();
    EXPECT_TRUE(keeper.mature());
}

TEST(VocBaselineKeeper, MatureAtOnceWhenRestored)
{
    VocBaselineKeeper keeper;
    keeper.restored();
    EXPECT_TRUE(keeper.mature());
}

TEST(GasIndexState, RestoredAlgorithmCarriesOnLikeTheUninterruptedOne)
{
    // Three hours of learning, then a reboot: one algorithm runs on, the other starts from the
    // saved state. After the start-up blackout both give (nearly) the same index, while a third
    // that starts from nothing is still far off.
    GasIndex running{GasIndex::Kind::Voc};
    constexpr int32_t kMean = 30'000;
    uint32_t t = 0;
    for (; t < kVocMatureSamples; ++t) {
        running.process(signal(t, kMean));
    }
    const GasIndexState saved = running.state();
    ASSERT_TRUE(sensors::plausible(saved));

    GasIndex restored{GasIndex::Kind::Voc};
    restored.restore(saved);
    EXPECT_EQ(restored.state(), saved);
    GasIndex fresh{GasIndex::Kind::Voc};

    // A rise of the signal (in this sensor, more VOC means a lower raw signal): the restored
    // algorithm reacts like the running one.
    int32_t running_index = 0;
    int32_t restored_index = 0;
    int32_t fresh_index = 0;
    for (uint32_t i = 0; i < 600; ++i, ++t) {
        const uint16_t raw = signal(t, i < 300 ? kMean : kMean - 400);
        running_index = running.process(raw);
        restored_index = restored.process(raw);
        fresh_index = fresh.process(raw);
        if (i < GasIndex::kBlackoutSamples) {
            EXPECT_EQ(restored_index, 0) << "sample " << i;  // the blackout applies again
        } else if (i > 120) {
            // Within 3 % (the algorithm's low-pass filter restarts with the blackout).
            EXPECT_NEAR(restored_index, running_index, 3 + running_index * 3 / 100) << "sample " << i;
        }
    }
    EXPECT_GT(running_index, 150);  // the rise shows
    // A fresh algorithm takes the rise for the room's new normal within minutes.
    EXPECT_GT(std::abs(fresh_index - running_index), 100);
}
