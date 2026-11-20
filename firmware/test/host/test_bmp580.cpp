#include <algorithm>
#include <cstdint>
#include <expected>
#include <initializer_list>
#include <span>
#include <vector>

#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include "mock_i2c_bus.h"
#include "sensors/bmp580.h"

using sensors::Bmp580;
using sensors::I2cError;
using sensors::I2cResult;
using sensors::SensorError;
using ::testing::_;
using ::testing::InSequence;
using ::testing::Return;
using ::testing::SizeIs;
using ::testing::StrictMock;

namespace {

// Action for write_read(): fills the read buffer with `bytes` and succeeds.
auto respond(std::initializer_list<uint8_t> bytes)
{
    return [data = std::vector<uint8_t>(bytes)](uint8_t, std::span<const uint8_t>, std::span<uint8_t> rx) {
        std::copy(data.begin(), data.end(), rx.begin());
        return I2cResult{};
    };
}

const I2cResult kOk{};

class Bmp580Test : public ::testing::Test {
protected:
    // Expects a one-byte register read of `reg` and answers `value`.
    void expect_reg(uint8_t reg, uint8_t value)
    {
        EXPECT_CALL(bus, write_read(0x47, Bytes({reg}), SizeIs(1))).WillOnce(respond({value}));
    }

    StrictMock<MockI2cBus> bus;
    Bmp580 bmp{bus};
};

}  // namespace

// --- Conversion ----------------------------------------------------------------------------

TEST(Bmp580Conversion, Temperature)
{
    EXPECT_EQ(Bmp580::temperature_mc(0x190000), 25'000);   // 25 * 65536
    EXPECT_EQ(Bmp580::temperature_mc(0xF60000), -10'000);  // -10 * 65536, 24-bit two's complement
    EXPECT_EQ(Bmp580::temperature_mc(0), 0);
    EXPECT_EQ(Bmp580::temperature_mc(0x800000), -128'000); // most negative 24-bit value
    EXPECT_EQ(Bmp580::temperature_mc(0x000021), 1);        // 33 / 65.536 = 0.50 milli-degrees, rounds up
}

TEST(Bmp580Conversion, Pressure)
{
    EXPECT_EQ(Bmp580::pressure_milli_pa(0x62F340), 101'325'000);  // 101325 Pa * 64
    EXPECT_EQ(Bmp580::pressure_milli_pa(0), 0);
    EXPECT_EQ(Bmp580::pressure_milli_pa(1), 16);                  // 1/64 Pa = 15.6 mPa
    EXPECT_EQ(Bmp580::pressure_milli_pa(0xFFFFFF), 262'143'984);  // stays inside int32
}

// --- Start-up ------------------------------------------------------------------------------

TEST_F(Bmp580Test, SoftResetWritesTheResetCommand)
{
    EXPECT_CALL(bus, write(0x47, Bytes({0x7E, 0xB6}))).WillOnce(Return(kOk));
    EXPECT_TRUE(bmp.soft_reset());
}

TEST_F(Bmp580Test, CheckAfterResetAcceptsAGoodStart)
{
    InSequence order;
    expect_reg(0x01, 0x50);  // chip ID
    expect_reg(0x27, 0x10);  // reset complete
    expect_reg(0x28, 0x02);  // NVM ready, no error
    const auto id = bmp.check_after_reset();
    ASSERT_TRUE(id);
    EXPECT_EQ(*id, 0x50);
}

TEST_F(Bmp580Test, CheckAfterResetAcceptsTheOtherFamilyId)
{
    InSequence order;
    expect_reg(0x01, 0x51);
    expect_reg(0x27, 0x10);
    expect_reg(0x28, 0x02);
    EXPECT_TRUE(bmp.check_after_reset());
}

TEST_F(Bmp580Test, WrongChipIsRejectedBeforeAnythingElse)
{
    expect_reg(0x01, 0x58);  // a BMP280's ID; nothing else may be read (StrictMock)
    const auto id = bmp.check_after_reset();
    ASSERT_FALSE(id);
    EXPECT_EQ(id.error(), SensorError::UnexpectedId);
}

TEST_F(Bmp580Test, IncompleteResetIsNotReady)
{
    InSequence order;
    expect_reg(0x01, 0x50);
    expect_reg(0x27, 0x00);
    const auto id = bmp.check_after_reset();
    ASSERT_FALSE(id);
    EXPECT_EQ(id.error(), SensorError::NotReady);
}

TEST_F(Bmp580Test, NvmErrorIsNotReady)
{
    InSequence order;
    expect_reg(0x01, 0x50);
    expect_reg(0x27, 0x10);
    expect_reg(0x28, 0x06);  // ready, but with error
    const auto id = bmp.check_after_reset();
    ASSERT_FALSE(id);
    EXPECT_EQ(id.error(), SensorError::NotReady);
}

TEST_F(Bmp580Test, AbsentSensorIsANack)
{
    EXPECT_CALL(bus, write_read(0x47, _, _)).WillOnce(Return(std::unexpected(I2cError::Nack)));
    const auto id = bmp.check_after_reset();
    ASSERT_FALSE(id);
    EXPECT_EQ(id.error(), SensorError::Nack);
}

TEST_F(Bmp580Test, ConfigureSetsOversamplingAndStandbyKeepingTheRateBits)
{
    InSequence order;
    EXPECT_CALL(bus, write(0x47, Bytes({0x36, 0x61}))).WillOnce(Return(kOk));  // press_en, p 16x, t 2x
    expect_reg(0x37, 0x70);  // reset value: rate bits 0x70, standby
    EXPECT_CALL(bus, write(0x47, Bytes({0x37, 0xF0}))).WillOnce(Return(kOk));  // + deep standby off
    EXPECT_TRUE(bmp.configure());
}

// --- Measurement -----------------------------------------------------------------------------

TEST_F(Bmp580Test, StartMeasurementSelectsForcedMode)
{
    InSequence order;
    EXPECT_CALL(bus, write(0x47, Bytes({0x36, 0x61}))).WillOnce(Return(kOk));
    expect_reg(0x37, 0x70);
    EXPECT_CALL(bus, write(0x47, Bytes({0x37, 0xF0}))).WillOnce(Return(kOk));
    EXPECT_CALL(bus, write(0x47, Bytes({0x37, 0xF2}))).WillOnce(Return(kOk));
    ASSERT_TRUE(bmp.configure());
    EXPECT_TRUE(bmp.start_measurement());
}

TEST_F(Bmp580Test, ReadMeasurementReadsBothValuesOnceBackInStandby)
{
    InSequence order;
    expect_reg(0x37, 0xF0);  // standby again: measurement done
    EXPECT_CALL(bus, write_read(0x47, Bytes({0x1D}), SizeIs(6)))
        .WillOnce(respond({0x00, 0x00, 0x19, 0x40, 0xF3, 0x62}));  // little-endian T, then P
    const auto r = bmp.read_measurement();
    ASSERT_TRUE(r);
    EXPECT_EQ(r->temperature_mc, 25'000);
    EXPECT_EQ(r->pressure_milli_pa, 101'325'000);
}

TEST_F(Bmp580Test, ReadMeasurementWhileStillForcedIsNotReady)
{
    expect_reg(0x37, 0xF2);  // still in forced mode; the data must not be read (StrictMock)
    const auto r = bmp.read_measurement();
    ASSERT_FALSE(r);
    EXPECT_EQ(r.error(), SensorError::NotReady);
}
