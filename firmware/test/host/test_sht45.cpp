#include <algorithm>
#include <array>
#include <cstdint>
#include <expected>
#include <span>

#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include "mock_i2c_bus.h"
#include "sensors/sensirion.h"
#include "sensors/sht45.h"

using sensors::I2cError;
using sensors::I2cResult;
using sensors::SensorError;
using sensors::Sht45;
using ::testing::_;
using ::testing::ElementsAre;
using ::testing::Return;
using ::testing::SizeIs;
using ::testing::StrictMock;

namespace {

// CRCs computed independently of the code under test (Python, polynomial 0x31, init 0xFF).
constexpr uint8_t kCrc6666 = 0x93;
constexpr uint8_t kCrc0000 = 0x81;
constexpr uint8_t kCrcFFFF = 0xAC;
constexpr uint8_t kCrc1234 = 0x37;
constexpr uint8_t kCrc5678 = 0x7D;

// Action for read(): fills the buffer with `bytes` and succeeds.
auto respond(std::array<uint8_t, 6> bytes)
{
    return [bytes](uint8_t, std::span<uint8_t> out) {
        std::copy(bytes.begin(), bytes.end(), out.begin());
        return I2cResult{};
    };
}

class Sht45Test : public ::testing::Test {
protected:
    StrictMock<MockI2cBus> bus;
    Sht45 sht{bus};
};

}  // namespace

// --- CRC and framing ---------------------------------------------------------------------

TEST(Sensirion, Crc8MatchesTheDatasheetExample)
{
    const uint8_t data[] = {0xBE, 0xEF};
    EXPECT_EQ(sensors::sensirion::crc8(data), 0x92);
}

TEST(Sensirion, Crc8MatchesIndependentValues)
{
    const uint8_t a[] = {0x66, 0x66};
    const uint8_t b[] = {0x00, 0x00};
    const uint8_t c[] = {0xFF, 0xFF};
    EXPECT_EQ(sensors::sensirion::crc8(a), kCrc6666);
    EXPECT_EQ(sensors::sensirion::crc8(b), kCrc0000);
    EXPECT_EQ(sensors::sensirion::crc8(c), kCrcFFFF);
}

TEST(Sensirion, PackWordAppendsTheCrc)
{
    std::array<uint8_t, 3> out{};
    sensors::sensirion::pack_word(0xBEEF, out);
    EXPECT_THAT(out, ElementsAre(0xBE, 0xEF, 0x92));
}

TEST(Sensirion, UnpackWordsRejectsABadCrc)
{
    const std::array<uint8_t, 6> rx{0x12, 0x34, kCrc1234, 0x56, 0x78, kCrc5678 ^ 0x01};
    std::array<uint16_t, 2> words{};
    const auto r = sensors::sensirion::unpack_words<2>(rx, words);
    ASSERT_FALSE(r);
    EXPECT_EQ(r.error(), SensorError::Crc);
}

// --- Conversion ----------------------------------------------------------------------------

TEST(Sht45Conversion, TemperatureEndpointsAndMidValue)
{
    EXPECT_EQ(Sht45::temperature_mc(0), -45'000);
    EXPECT_EQ(Sht45::temperature_mc(0xFFFF), 130'000);
    EXPECT_EQ(Sht45::temperature_mc(0x6666), 25'000);  // 0x6666 / 0xFFFF = 0.4 exactly
}

TEST(Sht45Conversion, HumidityIsClampedToZeroAndHundredPercent)
{
    EXPECT_EQ(Sht45::humidity_mpercent(0), 0);             // formula gives -6 %
    EXPECT_EQ(Sht45::humidity_mpercent(0xFFFF), 100'000);  // formula gives 119 %
    EXPECT_EQ(Sht45::humidity_mpercent(0x6666), 44'000);   // -6 + 125 * 0.4
}

TEST(Sht45Conversion, HumidityJustInsideTheRangeIsNotClamped)
{
    // raw 3146: -6 + 125 * 3146 / 65535 = 0.0006 %, rounds to 1 milli-percent.
    EXPECT_EQ(Sht45::humidity_mpercent(3146), 1);
}

// --- Commands --------------------------------------------------------------------------------

TEST_F(Sht45Test, StartMeasurementSendsTheHighPrecisionCommand)
{
    EXPECT_CALL(bus, write(0x44, Bytes({0xFD}))).WillOnce(Return(I2cResult{}));
    EXPECT_TRUE(sht.start_measurement());
}

TEST_F(Sht45Test, ReadMeasurementConvertsBothValues)
{
    EXPECT_CALL(bus, read(0x44, SizeIs(6)))
        .WillOnce(respond({0x66, 0x66, kCrc6666, 0x66, 0x66, kCrc6666}));
    const auto r = sht.read_measurement();
    ASSERT_TRUE(r);
    EXPECT_EQ(r->temperature_mc, 25'000);
    EXPECT_EQ(r->humidity_mpercent, 44'000);
}

TEST_F(Sht45Test, ReadMeasurementRejectsABadCrc)
{
    EXPECT_CALL(bus, read(0x44, _)).WillOnce(respond({0x66, 0x66, kCrc6666, 0x66, 0x66, 0x00}));
    const auto r = sht.read_measurement();
    ASSERT_FALSE(r);
    EXPECT_EQ(r.error(), SensorError::Crc);
}

TEST_F(Sht45Test, ReadingTooEarlyIsANack)
{
    // The SHT45 does not acknowledge its address while it is still measuring.
    EXPECT_CALL(bus, read(0x44, _)).WillOnce(Return(std::unexpected(I2cError::Nack)));
    const auto r = sht.read_measurement();
    ASSERT_FALSE(r);
    EXPECT_EQ(r.error(), SensorError::Nack);
}

TEST_F(Sht45Test, BusTimeoutIsPassedOn)
{
    EXPECT_CALL(bus, write(0x44, _)).WillOnce(Return(std::unexpected(I2cError::Timeout)));
    const auto r = sht.start_measurement();
    ASSERT_FALSE(r);
    EXPECT_EQ(r.error(), SensorError::Timeout);
}

TEST_F(Sht45Test, SerialNumberIsTwoWords)
{
    {
        ::testing::InSequence order;
        EXPECT_CALL(bus, write(0x44, Bytes({0x89}))).WillOnce(Return(I2cResult{}));
        EXPECT_CALL(bus, read(0x44, SizeIs(6)))
            .WillOnce(respond({0x12, 0x34, kCrc1234, 0x56, 0x78, kCrc5678}));
    }
    ASSERT_TRUE(sht.request_serial());
    const auto serial = sht.read_serial();
    ASSERT_TRUE(serial);
    EXPECT_EQ(*serial, 0x12345678u);
}

TEST_F(Sht45Test, SoftResetSendsItsCommand)
{
    EXPECT_CALL(bus, write(0x44, Bytes({0x94}))).WillOnce(Return(I2cResult{}));
    EXPECT_TRUE(sht.soft_reset());
}
