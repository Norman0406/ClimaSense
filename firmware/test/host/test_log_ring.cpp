#include <array>
#include <cstddef>
#include <cstring>
#include <string>
#include <string_view>

#include <gtest/gtest.h>

#include "diagnostics/log_ring.h"

using diagnostics::LogRing;
using diagnostics::LogRingStorage;

namespace {

constexpr std::size_t kN = 16;  // small, so wrapping is easy to follow

class LogRingTest : public ::testing::Test {
protected:
    LogRingTest() { std::memset(&storage, 0xA5, sizeof(storage)); }  // like RAM after power-on

    std::string content(std::size_t out_size = kN) const
    {
        std::string out(out_size, '\0');
        out.resize(ring.copy_out(out));
        return out;
    }

    LogRingStorage<kN> storage;
    LogRing<kN> ring{storage};
};

}  // namespace

TEST_F(LogRingTest, PowerOnGarbageIsInvalidAndReadsEmpty)
{
    EXPECT_FALSE(ring.valid());
    EXPECT_EQ(content(), "");
}

TEST_F(LogRingTest, ClearMakesItValidAndEmpty)
{
    ring.clear();
    EXPECT_TRUE(ring.valid());
    EXPECT_EQ(content(), "");
}

TEST_F(LogRingTest, AppendToGarbageClearsFirst)
{
    ring.append("x\n");
    EXPECT_TRUE(ring.valid());
    EXPECT_EQ(content(), "x\n");
}

TEST_F(LogRingTest, KeepsTextBelowCapacityUnchanged)
{
    ring.clear();
    ring.append("a\n");
    ring.append("b\n");
    EXPECT_EQ(content(), "a\nb\n");
}

TEST_F(LogRingTest, ExactlyFullWithoutOverwriteKeepsTheFirstLine)
{
    ring.clear();
    ring.append("aaaaaaa\n");
    ring.append("bbbbbbb\n");  // 16 bytes in total, nothing overwritten
    EXPECT_EQ(content(), "aaaaaaa\nbbbbbbb\n");
}

TEST_F(LogRingTest, WrapDropsTheCutOffOldestLine)
{
    ring.clear();
    ring.append("line1\n");
    ring.append("line2\n");
    ring.append("line3\n");  // 18 bytes: "li" of line1 overwritten
    EXPECT_EQ(content(), "line2\nline3\n");
}

TEST_F(LogRingTest, ManyWrapsLeaveWholeRecentLines)
{
    ring.clear();
    for (int i = 0; i < 100; ++i) {
        ring.append("line" + std::to_string(i) + "\n");
    }
    const std::string c = content();
    EXPECT_EQ(c, "line98\nline99\n");
}

TEST_F(LogRingTest, TextLongerThanCapacityKeepsOnlyItsEndAndDropsThePartialLine)
{
    ring.clear();
    ring.append("0123456789abcdefghi\n");  // 20 bytes, one line: nothing whole fits
    EXPECT_EQ(content(), "");
    ring.append("ok\n");
    EXPECT_EQ(content(), "ok\n");
}

TEST_F(LogRingTest, SmallOutputKeepsTheNewestBytes)
{
    ring.clear();
    ring.append("a\nb\nc\n");
    EXPECT_EQ(content(4), "b\nc\n");
}

TEST_F(LogRingTest, ContentSurvivesANewRingOnTheSameStorage)
{
    // What happens across a soft reset: the storage stays, the ring object is created anew.
    ring.clear();
    ring.append("before reset\n");
    LogRing<kN> after_reset{storage};
    ASSERT_TRUE(after_reset.valid());
    std::string out(kN, '\0');
    out.resize(after_reset.copy_out(out));
    EXPECT_EQ(out, "before reset\n");
}

TEST_F(LogRingTest, CorruptHeaderIsInvalid)
{
    ring.clear();
    ring.append("x\n");
    storage.head = kN;  // out of range
    EXPECT_FALSE(ring.valid());
    EXPECT_EQ(content(), "");
}
