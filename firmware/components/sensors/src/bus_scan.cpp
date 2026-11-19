#include "sensors/bus_scan.h"

namespace sensors {

ScanResult scan_bus(I2cBus &bus, uint8_t first, uint8_t last)
{
    ScanResult result;
    for (unsigned address = first; address <= last && address < 128; ++address) {
        const I2cResult probe = bus.probe(static_cast<uint8_t>(address));
        if (probe) {
            result.responding.set(address);
        } else if (probe.error() != I2cError::Nack) {
            result.fault = BusFault{static_cast<uint8_t>(address), probe.error()};
            break;
        }
    }
    return result;
}

ScanReport compare(const ScanResult &result, std::span<const DeviceInfo> expected)
{
    ScanReport report;
    report.unexpected = result.responding;
    for (const DeviceInfo &device : expected) {
        if (device.address >= 128) {
            continue;
        }
        if (!result.found(device.address)) {
            report.missing.set(device.address);
        }
        report.unexpected.reset(device.address);
    }
    return report;
}

}  // namespace sensors
