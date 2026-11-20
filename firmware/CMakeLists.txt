# ClimaSense firmware (ESP-IDF).
# The app version is taken from `git describe` (ESP-IDF does this when PROJECT_VER is not set).
cmake_minimum_required(VERSION 3.22)

# Settings: sdkconfig.defaults (versioned), then sdkconfig.defaults.local if present
# (git-ignored; Wi-Fi credentials, see sdkconfig.defaults.local.example).
set(SDKCONFIG_DEFAULTS "sdkconfig.defaults")
if(EXISTS "${CMAKE_CURRENT_LIST_DIR}/sdkconfig.defaults.local")
    list(APPEND SDKCONFIG_DEFAULTS "sdkconfig.defaults.local")
endif()

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(climasense)
