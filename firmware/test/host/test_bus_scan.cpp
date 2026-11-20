#include <cstdint>
#include <expected>

#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include "mock_i2c_bus.h"
#include "sensors/bus_scan.h"
#include "sensors/devices.h"

using sensors::I2cError;
using sensors::I2cResult;
using sensors::kSensorBusDevices;
using ::testing::_;
using ::testing::Gt;
using ::testing::Lt;
using ::testing::InSequence;
using ::testing::NiceMock;
using ::testing::Return;

namespace {

const I2cResult kAck{};
const I2cResult kNack = std::unexpected(I2cError::Nack);
const I2cResult kTimeout = std::unexpected(I2cError::Timeout);

// A bus where nothing answers unless a test says otherwise.
class BusScanTest : public ::testing::Test {
protected:
    BusScanTest() { ON_CALL(bus, probe(_)).WillByDefault(Return(kNack)); }

    void answer(uint8_t address) { ON_CALL(bus, probe(address)).WillByDefault(Return(kAck)); }

    void answer_all_sensors()
    {
        for (const auto &d : kSensorBusDevices) {
            answer(d.address);
        }
    }

    NiceMock<MockI2cBus> bus;
};

}  // namespace

TEST_F(BusScanTest, ProbesEveryNonReservedAddressOnceInOrder)
{
    {
        InSequence order;
        for (unsigned a = sensors::kFirstScanAddress; a <= sensors::kLastScanAddress; ++a) {
            EXPECT_CALL(bus, probe(static_cast<uint8_t>(a))).WillOnce(Return(kNack));
        }
    }
    const auto result = sensors::scan_bus(bus);
    EXPECT_TRUE(result.responding.none());
    EXPECT_FALSE(result.fault);
}

TEST_F(BusScanTest, FindsAllFourSensors)
{
    answer_all_sensors();
    const auto result = sensors::scan_bus(bus);

    EXPECT_EQ(result.responding.count(), 4u);
    EXPECT_TRUE(result.found(0x44));  // SHT45
    EXPECT_TRUE(result.found(0x47));  // BMP580
    EXPECT_TRUE(result.found(0x59));  // SGP41
    EXPECT_TRUE(result.found(0x62));  // SCD41
    EXPECT_FALSE(result.fault);

    const auto report = sensors::compare(result, kSensorBusDevices);
    EXPECT_TRUE(report.missing.none());
    EXPECT_TRUE(report.unexpected.none());
    EXPECT_TRUE(report.all_as_expected(result));
}

TEST_F(BusScanTest, ReportsAMissingSensor)
{
    answer(sensors::kSht45.address);
    answer(sensors::kBmp580.address);
    answer(sensors::kSgp41.address);  // no SCD41

    const auto result = sensors::scan_bus(bus);
    const auto report = sensors::compare(result, kSensorBusDevices);

    EXPECT_EQ(report.missing.count(), 1u);
    EXPECT_TRUE(report.missing.test(sensors::kScd41.address));
    EXPECT_TRUE(report.unexpected.none());
    EXPECT_FALSE(report.all_as_expected(result));
}

TEST_F(BusScanTest, ReportsAnUnexpectedDevice)
{
    answer_all_sensors();
    answer(0x50);

    const auto result = sensors::scan_bus(bus);
    const auto report = sensors::compare(result, kSensorBusDevices);

    EXPECT_TRUE(report.missing.none());
    EXPECT_EQ(report.unexpected.count(), 1u);
    EXPECT_TRUE(report.unexpected.test(0x50));
    EXPECT_FALSE(report.all_as_expected(result));
}

TEST_F(BusScanTest, TimeoutStopsTheScanAndIsReportedAsFault)
{
    // A hung bus would otherwise cost one timeout per address. Every address up to the
    // failing one is probed exactly once, nothing after it. (Once a mock method has an
    // EXPECT_CALL, every call must match one, so the probes before 0x44 are listed too.)
    EXPECT_CALL(bus, probe(Lt(0x44))).Times(0x44 - sensors::kFirstScanAddress);
    EXPECT_CALL(bus, probe(0x44)).WillOnce(Return(kTimeout));
    EXPECT_CALL(bus, probe(Gt(0x44))).Times(0);

    const auto result = sensors::scan_bus(bus);

    ASSERT_TRUE(result.fault);
    EXPECT_EQ(result.fault->address, 0x44);
    EXPECT_EQ(result.fault->error, I2cError::Timeout);
    EXPECT_FALSE(sensors::compare(result, kSensorBusDevices).all_as_expected(result));
}

TEST_F(BusScanTest, NackIsNotAFault)
{
    const auto result = sensors::scan_bus(bus);
    EXPECT_FALSE(result.fault);
    EXPECT_EQ(sensors::compare(result, kSensorBusDevices).missing.count(), 4u);
}

TEST_F(BusScanTest, ScansOnlyTheGivenRange)
{
    EXPECT_CALL(bus, probe(_)).Times(0);
    EXPECT_CALL(bus, probe(0x44)).WillOnce(Return(kAck));
    EXPECT_CALL(bus, probe(0x45)).WillOnce(Return(kNack));

    const auto result = sensors::scan_bus(bus, 0x44, 0x45);
    EXPECT_EQ(result.responding.count(), 1u);
    EXPECT_TRUE(result.found(0x44));
}

TEST(BusScanLimits, RangeEndingAtTheTopAddressTerminates)
{
    NiceMock<MockI2cBus> bus;
    ON_CALL(bus, probe(_)).WillByDefault(Return(kNack));
    EXPECT_CALL(bus, probe(_)).Times(128 - 0x70);  // 0x70..0x7f, then stops
    const auto result = sensors::scan_bus(bus, 0x70, 0xff);
    EXPECT_FALSE(result.fault);
}
