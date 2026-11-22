#include <cstdint>

#include <gtest/gtest.h>

#include "board/status_pattern.h"

using board::LedStep;
using board::pick_status;
using board::shown_status;
using board::shows_send_flash;
using board::Rgb;
using board::Status;
using board::status_led;
using board::StatusInputs;

namespace {

bool same(Rgb a, Rgb b) { return a.r == b.r && a.g == b.g && a.b == b.b; }

bool lit(const LedStep &s) { return !same(s.colour, board::colour::kOff); }

StatusInputs all_well()
{
    StatusInputs in;
    in.wifi_connected = true;
    in.broker_configured = true;
    in.broker_connected = true;
    in.sensors_working = true;
    return in;
}

// Number of separate flashes in one period of a pattern.
int flashes(Status status, uint32_t period_ms)
{
    int count = 0;
    bool was_lit = false;
    for (uint32_t t = 0; t < period_ms; t += 10) {
        const bool now_lit = lit(status_led(status, t, false));
        if (now_lit && !was_lit) {
            ++count;
        }
        was_lit = now_lit;
    }
    return count;
}

}  // namespace

TEST(StatusPick, AllWellIsOk)
{
    EXPECT_EQ(pick_status(all_well()), Status::Ok);
}

TEST(StatusPick, NoBrokerConfiguredIsNotAFault)
{
    StatusInputs in = all_well();
    in.broker_configured = false;
    in.broker_connected = false;
    EXPECT_EQ(pick_status(in), Status::Ok);
}

TEST(StatusPick, EachProblemOnItsOwn)
{
    StatusInputs in = all_well();
    in.sensors_working = false;
    EXPECT_EQ(pick_status(in), Status::SensorFault);

    in = all_well();
    in.broker_connected = false;
    EXPECT_EQ(pick_status(in), Status::NoBroker);

    in = all_well();
    in.wifi_connected = false;
    EXPECT_EQ(pick_status(in), Status::NoWifi);

    in = all_well();
    in.setup_open = true;
    EXPECT_EQ(pick_status(in), Status::Setup);

    in = all_well();
    in.updating = true;
    EXPECT_EQ(pick_status(in), Status::Updating);
}

TEST(StatusPick, TheMoreImportantStatusWins)
{
    StatusInputs in;  // nothing works at all
    in.broker_configured = true;
    in.sensors_working = false;
    EXPECT_EQ(pick_status(in), Status::NoWifi);  // without Wi-Fi the broker cannot be reached either
    in.setup_open = true;
    EXPECT_EQ(pick_status(in), Status::Setup);
    in.updating = true;
    EXPECT_EQ(pick_status(in), Status::Updating);

    in = all_well();
    in.broker_connected = false;
    in.sensors_working = false;
    EXPECT_EQ(pick_status(in), Status::NoBroker);
}

