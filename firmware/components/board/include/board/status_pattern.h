// What the status LED shows: one status at a time, picked by priority, each with its own colour
// and rhythm (docs/firmware/architecture.md, "Status LED and button"). Pure logic, no ESP-IDF
// dependencies, tested on the PC.
//
//   Updating       magenta, flashing 5 times a second
//   Setup          blue, blinking twice a second (setup portal open)
//   NoWifi         yellow, one short flash every 3 s (not connected to Wi-Fi)
//   NoBroker       yellow, two short flashes every 3 s (Wi-Fi up, MQTT broker not reached)
//   SensorFault    red, one short flash every 3 s (a sensor keeps failing)
//   Ok             off; green while a short button press asks for the status
//
// On top of Ok and SensorFault, every state message sent over MQTT shows green until the broker
// has acknowledged it (at least 80 ms, at most 5 s).
// With the LED switched off in the settings (e.g. in a bedroom), only the setup portal and a
// button press light it.
#pragma once

#include <cstdint>

#include "board/led_logic.h"

namespace board {

namespace colour {
inline constexpr Rgb kYellow{255, 255, 0};
inline constexpr Rgb kMagenta{255, 0, 255};
}  // namespace colour

// In order of priority, lowest first.
enum class Status : uint8_t { Ok, SensorFault, NoBroker, NoWifi, Setup, Updating };

const char *to_string(Status status);

struct StatusInputs {
    bool updating = false;           // an update is downloading or being uploaded
    bool setup_open = false;         // the setup portal is open
    bool wifi_connected = false;
    bool broker_configured = false;  // no broker set: nothing to reach, not a fault
    bool broker_connected = false;
    bool sensors_working = true;
};

// The most important status that applies.
Status pick_status(const StatusInputs &in);

// The status the LED shows. `led_enabled`: the setting. `asked`: a short button press asked for
// the status. With the LED off, only the setup portal shows (it was opened at the button), and
// everything does while asked.
Status shown_status(const StatusInputs &in, bool led_enabled, bool asked);

// A sent message: green from when it is queued until the broker acknowledges it, at least
// kSendFlashMinMs (a LAN round trip alone would be invisible) and at most kSendFlashMaxMs (an
// ack that never comes does not keep it lit). Shown over the statuses whose pattern it cannot be
// mistaken for, and only with the LED on.
inline constexpr uint32_t kSendFlashMinMs = 80;
inline constexpr uint32_t kSendFlashMaxMs = 5000;
constexpr bool send_flash_on(uint32_t elapsed_ms, bool acked)
{
    return elapsed_ms < kSendFlashMaxMs && (!acked || elapsed_ms < kSendFlashMinMs);
}
constexpr bool shows_send_flash(Status status, bool led_enabled)
{
    return led_enabled && (status == Status::Ok || status == Status::SensorFault);
}

struct LedStep {
    Rgb colour;
    uint32_t hold_ms;  // how long the colour stays as it is from now
};

// The LED `elapsed_ms` after `status` began. `show_ok`: the status was asked for with a button
// press, so Ok shows green instead of nothing.
LedStep status_led(Status status, uint32_t elapsed_ms, bool show_ok);

}  // namespace board
