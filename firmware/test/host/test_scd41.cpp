#include <algorithm>
#include <cstdint>
#include <expected>
#include <initializer_list>
#include <span>
#include <vector>

#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include "mock_i2c_bus.h"
#include "sensors/scd41.h"

using sensors::I2cError;
using sensors::I2cResult;
using sensors::Scd41;
using sensors::SensorError;
using ::testing::_;
using ::testing::ElementsAre;
using ::testing::InSequence;
using ::testing::Return;
using ::testing::SizeIs;
using ::testing::StrictMock;

namespace {

const I2cResult kOk{};

// Action for read(): fills the buffer with `bytes` and succeeds.
auto respond(std::initializer_list<uint8_t> bytes)
{
    return [data = std::vector<uint8_t>(bytes)](uint8_t, std::span<uint8_t> rx) {
        std::copy(data.begin(), data.end(), rx.begin());
        return I2cResult{};
    };
}

std::vector<uint32_t> g_delays;
void record_delay(uint32_t ms) { g_delays.push_back(ms); }

class Scd41Test : public ::testing::Test {
protected:
    Scd41Test() { g_delays.clear(); }

    StrictMock<MockI2cBus> bus;
    Scd41 scd{bus, record_delay};
};

}  // namespace

// --- Conversion ------------------------------------------------------------------------------

