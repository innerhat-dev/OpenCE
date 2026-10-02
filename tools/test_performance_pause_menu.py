"""Exercise the production native pause definitions and staged host controls.

The fixture supplies map tags, widget allocation, and the authority setter. It
checks the actual runtime tag construction and option callbacks, including
split-screen isolation and map reloads; real rendering/input remain app checks.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.test_performance_variants import block

ROOT = Path(__file__).resolve().parents[1]

PREFIX = r'''
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
typedef unsigned char byte, boolean;
typedef unsigned short word;
typedef struct { short y0,x0,y1,x1; } rectangle2d;
typedef struct { float alpha,red,green,blue; } real_argb_color;
#define TRUE 1
#define FALSE 0
#define NONE (-1)
#define MAXIMUM_NUMBER_OF_LOCAL_PLAYERS 4
#define FLAG(n) (1L << (n))
#define csmemset memset
#define csmemcpy memcpy
enum { _gamepad_analog_button_a=0, _gamepad_analog_button_b=1,
 _gamepad_binary_button_dpad_up=8, _gamepad_binary_button_dpad_down,
 _gamepad_binary_button_dpad_left, _gamepad_binary_button_dpad_right,
 _gamepad_binary_button_start, _gamepad_binary_button_back, NUMBER_OF_GAMEPAD_BUTTONS=16 };
enum { UNICODE_STRING_LIST_TAG='ustr', _performance_option_match_timer=1,
 _performance_option_spawn_markers=2, _performance_option_timer_audio=4,
 _performance_option_silent_movement=8, _performance_option_silent_weapon_ready=16,
 PERFORMANCE_PRACTICE_FLAGS=7, PERFORMANCE_OPTIONS_MASK=31 };
struct tag_block { long count; void *address; void *definition; };
struct tag_reference { unsigned long group_tag; char *name; long name_length,index; };
struct tag_data { long size; unsigned long pad; long file_offset; void *address,*definition; };
struct string_list { struct tag_block strings; };
struct string_list_entry { struct tag_data string; };
struct widget_instance {
 long definition_tag_index; short local_player_index,type; boolean disabled;
 struct widget_instance *parent,*child,*next,*focused_child;
 union { struct { short selected_index; unsigned number_of_items; } list;
 struct { short string_list_index; } text_box; } parameters;
};
struct event_record { int unused; };
static size_t ustrlen(const wchar_t *s) { size_t n=0; while(s[n]) ++n; return n; }
/* EXTRACTED NATIVE DEFINITIONS */
'''

STUBS = r'''
static struct ui_widget_definition originals[6], frame, legend;
static long native_pause_frame_tag(short height) { assert(height==240); frame.bounds=(rectangle2d){0,-4,240,222}; return 9001; }
static long native_pause_legend_tag(void) { legend.bounds=(rectangle2d){0,0,20,200}; return 9002; }
static struct ui_widget_child_reference root_children[3][3], list_children[2];
static const char *original_names[6]={
 "ui\\shell\\multiplayer_game\\pause_game\\1p_pause_game",
 "ui\\shell\\multiplayer_game\\pause_game\\2p_pause_game",
 "ui\\shell\\multiplayer_game\\pause_game\\4p_pause_game",
 "ui\\shell\\multiplayer_game\\pause_game\\mp_pause_list", "resume", "quit"};
static struct { long group,id; const char *name; void *definition; } registry[64];
static unsigned registry_count,generation,set_calls,host_flags;
static boolean host=TRUE,refuse;
static long tag_loaded(long group,const char *name) {
 if(group==FONT_GROUP_TAG && !strcmp(name,"ui\\small_ui")) return 7;
 for(unsigned i=0;i<6;i++) if(group==UI_WIDGET_DEFINITION_TAG && !strcmp(name,original_names[i])) return i+1;
 for(unsigned i=0;i<registry_count;i++) if(group==registry[i].group && !strcmp(name,registry[i].name)) return registry[i].id;
 return NONE;
}
static void *tag_get(long group,long index) {
 (void)group;
 if(index==9001) return &frame;
 if(index==9002) return &legend;
 if(index>=1 && index<=6) return &originals[index-1];
 for(unsigned i=0;i<registry_count;i++) if(index==registry[i].id) return registry[i].definition;
 assert(!"invalid tag"); return NULL;
}
#define ui_widget_definition_get(i) ((struct ui_widget_definition *)tag_get(UI_WIDGET_DEFINITION_TAG,(i)))
static long cache_files_register_runtime_ui_tag(long group,const char *name,void *definition) {
 for(unsigned i=0;i<registry_count;i++) if(!strcmp(name,registry[i].name)) {
   assert(group==registry[i].group && definition==registry[i].definition); return registry[i].id;
 }
 assert(registry_count<64); unsigned i=registry_count++;
 registry[i].group=group; registry[i].name=name; registry[i].definition=definition;
 return registry[i].id=100+generation*100+i;
}
static void *global_network_game_server_get(void) { return host ? &host : NULL; }
static unsigned long performance_options_get_flags(void) { return host_flags; }
static boolean performance_options_set_host_flags(unsigned long flags) {
 assert(host); ++set_calls; if(refuse) return FALSE; host_flags=flags; return TRUE;
}
static struct widget_instance *widget_instance_find_by_tag_index_recursive(struct widget_instance *w,long tag) {
 if(w->definition_tag_index==tag) return w;
 for(struct widget_instance *c=w->child;c;c=c->next) {
   struct widget_instance *result=widget_instance_find_by_tag_index_recursive(c,tag);
   if(result) return result;
 }
 return NULL;
}
static boolean widget_event_function_list_widget_goto_next_item(struct widget_instance *w,struct event_record *e,boolean *d) {
 (void)e; (void)d; w->parameters.list.selected_index=(w->parameters.list.selected_index+1)%w->parameters.list.number_of_items; return TRUE;
}
/* PRODUCTION NATIVE MENU */
'''

HARNESS = r'''
static long game_settings_pause_tag(short layout) { return 900 + layout; }
static struct widget_instance *make_widget(long tag,struct widget_instance *parent,short local) {
 struct widget_instance *w=calloc(1,sizeof(*w)); assert(w);
 struct ui_widget_definition *def=ui_widget_definition_get(tag);
 w->parent=parent; w->local_player_index=local; w->definition_tag_index=tag; w->type=def->type;
 if(def->type==_ui_widget_type_spinner_list)
   w->parameters.list.number_of_items=((struct string_list *)tag_get(UNICODE_STRING_LIST_TAG,def->text_label_string_list.index))->strings.count;
 struct widget_instance **tail=&w->child;
 for(long i=0;i<def->child_widgets.count;i++) {
   struct ui_widget_child_reference *c=(struct ui_widget_child_reference *)def->child_widgets.address+i;
   *tail=make_widget(c->widget_tag.index,w,local); tail=&(*tail)->next;
 }
 w->focused_child=w->child;
 if(w->child && w->child->definition_tag_index==9001) w->focused_child=w->child->next;
 return w;
}
static void free_widget(struct widget_instance *w) {
 struct widget_instance *next;
 for(struct widget_instance *c=w->child;c;c=next) { next=c->next; free_widget(c); }
 free(w);
}
static struct widget_instance *control(struct widget_instance *root,int i) {
 struct widget_instance *w=widget_instance_find_by_tag_index_recursive(root,performance_pause_tags[i]); assert(w); return w;
}
static struct widget_instance *open_options(int layout,int local) {
 struct widget_instance *root=make_widget(performance_pause_tags[_pp_options_1p+layout],NULL,local);
 assert(performance_pause_event(root,_performance_pause_created)); return root;
}
static void setup(void) {
 memset(originals,0,sizeof(originals));
 originals[3].type=_ui_widget_type_column_list;
 originals[3].child_widgets.count=2; originals[3].child_widgets.address=list_children;
 list_children[0].widget_tag.index=5; list_children[1].widget_tag.index=6;
 originals[4].type=originals[5].type=_ui_widget_type_text_box;
 originals[4].text_font.index=9; originals[4].background_bitmap.index=8;
 originals[4].vertical_offset=3;
 originals[4].bounds.x1=202; originals[4].bounds.y1=27;
 for(int i=0;i<3;i++) {
   originals[i].bounds.x1=i==2 ? 320 : 640; originals[i].bounds.y1=i ? 240 : 480;
   originals[i].child_widgets.count=3; originals[i].child_widgets.address=root_children[i];
   root_children[i][0].widget_tag.index=5; root_children[i][1].widget_tag.index=4; root_children[i][2].widget_tag.index=6;
   root_children[i][1].horizontal_offset=i==2 ? 58 : 218;
   root_children[i][1].vertical_offset=i ? 95 : 207;
 }
}
int main(void) {
 setup(); struct ui_widget_definition before[6]; memcpy(before,originals,sizeof(before));
 assert(performance_pause_remap_tag(5)==5 && performance_pause_remap_tag(NONE)==NONE);
 assert(performance_pause_remap_tag(1)!=1 && registry_count==32);
 assert(!memcmp(before,originals,sizeof(before)));
 for(int i=0;i<3;i++) {
   assert(performance_pause_remap_tag(i+1)==performance_pause_tags[_pp_pause_1p+i]);
   assert(performance_pause_children[i][1].horizontal_offset==root_children[i][1].horizontal_offset);
   assert(performance_pause_children[i][1].vertical_offset==root_children[i][1].vertical_offset-28);
   assert(performance_pause_list_children[i][0].widget_tag.index==5);
   assert(performance_pause_list_children[i][3].widget_tag.index==6);
   assert(performance_pause_settings_events[i][0].widget_tag.index==900+i);
   assert(performance_pause_entry_events[i][0].widget_tag.index==performance_pause_tags[_pp_options_1p+i]);
   assert(performance_pause_definitions[_pp_options_1p+i].controller_index==_widget_controller_any);
   int x=(originals[i].bounds.x1-202)/2, y=(originals[i].bounds.y1-240)/2;
   assert(performance_pause_option_children[i][0].widget_tag.index==9001);
   assert(performance_pause_option_children[i][0].horizontal_offset==x-8);
   assert(performance_pause_option_children[i][0].vertical_offset==y);
   assert(performance_pause_option_children[i][1].horizontal_offset==x);
   assert(performance_pause_option_children[i][1].vertical_offset==y+22);
   assert(performance_pause_option_children[i][2].vertical_offset==y);
   assert(performance_pause_option_children[i][3].widget_tag.index==9002);
   assert(performance_pause_option_children[i][3].horizontal_offset==x+17);
   assert(performance_pause_option_children[i][3].vertical_offset==y+215);
   assert(performance_pause_definitions[_pp_options_1p+i].child_widgets.count==(i ? 4:5));
   if(!i) assert(performance_pause_option_children[i][4].vertical_offset+40<=originals[i].bounds.y1);
 }
 assert(performance_pause_definitions[_pp_column].child_widgets.count==7);
 for(int i=0;i<7;i++) {
   struct ui_widget_child_reference *row=&performance_pause_column_children[i];
   struct ui_widget_definition *definition=ui_widget_definition_get(row->widget_tag.index);
   assert(row->vertical_offset==27*i && definition->bounds.y1==27 && definition->bounds.x1==202);
   assert(row->horizontal_offset==0 && definition->vertical_offset==3 && definition->text_font.index==9);
   assert(definition->background_bitmap.index==originals[4].background_bitmap.index);
   assert(row->vertical_offset+definition->bounds.y1<=performance_pause_definitions[_pp_column].bounds.y1);
   struct widget_instance candidate={.definition_tag_index=row->widget_tag.index};
   assert(performance_pause_is_spinner(&candidate)==(i<6));
 }
 assert(!performance_pause_is_spinner(NULL));
 assert(performance_pause_definitions[_pp_title].bounds.y1==22);
 assert(performance_pause_definitions[_pp_title].text_font.index==9);
 assert(performance_pause_definitions[_pp_title].vertical_offset==0);
 // Seven complete buttons finish at the cap-preserved footer divider (240-29).
 assert(22+performance_pause_definitions[_pp_column].bounds.y1==211);
 assert(performance_pause_definitions[_pp_title].string_list_index==12);
 for(int text=3;text<=4;text++) {
   boolean line_break=FALSE;
   for(unsigned i=0;performance_pause_text[text][i];i++)
     if(performance_pause_text[text][i]==L'\r') line_break=TRUE;
 assert(!line_break);
 }
 assert(performance_pause_definitions[_pp_entry_1p].string_list_index==0);
 assert(performance_pause_root_events[1].flags==FLAG(_event_handler_go_back_to_previous_widget_bit));
 assert(performance_pause_apply_events[0].flags==(FLAG(_event_handler_run_function_bit)|FLAG(_event_handler_go_back_to_previous_widget_bit)));
 for(unsigned flags=0;flags<=PERFORMANCE_OPTIONS_MASK;flags++) {
   host_flags=flags;
   struct widget_instance *w=open_options(flags%3,flags%MAXIMUM_NUMBER_OF_LOCAL_PLAYERS);
   assert(performance_pause_drafts[flags%MAXIMUM_NUMBER_OF_LOCAL_PLAYERS].flags==flags);
   assert(control(w,_pp_preset)->parameters.list.selected_index==(flags==0 ? 0:flags==7 ? 1:2));
   assert(control(w,_pp_movement)->parameters.list.selected_index==!!(flags&8));
   assert(control(w,_pp_weapon)->parameters.list.selected_index==!!(flags&16));
   assert(performance_pause_event(control(w,_pp_apply),_performance_pause_apply) && host_flags==flags);
   free_widget(w);
 }
 set_calls=0;
 host_flags=2; struct widget_instance *root=open_options(0,0);
 assert(control(root,_pp_preset)->parameters.list.selected_index==2);
 assert(control(root,_pp_markers)->parameters.list.selected_index==1);
 control(root,_pp_preset)->parameters.list.selected_index=1; performance_pause_update(root);
 assert(host_flags==2 && set_calls==0 && control(root,_pp_timer)->parameters.list.selected_index==1 && control(root,_pp_audio)->parameters.list.selected_index==1);
 control(root,_pp_markers)->parameters.list.selected_index=0; performance_pause_update(root);
 assert(performance_pause_drafts[0].flags==5 && control(root,_pp_preset)->parameters.list.selected_index==2);
 free_widget(root); root=open_options(0,0); /* Cancel and reopen discard the draft. */
 assert(performance_pause_drafts[0].flags==2 && host_flags==2 && set_calls==0);
 struct widget_instance *other=open_options(2,1);
 control(root,_pp_preset)->parameters.list.selected_index=1; performance_pause_update(root);
 assert(performance_pause_drafts[1].flags==2); /* Independent local-player drafts. */
 refuse=TRUE; assert(!performance_pause_event(control(root,_pp_apply),_performance_pause_apply));
 assert(host_flags==2 && performance_pause_drafts[0].flags==7 && set_calls==1);
 refuse=FALSE; assert(performance_pause_event(control(root,_pp_apply),_performance_pause_apply));
 assert(host_flags==7 && set_calls==2);
 control(root,_pp_movement)->parameters.list.selected_index=1; performance_pause_update(root);
 assert(performance_pause_drafts[0].flags==15 && host_flags==7 && set_calls==2);
 control(root,_pp_weapon)->parameters.list.selected_index=1; performance_pause_update(root);
 assert(performance_pause_drafts[0].flags==31 && control(root,_pp_preset)->parameters.list.selected_index==2 && host_flags==7);
 control(root,_pp_column)->focused_child=control(root,_pp_movement); performance_pause_update(root);
 assert(control(root,_pp_footer)->parameters.text_box.string_list_index==20);
 control(root,_pp_column)->focused_child=control(root,_pp_weapon); performance_pause_update(root);
 assert(control(root,_pp_footer)->parameters.text_box.string_list_index==21);
 control(root,_pp_column)->focused_child=control(root,_pp_markers); performance_pause_update(root);
 assert(control(root,_pp_footer)->parameters.text_box.string_list_index==22);
 control(root,_pp_column)->focused_child=control(root,_pp_audio); performance_pause_update(root);
 assert(control(root,_pp_footer)->parameters.text_box.string_list_index==23);
 control(root,_pp_preset)->parameters.list.selected_index=1; performance_pause_update(root);
 assert(performance_pause_drafts[0].flags==7 && !control(root,_pp_movement)->parameters.list.selected_index && !control(root,_pp_weapon)->parameters.list.selected_index);
 control(root,_pp_movement)->parameters.list.selected_index=1; performance_pause_update(root);
 control(root,_pp_preset)->parameters.list.selected_index=0; performance_pause_update(root);
 assert(!performance_pause_drafts[0].flags && !control(root,_pp_movement)->parameters.list.selected_index && !control(root,_pp_weapon)->parameters.list.selected_index);
 free_widget(root); root=open_options(0,0); /* Cancel restores live host defaults. */
 assert(performance_pause_drafts[0].flags==7 && !control(root,_pp_movement)->parameters.list.selected_index && !control(root,_pp_weapon)->parameters.list.selected_index);
 assert(performance_pause_event(control(root,_pp_movement),_performance_pause_next));
 assert(performance_pause_event(control(root,_pp_weapon),_performance_pause_next));
 assert(performance_pause_drafts[0].flags==31 && host_flags==7 && set_calls==2);
 assert(performance_pause_event(control(root,_pp_apply),_performance_pause_apply) && host_flags==31 && set_calls==3);
 host=FALSE; performance_pause_update(other);
 assert(control(other,_pp_preset)->disabled && performance_pause_drafts[1].flags==31);
 assert(control(other,_pp_movement)->disabled && control(other,_pp_weapon)->disabled);
 assert(!widget_instance_find_by_tag_index_recursive(other,performance_pause_tags[_pp_footer]));
 control(other,_pp_timer)->parameters.list.selected_index=0; performance_pause_update(other);
 control(other,_pp_movement)->parameters.list.selected_index=0; performance_pause_update(other);
 control(other,_pp_weapon)->parameters.list.selected_index=0; performance_pause_update(other);
 assert(control(other,_pp_timer)->parameters.list.selected_index==1 && host_flags==31);
 assert(control(other,_pp_movement)->parameters.list.selected_index==1 && control(other,_pp_weapon)->parameters.list.selected_index==1);
 assert(!performance_pause_event(control(other,_pp_timer),_performance_pause_next));
 assert(!performance_pause_event(control(other,_pp_movement),_performance_pause_next));
 assert(!performance_pause_event(control(other,_pp_weapon),_performance_pause_next));
 assert(performance_pause_event(control(other,_pp_apply),_performance_pause_apply) && set_calls==3);
 host_flags=1; performance_pause_update(other); assert(performance_pause_drafts[1].flags==1);
 free_widget(root); free_widget(other); long old=performance_pause_tags[_pp_pause_1p];
 registry_count=0; generation++; assert(performance_pause_remap_tag(1)!=old && registry_count==32);
 assert(!performance_pause_drafts[0].root && !performance_pause_drafts[1].root);
 return 0;
}
'''


class PerformancePauseMenuTest(unittest.TestCase):
    def test_native_layout_staging_authority_and_reload(self):
        source = (ROOT / "source/interface/ui_widget.c").read_text()
        declarations = []
        for name in ("ui_widget_event_handler_reference", "ui_widget_child_reference", "ui_widget_definition"):
            declarations.append(block(source, f"struct {name}\n{{") + ";")
        for member in ("_ui_widget_type_container", "UI_WIDGET_DEFINITION_TAG =", "_widget_controller0", "_widget_pass_unhandled_events_to_children_bit =", "_event_handler_close_current_widget_bit", "_list_items_generated_in_code", "_text_justification_left", "_widget_event_b_button ="):
            start = source.rfind("enum\n{", 0, source.index(member))
            declarations.append(block(source[start:], "enum\n{") + ";")
        fixture = PREFIX + "\n".join(declarations) + STUBS
        fixture += (ROOT / "source/interface/performance_pause_menu.inc").read_text() + HARNESS
        with tempfile.TemporaryDirectory(prefix="halo-native-pause-") as tmp:
            path = Path(tmp) / "test.c"
            path.write_text(fixture)
            binary = Path(tmp) / "test"
            subprocess.run(["clang", "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wno-multichar", "-fshort-wchar", str(path), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    unittest.main()
