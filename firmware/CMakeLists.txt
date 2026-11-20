# ClimaSense firmware (ESP-IDF).
cmake_minimum_required(VERSION 3.22)

# The firmware version, from git: X.Y.Z+<hash> for a commit tagged vX.Y.Z, <branch>-<hash> otherwise
# (cmake/version.cmake). Releases are made by pushing a tag vX.Y.Z.
include("${CMAKE_CURRENT_LIST_DIR}/cmake/version.cmake")

# Settings: sdkconfig.defaults (versioned), then sdkconfig.defaults.local if present
# (git-ignored; Wi-Fi credentials, see sdkconfig.defaults.local.example).
set(SDKCONFIG_DEFAULTS "sdkconfig.defaults")
if(EXISTS "${CMAKE_CURRENT_LIST_DIR}/sdkconfig.defaults.local")
    list(APPEND SDKCONFIG_DEFAULTS "sdkconfig.defaults.local")
endif()

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(climasense)