TEST(StatusLed, OkIsDarkUnlessAskedFor)
{
    EXPECT_FALSE(lit(status_led(Status::Ok, 0, false)));
    EXPECT_FALSE(lit(status_led(Status::Ok, 123'456, false)));
    EXPECT_TRUE(same(status_led(Status::Ok, 0, true).colour, board::colour::kGreen));
}

TEST(StatusLed, ColoursOfTheStatuses)
{
    EXPECT_TRUE(same(status_led(Status::Updating, 0, false).colour, board::colour::kMagenta));
    EXPECT_TRUE(same(status_led(Status::Setup, 0, false).colour, board::colour::kBlue));
    EXPECT_TRUE(same(status_led(Status::NoWifi, 0, false).colour, board::colour::kYellow));
    EXPECT_TRUE(same(status_led(Status::NoBroker, 0, false).colour, board::colour::kYellow));
    EXPECT_TRUE(same(status_led(Status::SensorFault, 0, false).colour, board::colour::kRed));
}

TEST(StatusLed, EveryPatternStartsLit)
{
    for (const Status s : {Status::Updating, Status::Setup, Status::NoWifi, Status::NoBroker, Status::SensorFault}) {
        EXPECT_TRUE(lit(status_led(s, 0, false))) << board::to_string(s);
    }
}

TEST(StatusLed, SetupBlinksTwiceASecondLikeBefore)
{
    EXPECT_TRUE(lit(status_led(Status::Setup, 0, false)));
    EXPECT_TRUE(lit(status_led(Status::Setup, 249, false)));
    EXPECT_FALSE(lit(status_led(Status::Setup, 250, false)));
    EXPECT_FALSE(lit(status_led(Status::Setup, 499, false)));
    EXPECT_TRUE(lit(status_led(Status::Setup, 500, false)));
    EXPECT_EQ(flashes(Status::Setup, 1000), 2);
}

TEST(StatusLed, FlashCountsTellTheConnectionProblemsApart)
{
    EXPECT_EQ(flashes(Status::NoWifi, 3000), 1);
    EXPECT_EQ(flashes(Status::NoBroker, 3000), 2);
    EXPECT_EQ(flashes(Status::SensorFault, 3000), 1);
    EXPECT_EQ(flashes(Status::Updating, 1000), 5);
}

TEST(StatusLed, PatternsRepeat)
{
    for (uint32_t t = 0; t < 3000; t += 50) {
        EXPECT_TRUE(same(status_led(Status::NoBroker, t, false).colour,
                         status_led(Status::NoBroker, t + 3000 * 7, false).colour))
            << t;
    }
}

TEST(StatusLed, HoldTimeLeadsExactlyToTheNextChange)
{
    // The app task sleeps for hold_ms; the colour must not change before, and must change then.
    for (const Status s : {Status::Updating, Status::Setup, Status::NoWifi, Status::NoBroker, Status::SensorFault}) {
        uint32_t t = 0;
        for (int step = 0; step < 20; ++step) {
            const LedStep now = status_led(s, t, false);
            ASSERT_GT(now.hold_ms, 0u);
            EXPECT_TRUE(same(status_led(s, t + now.hold_ms - 1, false).colour, now.colour)) << board::to_string(s);
            EXPECT_FALSE(same(status_led(s, t + now.hold_ms, false).colour, now.colour)) << board::to_string(s);
            t += now.hold_ms;
        }
    }
}

TEST(StatusLed, FlashesAreShort)
{
    // A connection or sensor problem lights the LED for 10 % of the time at most: little light
    // in a dark room, and no heat next to the sensors.
    for (const Status s : {Status::NoWifi, Status::NoBroker, Status::SensorFault}) {
        uint32_t lit_ms = 0;
        for (uint32_t t = 0; t < 3000; ++t) {
            lit_ms += lit(status_led(s, t, false)) ? 1 : 0;
        }
        EXPECT_LE(lit_ms, 300u) << board::to_string(s);
    }
}

TEST(StatusShown, LedOnShowsEverything)
{
    StatusInputs in = all_well();
    in.broker_connected = false;
    EXPECT_EQ(shown_status(in, true, false), Status::NoBroker);
}

TEST(StatusShown, LedOffIsDarkExceptForSetupAndWhenAsked)
{
    StatusInputs in = all_well();
    in.wifi_connected = false;
    EXPECT_EQ(shown_status(in, false, false), Status::Ok);  // Ok, not asked: dark
    EXPECT_FALSE(lit(status_led(shown_status(in, false, false), 0, false)));
    EXPECT_EQ(shown_status(in, false, true), Status::NoWifi);  // a button press asks

    in.updating = true;
    EXPECT_EQ(shown_status(in, false, false), Status::Ok);  // an update over MQTT at night stays dark
    in.updating = false;
    in.setup_open = true;
    EXPECT_EQ(shown_status(in, false, false), Status::Setup);  // opened at the button
}

TEST(StatusShown, SendFlashOnlyWithTheLedOnAndOverQuietPatterns)
{
    EXPECT_TRUE(shows_send_flash(Status::Ok, true));
    EXPECT_TRUE(shows_send_flash(Status::SensorFault, true));
    EXPECT_FALSE(shows_send_flash(Status::Ok, false));
    for (const Status s : {Status::NoBroker, Status::NoWifi, Status::Setup, Status::Updating}) {
        EXPECT_FALSE(shows_send_flash(s, true)) << board::to_string(s);
    }
}
