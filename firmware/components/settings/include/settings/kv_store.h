// Key-value storage for settings, as the load/save logic sees it. Pure interface: NvsStore
// implements it on the chip, an in-memory fake in the unit tests.
#pragma once

#include <cstddef>
#include <cstdint>
#include <expected>
#include <span>
#include <string_view>

namespace settings {

enum class KvError : uint8_t {
    NotFound,  // no value stored under this key
    TooLong,   // the stored value does not fit the buffer
    Failed,    // the storage itself failed
};

class KvStore {
public:
    virtual ~KvStore() = default;

    // Copies the value into `out` with a terminating NUL and returns its length.
    virtual std::expected<std::size_t, KvError> get(const char *key, std::span<char> out) = 0;
    virtual std::expected<void, KvError> set(const char *key, std::string_view value) = 0;
    // Makes the writes since the last commit durable.
    virtual std::expected<void, KvError> commit() = 0;

protected:
    KvStore() = default;
    KvStore(const KvStore &) = delete;
    KvStore &operator=(const KvStore &) = delete;
};

}  // namespace settings
