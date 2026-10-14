cmake_minimum_required(VERSION 3.28)
project(HaloIOS LANGUAGES C CXX OBJC ASM)
get_filename_component(HALO_ROOT "../.." ABSOLUTE)
if(CMAKE_OSX_SYSROOT MATCHES "simulator")
    set(HALO_BUILD "${HALO_ROOT}/build/ios-simulator")
    add_compile_definitions(HALO_IOS_SIMULATOR=1)
else()
    set(HALO_BUILD "${HALO_ROOT}/build/ios")
endif()
set(HALO_BUNDLE_IDENTIFIER "local.halo.ce-universal.ios" CACHE STRING "Unique iOS app bundle identifier")
set(SDL_SHARED OFF CACHE BOOL "" FORCE)
set(SDL_STATIC ON CACHE BOOL "" FORCE)
set(SDL_TEST_LIBRARY OFF CACHE BOOL "" FORCE)
set(SDL_TESTS OFF CACHE BOOL "" FORCE)
add_subdirectory("${HALO_ROOT}/build/android/third_party/SDL3" "sdl")
file(GLOB HOST_SOURCES "${HALO_ROOT}/port/macos/host/*.c")
file(GLOB MBEDTLS_SOURCES "${HALO_ROOT}/port/third_party/mbedtls/library/*.c")
file(GLOB MINIUPNPC_SOURCES "${HALO_ROOT}/port/third_party/miniupnpc/src/*.c")
list(FILTER HOST_SOURCES EXCLUDE REGEX "host_(main|loader)\\.c$")
add_executable(Halo MACOSX_BUNDLE ${HOST_SOURCES} ${MINIUPNPC_SOURCES} ${MBEDTLS_SOURCES} host/host_loader.c host/host_main.m host/host_controls.m host/host_import.m host/host_orientation.m host/host_startup_error.m
    "${HALO_ROOT}/port/macos/native/HaloMapDownloads.m" "${HALO_ROOT}/port/apple/host_gl_diagnostics.c" "${HALO_ROOT}/port/apple/host_graphics.c" "${HALO_ROOT}/port/apple/host_debug.m"
    "${HALO_ROOT}/port/apple/host_metalfx.m" "${HALO_ROOT}/port/apple/host_shader_cache.m"
    "${HALO_ROOT}/port/apple/game_store.m" "${HALO_ROOT}/port/apple/xiso.c"
    "${HALO_ROOT}/port/linux/src/posix_dtls.c"
    "${HALO_ROOT}/port/macos/host/entry.s" "${HALO_BUILD}/host/host_import_table.c"
    "${HALO_BUILD}/embed/guest_image.s")
target_sources(Halo PRIVATE Assets.xcassets)
# Internet discovery reads this beside config.toml; host_main installs the default.
target_sources(Halo PRIVATE "${HALO_ROOT}/port/assets/network/brokers.txt")
set_source_files_properties("${HALO_ROOT}/port/assets/network/brokers.txt"
    PROPERTIES MACOSX_PACKAGE_LOCATION Resources)
set_source_files_properties(Assets.xcassets PROPERTIES MACOSX_PACKAGE_LOCATION Resources)
target_compile_definitions(Halo PRIVATE HALO_IOS=1 HALO_MACOS=1 HALO_APPLE_GRAPHICS=1 _DARWIN_C_SOURCE=1)
target_compile_definitions(Halo PRIVATE MINIUPNP_STATICLIB MINIUPNPC_SET_SOCKET_TIMEOUT
    MINIUPNPC_GET_SRC_ADDR _BSD_SOURCE _DEFAULT_SOURCE)
target_compile_options(Halo PRIVATE -O2 -g -Wall -Wextra -Wno-unused-parameter -Wno-unused-function
    "$<$<COMPILE_LANGUAGE:OBJC>:-fobjc-arc>")
target_include_directories(Halo PRIVATE "${HALO_ROOT}" "${HALO_ROOT}/port/macos/host"
    "${HALO_ROOT}/port/android/include" "${HALO_ROOT}/port/linux/src"
    "${HALO_ROOT}/port/apple" "${HALO_ROOT}/port/third_party/mbedtls/include" "${HALO_ROOT}/port/third_party/mbedtls/library"
    "${HALO_ROOT}/build/macos/toolchain/gl" "${HALO_BUILD}/embed"
    "${HALO_ROOT}/port/third_party/miniupnpc/include" "${HALO_ROOT}/port/third_party/miniupnpc/src")
if(CMAKE_OSX_SYSROOT MATCHES "simulator")
    set(ANGLE_PLATFORM ios-arm64-simulator)
else()
    set(ANGLE_PLATFORM ios-arm64)
    target_link_libraries(Halo PRIVATE "-framework MetalFX")
