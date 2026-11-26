cmake_minimum_required(VERSION 3.13)

# Требуется pico-sdk >= 2.0 (поддержка RP2350): export PICO_SDK_PATH=...
set(PICO_PLATFORM rp2350 CACHE STRING "")
set(PICO_BOARD pico2 CACHE STRING "")  # Waveshare RP2350-USB-A: пины задаются в src/board.h
include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)

project(d11diag C CXX ASM)
set(CMAKE_C_STANDARD 11)
pico_sdk_init()

add_executable(d11diag
    src/main.c
    src/usb_descriptors.c
    src/events.c
)
target_include_directories(d11diag PRIVATE src)
target_link_libraries(d11diag PRIVATE pico_stdlib pico_unique_id hardware_uart tinyusb_device tinyusb_board)
pico_enable_stdio_usb(d11diag 0)
pico_enable_stdio_uart(d11diag 0)
pico_add_extra_outputs(d11diag)
