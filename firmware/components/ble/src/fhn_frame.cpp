#include "ble/fhn_frame.h"

#include <cstring>

namespace ble {

namespace {

constexpr uint8_t kServiceData16 = 0x16;  // AD type: service data, 16-bit UUID
constexpr uint8_t kUuidLow = 0xAA;        // 0xFEAA, little-endian on air
constexpr uint8_t kUuidHigh = 0xFE;

// The frame in one service data structure (the bytes after the AD type).
std::optional<FhnFrame> from_service_data(std::span<const uint8_t> data)
{
    if (data.size() < 3 || data[0] != kUuidLow || data[1] != kUuidHigh) {
        return std::nullopt;
    }
    const uint8_t type = data[2];
    if (type != kFhnFrame && type != kFhnFrameProtected) {
        return std::nullopt;
    }
    const std::span<const uint8_t> rest = data.subspan(3);
    for (const std::size_t eid_len : {std::size_t{20}, std::size_t{32}}) {
        if (rest.size() != eid_len && rest.size() != eid_len + 1) {
            continue;
        }
        FhnFrame frame;
        frame.type = type;
        frame.eid_len = static_cast<uint8_t>(eid_len);
        std::memcpy(frame.eid.data(), rest.data(), eid_len);
        if (rest.size() == eid_len + 1) {
            frame.flags = rest[eid_len];
        }
        return frame;
    }
    return std::nullopt;
}

}  // namespace

std::optional<FhnFrame> parse_fhn(std::span<const uint8_t> advertisement)
{
    std::size_t at = 0;
    while (at < advertisement.size()) {
        const std::size_t length = advertisement[at];  // counts the type byte and the data
        if (length == 0) {
            break;  // padding: the significant part ends here
        }
        if (at + 1 + length > advertisement.size()) {
            return std::nullopt;  // a structure that runs past the end
        }
        if (advertisement[at + 1] == kServiceData16) {
            if (const auto frame = from_service_data(advertisement.subspan(at + 2, length - 1))) {
                return frame;
            }
        }
        at += 1 + length;
    }
    return std::nullopt;
}

}  // namespace ble
