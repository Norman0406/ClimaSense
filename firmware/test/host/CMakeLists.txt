# Unit tests for the hardware-independent firmware logic, built with the PC's own compiler
# (not ESP-IDF) and GoogleTest. See firmware/README.md, "Tests on the PC".
cmake_minimum_required(VERSION 3.22)
project(climasense_host_tests C CXX)

# C++23 for std::expected, as the firmware uses it.
set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

include(FetchContent)
FetchContent_Declare(
    googletest
    URL https://github.com/google/googletest/archive/refs/tags/v1.18.0.tar.gz
    URL_HASH SHA256=6e3191c1455468b3fc35a417fb565c1c5071aee1b7e7f85e30cf48a98d37d8b5
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE
)
set(INSTALL_GTEST OFF CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(googletest)

set(FW ${CMAKE_CURRENT_SOURCE_DIR}/../..)

add_executable(host_tests
    test_bmp580.cpp
    test_bus_scan.cpp
    test_button_logic.cpp
    test_led_logic.cpp
    test_log_ring.cpp
    test_net.cpp
    test_scd41.cpp
    test_sgp41.cpp
    test_sht45.cpp
    test_single_shot.cpp
    ${FW}/components/board/src/button_logic.cpp
    ${FW}/components/board/src/led_logic.cpp
    ${FW}/components/net/src/settings.cpp
    ${FW}/components/sensors/src/bmp580.cpp
    ${FW}/components/sensors/src/bus_scan.cpp
    ${FW}/components/sensors/src/scd41.cpp
    ${FW}/components/sensors/src/sgp41.cpp
    ${FW}/components/sensors/vendor/gas_index_algorithm/sensirion_gas_index_algorithm.c
    ${FW}/components/sensors/src/sht45.cpp
)
target_include_directories(host_tests PRIVATE
    ${FW}/components/board/include
    ${FW}/components/diagnostics/include
    ${FW}/components/net/include
    ${FW}/components/sensors/include
    ${FW}/components/sensors/vendor/gas_index_algorithm
)
# Our code with all warnings as errors; Sensirion's vendored C file as it is.
target_compile_options(host_tests PRIVATE "$<$<COMPILE_LANGUAGE:CXX>:-Wall;-Wextra;-Werror>")
target_compile_definitions(host_tests PRIVATE TEST_DATA_DIR="${CMAKE_CURRENT_SOURCE_DIR}/data")
target_link_libraries(host_tests PRIVATE GTest::gtest_main GTest::gmock)

enable_testing()
include(GoogleTest)
gtest_discover_tests(host_tests)
