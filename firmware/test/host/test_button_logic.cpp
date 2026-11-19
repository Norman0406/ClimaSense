#include <cstdint>
#include <utility>
#include <vector>

#include "board/button_logic.h"
#include "test.h"

using board::ButtonEvent;
using board::PressDetector;

namespace {

constexpr uint32_t kStep = 10;  // poll period of the firmware

struct Recorded {
    uint32_t at_ms;
    ButtonEvent event;
};

// Polls from `from` (inclusive) to `to` (exclusive) with the given raw state.
void run(PressDetector &d, bool pressed, uint32_t from, uint32_t to, std::vector<Recorded> &out)
{
    for (uint32_t t = from; t != to; t += kStep) {
        if (const auto e = d.update(pressed, t)) {
            out.push_back({t, *e});
        }
    }
}

}  // namespace

TEST(no_press_no_event)
{
    PressDetector d;
    std::vector<Recorded> ev;
    run(d, false, 0, 10'000, ev);
    CHECK(ev.empty());
    CHECK(!d.pressed());
}

TEST(short_press_reported_after_release_debounce)
{
    PressDetector d;
    std::vector<Recorded> ev;
    run(d, false, 0, 100, ev);
    run(d, true, 100, 300, ev);   // 200 ms press
    run(d, false, 300, 1000, ev);
    CHECK_EQ(ev.size(), 1u);
    if (ev.size() == 1) {
        CHECK(ev[0].event == ButtonEvent::ShortPress);
        CHECK_EQ(ev[0].at_ms, 300u + PressDetector::kDebounceMs);
    }
}

TEST(bounce_shorter_than_debounce_is_ignored)
{
    PressDetector d;
    std::vector<Recorded> ev;
    run(d, true, 0, 20, ev);      // 20 ms contact, below the 30 ms debounce
    run(d, false, 20, 1000, ev);
    CHECK(ev.empty());
    CHECK(!d.pressed());
}

TEST(bouncy_press_gives_one_short_press)
{
    PressDetector d;
    std::vector<Recorded> ev;
    // Contact bounce on press and on release, then a clean 500 ms press.
    for (uint32_t t = 0; t < 40; t += kStep) {
        if (const auto e = d.update((t / kStep) % 2 == 0, t)) ev.push_back({t, *e});
    }
    run(d, true, 40, 540, ev);
    for (uint32_t t = 540; t < 580; t += kStep) {
        if (const auto e = d.update((t / kStep) % 2 == 1, t)) ev.push_back({t, *e});
    }
    run(d, false, 580, 1500, ev);
    CHECK_EQ(ev.size(), 1u);
    if (ev.size() == 1) CHECK(ev[0].event == ButtonEvent::ShortPress);
}

TEST(long_press_reported_while_held_and_release_gives_nothing)
{
    PressDetector d;
    std::vector<Recorded> ev;
    run(d, true, 0, 5000, ev);
    run(d, false, 5000, 6000, ev);
    CHECK_EQ(ev.size(), 1u);
    if (ev.size() == 1) {
        CHECK(ev[0].event == ButtonEvent::LongPress);
        CHECK_EQ(ev[0].at_ms, PressDetector::kLongPressMs);  // measured from the first edge
    }
}

TEST(press_just_below_long_threshold_is_short)
{
    PressDetector d;
    std::vector<Recorded> ev;
    run(d, true, 0, PressDetector::kLongPressMs - kStep, ev);
    run(d, false, PressDetector::kLongPressMs - kStep, 5000, ev);
    CHECK_EQ(ev.size(), 1u);
    if (ev.size() == 1) CHECK(ev[0].event == ButtonEvent::ShortPress);
}

TEST(two_presses_give_two_events)
{
    PressDetector d;
    std::vector<Recorded> ev;
    run(d, true, 0, 200, ev);
    run(d, false, 200, 500, ev);
    run(d, true, 500, 4000, ev);
    run(d, false, 4000, 4500, ev);
    CHECK_EQ(ev.size(), 2u);
    if (ev.size() == 2) {
        CHECK(ev[0].event == ButtonEvent::ShortPress);
        CHECK(ev[1].event == ButtonEvent::LongPress);
    }
}

TEST(clock_wrap_around)
{
    PressDetector d;
    std::vector<Recorded> ev;
    const uint32_t start = 0xFFFF'FFFFu - 995;  // multiple of 10 below 2^32, wraps after ~1 s
    run(d, false, start - 100, start, ev);
    run(d, true, start, start + 4000, ev);  // crosses 2^32
    CHECK_EQ(ev.size(), 1u);
    if (ev.size() == 1) {
        CHECK(ev[0].event == ButtonEvent::LongPress);
        CHECK_EQ(ev[0].at_ms, start + PressDetector::kLongPressMs);
    }
}
