#include "board/button_logic.h"

namespace board {

std::optional<ButtonEvent> PressDetector::update(bool raw_pressed, uint32_t now_ms)
{
    if (raw_pressed != raw_) {
        raw_ = raw_pressed;
        raw_since_ = now_ms;
    }

    // Unsigned subtraction keeps the time differences right across a clock wrap-around.
    if (raw_ != stable_ && now_ms - raw_since_ >= kDebounceMs) {
        stable_ = raw_;
        if (stable_) {
            pressed_since_ = raw_since_;
            long_reported_ = false;
        } else if (!long_reported_) {
            return ButtonEvent::ShortPress;
        }
    }

    // raw_ as well: a button let go just before the threshold is still "pressed" during the
    // release debounce, and must give a short press, not a long one.
    if (stable_ && raw_ && !long_reported_ && now_ms - pressed_since_ >= kLongPressMs) {
        long_reported_ = true;
        return ButtonEvent::LongPress;
    }

    return std::nullopt;
}

}  // namespace board
