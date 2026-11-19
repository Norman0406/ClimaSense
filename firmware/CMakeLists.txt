# ClimaSense firmware (ESP-IDF).
# The app version is taken from `git describe` (ESP-IDF does this when PROJECT_VER is not set).
cmake_minimum_required(VERSION 3.22)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(climasense)
