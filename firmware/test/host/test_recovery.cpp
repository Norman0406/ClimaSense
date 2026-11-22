#include <cstdint>

#include <gtest/gtest.h>

#include "sensors/recovery.h"

using sensors::RailRecovery;

TEST(RailRecovery, NothingWhileNoSensorIsStuck)
{
    RailRecovery r;
    for (uint32_t t = 0; t < 10'000; t += 7) {
        EXPECT_FALSE(r.due(t, false, t % 2 == 0));
    }
    EXPECT_EQ(r.count(), 0u);
}

TEST(RailRecovery, FirstRecoveryAtOnce)
{
    RailRecovery r;
    EXPECT_TRUE(r.due(30, true, false));
    EXPECT_EQ(r.count(), 1u);
}

TEST(RailRecovery, PausesDoubleUpToFourHours)
{
    RailRecovery r;
    uint32_t t = 100;
    ASSERT_TRUE(r.due(t, true, false));
    uint32_t pause = RailRecovery::kFirstPauseS;
    for (int i = 0; i < 12; ++i) {
        EXPECT_FALSE(r.due(t + pause - 1, true, false)) << "recovery " << i;
        EXPECT_TRUE(r.due(t + pause, true, false)) << "recovery " << i;
        t += pause;
        pause = pause * 2 > RailRecovery::kMaxPauseS ? RailRecovery::kMaxPauseS : pause * 2;
    }
    EXPECT_EQ(pause, RailRecovery::kMaxPauseS);
    EXPECT_EQ(r.count(), 13u);
}

TEST(RailRecovery, PauseStartsAgainAfterAnHourOfEverythingWorking)
{
    RailRecovery r;
    ASSERT_TRUE(r.due(0, true, false));        // next pause 2 min
    ASSERT_TRUE(r.due(120, true, false));      // next pause 4 min
    ASSERT_TRUE(r.due(360, true, false));      // next pause 8 min
    // Fixed: everything works for an hour.
    for (uint32_t t = 400; t <= 400 + RailRecovery::kSettledS; t += 1) {
        ASSERT_FALSE(r.due(t, false, true));
    }
    const uint32_t t = 400 + RailRecovery::kSettledS + 10;
    ASSERT_TRUE(r.due(t, true, false));
    EXPECT_FALSE(r.due(t + RailRecovery::kFirstPauseS - 1, true, false));
    EXPECT_TRUE(r.due(t + RailRecovery::kFirstPauseS, true, false));
}

TEST(RailRecovery, ShortSpellsOfWorkingDoNotResetThePause)
{
    RailRecovery r;
    ASSERT_TRUE(r.due(0, true, false));    // next pause 2 min
    ASSERT_TRUE(r.due(120, true, false));  // next pause 4 min, then 8
    for (uint32_t t = 121; t < 121 + 1800; ++t) {
        ASSERT_FALSE(r.due(t, false, true));  // half an hour working: not enough
    }
    const uint32_t t = 1921;
    ASSERT_TRUE(r.due(t, true, false));  // stuck again; the 4-minute pause has passed
    EXPECT_FALSE(r.due(t + RailRecovery::kFirstPauseS, true, false));
    EXPECT_FALSE(r.due(t + 8 * 60 - 1, true, false));
    EXPECT_TRUE(r.due(t + 8 * 60, true, false));
}

TEST(RailRecovery, CountsAcrossTheUptimeWrap)
{
    RailRecovery r;
    const uint32_t t = 0xFFFF'FF00u;
    ASSERT_TRUE(r.due(t, true, false));
    EXPECT_FALSE(r.due(t + 100, true, false));  // wraps past zero, still within the pause
    EXPECT_TRUE(r.due(t + RailRecovery::kFirstPauseS, true, false));
}
