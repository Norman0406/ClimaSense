#include <cstdint>

#include "board/led_logic.h"
#include "test.h"

using board::Duty;
using board::kDutyMax;
using board::Rgb;
using board::to_duty;
namespace colour = board::colour;

namespace {

bool near(uint32_t a, uint32_t b, uint32_t tolerance = 1)
{
    return (a > b ? a - b : b - a) <= tolerance;
}

}  // namespace

TEST(off_and_zero_brightness_give_zero_duty)
{
    const Duty off = to_duty(colour::kOff, 255);
    CHECK_EQ(off.r, 0u);
    CHECK_EQ(off.g, 0u);
    CHECK_EQ(off.b, 0u);

    const Duty dark = to_duty(colour::kWhite, 0);
    CHECK_EQ(dark.r, 0u);
    CHECK_EQ(dark.g, 0u);
    CHECK_EQ(dark.b, 0u);
}

TEST(full_white_scales_to_the_weakest_colour)
{
    // Board balance: red 13, green 21, blue 8 mcd -> blue full, others scaled to 8 mcd.
    const Duty d = to_duty(colour::kWhite, 255);
    CHECK_EQ(d.b, kDutyMax);
    CHECK(near(d.g, 390));  // 1023 * 8 / 21 = 389.7
    CHECK(near(d.r, 630));  // 1023 * 8 / 13 = 629.5
}

TEST(single_colours_only_drive_their_channel)
{
    const Duty r = to_duty(colour::kRed, 255);
    CHECK(r.r > 0 && r.g == 0 && r.b == 0);
    const Duty g = to_duty(colour::kGreen, 255);
    CHECK(g.r == 0 && g.g > 0 && g.b == 0);
    const Duty b = to_duty(colour::kBlue, 255);
    CHECK(b.r == 0 && b.g == 0 && b.b > 0);
}

TEST(gamma_correction_at_half_level)
{
    // (128/255)^2.2 * 1023 = 224.6
    const Duty d = to_duty(Rgb{0, 0, 128}, 255);
    CHECK(near(d.b, 225));
    // Value and brightness combine: 255 at brightness 128 equals 128 at full brightness.
    CHECK_EQ(to_duty(Rgb{0, 0, 255}, 128).b, d.b);
}

TEST(duty_rises_with_brightness_and_stays_in_range)
{
    uint32_t previous = 0;
    for (int brightness = 0; brightness <= 255; ++brightness) {
        const Duty d = to_duty(colour::kWhite, static_cast<uint8_t>(brightness));
        CHECK(d.b >= previous);
        CHECK(d.r <= kDutyMax && d.g <= kDutyMax && d.b <= kDutyMax);
        previous = d.b;
    }
}

TEST(equal_balance_drives_all_channels_equally)
{
    const Duty d = to_duty(colour::kWhite, 255, board::LedBalance{1.0f, 1.0f, 1.0f});
    CHECK_EQ(d.r, kDutyMax);
    CHECK_EQ(d.g, kDutyMax);
    CHECK_EQ(d.b, kDutyMax);
}
