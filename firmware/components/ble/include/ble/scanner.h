// The Bluetooth scanner: listens passively for the frames of Find Hub tags (ble/fhn_frame.h) and
// keeps what it heard (ble/sightings.h) for the app task to publish. It never transmits, connects
// or answers; every other advertisement is dropped unread.
//
// Wi-Fi and Bluetooth share one radio. The scanner listens for kScanWindowMs out of every
// kScanIntervalMs: a tag sends its frame at least every 2 s, so at 30 % it is heard within about
// 6 s on average, for an estimated 42 mW of extra heat; listening all the time would cost about
// 140 mW (docs/research/presence-sensing.md; none of it measured). Scanning has to
// stop while the setup portal's access point is up (Espressif rates that combination unstable)
// and during an update; the app task says when (set_scanning).
#pragma once

#include <cstdint>

#include "esp_err.h"

#include "ble/sightings.h"

namespace ble {

inline constexpr uint16_t kScanIntervalMs = 1000;
inline constexpr uint16_t kScanWindowMs = 300;  // 30 % (decided 2026-11-23; it was 10 % at first)

// Starts the Bluetooth controller and host. Scanning begins once set_scanning(true) was called
// and the host is ready. Call once, after NVS is initialised.
esp_err_t start();

// Whether to scan; may be called at any time after start(), from any task.
void set_scanning(bool wanted);

// True while the controller is scanning.
bool scanning();

// True once after a tag was heard that was not known (ble/sightings.h): worth a message soon.
bool take_new_tag();

// Fills `report` with what was heard since the last call; starts the next window.
void take_report(uint32_t now_s, Report &report);

}  // namespace ble
