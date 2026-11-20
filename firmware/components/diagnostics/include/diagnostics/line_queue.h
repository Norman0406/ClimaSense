// A small fixed-size queue of text lines, for log lines waiting to be sent over MQTT. Pure, no heap,
// tested on the PC. Not thread-safe by itself: the log hook and the sender share it under a lock.
#pragma once

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <span>
#include <string_view>

namespace diagnostics {

template <std::size_t Count, std::size_t Size>
class LineQueue {
public:
    // Adds a line (cut to Size bytes). When full, the new line is dropped and counted: the older
    // lines, often the cause, are kept.
    void push(std::string_view line)
    {
        if (used_ == Count) {
            ++dropped_;
            return;
        }
        Slot &slot = slots_[(head_ + used_) % Count];
        slot.length = std::min(line.size(), Size);
        std::copy_n(line.begin(), slot.length, slot.text.begin());
        ++used_;
    }

    // Copies the oldest line into `out` and removes it; returns its length, 0 if the queue is empty.
    std::size_t pop(std::span<char> out)
    {
        if (used_ == 0) {
            return 0;
        }
        const Slot &slot = slots_[head_];
        const std::size_t n = std::min(slot.length, out.size());
        std::copy_n(slot.text.begin(), n, out.begin());
        head_ = (head_ + 1) % Count;
        --used_;
        return n;
    }

    std::size_t size() const { return used_; }

    // Lines dropped because the queue was full, since the last call.
    uint32_t take_dropped()
    {
        const uint32_t d = dropped_;
        dropped_ = 0;
        return d;
    }

private:
    struct Slot {
        std::array<char, Size> text{};
        std::size_t length = 0;
    };
    std::array<Slot, Count> slots_{};
    std::size_t head_ = 0;
    std::size_t used_ = 0;
    uint32_t dropped_ = 0;
};

}  // namespace diagnostics
