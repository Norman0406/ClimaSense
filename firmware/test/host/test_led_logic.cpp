#include <cstdint>

#include <gtest/gtest.h>

#include "board/led_logic.h"

using board::Duty;
using board::kDutyMax;
using board::LedBalance;
using board::Rgb;
using board::to_duty;
namespace colour = board::colour;

TEST(LedLogic, OffAndZeroBrightnessGiveZeroDuty)
{
    const Duty off = to_duty(colour::kOff, 255);
    EXPECT_EQ(off.r, 0u);
    EXPECT_EQ(off.g, 0u);
    EXPECT_EQ(off.b, 0u);

    const Duty dark = to_duty(colour::kWhite, 0);
    EXPECT_EQ(dark.r, 0u);
    EXPECT_EQ(dark.g, 0u);
    EXPECT_EQ(dark.b, 0u);
}

TEST(LedLogic, FullWhiteScalesToTheWeakestColour)
{
    // Board balance: red 13, green 21, blue 8 mcd -> blue full, the others scaled to 8 mcd.
    const Duty d = to_duty(colour::kWhite, 255);
    EXPECT_EQ(d.b, kDutyMax);
    EXPECT_NEAR(d.g, 390, 1);  // 1023 * 8 / 21 = 389.7
    EXPECT_NEAR(d.r, 630, 1);  // 1023 * 8 / 13 = 629.5
}

TEST(LedLogic, SingleColoursOnlyDriveTheirChannel)
{
    const Duty r = to_duty(colour::kRed, 255);
    EXPECT_GT(r.r, 0u);
    EXPECT_EQ(r.g, 0u);
    EXPECT_EQ(r.b, 0u);

    const Duty g = to_duty(colour::kGreen, 255);
    EXPECT_EQ(g.r, 0u);
    EXPECT_GT(g.g, 0u);
    EXPECT_EQ(g.b, 0u);

    const Duty b = to_duty(colour::kBlue, 255);
    EXPECT_EQ(b.r, 0u);
    EXPECT_EQ(b.g, 0u);
    EXPECT_GT(b.b, 0u);
}

TEST(LedLogic, GammaCorrectionAtHalfLevel)
{
    // (128/255)^2.2 * 1023 = 224.6
    const Duty d = to_duty(Rgb{0, 0, 128}, 255);
    EXPECT_NEAR(d.b, 225, 1);
    // Value and brightness combine: 255 at brightness 128 equals 128 at full brightness.
    EXPECT_EQ(to_duty(Rgb{0, 0, 255}, 128).b, d.b);
}

TEST(LedLogic, DutyRisesWithBrightnessAndStaysInRange)
{
    uint32_t previous = 0;
    for (int brightness = 0; brightness <= 255; ++brightness) {
        const Duty d = to_duty(colour::kWhite, static_cast<uint8_t>(brightness));
        EXPECT_GE(d.b, previous) << "brightness " << brightness;
        EXPECT_LE(d.r, kDutyMax);
        EXPECT_LE(d.g, kDutyMax);
        EXPECT_LE(d.b, kDutyMax);
        previous = d.b;
    }
}

TEST(LedLogic, EqualBalanceDrivesAllChannelsEqually)
{
    const Duty d = to_duty(colour::kWhite, 255, LedBalance{1.0f, 1.0f, 1.0f});
    EXPECT_EQ(d.r, kDutyMax);
    EXPECT_EQ(d.g, kDutyMax);
    EXPECT_EQ(d.b, kDutyMax);
}
