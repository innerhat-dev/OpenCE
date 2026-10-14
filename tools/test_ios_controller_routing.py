"""Run production iOS routing with deterministic controller discovery/input."""
import subprocess
from pathlib import Path
from harness import function

ROOT = Path(__file__).resolve().parents[1]


def test_ios_touch_and_hardware_ports(tmp_path):
    source = (ROOT / "port/ios/host/host_controls.m").read_text()
    code = r'''#import <Foundation/Foundation.h>
#include <SDL3/SDL.h>
#include <assert.h>
#include <math.h>
#include <stdlib.h>
struct SDL_Gamepad { SDL_JoystickID id; };
static struct SDL_Gamepad pads[]={{0},{1},{2},{3}};
static SDL_JoystickID touch_id=1, primary_hardware;
static SDL_Gamepad *primary_gamepad;
static BOOL separate_players;
static NSString *const controllerChanged=@"test";
static int attached=3, modal;
static int axes[4], buttons[4];
static void host_logf(int level,const char *format,...) {}
#define HOST_LOG_INFO 1
static int halo_debug_is_presented(void) {return modal;}
SDL_JoystickID *SDL_GetGamepads(int *count) {
    *count=attached; SDL_JoystickID *ids=calloc(attached+1,sizeof(*ids));
    for(int i=0;i<attached;i++) ids[i]=i+1; return ids;
}
void SDL_free(void *p) {free(p);}
SDL_Gamepad *SDL_OpenGamepad(SDL_JoystickID id) {return &pads[id];}
void SDL_CloseGamepad(SDL_Gamepad *pad) {}
const char *SDL_GetGamepadName(SDL_Gamepad *pad) {return "fixture";}
SDL_JoystickID SDL_GetGamepadID(SDL_Gamepad *pad) {return pad->id;}
SDL_GamepadType SDL_GetGamepadType(SDL_Gamepad *pad) {return SDL_GAMEPAD_TYPE_STANDARD;}
Sint16 SDL_GetGamepadAxis(SDL_Gamepad *pad,SDL_GamepadAxis axis) {return axes[pad->id];}
bool SDL_GetGamepadButton(SDL_Gamepad *pad,SDL_GamepadButton button) {return buttons[pad->id];}
'''
    for name in ("host_ios_gamepads", "host_ios_gamepad_type", "host_ios_gamepad_axis", "host_ios_gamepad_button"):
        code += function(source, name) + "\n"
    code += r'''
int main(void) {@autoreleasepool {
    uint32_t out[4]={99,99,99,99};
    // Default: touch and first hardware share P1; second hardware gets P2.
    assert(host_ios_gamepads(out,4)==2 && out[0]==1 && out[1]==3);
    axes[1]=100; axes[2]=200; buttons[2]=1;
    assert(host_ios_gamepad_axis(&pads[1],0)==200);
    assert(host_ios_gamepad_button(&pads[1],0));
    // Opt-in split: touch P1, first hardware P2, second hardware P3.
    separate_players=YES;
    assert(host_ios_gamepads(out,4)==3 && out[0]==1 && out[1]==2 && out[2]==3);
    assert(host_ios_gamepad_axis(&pads[1],0)==100);
    assert(!host_ios_gamepad_button(&pads[1],0));
    assert(host_ios_gamepad_axis(&pads[2],0)==200);
    assert(host_ios_gamepad_button(&pads[2],0));
    modal=1;
    assert(!host_ios_gamepad_axis(&pads[2],0) && !host_ios_gamepad_button(&pads[2],0));
    modal=0;
    assert(host_ios_gamepads(out,0)==0);
    out[1]=99; assert(host_ios_gamepads(out,1)==1 && out[1]==99);
    // Disconnect and reconnect keep touch first, without a ghost shared pad.
    attached=1;
    assert(host_ios_gamepads(out,4)==1 && out[0]==1 && !primary_hardware);
    attached=2;
    assert(host_ios_gamepads(out,4)==2 && out[1]==2);
}}
'''
    src=tmp_path / "routing.m"; src.write_text(code)
    exe=tmp_path / "routing"
    subprocess.run(["clang", "-fobjc-arc", "-fblocks", "-framework", "Foundation",
                    "-fsanitize=address,undefined", "-I/opt/homebrew/opt/sdl3/include",
                    str(src), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)


def test_touch_never_moves_to_keyboard_port(tmp_path):
    source=(ROOT / "port/linux/src/xinput_sdl.c").read_text()
    code="""
#include <assert.h>
#include <stddef.h>
typedef int BOOL;
typedef int SDL_Gamepad;
#define PORT_COUNT 4
static int lone_gamepad_split, split;
static int pc_menu_split_players(void) {return split;}
static int gamepad_idle(SDL_Gamepad *p) {return 1;}
""" + function(source,"port_gamepad") + """
int main(void) {
    int p1=1,p2=2; SDL_Gamepad *pads[4]={&p1,&p2};
    assert(port_gamepad(pads,1,0)==&p1);
    split=1;
#ifdef HALO_IOS
    assert(port_gamepad(pads,1,0)==&p1);
    assert(port_gamepad(pads,1,1)==NULL);
#else
    assert(port_gamepad(pads,1,0)==NULL);
    assert(port_gamepad(pads,1,1)==&p1);
#endif
    assert(port_gamepad(pads,2,0)==&p1 && port_gamepad(pads,2,1)==&p2);
}
"""
    src=tmp_path / "ports.c";src.write_text(code)
    for ios in (False,True):
        exe=tmp_path / ("ios" if ios else "desktop")
        subprocess.run(["clang", *(["-DHALO_IOS=1"] if ios else []),
                        "-fsanitize=address,undefined", str(src), "-o", str(exe)],check=True)
        subprocess.run([str(exe)],check=True)
