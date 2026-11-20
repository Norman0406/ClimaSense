# ClimaSense firmware (ESP-IDF).
cmake_minimum_required(VERSION 3.22)

# The firmware version: from version.txt (x.y.z), so that updates can be compared. Raise it for
# every release; the build fingerprint (ELF SHA-256) tells builds of the same version apart.
file(STRINGS "${CMAKE_CURRENT_LIST_DIR}/version.txt" PROJECT_VER LIMIT_COUNT 1)

# Settings: sdkconfig.defaults (versioned), then sdkconfig.defaults.local if present
# (git-ignored; Wi-Fi credentials, see sdkconfig.defaults.local.example).
set(SDKCONFIG_DEFAULTS "sdkconfig.defaults")
if(EXISTS "${CMAKE_CURRENT_LIST_DIR}/sdkconfig.defaults.local")
    list(APPEND SDKCONFIG_DEFAULTS "sdkconfig.defaults.local")
endif()
# In CI (GitHub Actions sets CI): no signing key there, so unsigned images (sdkconfig.ci).
if(DEFINED ENV{CI})
    list(APPEND SDKCONFIG_DEFAULTS "sdkconfig.ci")
endif()

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(climasense)
