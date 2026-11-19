# Tests for the hardware-independent firmware logic, built with the PC's own compiler
# (not ESP-IDF). See firmware/README.md, "Tests on the PC".
cmake_minimum_required(VERSION 3.22)
project(climasense_host_tests CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(FW ${CMAKE_CURRENT_SOURCE_DIR}/../..)

add_executable(host_tests
    test_main.cpp
    test_button_logic.cpp
    test_led_logic.cpp
    ${FW}/components/board/src/button_logic.cpp
    ${FW}/components/board/src/led_logic.cpp
)
target_include_directories(host_tests PRIVATE ${FW}/components/board/include)
target_compile_options(host_tests PRIVATE -Wall -Wextra -Werror)

enable_testing()
add_test(NAME host_tests COMMAND host_tests)
