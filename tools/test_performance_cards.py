"""Exercise the production gametype-card callback and saved-option decoder."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from tools.test_runtime_ui_tags import c_block

ROOT = Path(__file__).resolve().parents[1]

PREFIX = r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef unsigned char byte,boolean;
typedef unsigned short word;
typedef float real;
#define TRUE 1
#define FALSE 0
#define NONE (-1)
#define HALO_PORT_MAXIMUM_NETWORK_PLAYERS 128
#define NUMBEROF(a) (sizeof(a)/sizeof((a)[0]))
#define TEST_FLAG(v,n) ((v)&(1u<<(n)))
#define match_vassert(file,line,condition,message) assert(condition)
enum game_engine_type { game_engine_ctf=1,game_engine_slayer,game_engine_oddball,game_engine_king,game_engine_race };
enum { UNICODE_STRING_LIST_TAG='ustr', _ui_widget_type_text_box=1,_ui_widget_type_bitmap=0,_ui_widget_type_spinner_list=2,
       _multiplayer_game_bitmap_ctf,_multiplayer_game_bitmap_king,_multiplayer_game_bitmap_slayer,
       _multiplayer_game_bitmap_oddball,_multiplayer_game_bitmap_race,_multiplayer_game_bitmap_unknown };
/* VARIANT DECLARATIONS */
#define __GAME_ENGINE_H
#include "game/performance_variant.h"
/* PLAYLIST DECLARATION */
struct widget_instance { long definition_tag_index; struct widget_instance *child,*next;
    boolean visible; union { struct { wchar_t *text; } text_box; struct { void *list_items; } list; } parameters;
    struct { short current_frame_index; } animation; };
struct ui_widget_definition { short type; long child_count; };
static struct ui_widget_definition definitions[16];
static struct { long profile_index; struct playlist_profile profile; } cached_variant_profile[3];
static wchar_t const *descriptions[]={
    L"Custom Game Type\r\nCapture the Flag",L"Custom Game Type\r\nCapture the Flag",
    L"Custom Game Type\r\nSlayer\r\nFree for All",L"Custom Game Type\r\nSlayer\r\nTeams Enabled",
    L"Custom Game Type\r\nOddball\r\nFree for All",L"Custom Game Type\r\nOddball\r\nTeams Enabled",
    L"Custom Game Type\r\nKing of the Hill\r\nFree for All",L"Custom Game Type\r\nKing of the Hill\r\nTeams Enabled",
    L"Custom Game Type\r\nRacing\r\nFree for All",L"Custom Game Type\r\nRacing\r\nTeams Enabled",
    L"Classic deathmatch.\r\n15 kills to win."};
static unsigned long ustrlen(wchar_t const *s) { unsigned long n=0; while(s[n])n++; return n; }
static unsigned long ustrnlen(wchar_t const *s,unsigned long max) { unsigned long n=0; while(n<max && s[n])n++; return n; }
static wchar_t *ustrncpy(wchar_t *d,wchar_t const *s,unsigned long n) { unsigned long i=0; for(;i<n && s[i];i++)d[i]=s[i]; for(;i<n;i++)d[i]=0; return d; }
static boolean equal(wchar_t const *a,wchar_t const *b) { unsigned long n=ustrlen(a); return n==ustrlen(b) && !memcmp(a,b,(n+1)*sizeof(wchar_t)); }
static long tag_loaded(long group,char const *name) { assert(group=='ustr'); (void)name; return 100; }
static wchar_t *unicode_string_list_get_string(long tag,short index) { assert(tag==100 && index>=0 && index<11); return (wchar_t *)descriptions[index]; }
static struct ui_widget_definition *ui_widget_definition_get(long tag) { assert(tag>=0 && tag<16); return &definitions[tag]; }
static void spinner_list_3wide_determine_displayed_item_indices(struct widget_instance *w,long *indices) { (void)w; for(int i=0;i<3;i++)indices[i]=i; }
static void variant_profile_update_cache_for_nwide_list(long *indices,long count) { assert(count==3); for(int i=0;i<3;i++)assert(indices[i]==i); }
static struct widget_instance *widget_instance_get_nth_child(struct widget_instance *w,long n) { w=w->child; while(n--)w=w->next; return w; }
static void *ui_widget_realloc(void *p,unsigned long bytes,char const *file,long line) { (void)file;(void)line; return realloc(p,bytes); }
/* PRODUCTION FUNCTIONS */
'''

HARNESS = r'''
static struct widget_instance list,cards[3],names[3],icons[3],labels[3],locks[3];
static long profile_indices[]={0,1,2};
static void setup(void) {
    assert(sizeof(wchar_t)==2 && sizeof(struct game_variant)==104 && sizeof(struct playlist_profile)==104);
    list.definition_tag_index=0; list.child=cards; list.parameters.list.list_items=profile_indices;
    definitions[0]=(struct ui_widget_definition){2,3};
    for(int i=0;i<3;i++) {
        cards[i].definition_tag_index=1+4*i; cards[i].child=&names[i]; cards[i].next=i<2 ? &cards[i+1]:NULL;
        names[i].definition_tag_index=2+4*i; names[i].next=&icons[i];
        icons[i].definition_tag_index=3+4*i; icons[i].next=&labels[i];
        labels[i].definition_tag_index=4+4*i; labels[i].next=&locks[i];
        definitions[1+4*i]=(struct ui_widget_definition){0,4};
        definitions[2+4*i].type=1; definitions[3+4*i].type=0; definitions[4+4*i].type=1;
        cached_variant_profile[i].profile_index=i;
        cached_variant_profile[i].profile.name[0]='A'+i;
    }
}
static void check_cards(void) {
    wchar_t expected[256];
    for(int engine=game_engine_ctf;engine<=game_engine_race;engine++) for(int teams=0;teams<2;teams++)
    for(unsigned flags=0;flags<=PERFORMANCE_OPTIONS_MASK;flags++) {
        for(int i=0;i<3;i++) {
            struct playlist_profile *p=&cached_variant_profile[i].profile;
            p->engine_type=engine; p->teams=teams;
            performance_variant_set_flags((struct game_variant *)p,i==1 ? flags:0);
        }
        mutliplayer_settings_select_list_update_displayed_items(&list);
        unsigned index=2*(engine-1)+teams;
        assert(equal(labels[0].parameters.text_box.text,descriptions[index]));
        assert(equal(labels[2].parameters.text_box.text,descriptions[index]));
        ustrncpy(expected,descriptions[index],256);
        if(flags) ustrncpy(expected+ustrlen(expected),L"\r\nPB options active",20);
        assert(equal(labels[1].parameters.text_box.text,expected));
        /* Repeated per-frame callbacks replace the base description: no duplicate status. */
        mutliplayer_settings_select_list_update_displayed_items(&list);
        assert(equal(labels[1].parameters.text_box.text,expected));
    }
    struct playlist_profile *p=&cached_variant_profile[1].profile;
    p->flags=1; performance_variant_set_flags((struct game_variant *)p,PERFORMANCE_OPTIONS_MASK);
    mutliplayer_settings_select_list_update_displayed_items(&list);
    ustrncpy(expected,descriptions[10],256); ustrncpy(expected+ustrlen(expected),L"\r\nPB options active",20);
    assert(equal(labels[1].parameters.text_box.text,expected) && locks[1].visible);
    ((struct game_variant *)p)->universal_variant.pad6^=1;
    mutliplayer_settings_select_list_update_displayed_items(&list);
    assert(equal(labels[1].parameters.text_box.text,descriptions[10]));
}
static void bounds(void) {
    struct { wchar_t text[256]; unsigned sentinel; } buffer;
    struct playlist_profile *p=&cached_variant_profile[0].profile;
    performance_variant_set_flags((struct game_variant *)p,PERFORMANCE_OPTIONS_MASK);
    memset(&buffer,0,sizeof(buffer)); buffer.sentinel=0x12345678;
    playlist_profile_append_performance_status(buffer.text,p);
    assert(equal(buffer.text,L"PB options active"));
    for(int i=0;i<255;i++) buffer.text[i]='x'; buffer.text[255]=0;
    playlist_profile_append_performance_status(buffer.text,p);
    assert(ustrlen(buffer.text)==255 && buffer.sentinel==0x12345678);
    playlist_profile_append_performance_status(NULL,p);
    playlist_profile_append_performance_status(buffer.text,NULL);
}
int main(void) {
    setup(); check_cards(); bounds();
    for(int i=0;i<3;i++) { free(names[i].parameters.text_box.text); free(labels[i].parameters.text_box.text); }
    puts("performance card tests passed"); return 0;
}
'''


class PerformanceCardTests(unittest.TestCase):
    def test_production_card_callback(self):
        engine = (ROOT / "source/game/game_engine.h").read_text()
        source = (ROOT / "source/interface/ui_widget_game_data_input_functions.c").read_text()
        declarations = "\n".join(c_block(engine, signature) + ";" for signature in (
            "struct universal_variant\n", "struct ctf_variant\n", "struct slayer_variant\n",
            "struct king_variant\n", "struct oddball_variant\n", "struct race_variant\n",
            "union game_engine_variant\n", "struct game_variant\n"))
        functions = "\n".join(c_block(source, signature) for signature in (
            "static void playlist_profile_append_performance_status(\n",
            "static void mutliplayer_settings_select_list_update_displayed_items(\n\tstruct widget_instance *list_widget)\n{"))
        fixture = PREFIX.replace("/* VARIANT DECLARATIONS */", declarations)
        fixture = fixture.replace("/* PLAYLIST DECLARATION */", c_block(source, "struct playlist_profile\n") + ";")
        fixture = fixture.replace("/* PRODUCTION FUNCTIONS */", functions) + HARNESS
        fixture = re.sub(r"\bunsigned long\b", "uint32_t", fixture)
        fixture = re.sub(r"\blong\b", "int32_t", fixture)
        with tempfile.TemporaryDirectory(prefix="halo-performance-cards-") as temporary:
            folder = Path(temporary)
            (folder / "fixture.c").write_text(fixture)
            subprocess.run(["clang", "-std=c99", "-fshort-wchar", "-Wall", "-Wextra", "-Werror", "-Wno-multichar",
                            "-I", str(ROOT / "source"), str(folder / "fixture.c"), "-o", str(folder / "fixture")], check=True)
            result = subprocess.run([str(folder / "fixture")], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stdout.strip(), "performance card tests passed")


if __name__ == "__main__":
    unittest.main()