TEST(Scd41Conversion, DatasheetExampleValues)
{
    EXPECT_EQ(Scd41::temperature_mc(0x6667), 25'003);       // 25.0027 degrees C
    EXPECT_EQ(Scd41::humidity_mpercent(0x5EB9), 37'002);    // 37.0016 %
}

TEST(Scd41Conversion, Endpoints)
{
    EXPECT_EQ(Scd41::temperature_mc(0), -45'000);
    EXPECT_EQ(Scd41::temperature_mc(0xFFFF), 130'000);
    EXPECT_EQ(Scd41::humidity_mpercent(0), 0);
    EXPECT_EQ(Scd41::humidity_mpercent(0xFFFF), 100'000);
}

// --- Commands --------------------------------------------------------------------------------

TEST_F(Scd41Test, StopPeriodicMeasurementSendsItsCommand)
{
    EXPECT_CALL(bus, write(0x62, Bytes({0x3F, 0x86}))).WillOnce(Return(kOk));
    EXPECT_TRUE(scd.stop_periodic_measurement());
    EXPECT_TRUE(g_delays.empty());  // the 500 ms are the caller's
}

TEST_F(Scd41Test, StartSingleShotSendsItsCommandWithoutWaiting)
{
    EXPECT_CALL(bus, write(0x62, Bytes({0x21, 0x9D}))).WillOnce(Return(kOk));
    EXPECT_TRUE(scd.start_single_shot());
    EXPECT_TRUE(g_delays.empty());  // the 5 s are the caller's
}

TEST_F(Scd41Test, ReadMeasurementDecodesTheDatasheetExample)
{
    InSequence order;
    EXPECT_CALL(bus, write(0x62, Bytes({0xEC, 0x05}))).WillOnce(Return(kOk));
    EXPECT_CALL(bus, read(0x62, SizeIs(9)))
        .WillOnce(respond({0x01, 0xF4, 0x33, 0x66, 0x67, 0xA2, 0x5E, 0xB9, 0x3C}));
    const auto r = scd.read_measurement();
    ASSERT_TRUE(r);
    EXPECT_EQ(r->co2_ppm, 500);
    EXPECT_EQ(r->temperature_mc, 25'003);
    EXPECT_EQ(r->humidity_mpercent, 37'002);
    EXPECT_THAT(g_delays, ElementsAre(1u));  // 1 ms between command and read
}

TEST_F(Scd41Test, ReadMeasurementRejectsABadCrc)
{
    InSequence order;
    EXPECT_CALL(bus, write(0x62, _)).WillOnce(Return(kOk));
    EXPECT_CALL(bus, read(0x62, _))
        .WillOnce(respond({0x01, 0xF4, 0x33, 0x66, 0x67, 0xA2, 0x5E, 0xB9, 0x3D}));
    const auto r = scd.read_measurement();
    ASSERT_FALSE(r);
    EXPECT_EQ(r.error(), SensorError::Crc);
}

TEST_F(Scd41Test, DataReadyLooksAtTheLowElevenBits)
{
    {
        InSequence order;
        EXPECT_CALL(bus, write(0x62, Bytes({0xE4, 0xB8}))).WillOnce(Return(kOk));
        EXPECT_CALL(bus, read(0x62, SizeIs(3))).WillOnce(respond({0x80, 0x06, 0x04}));
        EXPECT_CALL(bus, write(0x62, Bytes({0xE4, 0xB8}))).WillOnce(Return(kOk));
        EXPECT_CALL(bus, read(0x62, SizeIs(3))).WillOnce(respond({0x80, 0x00, 0xA2}));
    }
    const auto ready = scd.data_ready();
    ASSERT_TRUE(ready);
    EXPECT_TRUE(*ready);  // 0x8006: low bits set
    const auto not_ready = scd.data_ready();
    ASSERT_TRUE(not_ready);
    EXPECT_FALSE(*not_ready);  // 0x8000: only a high bit set
}

TEST_F(Scd41Test, AmbientPressureMatchesTheDatasheetExample)
{
    // 98700 Pa -> 987 hPa = 0x03DB, CRC 0x42.
    EXPECT_CALL(bus, write(0x62, Bytes({0xE0, 0x00, 0x03, 0xDB, 0x42}))).WillOnce(Return(kOk));
    EXPECT_TRUE(scd.set_ambient_pressure(98'700'000));
    EXPECT_THAT(g_delays, ElementsAre(1u));
}

TEST_F(Scd41Test, AmbientPressureIsRoundedToWholeHectopascal)
{
    // 101325 Pa -> 1013 hPa (0x03F5, CRC 0xDB).
    EXPECT_CALL(bus, write(0x62, Bytes({0xE0, 0x00, 0x03, 0xF5, 0xDB}))).WillOnce(Return(kOk));
    EXPECT_TRUE(scd.set_ambient_pressure(101'325'000));
}

TEST_F(Scd41Test, AmbientPressureIsClampedToTheAcceptedRange)
{
    InSequence order;
    EXPECT_CALL(bus, write(0x62, Bytes({0xE0, 0x00, 0x02, 0xBC, 0x9A}))).WillOnce(Return(kOk));  // 700
    EXPECT_CALL(bus, write(0x62, Bytes({0xE0, 0x00, 0x04, 0xB0, 0xBD}))).WillOnce(Return(kOk));  // 1200
    EXPECT_TRUE(scd.set_ambient_pressure(50'000'000));   // 500 hPa
    EXPECT_TRUE(scd.set_ambient_pressure(130'000'000));  // 1300 hPa
}

TEST_F(Scd41Test, SerialNumberIsThreeWords)
{
    InSequence order;
    EXPECT_CALL(bus, write(0x62, Bytes({0x36, 0x82}))).WillOnce(Return(kOk));
    EXPECT_CALL(bus, read(0x62, SizeIs(9)))
        .WillOnce(respond({0x12, 0x34, 0x37, 0x56, 0x78, 0x7D, 0x9A, 0xBC, 0xE0}));
    const auto serial = scd.read_serial();
    ASSERT_TRUE(serial);
    EXPECT_EQ(*serial, 0x123456789ABCull);
}

TEST_F(Scd41Test, SelfCalibrationEnabledIsReadAsAWord)
{
    InSequence order;
    EXPECT_CALL(bus, write(0x62, Bytes({0x23, 0x13}))).WillOnce(Return(kOk));
    EXPECT_CALL(bus, read(0x62, SizeIs(3))).WillOnce(respond({0x00, 0x01, 0xB0}));
    const auto asc = scd.automatic_self_calibration_enabled();
    ASSERT_TRUE(asc);
    EXPECT_TRUE(*asc);
}

TEST_F(Scd41Test, FailedCommandIsNotFollowedByARead)
{
    EXPECT_CALL(bus, write(0x62, _)).WillOnce(Return(std::unexpected(I2cError::Nack)));
    const auto r = scd.read_measurement();  // StrictMock: a read here would fail the test
    ASSERT_FALSE(r);
    EXPECT_EQ(r.error(), SensorError::Nack);
    EXPECT_TRUE(g_delays.empty());
}
