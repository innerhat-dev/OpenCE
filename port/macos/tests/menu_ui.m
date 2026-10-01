/* The real menu/settings and SDL bridge, in a separate bundle with test saves. */
#import <Cocoa/Cocoa.h>
#define SDL_MAIN_HANDLED
#include <SDL3/SDL.h>
#include <SDL3/SDL_main.h>
#include "host_menu.h"
#include <assert.h>
#include <unistd.h>
extern uint32_t host_sdl_create_window(const char *, int, int, int64_t);

int main(int argc, const char **argv) {
    @autoreleasepool {
        assert(argc == 3);
        printf("Menu UI test PID %d\n", getpid());
        fflush(stdout);
        SDL_SetMainReady();
        SDL_SetHint(SDL_HINT_VIDEO_MAC_FULLSCREEN_SPACES, "0");
        SDL_SetHint(SDL_HINT_VIDEO_MAC_FULLSCREEN_MENU_VISIBILITY, "1");
        SDL_SetHint(SDL_HINT_WINDOW_ALLOW_TOPMOST, "0");
        assert(SDL_Init(SDL_INIT_VIDEO));
        char data[4096];
        assert(host_menu_prepare(argv[1], argv[2], data, sizeof(data)));
        assert(host_sdl_create_window("Halo Menu Test", 640, 480, 0));
        host_menu_begin_game();
        [NSTimer scheduledTimerWithTimeInterval:0.05 repeats:YES block:^(NSTimer *timer) {
            SDL_Event event;
            while (SDL_PollEvent(&event)) {
                if (event.type == SDL_EVENT_QUIT) {
                    [timer invalidate];
                    [NSApp stop:nil];
                }
            }
        }];
        /* Open the actual settings panel without a moving/captured game canvas. */
        [NSTimer scheduledTimerWithTimeInterval:0.1 repeats:NO block:^(NSTimer *timer) {
            (void)timer;
            NSMenuItem *settings = NSApp.mainMenu.itemArray[0].submenu.itemArray[1];
            [NSApp sendAction:settings.action to:settings.target from:settings];
        }];
        [NSApp run];
        host_menu_finish_game(0);
        SDL_Quit();
    }
    return 0;
}