endif()
# SDL UIKit uses direct GL calls for its EAGL drawable. Bind those to Apple,
# while the game and diagnostics select ANGLE/Apple through host_gl_dispatch.
target_link_libraries(Halo PRIVATE "-framework OpenGLES")
foreach(NAME EGL GLESv2)
    set(FRAMEWORK "${HALO_ROOT}/build/macos/angle/dist/${NAME}.xcframework/${ANGLE_PLATFORM}/lib${NAME}.framework")
    list(APPEND ANGLE_FRAMEWORKS "${FRAMEWORK}")
    target_link_libraries(Halo PRIVATE "${FRAMEWORK}")
endforeach()
target_link_libraries(Halo PRIVATE SDL3::SDL3-static "-framework Foundation" "-framework UIKit" "-framework GameController" "-framework UniformTypeIdentifiers" "-framework Metal" "-framework QuartzCore" "-framework CoreVideo" "-framework IOSurface")
set_target_properties(Halo PROPERTIES
    MACOSX_BUNDLE_INFO_PLIST "${CMAKE_CURRENT_SOURCE_DIR}/Info.plist.in"
    XCODE_ATTRIBUTE_PRODUCT_BUNDLE_IDENTIFIER "${HALO_BUNDLE_IDENTIFIER}"
    XCODE_ATTRIBUTE_ASSETCATALOG_COMPILER_APPICON_NAME "AppIcon"
    XCODE_ATTRIBUTE_TARGETED_DEVICE_FAMILY "1,2"
    XCODE_ATTRIBUTE_CODE_SIGN_STYLE "Automatic"
    XCODE_ATTRIBUTE_CODE_SIGN_ENTITLEMENTS "${CMAKE_CURRENT_SOURCE_DIR}/Halo.entitlements"
    XCODE_ATTRIBUTE_ENABLE_HARDENED_RUNTIME NO
    XCODE_ATTRIBUTE_CLANG_ENABLE_OBJC_ARC YES
    XCODE_EMBED_FRAMEWORKS "${ANGLE_FRAMEWORKS}"
    XCODE_EMBED_FRAMEWORKS_CODE_SIGN_ON_COPY YES
    XCODE_EMBED_FRAMEWORKS_REMOVE_HEADERS_ON_COPY YES
    XCODE_ATTRIBUTE_LD_RUNPATH_SEARCH_PATHS "@executable_path/Frameworks")
if(HALO_DEVELOPMENT_TEAM)
    set_target_properties(Halo PROPERTIES XCODE_ATTRIBUTE_DEVELOPMENT_TEAM "${HALO_DEVELOPMENT_TEAM}")
endif()
# Game data is always supplied by the user after installation, never bundled.

# License texts ship with the code; retail game images never do.
set(LICENSE_INPUTS
    "LICENSE.md" "port/macos/licenses/ANGLE.txt"
    "build/android/third_party/SDL3/LICENSE.txt"
    "build/android/third_party/musl-1.2.5/COPYRIGHT"
    "port/third_party/kcp/LICENSE" "port/third_party/miniupnpc/LICENSE"
    "port/third_party/tomlc17/LICENSE" "port/third_party/mbedtls/LICENSE"
    "port/third_party/zlib/LICENSE" "port/third_party/expat/COPYING"
    "port/third_party/stb/LICENSE" "port/third_party/stb_vorbis/LICENSE" "port/third_party/smaa/LICENSE")
foreach(INPUT IN LISTS LICENSE_INPUTS)
    string(REPLACE "/" "-" NAME "${INPUT}")
    set(OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/Licenses/${NAME}.txt")
    configure_file("${HALO_ROOT}/${INPUT}" "${OUTPUT}" COPYONLY)
    target_sources(Halo PRIVATE "${OUTPUT}")
    set_source_files_properties("${OUTPUT}" PROPERTIES MACOSX_PACKAGE_LOCATION "Resources/Licenses")
endforeach()

# Ship the same app artwork as a standard PNG for IPA catalog readers.
# Asset-catalog icons may be Apple CgBI PNGs, which web image decoders reject.
configure_file(Assets.xcassets/AppIcon.appiconset/AppIcon.png
    "${CMAKE_CURRENT_BINARY_DIR}/AppIcon1024.png" COPYONLY)
target_sources(Halo PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/AppIcon1024.png")
set_source_files_properties("${CMAKE_CURRENT_BINARY_DIR}/AppIcon1024.png"
    PROPERTIES MACOSX_PACKAGE_LOCATION Resources)
set_target_properties(Halo PROPERTIES XCODE_ATTRIBUTE_COMPRESS_PNG_FILES NO)
