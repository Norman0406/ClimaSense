// Text ring buffer for the last log lines. Pure logic, no ESP-IDF dependencies, tested on the PC.
// On the chip its storage lives in RTC_NOINIT memory, which keeps its content across a software
// reset, panic or watchdog reset, but not across a power cut.
#pragma once

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <span>
#include <string_view>

namespace diagnostics {

// Plain data, no constructor: the memory is not initialised at start-up. After a power-on it
// holds garbage, which LogRing::valid() rejects.
template <std::size_t N>
struct LogRingStorage {
    uint32_t magic;
    uint32_t head;         // next write position, 0..N-1
    uint32_t used;         // bytes held, 0..N
    uint32_t overwritten;  // non-zero once old bytes have been overwritten
    char data[N];
};

template <std::size_t N>
class LogRing {
public:
    static_assert(N > 0);
    static constexpr uint32_t kMagic = 0x52474f4cu;  // "LOGR"

    explicit constexpr LogRing(LogRingStorage<N> &storage) : s_(storage) {}

    // True if the storage holds a ring this code wrote (and not power-on garbage).
    bool valid() const
    {
        return s_.magic == kMagic && s_.head < N && s_.used <= N && s_.overwritten <= 1;
    }

    void clear()
    {
        s_.head = 0;
        s_.used = 0;
        s_.overwritten = 0;
        s_.magic = kMagic;
    }

    // Appends text; once full, the oldest bytes are overwritten.
    void append(std::string_view text)
    {
        if (!valid()) {
            clear();
        }
        // Counted before cutting: a text longer than the ring overwrites (part of) itself.
        const std::size_t total = s_.used + text.size();
        if (text.size() > N) {
            text.remove_prefix(text.size() - N);
        }
        for (const char c : text) {
            s_.data[s_.head] = c;
            s_.head = static_cast<uint32_t>((s_.head + 1) % N);
        }
        if (total > N) {
            s_.overwritten = 1;
        }
        s_.used = static_cast<uint32_t>(std::min(total, N));
    }

    // Copies the content into `out`, oldest first, and returns the number of bytes copied.
    // If old bytes were overwritten, the oldest (cut-off) line is dropped. If `out` is smaller
    // than the content, the newest bytes are kept.
    std::size_t copy_out(std::span<char> out) const
    {
        if (!valid()) {
            return 0;
        }
        std::size_t start = (s_.head + N - s_.used) % N;
        std::size_t length = s_.used;

        if (s_.overwritten) {
            std::size_t i = 0;
            while (i < length && s_.data[(start + i) % N] != '\n') {
                ++i;
            }
            const std::size_t skip = (i < length) ? i + 1 : length;
            start = (start + skip) % N;
            length -= skip;
        }
        if (length > out.size()) {
            start = (start + (length - out.size())) % N;
            length = out.size();
        }
        for (std::size_t i = 0; i < length; ++i) {
            out[i] = s_.data[(start + i) % N];
        }
        return length;
    }

private:
    LogRingStorage<N> &s_;
};

}  // namespace diagnostics
