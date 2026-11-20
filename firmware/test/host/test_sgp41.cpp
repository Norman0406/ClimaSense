#include <algorithm>
#include <cstdint>
#include <expected>
#include <fstream>
#include <initializer_list>
#include <span>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include "mock_i2c_bus.h"
#include "sensors/gas_index.h"
#include "sensors/sgp41.h"

using sensors::GasIndex;
using sensors::I2cError;
using sensors::I2cResult;
using sensors::SensorError;
using sensors::Sgp41;
using ::testing::_;
using ::testing::InSequence;
using ::testing::Return;
using ::testing::SizeIs;
using ::testing::StrictMock;

namespace {

const I2cResult kOk{};

auto respond(std::initializer_list<uint8_t> bytes)
{
    return [data = std::vector<uint8_t>(bytes)](uint8_t, std::span<uint8_t> rx) {
        std::copy(data.begin(), data.end(), rx.begin());
        return I2cResult{};
    };
}

class Sgp41Test : public ::testing::Test {
protected:
    StrictMock<MockI2cBus> bus;
    Sgp41 sgp{bus};
};

// Sensirion's test data: pairs of (raw VOC signal, VOC index from their floating-point variant).
std::vector<std::pair<uint16_t, int32_t>> load_voc_csv()
{
    std::vector<std::pair<uint16_t, int32_t>> rows;
    std::ifstream file(TEST_DATA_DIR "/sensirion_voc.csv");
    std::string line;
    while (std::getline(file, line)) {
        std::istringstream fields(line);
        std::string raw, index;
        if (std::getline(fields, raw, ',') && std::getline(fields, index)) {
            rows.emplace_back(static_cast<uint16_t>(std::stoi(raw)), std::stoi(index));
        }
    }
    return rows;
}

}  // namespace

// --- Compensation arguments ------------------------------------------------------------------

