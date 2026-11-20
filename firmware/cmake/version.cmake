# The firmware version, from git (decided 2026-11-20). Sets PROJECT_VER, which ESP-IDF writes into
# the image (esp_app_desc_t.version, at most 31 characters):
#
#   commit tagged vX.Y.Z      X.Y.Z+<hash>             a release; devices compare X.Y.Z, ignore +<hash>
#   any other commit          <branch>-<hash>          e.g. main-1a2b3c4; not comparable
#   uncommitted changes       <branch>-<hash>-dirty    (tracked files under firmware/ only)
#   no git                    unknown
#
# <hash> is the commit's first 7 hex digits. In GitHub Actions the ref comes from GITHUB_REF_TYPE /
# GITHUB_REF_NAME / GITHUB_SHA (the checkout is a single commit, often without branch or tags).
# The version is fixed when CMake configures; a new commit or branch triggers a reconfigure (the
# git files below are configure dependencies).

get_filename_component(_climasense_root "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE)  # firmware/
set(_version "unknown")
set(_tag "")
set(_branch "")
set(_hash "")
set(_dirty FALSE)

if(DEFINED ENV{GITHUB_REF_TYPE} AND DEFINED ENV{GITHUB_REF_NAME} AND DEFINED ENV{GITHUB_SHA})
    string(SUBSTRING "$ENV{GITHUB_SHA}" 0 7 _hash)
    if("$ENV{GITHUB_REF_TYPE}" STREQUAL "tag")
        set(_tag "$ENV{GITHUB_REF_NAME}")
    else()
        set(_branch "$ENV{GITHUB_REF_NAME}")
    endif()
else()
    find_package(Git QUIET)
    if(GIT_FOUND)
        execute_process(COMMAND "${GIT_EXECUTABLE}" rev-parse --short=7 HEAD
                        WORKING_DIRECTORY "${_climasense_root}" OUTPUT_VARIABLE _hash
                        RESULT_VARIABLE _rc OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
        if(NOT _rc EQUAL 0)
            set(_hash "")
        endif()
    endif()
    if(_hash)
        execute_process(COMMAND "${GIT_EXECUTABLE}" describe --exact-match --tags --match "v[0-9]*.[0-9]*.[0-9]*" HEAD
                        WORKING_DIRECTORY "${_climasense_root}" OUTPUT_VARIABLE _tag
                        RESULT_VARIABLE _rc OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
        if(NOT _rc EQUAL 0)
            set(_tag "")
        endif()
        execute_process(COMMAND "${GIT_EXECUTABLE}" rev-parse --abbrev-ref HEAD
                        WORKING_DIRECTORY "${_climasense_root}" OUTPUT_VARIABLE _branch
                        OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
        execute_process(COMMAND "${GIT_EXECUTABLE}" status --porcelain --untracked-files=no -- .
                        WORKING_DIRECTORY "${_climasense_root}" OUTPUT_VARIABLE _status
                        OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
        if(_status)
            set(_dirty TRUE)
        endif()

        # Reconfigure when HEAD moves: on a branch switch (.git/HEAD) or a new commit (the branch's ref).
        execute_process(COMMAND "${GIT_EXECUTABLE}" rev-parse --git-dir
                        WORKING_DIRECTORY "${_climasense_root}" OUTPUT_VARIABLE _git_dir
                        OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
        get_filename_component(_git_dir "${_git_dir}" ABSOLUTE BASE_DIR "${_climasense_root}")
        foreach(_f "${_git_dir}/HEAD" "${_git_dir}/refs/heads/${_branch}" "${_git_dir}/packed-refs")
            if(EXISTS "${_f}")
                set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${_f}")
            endif()
        endforeach()
    endif()
endif()

if(_hash)
    if(_tag MATCHES "^v([0-9]+\\.[0-9]+\\.[0-9]+)$" AND NOT _dirty)
        set(_version "${CMAKE_MATCH_1}+${_hash}")
    else()
        if(NOT _branch OR _branch STREQUAL "HEAD")
            set(_branch "detached")
        endif()
        string(REGEX REPLACE "[^A-Za-z0-9._-]" "-" _branch "${_branch}")
        set(_suffix "-${_hash}")
        if(_dirty)
            string(APPEND _suffix "-dirty")
        endif()
        string(LENGTH "${_suffix}" _suffix_length)
        math(EXPR _room "31 - ${_suffix_length}")
        string(SUBSTRING "${_branch}" 0 ${_room} _branch)
        set(_version "${_branch}${_suffix}")
    endif()
endif()

set(PROJECT_VER "${_version}")
message(STATUS "ClimaSense firmware version: ${PROJECT_VER}")
