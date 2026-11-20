// When to start an SCD41 single shot and when to look for its result, tick by tick (1 s ticks
// of the sensor task). Pure logic, tested on the PC.
//
// A shot is started every kIntervalTicks (5 minutes, measured from start to start). Its result
// is looked for from kFirstPollTicks after the start (the 5 s the measurement takes) on every
// tick, until it is read or kGiveUpTicks have passed. Nothing blocks: the other sensors keep
// their 1 s rhythm meanwhile.
#pragma once

#include <cstdint>

namespace sensors {

class SingleShotSchedule {
public:
    static constexpr uint32_t kIntervalTicks = 300;  // 5 minutes
    static constexpr uint32_t kFirstPollTicks = 6;   // 5 s measurement, plus one tick of margin
    static constexpr uint32_t kGiveUpTicks = 10;     // no result by then: counts as failed
    static constexpr uint32_t kRetryTicks = 10;      // after a start that failed

    enum class Step : uint8_t {
        Wait,    // nothing to do this tick
        Start,   // start a shot; then call started() or start_failed()
        Poll,    // check for the result; call done() once it is read or failed
        GiveUp,  // no result in time: count a failure and call done()
    };

    // What to do in this tick. The first call (any tick) gives Start.
    Step next(uint32_t tick) const
    {
        if (measuring_) {
            const uint32_t since = tick - started_tick_;
            if (since >= kGiveUpTicks) {
                return Step::GiveUp;
            }
            return since >= kFirstPollTicks ? Step::Poll : Step::Wait;
        }
        if (!scheduled_ || static_cast<int32_t>(tick - next_start_) >= 0) {
            return Step::Start;
        }
        return Step::Wait;
    }

    void started(uint32_t tick)
    {
        measuring_ = true;
        started_tick_ = tick;
        scheduled_ = true;
        next_start_ = tick + kIntervalTicks;
    }

    void start_failed(uint32_t tick)
    {
        scheduled_ = true;
        next_start_ = tick + kRetryTicks;
    }

    void done() { measuring_ = false; }

    bool measuring() const { return measuring_; }

private:
    bool scheduled_ = false;
    bool measuring_ = false;
    uint32_t started_tick_ = 0;
    uint32_t next_start_ = 0;
};

}  // namespace sensors
