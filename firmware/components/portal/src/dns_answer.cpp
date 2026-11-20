#include "portal/dns_answer.h"

#include <algorithm>

namespace portal {

namespace {

constexpr std::size_t kHeaderSize = 12;
constexpr uint16_t kFlagResponse = 0x8000;
constexpr uint16_t kFlagAuthoritative = 0x0400;
constexpr uint16_t kFlagRecursionDesired = 0x0100;
constexpr uint16_t kTypeA = 1;
constexpr uint16_t kTypeAny = 255;
constexpr uint16_t kClassIn = 1;
constexpr uint16_t kClassAny = 255;

uint16_t read16(std::span<const uint8_t> p, std::size_t at) { return static_cast<uint16_t>((p[at] << 8) | p[at + 1]); }

void write16(std::span<uint8_t> p, std::size_t at, uint16_t v)
{
    p[at] = static_cast<uint8_t>(v >> 8);
    p[at + 1] = static_cast<uint8_t>(v & 0xFF);
}

}  // namespace

std::optional<std::size_t> build_dns_answer(std::span<const uint8_t> query, std::array<uint8_t, 4> ip,
                                            std::span<uint8_t> out)
{
    if (query.size() < kHeaderSize) {
        return std::nullopt;
    }
    const uint16_t flags = read16(query, 2);
    const unsigned opcode = (flags >> 11) & 0x0F;
    if ((flags & kFlagResponse) != 0 || opcode != 0 || read16(query, 4) != 1) {
        return std::nullopt;
    }

    // The question's name: length-prefixed labels up to a zero byte. Compression pointers do not
    // belong in a question.
    std::size_t at = kHeaderSize;
    std::size_t name_length = 0;
    for (;;) {
        if (at >= query.size()) {
            return std::nullopt;
        }
        const uint8_t label = query[at];
        if (label == 0) {
            ++at;
            break;
        }
        if ((label & 0xC0) != 0) {
            return std::nullopt;
        }
        name_length += label + 1;
        if (name_length > 255) {
            return std::nullopt;
        }
        at += 1 + label;
    }
    if (at + 4 > query.size()) {
        return std::nullopt;
    }
    const uint16_t type = read16(query, at);
    const uint16_t klass = read16(query, at + 2);
    const std::size_t question_end = at + 4;

    const bool answer = (type == kTypeA || type == kTypeAny) && (klass == kClassIn || klass == kClassAny);
    const std::size_t length = question_end + (answer ? 16 : 0);
    if (out.size() < length) {
        return std::nullopt;
    }

    std::copy(query.begin(), query.begin() + static_cast<std::ptrdiff_t>(question_end), out.begin());
    write16(out, 2, static_cast<uint16_t>(kFlagResponse | kFlagAuthoritative | (flags & kFlagRecursionDesired)));
    write16(out, 4, 1);                        // one question
    write16(out, 6, answer ? 1 : 0);           // answers
    write16(out, 8, 0);                        // authority records
    write16(out, 10, 0);                       // additional records

    if (answer) {
        std::size_t a = question_end;
        write16(out, a, 0xC000 | kHeaderSize);  // name: pointer to the question's name
        write16(out, a + 2, kTypeA);
        write16(out, a + 4, kClassIn);
        out[a + 6] = static_cast<uint8_t>(kDnsTtlSeconds >> 24);
        out[a + 7] = static_cast<uint8_t>(kDnsTtlSeconds >> 16);
        out[a + 8] = static_cast<uint8_t>(kDnsTtlSeconds >> 8);
        out[a + 9] = static_cast<uint8_t>(kDnsTtlSeconds);
        write16(out, a + 10, 4);
        std::copy(ip.begin(), ip.end(), out.begin() + static_cast<std::ptrdiff_t>(a + 12));
    }
    return length;
}

}  // namespace portal
