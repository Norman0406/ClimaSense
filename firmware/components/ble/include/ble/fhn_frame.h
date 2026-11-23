// The Bluetooth advertisement of a Find Hub tag (Google's Find Hub Network, formerly Find My
// Device network). Pure, tested on the PC.
//
// A tag sends, at least every 2 s, service data for the 16-bit UUID 0xFEAA: a frame type (0x40,
// or 0x41 while the tag is in unwanted tracking protection mode), an ephemeral identifier (EID)
// of 20 bytes (32 with extended advertising) that changes about every 17 minutes, and optionally
// one byte of hashed flags. Only the holder of the tag's key can tell whose tag an EID belongs
// to or read the flags; the firmware only passes them on (docs/research/presence-sensing.md).
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>

namespace ble {

inline constexpr std::size_t kMaxEidBytes = 32;
inline constexpr uint8_t kFhnFrame = 0x40;
inline constexpr uint8_t kFhnFrameProtected = 0x41;  // unwanted tracking protection mode

struct FhnFrame {
    std::array<uint8_t, kMaxEidBytes> eid{};
    uint8_t eid_len = 0;           // 20 or 32
    uint8_t type = 0;              // kFhnFrame or kFhnFrameProtected
    std::optional<uint8_t> flags;  // the hashed flags byte, if the tag sends one

    std::span<const uint8_t> eid_bytes() const { return {eid.data(), eid_len}; }
};

// The Find Hub frame in an advertisement's data (its sequence of length, type, data structures),
// if it carries one. Anything malformed or of another length gives nothing.
std::optional<FhnFrame> parse_fhn(std::span<const uint8_t> advertisement);

}  // namespace ble
