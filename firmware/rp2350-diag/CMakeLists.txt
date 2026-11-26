cmake_minimum_required(VERSION 3.13)

# Requires Pico SDK >= 2.0 (RP2350 support): export PICO_SDK_PATH=/path/to/pico-sdk
set(PICO_BOARD pico2 CACHE STRING "Board (Waveshare RP2350-USB-A is pin-compatible enough for UART/ADC use)")
set(PICO_PLATFORM rp2350-arm-s CACHE STRING "")
include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)

project(halcyon_diag C CXX ASM)
set(CMAKE_C_STANDARD 11)
pico_sdk_init()

add_executable(halcyon_diag src/main.c)
target_compile_definitions(halcyon_diag PRIVATE HALCYON_DIAG_VERSION="0.1.0")
target_link_libraries(halcyon_diag pico_stdlib hardware_uart hardware_adc hardware_irq)

pico_enable_stdio_usb(halcyon_diag 1)
pico_enable_stdio_uart(halcyon_diag 0)
pico_add_extra_outputs(halcyon_diag)
