// Button press detection: debouncing, short and long press. Pure logic, no ESP-IDF
// dependencies, so it is tested on the PC (firmware/test/host).
#pragma once

#include <cstdint>
#include <optional>

namespace board {

enum class ButtonEvent : uint8_t {
    ShortPress,  // released before kLongPressMs
    LongPress,   // held for kLongPressMs; reported while still held, the release gives nothing
};

class PressDetector {
public:
    static constexpr uint32_t kDebounceMs = 30;
    static constexpr uint32_t kLongPressMs = 3000;

    // Feed the raw button state (true = pressed) with a millisecond clock. Call it regularly
    // (every 10 ms); the clock may wrap around.
    std::optional<ButtonEvent> update(bool raw_pressed, uint32_t now_ms);

    // Debounced state.
    bool pressed() const { return stable_; }

private:
    bool raw_ = false;           // last raw sample
    uint32_t raw_since_ = 0;     // time the raw state last changed
    bool stable_ = false;        // debounced state
    uint32_t pressed_since_ = 0; // start of the current press (first raw edge)
    bool long_reported_ = false; // long press already reported for the current press
};

}  // namespace board
