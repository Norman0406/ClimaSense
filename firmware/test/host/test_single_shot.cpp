#include <cstdint>
#include <vector>

#include <gtest/gtest.h>

#include "sensors/single_shot.h"

using sensors::SingleShotSchedule;
using Step = SingleShotSchedule::Step;

namespace {

// Runs the schedule like the sensor task does, with a sensor whose result becomes ready
// `ready_after` ticks after the start (or never, if 0). Returns the ticks at which shots were
// started, and counts reads and give-ups.
struct ShotRun {
    std::vector<uint32_t> starts;
    std::vector<uint32_t> reads;
    int give_ups = 0;
};

ShotRun simulate(uint32_t ticks, uint32_t ready_after, uint32_t first_tick = 1)
{
    ShotRun run;
    SingleShotSchedule s;
    uint32_t started_at = 0;
    for (uint32_t t = first_tick; t != first_tick + ticks; ++t) {
        switch (s.next(t)) {
        case Step::Start:
            s.started(t);
            started_at = t;
            run.starts.push_back(t);
            break;
        case Step::Poll:
            if (ready_after != 0 && t - started_at >= ready_after) {
                run.reads.push_back(t);
                s.done();
            }
            break;
        case Step::GiveUp:
            ++run.give_ups;
            s.done();
            break;
        case Step::Wait:
            break;
        }
    }
    return run;
}

}  // namespace

TEST(SingleShotSchedule, FirstShotStartsAtTheFirstTick)
{
    SingleShotSchedule s;
    EXPECT_EQ(s.next(1), Step::Start);
    EXPECT_EQ(s.next(12345), Step::Start);
}

TEST(SingleShotSchedule, WaitsBeforePollingThenPolls)
{
    SingleShotSchedule s;
    s.started(100);
    for (uint32_t t = 100; t < 100 + SingleShotSchedule::kFirstPollTicks; ++t) {
        EXPECT_EQ(s.next(t), Step::Wait) << "tick " << t;
    }
    EXPECT_EQ(s.next(100 + SingleShotSchedule::kFirstPollTicks), Step::Poll);
}

TEST(SingleShotSchedule, FirstPollComesAfterTheFiveSecondMeasurement)
{
    // The sensor task sends the shot at the end of a tick (after the other sensors), so the
    // result is ready a little more than 5 ticks later: the first poll needs a tick of margin.
    EXPECT_GE(SingleShotSchedule::kFirstPollTicks, 6u);
}

TEST(SingleShotSchedule, ShotsComeEveryFiveMinutesWhenResultsArrive)
{
    const ShotRun run = simulate(3 * 300 + 50, 6);
    ASSERT_EQ(run.starts.size(), 4u);
    EXPECT_EQ(run.starts[0], 1u);
    EXPECT_EQ(run.starts[1], 301u);
    EXPECT_EQ(run.starts[2], 601u);
    EXPECT_EQ(run.starts[3], 901u);
    EXPECT_EQ(run.reads.size(), 4u);
    EXPECT_EQ(run.give_ups, 0);
}

TEST(SingleShotSchedule, LateResultIsStillReadBeforeGivingUp)
{
    const ShotRun run = simulate(100, 9);  // ready 9 s after the start
    ASSERT_EQ(run.reads.size(), 1u);
    EXPECT_EQ(run.reads[0], 1u + 9);
    EXPECT_EQ(run.give_ups, 0);
}

TEST(SingleShotSchedule, MissingResultGivesUpOnceAndKeepsTheRhythm)
{
    const ShotRun run = simulate(2 * 300 + 50, 0);  // never ready
    EXPECT_TRUE(run.reads.empty());
    EXPECT_EQ(run.give_ups, 3);  // shots at 1, 301, 601
    ASSERT_EQ(run.starts.size(), 3u);
    EXPECT_EQ(run.starts[1], 301u);
}

TEST(SingleShotSchedule, FailedStartIsRetriedSoon)
{
    SingleShotSchedule s;
    ASSERT_EQ(s.next(50), Step::Start);
    s.start_failed(50);
    for (uint32_t t = 50; t < 50 + SingleShotSchedule::kRetryTicks; ++t) {
        EXPECT_EQ(s.next(t), Step::Wait) << "tick " << t;
    }
    EXPECT_EQ(s.next(50 + SingleShotSchedule::kRetryTicks), Step::Start);
}

TEST(SingleShotSchedule, TickCounterWrapAroundKeepsTheRhythm)
{
    const ShotRun run = simulate(400, 6, 0xFFFF'FFFFu - 100);
    ASSERT_EQ(run.starts.size(), 2u);
    EXPECT_EQ(run.starts[1] - run.starts[0], 300u);  // unsigned difference across the wrap
    EXPECT_EQ(run.reads.size(), 2u);
}
