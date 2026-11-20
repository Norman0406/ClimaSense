// In-memory settings store for the unit tests.
#pragma once

#include <algorithm>
#include <expected>
#include <map>
#include <span>
#include <string>
#include <string_view>

#include "settings/kv_store.h"

namespace test_support {

using settings::KvError;

// In-memory KvStore. Writes are only visible after commit(), like NVS after a reboot.
class FakeStore : public settings::KvStore {
public:
    std::expected<std::size_t, KvError> get(const char *k, std::span<char> out) override
    {
        if (fail_reads) {
            return std::unexpected(KvError::Failed);
        }
        const auto it = committed.find(k);
        if (it == committed.end()) {
            return std::unexpected(KvError::NotFound);
        }
        if (it->second.size() + 1 > out.size()) {
            return std::unexpected(KvError::TooLong);
        }
        std::copy(it->second.begin(), it->second.end(), out.begin());
        out[it->second.size()] = '\0';
        return it->second.size();
    }

    std::expected<void, KvError> set(const char *k, std::string_view value) override
    {
        if (fail_writes) {
            return std::unexpected(KvError::Failed);
        }
        pending[k] = std::string(value);
        ++writes;
        return {};
    }

    std::expected<void, KvError> commit() override
    {
        for (auto &[k, v] : pending) {
            committed[k] = v;
        }
        pending.clear();
        return {};
    }

    std::map<std::string, std::string> committed;
    std::map<std::string, std::string> pending;
    int writes = 0;
    bool fail_reads = false;
    bool fail_writes = false;
};

}  // namespace test_support
