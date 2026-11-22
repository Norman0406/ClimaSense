#include "board/status_pattern.h"

#include <span>

namespace board {

namespace {

struct Segment {
    bool on;
    uint32_t ms;
};

constexpr uint32_t kFlashMs = 150;
constexpr uint32_t kSteadyHoldMs = 1000;  // a steady colour: look again in a second

constexpr Segment kUpdating[] = {{true, 100}, {false, 100}};
constexpr Segment kSetup[] = {{true, 250}, {false, 250}};
constexpr Segment kOneFlash[] = {{true, kFlashMs}, {false, 3000 - kFlashMs}};
constexpr Segment kTwoFlashes[] = {{true, kFlashMs}, {false, 250}, {true, kFlashMs}, {false, 3000 - 2 * kFlashMs - 250}};

LedStep play(std::span<const Segment> pattern, Rgb colour, uint32_t elapsed_ms)
{
    uint32_t period = 0;
    for (const Segment &s : pattern) {
        period += s.ms;
    }
    uint32_t t = elapsed_ms % period;
    for (const Segment &s : pattern) {
        if (t < s.ms) {
            return {s.on ? colour : colour::kOff, s.ms - t};
        }
        t -= s.ms;
    }
    return {colour::kOff, 1};  // not reached
}

}  // namespace

const char *to_string(Status status)
{
    switch (status) {
    case Status::Ok:          return "ok";
    case Status::SensorFault: return "sensor fault";
    case Status::NoBroker:    return "no MQTT broker";
    case Status::NoWifi:      return "no Wi-Fi";
    case Status::Setup:       return "setup";
    case Status::Updating:    return "updating";
    }
    return "?";
}

Status pick_status(const StatusInputs &in)
{
    if (in.updating) {
        return Status::Updating;
    }
    if (in.setup_open) {
        return Status::Setup;
    }
    if (!in.wifi_connected) {
        return Status::NoWifi;
    }
    if (in.broker_configured && !in.broker_connected) {
        return Status::NoBroker;
    }
    if (!in.sensors_working) {
        return Status::SensorFault;
    }
    return Status::Ok;
}

LedStep status_led(Status status, uint32_t elapsed_ms, bool show_ok)
{
    switch (status) {
    case Status::Updating:    return play(kUpdating, colour::kMagenta, elapsed_ms);
    case Status::Setup:       return play(kSetup, colour::kBlue, elapsed_ms);
    case Status::NoWifi:      return play(kOneFlash, colour::kYellow, elapsed_ms);
    case Status::NoBroker:    return play(kTwoFlashes, colour::kYellow, elapsed_ms);
    case Status::SensorFault: return play(kOneFlash, colour::kRed, elapsed_ms);
    case Status::Ok:          break;
    }
    return {show_ok ? colour::kGreen : colour::kOff, kSteadyHoldMs};
}

}  // namespace board
