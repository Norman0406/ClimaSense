#include <cstdint>
#include <ostream>
#include <vector>

#include <gtest/gtest.h>

#include "board/button_logic.h"

namespace board {
// Readable names in GoogleTest's failure messages.
void PrintTo(ButtonEvent event, std::ostream *os)
{
    *os << (event == ButtonEvent::ShortPress ? "ShortPress" : "LongPress");
}
}  // namespace board

using board::ButtonEvent;
using board::PressDetector;

namespace {

constexpr uint32_t kStep = 10;  // poll period of the firmware

struct Recorded {
    uint32_t at_ms;
    ButtonEvent event;
};

// Drives a PressDetector the way the firmware's 10 ms poll does and records its events.
class PressDetectorTest : public ::testing::Test {
protected:
    // Polls from `from` (inclusive) to `to` (exclusive) with a constant raw state.
    void hold(bool pressed, uint32_t from, uint32_t to)
    {
        for (uint32_t t = from; t != to; t += kStep) {
            sample(pressed, t);
        }
    }

    // Polls from `from` to `to` with the raw state toggling every sample (contact bounce),
    // starting with `first`.
    void bounce(bool first, uint32_t from, uint32_t to)
    {
        bool pressed = first;
        for (uint32_t t = from; t != to; t += kStep) {
            sample(pressed, t);
            pressed = !pressed;
        }
    }

    void sample(bool pressed, uint32_t t)
    {
        if (const auto e = detector.update(pressed, t)) {
            events.push_back({t, *e});
        }
    }

    PressDetector detector;
    std::vector<Recorded> events;
};

}  // namespace

TEST_F(PressDetectorTest, NoPressGivesNoEvent)
{
    hold(false, 0, 10'000);
    EXPECT_TRUE(events.empty());
    EXPECT_FALSE(detector.pressed());
}

TEST_F(PressDetectorTest, ShortPressIsReportedAfterReleaseDebounce)
{
    hold(false, 0, 100);
    hold(true, 100, 300);  // 200 ms press
    hold(false, 300, 1000);
    ASSERT_EQ(events.size(), 1u);
    EXPECT_EQ(events[0].event, ButtonEvent::ShortPress);
    EXPECT_EQ(events[0].at_ms, 300u + PressDetector::kDebounceMs);
}

TEST_F(PressDetectorTest, ContactShorterThanDebounceIsIgnored)
{
    hold(true, 0, 20);  // 20 ms, below the 30 ms debounce
    hold(false, 20, 1000);
    EXPECT_TRUE(events.empty());
    EXPECT_FALSE(detector.pressed());
}

TEST_F(PressDetectorTest, BouncyPressGivesOneShortPress)
{
    bounce(true, 0, 40);     // bounce on press
    hold(true, 40, 540);     // clean 500 ms press
    bounce(false, 540, 580); // bounce on release
    hold(false, 580, 1500);
    ASSERT_EQ(events.size(), 1u);
    EXPECT_EQ(events[0].event, ButtonEvent::ShortPress);
}

TEST_F(PressDetectorTest, LongPressIsReportedWhileHeldAndReleaseGivesNothing)
{
    hold(true, 0, 5000);
    hold(false, 5000, 6000);
    ASSERT_EQ(events.size(), 1u);
    EXPECT_EQ(events[0].event, ButtonEvent::LongPress);
    EXPECT_EQ(events[0].at_ms, PressDetector::kLongPressMs);  // measured from the first edge
}

TEST_F(PressDetectorTest, ReleaseJustBeforeLongThresholdIsShortPress)
{
    // Released at 2990 ms: the debounced state is still "pressed" at 3000 ms, which must not
    // count as a long press.
    hold(true, 0, PressDetector::kLongPressMs - kStep);
    hold(false, PressDetector::kLongPressMs - kStep, 5000);
    ASSERT_EQ(events.size(), 1u);
    EXPECT_EQ(events[0].event, ButtonEvent::ShortPress);
}

TEST_F(PressDetectorTest, TwoPressesGiveTwoEvents)
{
    hold(true, 0, 200);
    hold(false, 200, 500);
    hold(true, 500, 4000);
    hold(false, 4000, 4500);
    ASSERT_EQ(events.size(), 2u);
    EXPECT_EQ(events[0].event, ButtonEvent::ShortPress);
    EXPECT_EQ(events[1].event, ButtonEvent::LongPress);
}

TEST_F(PressDetectorTest, ClockWrapAroundDuringPress)
{
    const uint32_t start = 0xFFFF'FFFFu - 995;  // multiple of 10, 2^32 is reached after ~1 s
    hold(false, start - 100, start);
    hold(true, start, start + 4000);  // crosses 2^32
    ASSERT_EQ(events.size(), 1u);
    EXPECT_EQ(events[0].event, ButtonEvent::LongPress);
    EXPECT_EQ(events[0].at_ms, start + PressDetector::kLongPressMs);
}
