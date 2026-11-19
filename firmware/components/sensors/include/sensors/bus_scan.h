// I2C address scan and its comparison with the expected devices. Pure logic on top of I2cBus,
// tested on the PC.
#pragma once

#include <bitset>
#include <cstdint>
#include <optional>
#include <span>

#include "sensors/devices.h"
#include "sensors/i2c_bus.h"

namespace sensors {

// Addresses below 0x08 and above 0x77 are reserved by the I2C specification.
inline constexpr uint8_t kFirstScanAddress = 0x08;
inline constexpr uint8_t kLastScanAddress = 0x77;

struct BusFault {
    uint8_t address;  // address being probed when the bus failed
    I2cError error;   // Timeout or Other; a NACK is not a fault
};

struct ScanResult {
    std::bitset<128> responding;    // addresses that acknowledged
    std::optional<BusFault> fault;  // set if the scan stopped early because the bus failed

    bool found(uint8_t address) const { return address < 128 && responding.test(address); }
};

// Probes every address from `first` to `last` once, in order. Stops at the first timeout or
// driver error: a hung bus would otherwise cost a timeout per address.
ScanResult scan_bus(I2cBus &bus, uint8_t first = kFirstScanAddress, uint8_t last = kLastScanAddress);

struct ScanReport {
    std::bitset<128> missing;     // expected, but did not acknowledge
    std::bitset<128> unexpected;  // acknowledged, but not expected
    bool all_as_expected(const ScanResult &result) const
    {
        return !result.fault && missing.none() && unexpected.none();
    }
};

ScanReport compare(const ScanResult &result, std::span<const DeviceInfo> expected);

}  // namespace sensors
