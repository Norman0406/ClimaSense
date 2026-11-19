// Minimal test harness: TEST(name) { ... CHECK(cond); CHECK_EQ(a, b); }
#pragma once

#include <cstdio>
#include <functional>
#include <utility>
#include <vector>

namespace test {

struct Case {
    const char *name;
    std::function<void()> body;
};

inline std::vector<Case> &registry()
{
    static std::vector<Case> cases;
    return cases;
}

inline int &failures()
{
    static int count = 0;
    return count;
}

struct Register {
    Register(const char *name, std::function<void()> body) { registry().push_back({name, std::move(body)}); }
};

}  // namespace test

#define TEST_CONCAT_(a, b) a##b
#define TEST_CONCAT(a, b) TEST_CONCAT_(a, b)

#define TEST(name)                                                              \
    static void name();                                                         \
    static const test::Register TEST_CONCAT(register_, name){#name, name};      \
    static void name()

#define CHECK(cond)                                                             \
    do {                                                                        \
        if (!(cond)) {                                                          \
            std::printf("  FAILED %s:%d: %s\n", __FILE__, __LINE__, #cond);     \
            ++test::failures();                                                 \
        }                                                                       \
    } while (0)

#define CHECK_EQ(a, b)                                                          \
    do {                                                                        \
        const auto va_ = (a);                                                   \
        const auto vb_ = (b);                                                   \
        if (!(va_ == vb_)) {                                                    \
            std::printf("  FAILED %s:%d: %s == %s (%lld vs %lld)\n", __FILE__,  \
                        __LINE__, #a, #b, static_cast<long long>(va_),          \
                        static_cast<long long>(vb_));                           \
            ++test::failures();                                                 \
        }                                                                       \
    } while (0)
