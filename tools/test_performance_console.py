"""Compile the production PB console parser and completion with authority stubs."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

HARNESS = r'''
#include <assert.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include "networking/network_performance_protocol.h"
#include "performance_audio.h"
#include "performance_sound.h"
typedef int boolean;
#define TRUE 1
#define FALSE 0
#define NONE (-1)
#define NUMBEROF(a) (sizeof(a)/sizeof((a)[0]))
enum { _performance_option_match_timer=1, _performance_option_spawn_markers=2,
       _performance_option_timer_audio=4, _performance_option_silent_movement=8,
       _performance_option_silent_weapon_ready=16, PERFORMANCE_PRACTICE_FLAGS=7, PERFORMANCE_OPTIONS_MASK=31 };
static unsigned long flags;
static unsigned mutation_calls, peer_support=31;
static boolean host=TRUE;
static int recordings=1;
int halo_performance_audio_available(void) { return recordings; }
void performance_sound_get_statistics(struct performance_sound_statistics *s) {
    memset(s,0,sizeof(*s)); s->voices_by_role[1]=12; s->voices_by_role[2]=3;
}
static char output[4096];
static unsigned long performance_options_get_flags(void) { return flags; }
struct performance_timer_statistics { unsigned preferences; unsigned long countdown,beeps,minutes,items; unsigned long items_by_category[3]; char const *last_cue; };
static void performance_options_timer_statistics(struct performance_timer_statistics *s) {
 *s=(struct performance_timer_statistics){7,1,2,3,0,{0,0,0},"1_minute"};
}
static long performance_options_timer_ticks(void) { return 1800; }
static short performance_options_markers_visible_count(void) { return (flags&2) ? 24 : 0; }
static short performance_options_markers_supported_count(void) { return 24; }
static boolean performance_options_set_host_flags(unsigned long value) {
    mutation_calls++;
    if (!host || ((value&4) && !recordings) || !network_performance_can_join(value,peer_support)) return FALSE;
    flags=value; return TRUE;
}
static void console_printf(boolean clear,const char *format,...) {
    va_list args;
    if(clear) output[0]=0;
    va_start(args,format);
    size_t used=strlen(output);
    int length=vsnprintf(output+used,sizeof(output)-used,format,args);
    va_end(args);
    assert(length>=0 && used+(size_t)length+2<sizeof(output));
    strcat(output,"\n");
}
#include "main/performance_console.inc"
static void run(const char *command) {
    output[0]=0;
    assert(console_process_native_command(command));
}
static void inspect(const char *command) {
    unsigned before=mutation_calls;
    unsigned long saved=flags;
    run(command);
    assert(mutation_calls==before && flags==saved);
}
static void change(const char *command,unsigned long expected) {
    unsigned before=mutation_calls;
    run(command);
    assert(mutation_calls==before+1 && flags==expected);
    assert(strstr(output,"performance options: flags="));
}
static short complete(const char *command,char **matches,boolean *native_only,char *token_text) {
    char input[128],*token=NULL;
    strcpy(input,command);
    short count=performance_console_complete(input,&token,matches,16,native_only);
    if(token) strcpy(token_text,token);
    return count;
}
int main(void) {
    assert(!console_process_native_command("print"));
    assert(!console_process_native_command("pb_other"));
    inspect("pb"); assert(strstr(output,"pb timer|markers|audio on|off|toggle"));
    inspect("pb status"); inspect("pb help"); inspect("pb timer");
    inspect("performance_options");
    assert(strstr(output,"performance options: flags=0 ticks=1800 markers=0/24"));
    assert(strstr(output,"timer recordings: installed"));
    assert(strstr(output,"PB sound voices: normal=0 movement=12 ready=3"));
    const char *invalid[]={"pb bad","pb timer maybe","pb timer on extra","pb status extra",
        "pb practice extra","pb audio onxxxxxxxxxxxxxxxxxxxxxxxxxxxxx","performance_options -1",
        "performance_options 32","performance_options 99","performance_options 3x",
        "performance_options 3 extra"};
    for(unsigned i=0;i<NUMBEROF(invalid);i++) inspect(invalid[i]);
    change("pb practice",7);
    change("pb audio off",3);
    change("pb timer toggle",2);
    change("pb markers off",0);
    change("pb audio on",4);
    change("pb markers on",6);
    change("pb timer on",7);
    change("pb movement silent",15);
    change("pb weapons silent",31);
    change("pb movement normal",23);
    change("pb weapons toggle",7);
    change("pb movement silent",15);
    change("pb practice",7); /* existing preset retains original sounds */
    inspect("pb movement on"); inspect("pb weapons off");
    change("pb stock",0);
    recordings=0;
    inspect("pb status"); assert(strstr(output,"timer recordings: missing"));
    run("pb audio on"); assert(flags==0 && strstr(output,"Timer recordings are missing"));
    change("pb markers on",2);
    recordings=1;
    for(unsigned value=0;value<=31;value++) {
        char command[64]; snprintf(command,sizeof(command)," performance_options\t%u  ",value);
        change(command,value);
    }
    host=FALSE;
    run("pb stock"); assert(flags==31 && strstr(output,"change refused"));
    inspect("pb status"); assert(strstr(output,"timer audio ON"));
    host=TRUE; flags=3; peer_support=3;
    run("pb audio on"); assert(flags==3 && strstr(output,"change refused"));
    run("pb practice"); assert(flags==3 && strstr(output,"change refused"));
    change("pb timer off",2);
    change("pb stock",0);
    char *matches[16],token[128]; boolean native_only;
    assert(complete("pb ",matches,&native_only,token)==9 && native_only);
    assert(complete("pb mar",matches,&native_only,token)==1 && !strcmp(matches[0],"markers"));
    assert(!strcmp(token,"mar"));
    assert(complete("pb markers ",matches,&native_only,token)==3 && native_only);
    assert(complete("pb audio tog",matches,&native_only,token)==1 && !strcmp(matches[0],"toggle"));
    assert(complete("performance_options ",matches,&native_only,token)==16 && native_only);
    assert(complete("pb movement s",matches,&native_only,token)==1 && !strcmp(matches[0],"silent"));
    assert(complete("pb weapons n",matches,&native_only,token)==1 && !strcmp(matches[0],"normal"));
    assert(complete("performance_options 3",matches,&native_only,token)==3);
    assert(complete("p",matches,&native_only,token)==2 && !native_only);
    assert(complete("print",matches,&native_only,token)==NONE);
    assert(complete("(print ",matches,&native_only,token)==NONE);
    assert(complete("pb stock ",matches,&native_only,token)==0);
    puts("performance console: PASS");
    return 0;
}
'''


class PerformanceConsoleTests(unittest.TestCase):
    def test_controls_completion_and_authority(self):
        with tempfile.TemporaryDirectory(prefix="halo-pb-console-") as temporary:
            source = Path(temporary) / "console_test.c"
            binary = Path(temporary) / "console_test"
            source.write_text(HARNESS)
            subprocess.run([
                "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT / "source"),
                "-iquote", str(ROOT / "port/linux/include"),
                "-iquote", str(ROOT / "port/linux/game"),
                str(source), "-o", str(binary),
            ], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    unittest.main()
