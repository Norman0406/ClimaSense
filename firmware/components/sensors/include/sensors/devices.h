// The devices on the sensor bus and the bus parameters they dictate. Pure, no ESP-IDF dependencies.
#pragma once

#include <array>
#include <cstdint>

namespace sensors {

struct DeviceInfo {
    const char *name;
    uint8_t address;  // 7-bit
};

inline constexpr DeviceInfo kSht45{"SHT45", 0x44};
inline constexpr DeviceInfo kBmp580{"BMP580", 0x47};  // 0x47 because the board ties SDO high
inline constexpr DeviceInfo kSgp41{"SGP41", 0x59};
inline constexpr DeviceInfo kScd41{"SCD41", 0x62};

inline constexpr std::array kSensorBusDevices{kSht45, kBmp580, kSgp41, kScd41};

// The SCD41 allows at most 100 kHz; the other three are faster, so it sets the bus clock.
inline constexpr uint32_t kSensorBusHz = 100'000;

// The slowest start-up after the sensor rail comes on: the SCD41 needs up to 1000 ms before it
// answers on I2C. Nothing on the bus is addressed earlier.
inline constexpr uint32_t kPowerUpMs = 1000;

}  // namespace sensors
