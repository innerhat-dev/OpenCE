/* SDL owns UIApplication and invokes this entry on the UIKit main thread. */
#include "host.h"
#include "image.h"
extern void host_ios_show_fatal(const char *) __attribute__((noreturn));
#include "../../apple/host_graphics.h"
#include "../../apple/host_debug.h"
#include <SDL3/SDL.h>
#include <SDL3/SDL_main.h>
#import <Foundation/Foundation.h>
#import "../../apple/game_store.h"
extern void host_ios_prepare_assets(const char *root);
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
static char data_root[4096], save_root[4096];
void host_logf(int priority, const char *format, ...) {
    (void)priority;
    va_list a; va_start(a, format); vfprintf(stderr, format, a); va_end(a);
    fputc('\n', stderr);
}
void host_log(int priority, const char *text) { host_logf(priority, "%s", text); }
void host_fatal(const char *format, ...) {
    char message[2048];
    va_list a; va_start(a, format); vsnprintf(message, sizeof(message), format, a); va_end(a);
    host_logf(HOST_LOG_ERROR, "%s", message);
    host_ios_show_fatal(message);
}
void host_abort(const char *reason) { host_fatal("Game stopped: %s", reason); }
void host_exit(int code) { host_logf(HOST_LOG_INFO, "Game exited (%d)", code); exit(code); }
int host_errno(void) { return host_linux_errno(errno); }
void host_android_path(int which, char *buffer, uint32_t size) {
    snprintf(buffer, size, "%s", which ? save_root : data_root);
}
/* UIKit touch controls use an SDL virtual gamepad; disable the Android overlay. */
void host_gesture_insets(int *insets) {
    if (!insets)
        return;
    insets[0] = insets[1] = insets[2] = insets[3] = 0;
}
void host_touch_read(int *state) {
    int i;

    if (!state)
        return;
    for (i = 0; i < 7; i++)
        state[i] = 0;
}
void host_touch_look_read(float *delta) {
    int i;

    if (!delta)
        return;
    for (i = 0; i < 4; i++)
        delta[i] = 0.0f;
}
void host_touch_rumble(unsigned int low, unsigned int high) {
    (void)low;
    (void)high;
}
void host_touch_scene(int scene) { (void)scene; }
void host_touch_bindings(const int *controls) { (void)controls; }
extern char **environ;
static uint32_t make_boot(void) {
    size_t size = 0x20000;
    char *memory = host_low_map(size, PROT_READ | PROT_WRITE);
    if (!memory) host_fatal("Cannot allocate game startup memory.");
    struct halo_guest_boot *boot = (void *)memory;
    uint32_t *args = (void *)(memory + sizeof(*boot)), *env = args + 2;
    char *strings = (void *)(env + 256);
    unsigned count = 0;
    strcpy(strings, "halo"); args[0] = (uint32_t)(uintptr_t)strings; args[1] = 0; strings += 5;
    for (char **p = environ; *p && count < 255; p++) {
        size_t n = strlen(*p) + 1;
        if (strings + n > memory + size) break;
        memcpy(strings, *p, n); env[count++] = (uint32_t)(uintptr_t)strings; strings += n;
    }
    env[count] = 0;
    *boot = (struct halo_guest_boot){1, (uint32_t)(uintptr_t)args,
        (uint32_t)(uintptr_t)env, HALO_MACOS_PAGE};
    return (uint32_t)(uintptr_t)boot;
}
extern void macos_enter_guest_stack(void *, uint32_t) __attribute__((noreturn));
int main(int argc, char **argv) {
    (void)argc; (void)argv;
    halo_debug_configure_launch();
    halo_graphics_initialize();
    SDL_SetHint(SDL_HINT_ORIENTATIONS, "LandscapeLeft LandscapeRight");
    SDL_SetHint(SDL_HINT_IOS_HIDE_HOME_INDICATOR, "2");
    if (!SDL_InitSubSystem(SDL_INIT_VIDEO | SDL_INIT_GAMEPAD))
        host_fatal("Cannot initialize display: %s", SDL_GetError());
    if (!halo_graphics_metal() && !SDL_GL_LoadLibrary(NULL))
        host_fatal("Cannot load native OpenGL ES: %s", SDL_GetError());
    @autoreleasepool {
        NSFileManager *files = NSFileManager.defaultManager;
        NSString *documents = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
        NSString *saves = [documents stringByAppendingPathComponent:@"save"];
        NSString *legacySaves = [NSSearchPathForDirectoriesInDomains(NSApplicationSupportDirectory, NSUserDomainMask, YES).firstObject stringByAppendingPathComponent:@"Halo"];
        if (![files fileExistsAtPath:saves] && [files fileExistsAtPath:legacySaves]) saves = legacySaves;
        setenv("HALO_CONFIG_ROOT", documents.fileSystemRepresentation, 1);
        [files createDirectoryAtPath:saves withIntermediateDirectories:YES attributes:nil error:NULL];
        snprintf(save_root, sizeof(save_root), "%s", saves.fileSystemRepresentation);
        freopen([[saves stringByAppendingPathComponent:@"halo.log"] fileSystemRepresentation], "w", stderr);
        setbuf(stderr, NULL);
        // Fail before asking the user to spend time importing a large image.
        if ([NSProcessInfo.processInfo.environment[@"HALO_IOS_TEST_STARTUP_ERROR"] boolValue] ||
            host_memory_initialize(HALO_IOS_IMAGE_BASE, HALO_IOS_IMAGE_SIZE))
            host_fatal("iOS could not reserve an aligned %llu MiB virtual memory region for the game.\n\n"
                "This build does not require Extended Virtual Addressing. The running process may "
                "have insufficient contiguous address space, particularly inside an app container.\n\n"
                "Try closing and reopening the app, or installing it directly instead of inside "
                "LiveContainer. Your imported game and saves have not been removed. Re-importing "
                "the ISO will not fix this memory error. Details are in save/halo.log.",
                (unsigned long long)(HALO_ARENA_SIZE/(1024*1024)));
        NSString *data = halo_game_store_current(documents);
        NSString *legacy = [documents stringByAppendingPathComponent:@"GameData"];
        // Existing innerhat extracted maps and our retained ISO generations
        // both remain readable; new installations import through Files.
        if (!data && xiso_maps_ready([legacy stringByAppendingPathComponent:@"maps"].fileSystemRepresentation, NULL, 0))
            data = legacy;
        if (!data) {
            host_ios_prepare_assets(documents.fileSystemRepresentation);
            data = halo_game_store_current(documents);
        }
        snprintf(data_root, sizeof(data_root), "%s", data.fileSystemRepresentation);
        // Refresh the shipped default; custom broker files use a separate
        // network.brokers_file path and remain untouched.
        NSURL *brokers = [NSBundle.mainBundle URLForResource:@"brokers" withExtension:@"txt"];
        NSError *brokerError = nil;
        NSData *brokerData = brokers ? [NSData dataWithContentsOfURL:brokers options:0 error:&brokerError] : nil;
        if (!brokerData || ![brokerData writeToFile:[saves stringByAppendingPathComponent:@"brokers.txt"]
                                         options:NSDataWritingAtomic error:&brokerError])
            host_logf(HOST_LOG_ERROR, "Cannot install server discovery brokers: %s",
                      brokerError.localizedDescription.UTF8String ?: "bundled brokers.txt is missing");
        // A sandbox-relative shortcut for opt-in device frame profiling.
        const char *profile = getenv("HALO_PERF_LOG");
        if (profile && !strcmp(profile, "1"))
            setenv("HALO_PERF_LOG", [[saves stringByAppendingPathComponent:@"frames.csv"] fileSystemRepresentation], 1);
        if (![files fileExistsAtPath:[data stringByAppendingPathComponent:@"maps/ui.map"]])
            host_fatal("Copy your Xbox Halo maps folder into Halo OG's GameData folder using Files or Finder, then reopen the app.");
    }
    host_install_signal_handlers();
    setenv("HALO_DATA_ROOT", data_root, 1); setenv("HALO_SAVE_ROOT", save_root, 1);
    const SDL_DisplayMode *display = SDL_GetDesktopDisplayMode(SDL_GetPrimaryDisplay());
    if (display && display->h > 0 && display->w > 0) {
        int long_side = display->w > display->h ? display->w : display->h;
        int short_side = display->w < display->h ? display->w : display->h;
        char width[32]; snprintf(width, sizeof(width), "%d", (480 * long_side / short_side) & ~1);
        setenv("HALO_DISPLAY_WIDTH", width, 0);
    }
    if (host_load_image(NULL, 0)) host_fatal("Cannot initialize game memory. See save/halo.log for the failed memory reservation or image load.");
    uint32_t boot = make_boot();
    size_t stack_size = 16 * 1024 * 1024;
    char *stack = host_low_map(stack_size + HALO_MACOS_PAGE, PROT_READ | PROT_WRITE);
    if (!stack) host_fatal("Cannot allocate game stack.");
    mprotect(stack, HALO_MACOS_PAGE, PROT_NONE);
    host_logf(HOST_LOG_INFO, "Halo iOS starting; data %s; saves %s", data_root, save_root);
    macos_enter_guest_stack(stack + stack_size + HALO_MACOS_PAGE, boot);
}
