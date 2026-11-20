// The captive portal's DNS answers: every name points at the device. Pure, tested on the PC.
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>

namespace portal {

inline constexpr uint32_t kDnsTtlSeconds = 60;  // short: the redirect should not outlive the portal

// Writes the answer to `query` into `out` and returns its length, or nothing if the query is not
// one to answer: malformed, itself a response, not a standard query, or not exactly one question.
// A and ANY questions get one A record with `ip`; other types (AAAA and so on) get an empty
// answer, so clients fall back to IPv4. Extra records in the query (such as EDNS) are dropped.
std::optional<std::size_t> build_dns_answer(std::span<const uint8_t> query, std::array<uint8_t, 4> ip,
                                            std::span<uint8_t> out);

}  // namespace portal
