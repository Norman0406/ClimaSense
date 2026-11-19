// The I2C bus as the sensor drivers see it. Pure interface, no ESP-IDF dependencies:
// EspI2cBus implements it on the chip, a GoogleMock mock in the unit tests (firmware/test/host).
#pragma once

#include <cstdint>
#include <expected>
#include <span>

namespace sensors {

enum class I2cError : uint8_t {
    Nack,     // no device acknowledged the address, or it refused a byte
    Timeout,  // the transfer did not complete: a line held low, pull-ups missing or unpowered
    Other,    // invalid argument or driver failure
};

constexpr const char *to_string(I2cError error)
{
    switch (error) {
    case I2cError::Nack:    return "NACK";
    case I2cError::Timeout: return "timeout";
    case I2cError::Other:   return "error";
    }
    return "?";
}

using I2cResult = std::expected<void, I2cError>;

// One I2C bus. Addresses are 7-bit. Not thread-safe: each bus has exactly one owner
// (the sensor task for the sensor bus).
class I2cBus {
public:
    virtual ~I2cBus() = default;

    // Sends only the address (write direction); succeeds if a device acknowledges.
    virtual I2cResult probe(uint8_t address) = 0;

    // One transfer each: start, address, data, stop.
    virtual I2cResult write(uint8_t address, std::span<const uint8_t> data) = 0;
    virtual I2cResult read(uint8_t address, std::span<uint8_t> data) = 0;

    // Write, repeated start, read: register access (BMP580).
    virtual I2cResult write_read(uint8_t address, std::span<const uint8_t> tx, std::span<uint8_t> rx) = 0;

protected:
    I2cBus() = default;
    I2cBus(const I2cBus &) = delete;
    I2cBus &operator=(const I2cBus &) = delete;
};

}  // namespace sensors