TEST(Sgp41Compensation, DefaultsAreFiftyPercentAndTwentyFiveDegrees)
{
    EXPECT_EQ(Sgp41::humidity_ticks(50'000), Sgp41::kDefaultHumidityTicks);       // 0x8000
    EXPECT_EQ(Sgp41::temperature_ticks(25'000), Sgp41::kDefaultTemperatureTicks); // 0x6666
}

TEST(Sgp41Compensation, RangeEndsAndClamping)
{
    EXPECT_EQ(Sgp41::humidity_ticks(0), 0);
    EXPECT_EQ(Sgp41::humidity_ticks(100'000), 65535);
    EXPECT_EQ(Sgp41::humidity_ticks(-5'000), 0);
    EXPECT_EQ(Sgp41::humidity_ticks(120'000), 65535);
    EXPECT_EQ(Sgp41::temperature_ticks(-45'000), 0);
    EXPECT_EQ(Sgp41::temperature_ticks(130'000), 65535);
    EXPECT_EQ(Sgp41::temperature_ticks(-60'000), 0);
    EXPECT_EQ(Sgp41::temperature_ticks(150'000), 65535);
}

TEST(Sgp41Compensation, IsTheInverseOfTheShtFormula)
{
    // 64 %RH -> 41942.4 -> 41942 (0xA3D6); 21.5 C -> 24903.3 -> 24903 (0x6147).
    EXPECT_EQ(Sgp41::humidity_ticks(64'000), 0xA3D6);
    EXPECT_EQ(Sgp41::temperature_ticks(21'500), 0x6147);
}

// --- Commands --------------------------------------------------------------------------------

TEST_F(Sgp41Test, MeasurementCommandCarriesHumidityAndTemperatureWithCrcs)
{
    EXPECT_CALL(bus, write(0x59, Bytes({0x26, 0x19, 0x80, 0x00, 0xA2, 0x66, 0x66, 0x93}))).WillOnce(Return(kOk));
    EXPECT_TRUE(sgp.start_measurement(0x8000, 0x6666));
}

TEST_F(Sgp41Test, ConditioningCommandCarriesTheSameArguments)
{
    EXPECT_CALL(bus, write(0x59, Bytes({0x26, 0x12, 0x80, 0x00, 0xA2, 0x66, 0x66, 0x93}))).WillOnce(Return(kOk));
    EXPECT_TRUE(sgp.start_conditioning(0x8000, 0x6666));
}

TEST_F(Sgp41Test, ReadMeasurementGivesBothRawSignals)
{
    EXPECT_CALL(bus, read(0x59, SizeIs(6))).WillOnce(respond({0x75, 0x30, 0x08, 0x4E, 0x20, 0xE3}));
    const auto r = sgp.read_measurement();
    ASSERT_TRUE(r);
    EXPECT_EQ(r->voc, 30000);
    EXPECT_EQ(r->nox, 20000);
}

TEST_F(Sgp41Test, ReadMeasurementRejectsABadCrc)
{
    EXPECT_CALL(bus, read(0x59, _)).WillOnce(respond({0x75, 0x30, 0x08, 0x4E, 0x20, 0xE4}));
    const auto r = sgp.read_measurement();
    ASSERT_FALSE(r);
    EXPECT_EQ(r.error(), SensorError::Crc);
}

TEST_F(Sgp41Test, ReadConditioningGivesOneWord)
{
    EXPECT_CALL(bus, read(0x59, SizeIs(3))).WillOnce(respond({0x75, 0x30, 0x08}));
    const auto r = sgp.read_conditioning();
    ASSERT_TRUE(r);
    EXPECT_EQ(*r, 30000);
}

TEST_F(Sgp41Test, SerialNumberIsThreeWords)
{
    InSequence order;
    EXPECT_CALL(bus, write(0x59, Bytes({0x36, 0x82}))).WillOnce(Return(kOk));
    EXPECT_CALL(bus, read(0x59, SizeIs(9)))
        .WillOnce(respond({0x12, 0x34, 0x37, 0x56, 0x78, 0x7D, 0x9A, 0xBC, 0xE0}));
    ASSERT_TRUE(sgp.request_serial());
    const auto serial = sgp.read_serial();
    ASSERT_TRUE(serial);
    EXPECT_EQ(*serial, 0x123456789ABCull);
}

TEST_F(Sgp41Test, MeasuringTooEarlyIsANack)
{
    EXPECT_CALL(bus, read(0x59, _)).WillOnce(Return(std::unexpected(I2cError::Nack)));
    const auto r = sgp.read_measurement();
    ASSERT_FALSE(r);
    EXPECT_EQ(r.error(), SensorError::Nack);
}

// --- Gas index (Sensirion's algorithm, vendored) ---------------------------------------------

TEST(GasIndex, VocFollowsSensirionsTestData)
{
    const auto rows = load_voc_csv();
    ASSERT_EQ(rows.size(), 600u) << "test data not found at " TEST_DATA_DIR;

    GasIndex voc{GasIndex::Kind::Voc};
    for (std::size_t i = 0; i < rows.size(); ++i) {
        const int32_t index = voc.process(rows[i].first);
        if (i < GasIndex::kBlackoutSamples) {
            EXPECT_EQ(index, 0) << "sample " << i << " is in the start-up blackout";
        } else {
            // The data comes from the floating-point variant; the fixed-point one may differ
            // slightly.
            EXPECT_NEAR(index, rows[i].second, 3) << "sample " << i;
        }
    }
}

TEST(GasIndex, VocSettlesAtOneHundredForAConstantSignal)
{
    // As in Sensirion's own test: after a few hundred samples the index is at its mean.
    GasIndex voc{GasIndex::Kind::Voc};
    for (int i = 0; i < 200; ++i) {
        voc.process(1337);
    }
    EXPECT_EQ(voc.process(1337), 100);
}

TEST(GasIndex, NoxSettlesAtOneForAConstantSignal)
{
    GasIndex nox{GasIndex::Kind::Nox};
    for (int i = 0; i < 200; ++i) {
        nox.process(1337);
    }
    EXPECT_EQ(nox.process(1337), 1);
}

TEST(GasIndex, NoxIsZeroDuringTheBlackout)
{
    GasIndex nox{GasIndex::Kind::Nox};
    for (uint32_t i = 0; i < GasIndex::kBlackoutSamples; ++i) {
        EXPECT_EQ(nox.process(15000), 0) << "sample " << i;
    }
}
