"""Native game-settings navigation and real TOML persistence, using temporary files."""
import ast
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from tools.test_input_bindings import PREFIX, PORT, ROOT, SDL
from tools.test_performance_ui import fixture_source


CONFIG_HARNESS = r'''
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <SDL3/SDL.h>
#include "port_config.h"
void platform_log(const char *format, ...) { (void)format; }
#ifndef HALO_ANDROID
const char *SDL_GetBasePath(void) {
    static char path[1024]; snprintf(path,sizeof(path),"%s/",getenv("HALO_SAVE_ROOT")); return path;
}
void *SDL_LoadFile(const char *path,size_t *size) {
    FILE *file=fopen(path,"rb"); if(!file) return NULL;
    assert(!fseek(file,0,SEEK_END)); long length=ftell(file); assert(length>=0); rewind(file);
    void *data=malloc((size_t)length+1); assert(data);
    assert(fread(data,1,(size_t)length,file)==(size_t)length); fclose(file); *size=(size_t)length; return data;
}
bool SDL_SaveFile(const char *path,const void *data,size_t size) {
    FILE *file=fopen(path,"wb"); if(!file) return false;
    bool written=fwrite(data,1,size,file)==size; return fclose(file)==0 && written;
}
void SDL_free(void *data) { free(data); }
#endif
int main(int argc,char **argv) {
    assert(argc==5);
    int original=config_boolean("audio.menu_music");
    if(!strcmp(argv[1],"read")) { printf("%d\n",original); return 0; }
    char path[1024]; snprintf(path,sizeof(path),"%s/config.toml",getenv("HALO_SAVE_ROOT"));
    FILE *input=fopen(argv[1],"rb"),*output=fopen(path,"wb"); assert(input && output);
    for(int c;(c=fgetc(input))!=EOF;) assert(fputc(c,output)!=EOF);
    assert(!fclose(input) && !fclose(output));
    if(!strcmp(argv[2],"failure")) assert(!chmod(path,0400));
    int result=config_write_boolean(argv[3],atoi(argv[4]));
    printf("%d %d %d\n",original,result,config_boolean("audio.menu_music"));
    assert(!chmod(path,0600)); return 0;
}
'''

UI_STUBS = r'''
#define csmemcpy memcpy
#define FLAG(n) (1L << (n))
#define MAXIMUM_NUMBER_OF_LOCAL_PLAYERS 4
enum { FONT_GROUP_TAG='font', _ui_audio_feedback_flag_failure=7, _ui_widget_type_bitmap=0 };
/* NATIVE PREVIEW CALLBACK */
enum { _gamepad_analog_button_a=0, _gamepad_analog_button_b=1,
 _gamepad_binary_button_dpad_up=8, _gamepad_binary_button_dpad_down,
 _gamepad_binary_button_dpad_left, _gamepad_binary_button_dpad_right,
 _gamepad_binary_button_start, _gamepad_binary_button_back, NUMBER_OF_GAMEPAD_BUTTONS=16 };
/* NATIVE ENUMS */
#define TEST_FLAG(flags,bit) (((flags) & FLAG(bit)) != 0)
static struct { short pause_game_time_count; boolean sound_paused;
    struct widget_instance *active_widgets[4]; int initialization_thread; } widget_globals;
static boolean settings_game_paused, settings_sound_paused, we_are_at_the_main_menu;
static boolean game_time_get_paused(void) { return settings_game_paused; }
static void game_time_set_paused(boolean paused) { settings_game_paused=paused; }
static void sound_pause(boolean paused) { settings_sound_paused=paused; }
static void main_menu_ensure_player_queues_exist(void) { assert(0); }
static void game_time_dispose_from_old_map(void) { assert(0); }
static void game_time_initialize_for_new_map(void) { assert(0); }
static void game_time_start(void) { assert(0); }
/* PRODUCTION WIDGET PAUSE LIFECYCLE */
struct event_record { int unused; };
static size_t ustrlen(const wchar_t *s) { return wcslen(s); }
static void *global_network_game_server_get(void) { return NULL; }
static unsigned long performance_options_get_flags(void) { return 0; }
static boolean performance_options_set_host_flags(unsigned long flags) { (void)flags; return FALSE; }
static boolean widget_event_function_list_widget_goto_next_item(struct widget_instance *w,struct event_record *e,boolean *d) {
    (void)e; (void)d; w->parameters.list.selected_index=(w->parameters.list.selected_index+1)%w->parameters.list.number_of_items; return TRUE;
}
#include "game/device_settings.h"
static double settings_values[NUMBER_OF_DEVICE_SETTINGS];
static unsigned writes,errors;
static unsigned long applied_mask;
static boolean save_succeeds, rollback_incomplete;
static void ui_play_audio_feedback_sound(short sound) { assert(sound==7 || sound==1); if(sound==7) errors++; }
double device_settings_get(short setting) { assert(setting>=0 && setting<NUMBER_OF_DEVICE_SETTINGS); return settings_values[setting]; }
int device_settings_apply(unsigned long mask,const double values[NUMBER_OF_DEVICE_SETTINGS]) {
    if(!mask) return TRUE;
    writes++; applied_mask=mask; if(!save_succeeds) return FALSE;
    if(rollback_incomplete) { settings_values[_device_setting_fullscreen]=0; return -1; }
    for(unsigned i=0;i<NUMBER_OF_DEVICE_SETTINGS;i++) if(mask & (1UL<<i)) settings_values[i]=values[i];
    return TRUE;
}
/* The shared frame renderer has its own asset/UV fixture. Here its tag
 * boundary provides the production dimensions for Settings composition. */
static long native_pause_frame_tag(short height);
static long native_pause_legend_tag(void);
#include "interface/performance_pause_menu.inc"
#include "interface/game_settings_menu.inc"
'''

UI_HARNESS = r'''
static struct cache_file_tag_instance settings_map[64];
static struct cache_file_tag_header settings_header;
static struct ui_widget_definition originals[12], originals_before[12];
static struct ui_widget_child_reference original_roots[3][5],original_lists[2][4];
static struct ui_widget_event_handler_reference original_entry_events[2];
static long entry_id,profile_id,original_root_ids[3],original_list_ids[2],resume_id,quit_id;
static struct ui_widget_definition native_frames[3];
static int settings_assets[2];
static long native_pause_frame_tag(short height) {
    const short heights[]={159,213,240};
    const char *names[]={"ui\\fixture\\pause_frame159","ui\\fixture\\pause_frame213","ui\\fixture\\pause_frame240"};
    for(unsigned i=0;i<NUMBEROF(heights);i++) if(height==heights[i]) {
        long existing=tag_loaded('DeLa',names[i]); if(existing!=NONE) return existing;
        performance_pause_clear_definition(&native_frames[i]);
        native_frames[i].bounds=(rectangle2d){0,-4,height,222};
        return cache_files_register_runtime_ui_tag('DeLa',names[i],&native_frames[i]);
    }
    assert(0); return NONE;
}
static long native_pause_legend_tag(void) {return tag_loaded('DeLa',"ui\\shell\\main_menu\\button_key_sm");}
static long add_stock(long group,const char *name,void *definition) {
    assert(settings_header.tag_count < (long)NUMBEROF(settings_map));
    long id=stock_id(settings_header.tag_count);
    settings_map[settings_header.tag_count++]=(struct cache_file_tag_instance){group,{NONE,NONE},id,(char *)name,definition,{0,0}};
    return id;
}
/* Retail Multiplayer chooser geometry from the owned ui.map audit. The
 * full four-choice source stays intact while Settings borrows two rows. */
#define CHOOSER_PREFIX "ui\\shell\\main_menu\\multiplayer_type_select\\"
enum { CHOOSER_ROOT, CHOOSER_HEADER, CHOOSER_LIST, CHOOSER_PREVIEW,
    CHOOSER_MP_PICTURE, CHOOSER_DESCRIPTION, CHOOSER_COOP, CHOOSER_SPLIT,
    CHOOSER_CONNECTED, CHOOSER_GAMETYPES, CHOOSER_PROFILE_PICTURE,
    CHOOSER_BUTTON_KEY, CHOOSER_BLUE_LINE, CHOOSER_WIDGET_COUNT };
static const char *chooser_names[CHOOSER_WIDGET_COUNT]={
    CHOOSER_PREFIX "multiplayer_type_select_screen", CHOOSER_PREFIX "header_multiplayer",
    CHOOSER_PREFIX "multiplayer_type_select_list", CHOOSER_PREFIX "multiplayer_type_list_ext_desc",
    CHOOSER_PREFIX "multiplayer_options_pic", CHOOSER_PREFIX "multiplayer_options_txt",
    CHOOSER_PREFIX "multiplayer_type_coop_item", CHOOSER_PREFIX "multiplayer_type_split_item",
    CHOOSER_PREFIX "multiplayer_type_conn_item", CHOOSER_PREFIX "multiplayer_type_gametypes_item",
    "ui\\shell\\main_menu\\settings_select\\player_setup\\player_profile_edit\\profile_edit_extended_desc_pic",
    "ui\\shell\\main_menu\\button_key", "ui\\shell\\main_menu\\blueline"
};
static struct {
    struct ui_widget_definition defs[CHOOSER_WIDGET_COUNT];
    struct ui_widget_child_reference root[4], list[4], preview[2];
    struct ui_widget_event_handler_reference root_event, row_events[4][2];
    struct ui_widget_game_data_input_reference input;
} chooser,chooser_before;
static long chooser_ids[CHOOSER_WIDGET_COUNT];
static int chooser_assets[8];
static void chooser_setup(void) {
    memset(&chooser,0,sizeof(chooser));
    long large_font=add_stock(FONT_GROUP_TAG,"ui\\large_ui",&chooser_assets[0]);
    long gradient=add_stock('bitm',"ui\\shell\\bitmaps\\gradient",&chooser_assets[1]);
    long panel=add_stock('bitm',"ui\\shell\\bitmaps\\list_field",&chooser_assets[2]);
    long mp_picture=add_stock('bitm',CHOOSER_PREFIX "mp_options",&chooser_assets[3]);
    long profile_picture=add_stock('bitm',"ui\\shell\\main_menu\\settings_select\\player_setup\\player_profile_edit\\profile_options",&chooser_assets[4]);
    long row_top=add_stock('bitm',"ui\\shell\\bitmaps\\list_item_bkd_top",&chooser_assets[5]);
    long row_regular=add_stock('bitm',"ui\\shell\\bitmaps\\list_item_bkd",&chooser_assets[6]);
    long blue_line=add_stock('bitm',"ui\\shell\\bitmaps\\blue",&chooser_assets[7]);
    for(unsigned i=0;i<CHOOSER_WIDGET_COUNT;i++) {
        performance_pause_clear_definition(&chooser.defs[i]);
        chooser.defs[i].controller_index=0;
        chooser_ids[i]=add_stock('DeLa',chooser_names[i],&chooser.defs[i]);
    }
    chooser.defs[CHOOSER_ROOT].bounds=(rectangle2d){0,0,480,640};
    chooser.defs[CHOOSER_ROOT].controller_index=4;
    chooser.defs[CHOOSER_ROOT].flags=1;
    chooser.defs[CHOOSER_ROOT].background_bitmap=device_settings_reference('bitm',gradient);
    chooser.defs[CHOOSER_ROOT].child_widgets=(struct tag_block){4,chooser.root,NULL};
    chooser.root_event=(struct ui_widget_event_handler_reference){.flags=0x80,.event_type=24,.function=24,
        .widget_tag={'DeLa',NULL,0,NONE}};
    chooser.defs[CHOOSER_ROOT].event_handlers=(struct tag_block){1,&chooser.root_event,NULL};
    chooser.defs[CHOOSER_HEADER].bounds=(rectangle2d){11,35,70,298};
    chooser.defs[CHOOSER_LIST].bounds=chooser.defs[CHOOSER_ROOT].bounds;
    chooser.defs[CHOOSER_LIST].type=_ui_widget_type_column_list;
    chooser.defs[CHOOSER_LIST].controller_index=4;
    chooser.defs[CHOOSER_LIST].flags=0x21;
    chooser.defs[CHOOSER_LIST].child_widgets=(struct tag_block){4,chooser.list,NULL};
    chooser.defs[CHOOSER_LIST].extended_description_widget=device_settings_reference('DeLa',chooser_ids[CHOOSER_PREVIEW]);
    chooser.input.function=5;
    chooser.defs[CHOOSER_LIST].game_data_inputs=(struct tag_block){1,&chooser.input,NULL};
    chooser.defs[CHOOSER_PREVIEW].bounds=(rectangle2d){78,275,400,595};
    chooser.defs[CHOOSER_PREVIEW].background_bitmap=device_settings_reference('bitm',panel);
    chooser.defs[CHOOSER_PREVIEW].text_color=(real_argb_color){1,0,0.5f,1};
    chooser.defs[CHOOSER_PREVIEW].child_widgets=(struct tag_block){2,chooser.preview,NULL};
    chooser.defs[CHOOSER_MP_PICTURE].bounds=(rectangle2d){82,288,326,595};
    chooser.defs[CHOOSER_MP_PICTURE].background_bitmap=device_settings_reference('bitm',mp_picture);
    chooser.defs[CHOOSER_PROFILE_PICTURE].bounds=(rectangle2d){85,288,287,567};
    chooser.defs[CHOOSER_PROFILE_PICTURE].background_bitmap=device_settings_reference('bitm',profile_picture);
    chooser.defs[CHOOSER_DESCRIPTION].bounds=(rectangle2d){285,290,390,580};
    chooser.defs[CHOOSER_DESCRIPTION].type=_ui_widget_type_text_box;
    chooser.defs[CHOOSER_DESCRIPTION].text_font=device_settings_reference(FONT_GROUP_TAG,large_font);
    chooser.defs[CHOOSER_DESCRIPTION].text_color=(real_argb_color){1,0.156863f,0.588235f,1};
    chooser.defs[CHOOSER_DESCRIPTION].text_label_string_list=ref(STRINGS_TAG);
    chooser.defs[CHOOSER_BUTTON_KEY].bounds=(rectangle2d){414,371,440,577};
    chooser.defs[CHOOSER_BLUE_LINE].bounds=(rectangle2d){0,0,2,192};
    chooser.defs[CHOOSER_BLUE_LINE].background_bitmap=device_settings_reference('bitm',blue_line);
    unsigned root_children[4]={CHOOSER_HEADER,CHOOSER_LIST,CHOOSER_BUTTON_KEY,CHOOSER_BLUE_LINE};
    for(unsigned i=0;i<4;i++) {
        performance_pause_child(&chooser.root[i],chooser_ids[root_children[i]],i==3 ? 64:0,i==3 ? 186:0);
        struct ui_widget_definition *row=&chooser.defs[CHOOSER_COOP+i];
        row->type=_ui_widget_type_text_box; row->controller_index=4;
        row->bounds=(rectangle2d){111+33*i,51,143+33*i,283};
        row->background_bitmap=device_settings_reference('bitm',i ? row_regular:row_top);
        row->text_font=device_settings_reference(FONT_GROUP_TAG,large_font);
        row->text_color=chooser.defs[CHOOSER_DESCRIPTION].text_color;
        row->text_label_string_list=ref(STRINGS_TAG);
        row->string_list_index=(short)(i+1);
        row->horizontal_offset=13; row->vertical_offset=5;
        for(unsigned j=0;j<2;j++) chooser.row_events[i][j]=(struct ui_widget_event_handler_reference){
            .flags=8,.event_type=j ? 12:0,.widget_tag={'DeLa',NULL,0,profile_id},.sound_effect={'snd!',NULL,0,NONE}};
        row->event_handlers=(struct tag_block){2,chooser.row_events[i],NULL};
        performance_pause_child(&chooser.list[i],chooser_ids[CHOOSER_COOP+i],0,i==3 ? -11:-33);
    }
    performance_pause_child(&chooser.preview[0],chooser_ids[CHOOSER_MP_PICTURE],0,0);
    performance_pause_child(&chooser.preview[1],chooser_ids[CHOOSER_DESCRIPTION],0,37);
    chooser_before=chooser;
}

/* Advanced Controls supplies the retail option rows and A Accept/B Cancel
 * page shape. Keep a separate snapshot to catch changes to cached stock tags. */
#define ADV_PREFIX "ui\\shell\\main_menu\\settings_select\\player_setup\\player_profile_edit\\advanced_controls\\"
enum { ADV_ROOT, ADV_MENU, ADV_HELP, ADV_ROW, ADV_LABEL, ADV_SPINNER,
    ADV_HEADER, ADV_KEY, ADV_B_BUTTON, ADV_CANCEL_LABEL, ADV_A_BUTTON,
    ADV_ACCEPT_LABEL, ADV_WIDGET_COUNT };
static const char *advanced_names[ADV_WIDGET_COUNT]={
    ADV_PREFIX "advanced_controls_screen", ADV_PREFIX "advanced_controls_menu",
    ADV_PREFIX "advanced_controls_help", ADV_PREFIX "op_controller_sensitivity",
    ADV_PREFIX "controller_sensitivity_label", ADV_PREFIX "controller_sensitivity_spinner",
    ADV_PREFIX "header_advanced_controls", "ui\\shell\\main_menu\\button_key_options",
    "ui\\shell\\main_menu\\b_butn", "ui\\shell\\main_menu\\=cancel",
    "ui\\shell\\main_menu\\a_butn", "ui\\shell\\main_menu\\=accept_new"
};
static struct {
    struct ui_widget_definition defs[ADV_WIDGET_COUNT];
    struct ui_widget_child_reference root[3],menu[5],row[2],key[4];
    struct ui_widget_event_handler_reference menu_events[3];
    struct ui_widget_game_data_input_reference input;
} advanced,advanced_before;
static long advanced_ids[ADV_WIDGET_COUNT];
static int advanced_assets[4];
static void advanced_setup(void) {
    memset(&advanced,0,sizeof(advanced));
    long background=add_stock('bitm',"ui\\shell\\bitmaps\\option_bkds",&advanced_assets[0]);
    long left=add_stock('bitm',"ui\\shell\\bitmaps\\arrow_sm_left",&advanced_assets[1]);
    long right=add_stock('bitm',"ui\\shell\\bitmaps\\arrow_sm_right",&advanced_assets[2]);
    long header=add_stock('bitm',ADV_PREFIX "header_advanced_controls",&advanced_assets[3]);
    for(unsigned i=0;i<ADV_WIDGET_COUNT;i++) {
        performance_pause_clear_definition(&advanced.defs[i]);
        advanced_ids[i]=add_stock('DeLa',advanced_names[i],&advanced.defs[i]);
    }
    struct ui_widget_definition *root=&advanced.defs[ADV_ROOT],*menu=&advanced.defs[ADV_MENU];
    root->bounds=(rectangle2d){0,0,480,640}; root->controller_index=4; root->flags=1;
    root->background_bitmap=chooser.defs[CHOOSER_ROOT].background_bitmap;
    root->child_widgets=(struct tag_block){3,advanced.root,NULL};
    unsigned root_children[3]={ADV_MENU,ADV_HEADER,ADV_KEY};
    for(unsigned i=0;i<3;i++) performance_pause_child(&advanced.root[i],advanced_ids[root_children[i]],0,0);
    menu->type=_ui_widget_type_column_list; menu->bounds=root->bounds; menu->controller_index=4;
    menu->flags=9; menu->child_widgets=(struct tag_block){5,advanced.menu,NULL};
    menu->extended_description_widget=device_settings_reference('DeLa',advanced_ids[ADV_HELP]);
    advanced.input.function=17; menu->game_data_inputs=(struct tag_block){1,&advanced.input,NULL};
    for(unsigned i=0;i<5;i++) performance_pause_child(&advanced.menu[i],advanced_ids[ADV_ROW],54,73+30*i);
    for(unsigned i=0;i<3;i++) advanced.menu_events[i]=(struct ui_widget_event_handler_reference){
        .flags=i ? 0x280:0x80,.event_type=i==0 ? 24:i==1 ? 0:12,.function=i ? 71:69,
        .widget_tag={'DeLa',NULL,0,NONE},.sound_effect={'snd!',NULL,0,NONE}};
    menu->event_handlers=(struct tag_block){3,advanced.menu_events,NULL};
    struct ui_widget_definition *row=&advanced.defs[ADV_ROW],*label=&advanced.defs[ADV_LABEL],*spinner=&advanced.defs[ADV_SPINNER];
    row->bounds=(rectangle2d){0,0,28,512}; row->controller_index=4; row->flags=1;
    row->background_bitmap=device_settings_reference('bitm',background);
    row->text_color=chooser.defs[CHOOSER_DESCRIPTION].text_color;
    row->child_widgets=(struct tag_block){2,advanced.row,NULL};
    performance_pause_child(&advanced.row[0],advanced_ids[ADV_LABEL],0,0);
    performance_pause_child(&advanced.row[1],advanced_ids[ADV_SPINNER],373,1);
    label->type=_ui_widget_type_text_box; label->bounds=(rectangle2d){0,0,22,300};
    label->text_color=row->text_color; label->text_font=chooser.defs[CHOOSER_DESCRIPTION].text_font;
    label->text_label_string_list=ref(STRINGS_TAG); label->string_list_index=1;
    label->horizontal_offset=13; label->vertical_offset=4;
    spinner->type=_ui_widget_type_spinner_list; spinner->controller_index=4;
    spinner->bounds=(rectangle2d){2,3,22,36}; spinner->flags=0x41; spinner->list_flags=2;
    spinner->text_color=row->text_color; spinner->text_font=label->text_font;
    spinner->justification=_text_justification_center; spinner->vertical_offset=4;
    spinner->text_label_string_list=ref(STRINGS_TAG);
    spinner->list_header_bitmap=device_settings_reference('bitm',left);
    spinner->list_footer_bitmap=device_settings_reference('bitm',right);
    spinner->list_header_bounds=(rectangle2d){7,-6,19,0}; spinner->list_footer_bounds=(rectangle2d){7,36,19,40};
    struct ui_widget_definition *help=&advanced.defs[ADV_HELP];
    help->type=_ui_widget_type_text_box; help->bounds=(rectangle2d){321,68,400,550};
    help->text_font=label->text_font; help->text_color=(real_argb_color){1,1,1,1};
    help->text_label_string_list=ref(STRINGS_TAG);
    advanced.defs[ADV_HEADER].bounds=(rectangle2d){11,35,70,459};
    advanced.defs[ADV_HEADER].background_bitmap=device_settings_reference('bitm',header);
    advanced.defs[ADV_KEY].bounds=(rectangle2d){414,250,440,577};
    advanced.defs[ADV_KEY].child_widgets=(struct tag_block){4,advanced.key,NULL};
    const short key_x[4]={346,368,471,492};
    for(unsigned i=0;i<4;i++) {
        performance_pause_child(&advanced.key[i],advanced_ids[ADV_B_BUTTON+i],key_x[i],414);
        advanced.defs[ADV_B_BUTTON+i].bounds=(rectangle2d){0,0,22,i%2 ? 160:22};
        if(i%2) {
            advanced.defs[ADV_B_BUTTON+i].type=_ui_widget_type_text_box;
            advanced.defs[ADV_B_BUTTON+i].text_font=label->text_font;
            advanced.defs[ADV_B_BUTTON+i].text_label_string_list=ref(STRINGS_TAG);
        }
    }
    advanced_before=advanced;
}

static void settings_setup(short mode) {
    assert(!widget_globals.pause_game_time_count && !settings_game_paused && !settings_sound_paused);
    setup(); memset(&device_settings,0,sizeof(device_settings)); memset(&device_settings_campaign,0,sizeof(device_settings_campaign));
    performance_pause_ready=FALSE;
    memset(settings_map,0,sizeof(settings_map)); memset(originals,0,sizeof(originals));
    settings_header=(struct cache_file_tag_header){0,123};
    if(mode==0) {
        memcpy(settings_map,stock_tags,sizeof(stock_tags)); settings_header.tag_count=STOCK_WIDGET_COUNT+1;
        stock.defs[SCREEN_TAG].bounds=(rectangle2d){0,0,480,640};
    }
    add_stock(FONT_GROUP_TAG,"ui\\small_ui",&originals[11]);
    for(unsigned i=0;i<12;i++) performance_pause_clear_definition(&originals[i]);
    originals[6].type=originals[7].type=_ui_widget_type_text_box;
    originals[6].text_font.index=stock_id(settings_header.tag_count-1);
    originals[6].bounds=(rectangle2d){0,0,27,202};
    if(mode!=0) {
        originals[6].text_font.index=add_stock(FONT_GROUP_TAG,"ui\\large_ui",&settings_assets[0]);
        originals[6].background_bitmap=device_settings_reference('bitm',add_stock('bitm',"ui\\shell\\bitmaps\\menu_bkds",&settings_assets[1]));
        originals[6].vertical_offset=3;
        originals[6].text_color=(real_argb_color){1,0.156863f,0.588235f,1};
        originals[8].bounds=(rectangle2d){0,0,24,174};
        add_stock('DeLa',"ui\\shell\\main_menu\\button_key_sm",&originals[8]);
    }
    if(mode==0) {
        profile_id=add_stock('DeLa',"ui\\shell\\main_menu\\settings_select\\player_setup\\player_profile_select_screen",&originals[1]);
        entry_id=add_stock('DeLa',"ui\\shell\\main_menu\\main_menu_item_settings",&originals[0]);
        for(unsigned i=0;i<2;i++) original_entry_events[i]=(struct ui_widget_event_handler_reference){.flags=i ? 0x408:8,.event_type=i ? 12:0,.widget_tag={'DeLa',NULL,0,profile_id}};
        originals[0].event_handlers=(struct tag_block){2,original_entry_events,NULL};
        chooser_setup();
        advanced_setup();
    } else if(mode==1) {
        for(unsigned i=0;i<3;i++) {
            original_root_ids[i]=add_stock('DeLa',performance_pause_original_names[i],&originals[i]);
            originals[i].bounds=(rectangle2d){0,0,i ? 240:480,i==2 ? 320:640};
            originals[i].flags=0x1; /* Retail multiplayer menus keep the game running. */
            originals[i].child_widgets=(struct tag_block){3,original_roots[i],NULL};
        }
        original_list_ids[0]=add_stock('DeLa',"ui\\shell\\multiplayer_game\\pause_game\\mp_pause_list",&originals[3]);
        resume_id=add_stock('DeLa',"ui\\shell\\multiplayer_game\\pause_game\\resume_game_button",&originals[6]);
        quit_id=add_stock('DeLa',"quit",&originals[7]);
        originals[3].type=3; originals[3].child_widgets=(struct tag_block){2,original_lists[0],NULL};
        original_lists[0][0].widget_tag=device_settings_reference('DeLa',resume_id);
        original_lists[0][1].widget_tag=device_settings_reference('DeLa',quit_id);
        for(unsigned i=0;i<3;i++) {
            for(unsigned j=0;j<3;j++) performance_pause_child(&original_roots[i][j],resume_id,0,0);
            performance_pause_child(&original_roots[i][1],original_list_ids[0],i==2 ? 58:218,i ? 95:207);
            original_roots[i][2].vertical_offset=i==0 ? 298:i==1 ? 186:180;
        }
    } else {
        for(unsigned i=0;i<2;i++) {
            original_root_ids[i]=add_stock('DeLa',device_settings_campaign_roots[i],&originals[i]);
            originals[i].bounds=(rectangle2d){0,0,i ? 240:480,640};
            originals[i].flags=0x3; /* Retail solo/co-op menus pause time and audio. */
            originals[i].child_widgets=(struct tag_block){5,original_roots[i],NULL};
        }
        original_list_ids[0]=add_stock('DeLa',"ui\\shell\\solo_game\\pause_game\\pause_list",&originals[3]);
        original_list_ids[1]=add_stock('DeLa',"ui\\shell\\solo_game\\pause_game\\coop_pause_list",&originals[4]);
        resume_id=add_stock('DeLa',"ui\\shell\\solo_game\\pause_game\\resume_game_button",&originals[6]);
        quit_id=add_stock('DeLa',"quit",&originals[7]);
        for(unsigned i=0;i<2;i++) {
            originals[3+i].type=3; originals[3+i].child_widgets=(struct tag_block){4,original_lists[i],NULL};
            for(unsigned j=0;j<4;j++) performance_pause_child(&original_lists[i][j],j ? quit_id:resume_id,0,j*28);
            for(unsigned j=0;j<5;j++) performance_pause_child(&original_roots[i][j],resume_id,0,0);
            performance_pause_child(&original_roots[i][0],resume_id,64,i ? 42:162);
            performance_pause_child(&original_roots[i][1],original_list_ids[i],72,i ? 51:171);
            performance_pause_child(&original_roots[i][2],resume_id,302,i ? 75:195);
            performance_pause_child(&original_roots[i][3],resume_id,302,i ? 46:166);
            performance_pause_child(&original_roots[i][4],resume_id,87,i ? 176:296);
        }
    }
    memcpy(originals_before,originals,sizeof(originals));
    cache_file_globals.tag_header=&settings_header; global_tag_instances=settings_map;
    register_calls=0; writes=errors=applied_mask=0; save_succeeds=TRUE; rollback_incomplete=FALSE;
    for(unsigned i=0;i<NUMBER_OF_DEVICE_SETTINGS;i++) settings_values[i]=i<_device_setting_menu_music ? 0.5:1;
    settings_values[_device_setting_master_volume]=0.125;
    settings_values[_device_setting_timer_items]=0;
    settings_values[_device_setting_timer_position]=0;
}
static struct widget_instance *open_settings(short layout,short page,short local) {
    struct widget_instance *root=instantiate(device_settings.screen_tags[layout][page],NULL);
    root->local_player_index=local;
    assert(game_settings_event(root,_device_settings_initialize));
    assert(root->pause_game_time==(layout>=_ds_solo));
    assert(settings_game_paused==(layout>=_ds_solo) && settings_sound_paused==(layout>=_ds_solo));
    return root;
}
static struct widget_instance *setting_control(struct widget_instance *root,short setting) {
    long tag=device_settings.native_pages ? device_settings_native.spinner_tags[setting]:device_settings.row_tags[setting];
    struct widget_instance *w=widget_instance_find_by_tag_index_recursive(root,tag); assert(w); return w;
}
static void settings_structure(void) {
    settings_setup(0); assert(game_settings_remap_tag(entry_id)!=entry_id);
    assert(device_settings.settings_menu.child_widgets.count==2);
    assert(device_settings.column[0][_ds_game].child_widgets.count==2);
    assert(device_settings.column[0][_ds_audio].child_widgets.count==6);
    assert(device_settings.column[0][_ds_video].child_widgets.count==5);
    assert(device_settings.column[0][_ds_timer].child_widgets.count==5);
    assert(!game_settings_is_adjustable(NULL));
    struct widget_instance item={0};
    for(unsigned i=0;i<NUMBER_OF_DEVICE_SETTINGS;i++) {
        item.definition_tag_index=device_settings.row_tags[i];
        assert(game_settings_is_adjustable(&item));
    }
    device_settings.ready=FALSE; assert(!game_settings_is_adjustable(&item)); device_settings.ready=TRUE;
    item.definition_tag_index=device_settings.entry_tag; assert(!game_settings_is_adjustable(&item));
    item.definition_tag_index=device_settings.accept_tag; assert(!game_settings_is_adjustable(&item));
    item.definition_tag_index=device_settings.footer_tags[_ds_audio]; assert(!game_settings_is_adjustable(&item));
    assert(device_settings.settings_events[0][0].widget_tag.index==profile_id);
    assert(game_settings_remap_tag(profile_id)==profile_id && game_settings_remap_tag(NONE)==NONE);
    for(unsigned i=0;i<2;i++) {
        assert(device_settings.entry_events[i].flags==(i ? 0x408:8));
        assert(device_settings.settings_events[0][i].sound_effect.index==NONE);
        assert(device_settings.settings_events[1][i].widget_tag.index==device_settings.screen_tags[0][_ds_game]);
        assert(device_settings.choice_events[0][i][0].widget_tag.index==device_settings.screen_tags[0][i+1]);
    }
    assert(!wcscmp(device_settings.text[_ds_audio_help],L"Effects includes announcer.\r\nLeft/Right: Adjust    B: Cancel"));
    assert(!memcmp(originals,originals_before,sizeof(originals)));
    assert(!memcmp(&chooser,&chooser_before,sizeof(chooser)));
    assert(!memcmp(&advanced,&advanced_before,sizeof(advanced)));
    assert(pb_editor_build()); assert(register_calls==117); /* Both menus fit the real 128-tag registry. */
    long old=device_settings.entry_tag; scenario_tags_unload();
    cache_file_globals.tags_loaded=TRUE; global_tag_instances=settings_map;
    assert(!tag_index_is_group(old,'DeLa'));
    assert(game_settings_remap_tag(entry_id)!=old);
}
static void settings_native_chooser(void) {
    settings_setup(0); assert(device_settings_build());
    struct ui_widget_definition *root=&device_settings.settings_screen,*menu=&device_settings.settings_menu;
    assert(root->type==chooser.defs[CHOOSER_ROOT].type && root->child_widgets.count==4);
    assert(!memcmp(&root->bounds,&chooser.defs[CHOOSER_ROOT].bounds,sizeof(root->bounds)));
    assert(root->background_bitmap.index==chooser.defs[CHOOSER_ROOT].background_bitmap.index);
    assert(menu->type==_ui_widget_type_column_list && menu->child_widgets.count==2);
    assert(menu->flags==chooser.defs[CHOOSER_LIST].flags);
    assert(!memcmp(&menu->bounds,&chooser.defs[CHOOSER_LIST].bounds,sizeof(menu->bounds)));
    assert(menu->game_data_inputs.count==1);
    assert(((struct ui_widget_game_data_input_reference *)menu->game_data_inputs.address)->function==1);
    assert(chooser.input.function==5); /* The source Multiplayer callback is untouched. */
    struct ui_widget_child_reference *children=root->child_widgets.address,*rows=menu->child_widgets.address;
    assert(ui_widget_definition_get(children[0].widget_tag.index)==&device_settings.settings_title);
    assert(ui_widget_definition_get(children[1].widget_tag.index)==menu);
    assert(!memcmp(&children[2],&chooser.root[2],sizeof(children[2]))); /* Native button legend. */
    assert(children[3].widget_tag.index==chooser.root[3].widget_tag.index);
    assert(children[3].horizontal_offset==chooser.root[3].horizontal_offset);
    assert(children[3].vertical_offset==chooser.root[3].vertical_offset-33); /* Separator now follows two rows. */
    assert(!wcscmp(string_at(&device_settings.settings_title,device_settings.settings_title.string_list_index),L"SETTINGS"));
    assert(device_settings.settings_title.justification==_text_justification_left);
    for(unsigned i=0;i<2;i++) {
        struct ui_widget_definition *choice=ui_widget_definition_get(rows[i].widget_tag.index),*original=&chooser.defs[CHOOSER_COOP+i];
        struct ui_widget_child_reference expected_child=chooser.list[i];
        expected_child.widget_tag=rows[i].widget_tag;
        assert(!memcmp(&rows[i],&expected_child,sizeof(expected_child)));
        assert(!memcmp(&choice->bounds,&original->bounds,sizeof(choice->bounds)));
        assert(choice->text_font.index==original->text_font.index);
        assert(choice->background_bitmap.index==original->background_bitmap.index);
        assert(!memcmp(&choice->text_color,&original->text_color,sizeof(choice->text_color)));
        assert(choice->horizontal_offset==13 && choice->vertical_offset==5 && choice->justification==_text_justification_left);
        assert(!wcscmp(string_at(choice,choice->string_list_index),i ? L"GAME SETTINGS":L"PROFILE SETTINGS"));
        assert(choice->event_handlers.count==2);
        struct ui_widget_event_handler_reference *events=choice->event_handlers.address;
        for(unsigned j=0;j<2;j++) {
            assert(events[j].event_type==(j ? 12:0) && events[j].flags==FLAG(_event_handler_open_widget_bit));
            assert(events[j].widget_tag.index==(i ? device_settings.screen_tags[_ds_main][_ds_game]:profile_id));
        }
    }
    struct ui_widget_definition *preview=ui_widget_definition_get(menu->extended_description_widget.index);
    assert(preview->child_widgets.count==2);
    assert(!memcmp(&preview->bounds,&chooser.defs[CHOOSER_PREVIEW].bounds,sizeof(preview->bounds)));
    assert(preview->background_bitmap.index==chooser.defs[CHOOSER_PREVIEW].background_bitmap.index);
    struct ui_widget_child_reference *parts=preview->child_widgets.address;
    for(unsigned i=0;i<2;i++) {
        struct ui_widget_child_reference expected_child=chooser.preview[i];
        expected_child.widget_tag=parts[i].widget_tag;
        assert(!memcmp(&parts[i],&expected_child,sizeof(expected_child)));
    }
    struct ui_widget_definition *picture=ui_widget_definition_get(parts[0].widget_tag.index);
    struct ui_widget_definition *description=ui_widget_definition_get(parts[1].widget_tag.index);
    assert(!strcmp(tag_get_name(parts[0].widget_tag.index),"ui\\native_settings\\preview_pic"));
    assert(picture->background_bitmap.index==chooser.defs[CHOOSER_PROFILE_PICTURE].background_bitmap.index);
    assert(!memcmp(&picture->bounds,&chooser.defs[CHOOSER_PROFILE_PICTURE].bounds,sizeof(picture->bounds)));
    assert(description->text_font.index==chooser.defs[CHOOSER_DESCRIPTION].text_font.index);
    assert(!memcmp(&description->text_color,&chooser.defs[CHOOSER_DESCRIPTION].text_color,sizeof(description->text_color)));
    assert(!memcmp(&description->bounds,&chooser.defs[CHOOSER_DESCRIPTION].bounds,sizeof(description->bounds)));
    assert(unicode_string_list_definition_get(description->text_label_string_list.index)->strings.count==2);
    assert(wcsstr(string_at(description,0),L"profile") && wcsstr(string_at(description,0),L"controls"));
    assert(wcsstr(string_at(description,1),L"audio") && wcsstr(string_at(description,1),L"video"));
    struct widget_instance *screen=instantiate(device_settings.settings_tag,NULL),*list=screen->child->next;
    struct widget_instance *entry=list->child,*extended=list->parameters.list.extended_description;
    for(unsigned i=0;i<2;i++,entry=entry->next) {
        list->focused_child=entry; settings_menu_update_extended_description(list);
        assert(extended->child->animation.current_frame_index==(i ? 1:3));
        assert(extended->child->next->parameters.text_box.string_list_index==(short)i);
    }
    /* Moving back to Profile refreshes both picture and description. */
    list->focused_child=list->child; settings_menu_update_extended_description(list);
    assert(extended->child->animation.current_frame_index==3);
    assert(extended->child->next->parameters.text_box.string_list_index==0);
    dispose(screen);
    list=instantiate(chooser_ids[CHOOSER_LIST],NULL); entry=list->child;
    for(unsigned i=0;i<4;i++,entry=entry->next) {
        list->focused_child=entry; settings_menu_update_extended_description(list);
        assert(list->parameters.list.extended_description->child->animation.current_frame_index==(short)i);
        assert(list->parameters.list.extended_description->child->next->parameters.text_box.string_list_index==(short)i);
    }
    dispose(list);
    assert(!memcmp(&chooser,&chooser_before,sizeof(chooser)));
    assert(!memcmp(originals,originals_before,sizeof(originals)));
}
static void settings_native_options(void) {
    static const wchar_t *labels[NUMBER_OF_DEVICE_SETTINGS]={
        L"MASTER VOLUME:",L"MUSIC VOLUME:",L"EFFECTS VOLUME:",L"DIALOGUE VOLUME:",L"TIMER VOLUME:",
        L"MENU MUSIC:",L"FULLSCREEN:",L"VSYNC:",L"SMOOTH MOTION:",L"COUNTDOWN:",L"BEEPS:",
        L"MINUTE ANNOUNCEMENTS:",L"ITEM CUES:",L"TIMER POSITION:",L"TIMER SIZE:"};
    static const short rows_by_page[3][6]={
        {0,1,2,3,NONE,5}, {6,7,8,13,14}, {4,9,10,11,12}};
    static const short counts[3]={6,5,5};
    settings_setup(0); assert(device_settings_build());
    assert(device_settings.native_pages && !game_settings_is_native_spinner(NULL));
    for(short page=_ds_audio;page<=_ds_timer;page++) {
        struct ui_widget_definition *screen=&device_settings.screen[_ds_main][page];
        struct ui_widget_definition *column=&device_settings.column[_ds_main][page];
        struct ui_widget_definition *footer=&device_settings.footer[page];
        short count=counts[page-_ds_audio];
        assert(!memcmp(&screen->bounds,&advanced.defs[ADV_ROOT].bounds,sizeof(screen->bounds)));
        assert(screen->background_bitmap.index==advanced.defs[ADV_ROOT].background_bitmap.index);
        assert(screen->controller_index==_widget_controller_any && screen->child_widgets.count==4);
        struct ui_widget_child_reference *children=screen->child_widgets.address;
        assert(ui_widget_definition_get(children[0].widget_tag.index)==column);
        assert(ui_widget_definition_get(children[1].widget_tag.index)==&device_settings.heading[page]);
        if(page==_ds_audio) {
            assert(children[2].widget_tag.index==device_settings_native.audio_key_tag);
            struct ui_widget_child_reference *key=device_settings_native.audio_key.child_widgets.address;
            assert(device_settings_native.audio_key.child_widgets.count==4);
            for(unsigned i=0;i<3;i++) assert(!memcmp(&key[i],&advanced.key[i],sizeof(key[i])));
            assert(key[3].widget_tag.index==device_settings_native.audio_accept_tag);
            assert(!wcscmp(string_at(&device_settings_native.audio_accept_label,
                device_settings_native.audio_accept_label.string_list_index),L"=ACCEPT"));
        } else assert(!memcmp(&children[2],&advanced.root[2],sizeof(children[2])));
        assert(children[3].widget_tag.index==device_settings.footer_tags[page]);
        assert(column->type==_ui_widget_type_column_list && column->child_widgets.count==count);
        assert(column->extended_description_widget.index==NONE); /* Error/help is in the root tree. */
        assert(column->event_handlers.count==0); /* Stock profile save/init callbacks cannot run. */
        assert(column->game_data_inputs.count==1);
        assert(((struct ui_widget_game_data_input_reference *)column->game_data_inputs.address)->function==31981);
        assert(!memcmp(&footer->bounds,&advanced.defs[ADV_HELP].bounds,sizeof(footer->bounds)));
        assert(footer->text_font.index==advanced.defs[ADV_HELP].text_font.index);
        assert(footer->justification==_text_justification_left);
        assert(device_settings.heading[page].text_font.index==advanced.defs[ADV_LABEL].text_font.index);
        assert(device_settings.heading[page].justification==_text_justification_left);
        unsigned accept_events=0,cancel_events=0,created_events=0;
        for(long i=0;i<screen->event_handlers.count;i++) {
            struct ui_widget_event_handler_reference *event=(struct ui_widget_event_handler_reference *)screen->event_handlers.address+i;
            if(event->event_type==_gamepad_analog_button_a || event->event_type==_gamepad_binary_button_start) {
                assert(event->function==_device_settings_accept);
                assert(event->flags==(FLAG(_event_handler_run_function_bit)|FLAG(_event_handler_go_back_to_previous_widget_bit)));
                accept_events++;
            } else if(event->event_type==_widget_event_b_button || event->event_type==_widget_event_back_button) {
                assert(event->function==_device_settings_cancel);
                assert(event->flags==(FLAG(_event_handler_run_function_bit)|FLAG(_event_handler_go_back_to_previous_widget_bit))); cancel_events++;
            } else if(event->event_type==_widget_event_created) {
                assert(event->function==_device_settings_initialize && event->flags==FLAG(_event_handler_run_function_bit)); created_events++;
            } else assert(0);
        }
        assert(accept_events==2 && cancel_events==2 && created_events==1);
        struct ui_widget_child_reference *rows=column->child_widgets.address;
        for(short i=0;i<count;i++) {
            short setting=rows_by_page[page-_ds_audio][i];
            assert(rows[i].horizontal_offset==54 && rows[i].vertical_offset==73+30*i);
            struct ui_widget_definition *row=ui_widget_definition_get(rows[i].widget_tag.index);
            if(setting==NONE) {
                assert(rows[i].widget_tag.index==device_settings.timer_tags[_ds_main]);
                assert(row->type==_ui_widget_type_text_box && !row->child_widgets.count);
                assert(!wcscmp(string_at(row,row->string_list_index),L"TIMER AUDIO..."));
                assert(row->event_handlers.count==2);
                struct ui_widget_event_handler_reference *events=row->event_handlers.address;
                for(unsigned j=0;j<2;j++) {
                    assert(events[j].function==_device_settings_enter_timer);
                    assert(events[j].widget_tag.index==device_settings.screen_tags[_ds_main][_ds_timer]);
                }
                continue;
            }
            assert(rows[i].widget_tag.index==device_settings.row_tags[setting]);
            assert(row->type==_ui_widget_type_container && row->child_widgets.count==2);
            assert(row->background_bitmap.index==advanced.defs[ADV_ROW].background_bitmap.index);
            assert(!memcmp(&row->bounds,&advanced.defs[ADV_ROW].bounds,sizeof(row->bounds)));
            assert(row->event_handlers.count==0 && row->flags==FLAG(_widget_pass_unhandled_events_to_children_bit));
            struct ui_widget_child_reference *parts=row->child_widgets.address;
            struct ui_widget_definition *label=ui_widget_definition_get(parts[0].widget_tag.index);
            struct ui_widget_definition *spinner=ui_widget_definition_get(parts[1].widget_tag.index);
            assert(label->type==_ui_widget_type_text_box && !label->event_handlers.count && !label->flags);
            assert(label->horizontal_offset==13 && label->vertical_offset==4 && label->justification==_text_justification_left);
            assert(label->text_font.index==advanced.defs[ADV_LABEL].text_font.index);
            assert(!wcscmp(string_at(label,label->string_list_index),labels[setting]));
            assert(spinner->type==_ui_widget_type_spinner_list && parts[1].widget_tag.index==device_settings_native.spinner_tags[setting]);
            assert(!spinner->flags && !spinner->list_flags && !spinner->child_widgets.count);
            assert(spinner->bounds.x1-spinner->bounds.x0>=64); /* 12.5% fits without rounding. */
            assert(spinner->list_header_bitmap.index==advanced.defs[ADV_SPINNER].list_header_bitmap.index);
            assert(spinner->list_footer_bitmap.index==advanced.defs[ADV_SPINNER].list_footer_bitmap.index);
            assert(spinner->event_handlers.count==4 && spinner->justification==_text_justification_center);
            for(long event_index=0;event_index<spinner->event_handlers.count;event_index++) {
                struct ui_widget_event_handler_reference *event=(struct ui_widget_event_handler_reference *)spinner->event_handlers.address+event_index;
                assert(event->event_type!=_gamepad_analog_button_a && event->event_type!=_gamepad_binary_button_start);
            }
            struct widget_instance probe={.definition_tag_index=parts[1].widget_tag.index};
            assert(game_settings_is_native_spinner(&probe));
        }
        struct widget_instance *root=open_settings(_ds_main,page,0),*list=root->child;
        struct widget_instance *help=widget_instance_find_by_tag_index_recursive(root,device_settings.footer_tags[page]);
        for(short i=0;i<count;i++) {
            short setting=rows_by_page[page-_ds_audio][i];
            struct widget_instance *row=list->child;
            for(short j=0;j<i;j++) row=row->next;
            list->focused_child=row; list->parameters.list.selected_index=i;
            settings_render_inputs(list);
            short help_index=setting==NONE ? _ds_timer_link_help:_ds_help_start+setting;
            assert(help->parameters.text_box.string_list_index==help_index);
            assert(wcslen(device_settings.text[help_index])>10);
            if(page==_ds_audio) {
                struct widget_instance *caption=widget_instance_find_by_tag_index_recursive(root,device_settings_native.audio_accept_tag);
                assert(caption && caption->parameters.text_box.string_list_index==(setting==NONE ? _ds_select_key_label:_ds_accept_key_label));
            }
            if(setting!=NONE) {
                struct widget_instance *spinner=setting_control(root,setting);
                assert(!spinner->child && spinner->parameters.list.selected_index==_ds_value_start+setting);
            }
        }
        assert(!writes); dispose(root);
    }
    /* Main settings also retain separate exact values if multiple controllers
     * open a page. Rendering one draft cannot overwrite another's string slot. */
    struct widget_instance *one=open_settings(_ds_main,_ds_audio,0),*two=open_settings(_ds_main,_ds_audio,3);
    assert(game_settings_event(setting_control(two,_device_setting_master_volume),_device_settings_next));
    assert(!wcscmp(device_settings.text[_ds_value_start],L"12.5%"));
    assert(!wcscmp(device_settings.text[_ds_value_start+3*NUMBER_OF_DEVICE_SETTINGS],L"20%"));
    assert(device_settings_drafts[0].values[_device_setting_master_volume]==0.125);
    assert(!writes); dispose(one); dispose(two);
    assert(!memcmp(&advanced,&advanced_before,sizeof(advanced)));
    assert(!memcmp(&chooser,&chooser_before,sizeof(chooser)));
}
static void settings_game_chooser(void) {
    settings_setup(0); assert(device_settings_build());
    struct ui_widget_definition *screen=&device_settings.screen[_ds_main][_ds_game];
    struct ui_widget_definition *column=&device_settings.column[_ds_main][_ds_game];
    assert(screen->child_widgets.count==4 && column->child_widgets.count==2);
    assert(!memcmp(&screen->bounds,&chooser.defs[CHOOSER_ROOT].bounds,sizeof(screen->bounds)));
    struct ui_widget_child_reference *children=screen->child_widgets.address,*rows=column->child_widgets.address;
    assert(!memcmp(&children[2],&chooser.root[2],sizeof(children[2])));
    assert(children[3].vertical_offset==chooser.root[3].vertical_offset-33);
    assert(column->game_data_inputs.count==1);
    assert(((struct ui_widget_game_data_input_reference *)column->game_data_inputs.address)->function==31980);
    for(unsigned i=0;i<2;i++) {
        struct ui_widget_definition *row=ui_widget_definition_get(rows[i].widget_tag.index);
        assert(row->background_bitmap.index==chooser.defs[CHOOSER_COOP+i].background_bitmap.index);
        assert(row->text_font.index==chooser.defs[CHOOSER_COOP+i].text_font.index);
        assert(row->horizontal_offset==13 && row->vertical_offset==5);
        assert(!wcscmp(string_at(row,row->string_list_index),i ? L"VIDEO":L"AUDIO"));
        assert(row->event_handlers.count==2);
        struct ui_widget_event_handler_reference *events=row->event_handlers.address;
        for(unsigned j=0;j<2;j++) assert(events[j].widget_tag.index==device_settings.screen_tags[_ds_main][i+1]);
    }
    struct ui_widget_definition *preview=ui_widget_definition_get(column->extended_description_widget.index);
    assert(preview->child_widgets.count==3);
    struct ui_widget_child_reference *parts=preview->child_widgets.address;
    struct ui_widget_definition *audio=ui_widget_definition_get(parts[0].widget_tag.index);
    struct ui_widget_definition *video=ui_widget_definition_get(parts[1].widget_tag.index);
    struct ui_widget_definition *description=ui_widget_definition_get(parts[2].widget_tag.index);
    assert(audio->background_bitmap.index==chooser.defs[CHOOSER_PROFILE_PICTURE].background_bitmap.index);
    assert(video->background_bitmap.index==chooser.defs[CHOOSER_MP_PICTURE].background_bitmap.index);
    assert(unicode_string_list_definition_get(description->text_label_string_list.index)->strings.count==2);
    struct widget_instance *root=open_settings(_ds_main,_ds_game,0);
    struct widget_instance *list=widget_instance_find_by_tag_index_recursive(root,children[1].widget_tag.index);
    struct widget_instance *extended=list->parameters.list.extended_description;
    assert(extended && extended->child && extended->child->next && extended->child->next->next);
    for(unsigned turn=0;turn<3;turn++) {
        short selected=turn==1 ? 1:0;
        list->focused_child=selected ? list->child->next:list->child;
        list->parameters.list.selected_index=(short)selected;
        settings_render_inputs(list);
        assert(extended->child->visible==!selected && extended->child->next->visible==selected);
        assert(extended->child->animation.current_frame_index==2);
        assert(extended->child->next->animation.current_frame_index==0);
        assert(extended->child->next->next->parameters.text_box.string_list_index==(short)selected);
    }
    assert(!writes); dispose(root);
    assert(!memcmp(&chooser,&chooser_before,sizeof(chooser)));
}
static void settings_staging(void) {
    settings_setup(0); assert(device_settings_build());
    struct widget_instance *root=open_settings(0,_ds_audio,0),*music=setting_control(root,_device_setting_music_volume);
    assert(!wcscmp(device_settings.text[_ds_value_start],L"12.5%"));
    assert(game_settings_event(music,_device_settings_next));
    assert(music->parameters.list.last_list_tab_direction==15);
    assert(!writes && settings_values[_device_setting_music_volume]==0.5);
    dispose(root); root=open_settings(0,_ds_audio,0); /* Back discards all draft edits. */
    assert(device_settings_drafts[0].values[_device_setting_music_volume]==0.5);
    music=setting_control(root,_device_setting_music_volume);
    assert(game_settings_event(music,_device_settings_next));
    save_succeeds=FALSE; assert(!game_settings_event(root,_device_settings_accept));
    assert(writes==1 && errors==1 && settings_values[_device_setting_music_volume]==0.5);
    assert(widget_instance_find_by_tag_index_recursive(root,device_settings.footer_tags[_ds_audio])->parameters.text_box.string_list_index==_ds_failure_help);
    root->child->focused_child=root->child->child->next->next;
    settings_render_inputs(root->child);
    assert(widget_instance_find_by_tag_index_recursive(root,device_settings.footer_tags[_ds_audio])->parameters.text_box.string_list_index==_ds_failure_help);
    save_succeeds=TRUE; assert(game_settings_event(root,_device_settings_accept));
    assert(writes==2 && applied_mask==(1UL<<_device_setting_music_volume));
    assert(settings_values[_device_setting_master_volume]==0.125 && settings_values[_device_setting_music_volume]==0.6);
    assert(game_settings_event(root,_device_settings_accept) && writes==2);
    struct widget_instance *master=setting_control(root,_device_setting_master_volume);
    assert(game_settings_event(master,_device_settings_previous));
    assert(master->parameters.list.last_list_tab_direction==-15);
    assert(device_settings_drafts[0].values[_device_setting_master_volume]==0.1);
    assert(widget_instance_find_by_tag_index_recursive(root,device_settings.footer_tags[_ds_audio])->parameters.text_box.string_list_index!=_ds_failure_help);
    for(unsigned i=0;i<20;i++) assert(game_settings_event(master,_device_settings_previous));
    assert(device_settings_drafts[0].values[_device_setting_master_volume]==0);
    for(unsigned i=0;i<20;i++) assert(game_settings_event(master,_device_settings_next));
    assert(device_settings_drafts[0].values[_device_setting_master_volume]==1);
    dispose(root); root=open_settings(0,_ds_video,0);
    assert(game_settings_event(setting_control(root,_device_setting_interpolation),_device_settings_next));
    assert(game_settings_event(root,_device_settings_accept));
    assert(applied_mask==(1UL<<_device_setting_interpolation) && !settings_values[_device_setting_interpolation]);
    assert(game_settings_event(setting_control(root,_device_setting_vsync),_device_settings_next));
    rollback_incomplete=TRUE; assert(!game_settings_event(root,_device_settings_accept));
    assert(!device_settings_drafts[0].values[_device_setting_fullscreen]);
    assert(device_settings_drafts[0].values[_device_setting_vsync]==1);
    assert(widget_instance_find_by_tag_index_recursive(root,device_settings.footer_tags[_ds_video])->parameters.text_box.string_list_index==_ds_partial_failure_help);
    settings_render_inputs(root->child);
    assert(widget_instance_find_by_tag_index_recursive(root,device_settings.footer_tags[_ds_video])->parameters.text_box.string_list_index==_ds_partial_failure_help);
    rollback_incomplete=FALSE;
    assert(!game_settings_event(root,17)); dispose(root);
}
static struct widget_instance *enter_timer(struct widget_instance *audio,short layout,short local) {
    struct widget_instance *link=widget_instance_find_by_tag_index_recursive(audio,device_settings.timer_tags[layout]);
    assert(link && !game_settings_is_adjustable(link));
    if(layout==_ds_main) {
        struct ui_widget_event_handler_reference copy,original=device_settings_native.detail_events[3];
        struct widget_instance *dispatch=audio;
        audio->child->focused_child=link;
        struct ui_widget_event_handler_reference *routed=game_settings_route_handler(&dispatch,&device_settings_native.detail_events[3],&copy);
        assert(routed==&copy && routed->function==_device_settings_enter_timer);
        assert(dispatch==link); /* Engine history records the parent Audio row. */
        assert(routed->flags==(FLAG(_event_handler_run_function_bit)|FLAG(_event_handler_open_widget_bit)));
        assert(routed->widget_tag.index==device_settings.screen_tags[layout][_ds_timer]);
        assert(!memcmp(&original,&device_settings_native.detail_events[3],sizeof(original)));
        /* Start still accepts the parent page, including when Timer Audio has focus. */
        dispatch=audio;
        assert(game_settings_route_handler(&dispatch,&device_settings_native.detail_events[4],&copy)==&device_settings_native.detail_events[4]);
        assert(dispatch==audio);
        dispatch=link;
        assert(game_settings_route_handler(&dispatch,&device_settings_native.detail_events[3],&copy)==&device_settings_native.detail_events[3]);
        assert(dispatch==link);
        audio->child->focused_child=audio->child->child;
        dispatch=audio;
        assert(game_settings_route_handler(&dispatch,&device_settings_native.detail_events[3],&copy)==&device_settings_native.detail_events[3]);
        assert(dispatch==audio);
    }
    assert(game_settings_event(link,_device_settings_enter_timer));
    dispose(audio); return open_settings(layout,_ds_timer,local);
}
static void settings_timer_staging(void) {
    const short layouts[]={_ds_main,_ds_pause_1p,_ds_pause_4p,_ds_solo,_ds_coop};
    for(unsigned i=0;i<NUMBEROF(layouts);i++) {
        short layout=layouts[i],local=layout==_ds_pause_4p ? 3:0;
        settings_setup(layout==_ds_main ? 0:layout<=_ds_pause_4p ? 1:2);
        assert(device_settings_build());
        struct widget_instance *root=open_settings(layout,_ds_audio,local);
        assert(game_settings_event(setting_control(root,_device_setting_music_volume),_device_settings_next));
        root=enter_timer(root,layout,local);
        assert(device_settings_drafts[local].values[_device_setting_music_volume]==0.6);
        assert(game_settings_event(setting_control(root,_device_setting_timer_volume),_device_settings_next));
        assert(game_settings_event(setting_control(root,_device_setting_timer_countdown),_device_settings_next));
        assert(game_settings_event(root,_device_settings_accept) && !writes);
        assert(settings_values[_device_setting_timer_volume]==0.5 && settings_values[_device_setting_timer_countdown]==1);
        dispose(root); root=open_settings(layout,_ds_audio,local);
        assert(device_settings_drafts[local].values[_device_setting_music_volume]==0.6);
        assert(device_settings_drafts[local].values[_device_setting_timer_volume]==0.6);
        assert(device_settings_drafts[local].values[_device_setting_timer_countdown]==0);
        /* Cancel in the child restores its entry snapshot, including a timer
         * draft accepted on an earlier visit, without losing parent edits. */
        root=enter_timer(root,layout,local);
        assert(game_settings_event(setting_control(root,_device_setting_timer_volume),_device_settings_next));
        assert(game_settings_event(setting_control(root,_device_setting_timer_countdown),_device_settings_next));
        assert(game_settings_event(setting_control(root,_device_setting_timer_beeps),_device_settings_next));
        assert(game_settings_event(setting_control(root,_device_setting_timer_items),_device_settings_next));
        assert(game_settings_event(root,_device_settings_cancel) && !writes);
        dispose(root); root=open_settings(layout,_ds_audio,local);
        assert(device_settings_drafts[local].values[_device_setting_music_volume]==0.6);
        assert(device_settings_drafts[local].values[_device_setting_timer_volume]==0.6);
        assert(device_settings_drafts[local].values[_device_setting_timer_countdown]==0);
        assert(device_settings_drafts[local].values[_device_setting_timer_beeps]==1);
        assert(device_settings_drafts[local].values[_device_setting_timer_items]==0);
        /* Parent Cancel discards both kinds of draft. A fresh entry reloads
         * saved values; only parent Accept writes the combined dirty mask. */
        assert(game_settings_event(root,_device_settings_cancel)); dispose(root);
        root=open_settings(layout,_ds_audio,local);
        assert(device_settings_drafts[local].values[_device_setting_music_volume]==0.5);
        assert(device_settings_drafts[local].values[_device_setting_timer_volume]==0.5);
        assert(device_settings_drafts[local].values[_device_setting_timer_countdown]==1);
        assert(game_settings_event(setting_control(root,_device_setting_music_volume),_device_settings_next));
        root=enter_timer(root,layout,local);
        assert(game_settings_event(setting_control(root,_device_setting_timer_volume),_device_settings_next));
        assert(game_settings_event(setting_control(root,_device_setting_timer_minutes),_device_settings_previous));
        assert(game_settings_event(root,_device_settings_accept) && !writes);
        dispose(root); root=open_settings(layout,_ds_audio,local);
        save_succeeds=FALSE; assert(!game_settings_event(root,_device_settings_accept));
        assert(writes==1 && settings_values[_device_setting_timer_volume]==0.5);
        assert(device_settings_drafts[local].values[_device_setting_timer_volume]==0.6);
        struct widget_instance *failure_footer=widget_instance_find_by_tag_index_recursive(root,device_settings.footer_tags[_ds_audio]);
        struct widget_instance *failure_title=widget_instance_find_by_tag_index_recursive(root,device_settings.heading_tags[_ds_audio]);
        assert(failure_title);
        if(layout==_ds_pause_4p || layout==_ds_coop) {
            assert(!failure_footer && failure_title->parameters.text_box.string_list_index==_ds_failure_brief);
        } else assert(failure_footer && failure_footer->parameters.text_box.string_list_index==_ds_failure_help);
        save_succeeds=TRUE; assert(game_settings_event(root,_device_settings_accept));
        assert(writes==2 && applied_mask==((1UL<<_device_setting_music_volume)|
            (1UL<<_device_setting_timer_volume)|(1UL<<_device_setting_timer_minutes)));
        assert(settings_values[_device_setting_music_volume]==0.6 && settings_values[_device_setting_timer_volume]==0.6);
        assert(settings_values[_device_setting_timer_minutes]==0);
        assert(settings_values[_device_setting_master_volume]==0.125);
        assert(game_settings_event(root,_device_settings_accept) && writes==2);
        dispose(root);
    }
}
static void settings_timer_video(void) {
    settings_setup(0); assert(device_settings_build());
    struct widget_instance *root=open_settings(_ds_main,_ds_video,0);
    struct widget_instance *position=setting_control(root,_device_setting_timer_position),*scale=setting_control(root,_device_setting_timer_scale);
    assert(!wcscmp(device_settings.text[_ds_value_start+_device_setting_timer_position],L"Top Center"));
    assert(game_settings_event(position,_device_settings_previous));
    assert(!wcscmp(device_settings.text[_ds_value_start+_device_setting_timer_position],L"Bottom Right"));
    assert(game_settings_event(position,_device_settings_previous));
    assert(!wcscmp(device_settings.text[_ds_value_start+_device_setting_timer_position],L"Bottom Center"));
    assert(game_settings_event(scale,_device_settings_previous));
    assert(device_settings_drafts[0].values[_device_setting_timer_scale]==0.95);
    for(unsigned i=0;i<20;i++) assert(game_settings_event(scale,_device_settings_previous));
    assert(device_settings_drafts[0].values[_device_setting_timer_scale]==0.5);
    assert(!wcscmp(device_settings.text[_ds_value_start+_device_setting_timer_scale],L"50%"));
    for(unsigned i=0;i<20;i++) assert(game_settings_event(scale,_device_settings_next));
    assert(device_settings_drafts[0].values[_device_setting_timer_scale]==1);
    assert(game_settings_event(scale,_device_settings_previous));
    assert(!writes && game_settings_event(root,_device_settings_accept));
    assert(writes==1 && applied_mask==((1UL<<_device_setting_timer_position)|(1UL<<_device_setting_timer_scale)));
    dispose(root);
}
static void settings_pause_and_campaign(void) {
    settings_setup(1); assert(performance_pause_remap_tag(original_root_ids[0])!=original_root_ids[0]);
    assert(!device_settings.native_pages);
    for(unsigned i=0;i<NUMBER_OF_DEVICE_SETTINGS;i++) assert(device_settings_native.spinner_tags[i]==NONE);
    assert(register_calls==93 && !memcmp(originals,originals_before,sizeof(originals)));
    for(unsigned i=0;i<3;i++) {
        assert(performance_pause_list_children[i][0].widget_tag.index==resume_id);
        assert(performance_pause_list_children[i][3].widget_tag.index==quit_id);
        assert(performance_pause_settings_events[i][0].widget_tag.index==device_settings.screen_tags[i+1][_ds_game]);
        assert(performance_pause_children[i][1].vertical_offset+111<=original_roots[i][2].vertical_offset);
        for(unsigned page=0;page<_ds_page_count;page++) {
            assert(device_settings.screen[i+1][page].controller_index==_widget_controller_any);
            assert(!TEST_FLAG(device_settings.screen[i+1][page].flags,_widget_pause_game_time_bit));
            struct ui_widget_child_reference *children=device_settings.screen_children[i+1][page];
            struct ui_widget_definition *frame=ui_widget_definition_get(children[0].widget_tag.index);
            short height=page==_ds_game ? 159:page==_ds_audio ? 240:213;
            assert(frame->bounds.y1==height && frame->bounds.x0==-4 && frame->bounds.x1==222);
            assert(children[0].horizontal_offset==children[1].horizontal_offset-8);
            assert(children[0].vertical_offset>=0 && children[0].vertical_offset+height<=originals[i].bounds.y1);
            assert(children[2].widget_tag.index==device_settings.heading_tags[page]);
            assert(children[3].widget_tag.index==native_pause_legend_tag());
            assert(children[3].horizontal_offset==children[1].horizontal_offset+17);
            assert(children[3].vertical_offset==children[0].vertical_offset+height-25);
            assert(device_settings.screen[i+1][page].child_widgets.count==(!i && page!=_ds_game ? 5:4));
            struct ui_widget_definition *column=&device_settings.column[i+1][page];
            assert(column->bounds.x1==202);
            if(page!=_ds_game) {
                assert(children[1].vertical_offset==children[0].vertical_offset+22);
                assert(children[1].vertical_offset+column->child_widgets.count*27<=children[0].vertical_offset+height-29);
            }
            if(!i && page!=_ds_game) assert(children[4].vertical_offset+60<=originals[i].bounds.y1);
        }
    }
    for(unsigned row=0;row<NUMBER_OF_DEVICE_SETTINGS;row++) {
        assert(!memcmp(&device_settings.row[row].bounds,&originals[6].bounds,sizeof(rectangle2d)));
        assert(device_settings.row[row].background_bitmap.index==originals[6].background_bitmap.index);
        assert(device_settings.row[row].vertical_offset==3);
        long font=tag_loaded(FONT_GROUP_TAG,row==_device_setting_interpolation || row==_device_setting_timer_position ? "ui\\small_ui":"ui\\large_ui");
        assert(device_settings.row[row].text_font.index==font);
    }
    assert(device_settings.accept.text_font.index==originals[6].text_font.index && device_settings.accept.vertical_offset==3);
    assert(device_settings.choice[_ds_pause_1p][0].text_font.index==originals[6].text_font.index);
    assert(device_settings.heading[_ds_audio].text_font.index==originals[6].text_font.index);
    assert(device_settings.heading[_ds_audio].bounds.y1==22 && !device_settings.heading[_ds_audio].vertical_offset);
    struct widget_instance *one=open_settings(_ds_pause_1p,_ds_audio,0),*two=open_settings(_ds_pause_4p,_ds_audio,3);
    assert(!game_settings_is_native_spinner(setting_control(one,_device_setting_master_volume)));
    assert(device_settings.column[_ds_pause_1p][_ds_audio].child_widgets.count==7);
    assert(device_settings.column[_ds_pause_4p][_ds_video].child_widgets.count==6);
    assert(device_settings.column[_ds_pause_4p][_ds_timer].child_widgets.count==6);
    assert(game_settings_event(setting_control(two,_device_setting_master_volume),_device_settings_next));
    assert(device_settings_drafts[3].values[_device_setting_master_volume]==0.2 && device_settings_drafts[0].values[_device_setting_master_volume]==0.125);
    assert(!wcscmp(device_settings.text[_ds_value_start+3*NUMBER_OF_DEVICE_SETTINGS],L"Master: < 20% >"));
    assert(!wcscmp(device_settings.text[_ds_value_start],L"Master: < 12.5% >"));
    struct widget_instance *column=one->child->next,*help=widget_instance_find_by_tag_index_recursive(one,device_settings.footer_tags[_ds_audio]);
    assert(column->type==_ui_widget_type_column_list && help);
    column->focused_child=column->child->next;
    settings_render_inputs(column);
    assert(help->parameters.text_box.string_list_index==_ds_help_start+_device_setting_music_volume);
    column->focused_child=column->child;
    for(unsigned i=0;i<6;i++) column->focused_child=column->focused_child->next;
    settings_render_inputs(column);
    assert(help->parameters.text_box.string_list_index==_ds_audio_help);
    save_succeeds=FALSE;
    assert(!game_settings_event(two,_device_settings_accept));
    struct widget_instance *heading=widget_instance_find_by_tag_index_recursive(two,device_settings.heading_tags[_ds_audio]);
    assert(heading->parameters.text_box.string_list_index==_ds_failure_brief);
    assert(game_settings_event(setting_control(two,_device_setting_master_volume),_device_settings_next));
    assert(heading->parameters.text_box.string_list_index==_ds_audio_label);
    save_succeeds=TRUE;
    dispose(one); dispose(two);
    long old=performance_pause_tags[_pp_pause_1p]; scenario_tags_unload(); cache_file_globals.tags_loaded=TRUE; global_tag_instances=settings_map;
    assert(performance_pause_remap_tag(original_root_ids[0])!=old);
    settings_setup(2);
    for(unsigned i=0;i<2;i++) {
        assert(game_settings_remap_tag(original_root_ids[i])!=original_root_ids[i]);
        assert(device_settings_campaign.list[i].child_widgets.count==5);
        for(unsigned j=0;j<4;j++) assert(device_settings_campaign.list_children[i][j].widget_tag.index==original_lists[i][j].widget_tag.index);
        struct ui_widget_child_reference *children=device_settings_campaign.root_children[i];
        assert(children[1].horizontal_offset==72 && children[1].vertical_offset==(i ? 48:168));
        assert(children[1].vertical_offset-children[0].vertical_offset==6);
        assert(children[1].vertical_offset+device_settings_campaign.list_children[i][4].vertical_offset+27==children[0].vertical_offset+129);
        for(unsigned j=0;j<5;j++) if(j!=1) assert(!memcmp(&children[j],&original_roots[i][j],sizeof(children[j])));
        assert(device_settings_campaign.events[i][0].widget_tag.index==device_settings.screen_tags[_ds_solo+i][_ds_game]);
        assert(device_settings.screen[_ds_solo+i][_ds_game].child_widgets.count==4);
        for(unsigned page=0;page<_ds_page_count;page++) {
            assert(TEST_FLAG(device_settings.screen[_ds_solo+i][page].flags,_widget_pause_game_time_bit));
            one=open_settings(_ds_solo+i,page,i);
            assert(widget_globals.pause_game_time_count==1);
            dispose(one);
            assert(!settings_game_paused && !settings_sound_paused && !widget_globals.pause_game_time_count);
        }
        assert(!memcmp(originals,originals_before,sizeof(originals)));
        one=open_settings(_ds_solo+i,_ds_audio,i); dispose(one);
    }
    assert(register_calls==56);
}
static void settings_registration_failure(void) {
    settings_setup(0); assert(device_settings_build()); unsigned count=register_calls;
    for(unsigned fail=1;fail<=count;fail++) {
        settings_setup(0); fail_registration=fail;
        assert(game_settings_remap_tag(entry_id)==entry_id);
        fail_registration=0; assert(game_settings_remap_tag(entry_id)!=entry_id);
        assert(!memcmp(originals,originals_before,sizeof(originals)));
        assert(!memcmp(&chooser,&chooser_before,sizeof(chooser)));
        assert(!memcmp(&advanced,&advanced_before,sizeof(advanced)));
    }
    settings_setup(1); assert(performance_pause_build()); count=register_calls;
    for(unsigned fail=1;fail<=count;fail++) {
        settings_setup(1); fail_registration=fail;
        assert(performance_pause_remap_tag(original_root_ids[0])==original_root_ids[0]);
        fail_registration=0; assert(performance_pause_remap_tag(original_root_ids[0])!=original_root_ids[0]);
        assert(!memcmp(originals,originals_before,sizeof(originals)));
    }
    settings_setup(2); assert(device_settings_campaign_build()); count=register_calls;
    for(unsigned fail=1;fail<=count;fail++) {
        settings_setup(2); fail_registration=fail;
        assert(game_settings_remap_tag(original_root_ids[0])==original_root_ids[0]);
        fail_registration=0; assert(game_settings_remap_tag(original_root_ids[0])!=original_root_ids[0]);
        assert(!memcmp(originals,originals_before,sizeof(originals)));
    }
}
static void settings_cross_map_rebuild(void) {
    /* Keep the process's authored definitions alive across real registry
     * unloads, unlike the isolated map fixtures above. A missing solo root
     * and a saved NONE must never reuse the preceding map's string tags. */
    for(short mode=0;mode<2;mode++) {
        settings_setup(mode);
        assert(mode ? performance_pause_build() : device_settings_build());
        long old_strings=device_settings.heading[_ds_game].text_label_string_list.index;
        assert(device_settings.ready && device_settings.screen_tags[_ds_solo][_ds_game]==NONE);
        unsigned char preceding_state[sizeof(device_settings)];
        memcpy(preceding_state,&device_settings,sizeof(device_settings));
        settings_setup(2);
        memcpy(&device_settings,preceding_state,sizeof(device_settings));
        assert(!tag_index_is_group(old_strings,'ustr'));
        assert(game_settings_remap_tag(original_root_ids[0])!=original_root_ids[0]);
        long strings=device_settings_campaign.entry[0].text_label_string_list.index;
        assert(strings!=old_strings && tag_index_is_group(strings,'ustr'));
        assert(device_settings_campaign.events[0][0].widget_tag.index!=NONE);
        struct widget_instance *audio=open_settings(_ds_solo,_ds_audio,0);
        assert(!wcscmp(device_settings.text[_ds_value_start],L"Master: < 12.5% >"));
        dispose(audio);
    }
}
int main(void) {
    settings_structure(); settings_native_chooser(); settings_native_options(); settings_game_chooser(); settings_staging();
    settings_timer_staging(); settings_timer_video();
    settings_pause_and_campaign(); settings_registration_failure(); settings_cross_map_rebuild();
    puts("native game settings tests passed"); return 0;
}
'''

def game_settings_fixture_source():
    """Shared native widgets, including the renderer's actual input dispatch."""
    from tools.test_runtime_ui_tags import c_block
    source = fixture_source().split("static void shapes_and_preservation(void)", 1)[0]
    ui = (ROOT / "source/interface/ui_widget.c").read_text()
    initialize_pause = c_block(ui[ui.index("widget->pause_game_time = TEST_FLAG"):],
                              "if (widget->pause_game_time == TRUE)")
    delete_pause = c_block(ui, "if (widget->pause_game_time == TRUE)")
    pause_lifecycle = """static void settings_widget_pause_initialize(struct widget_instance *widget, struct ui_widget_definition *definition) {
    widget->pause_game_time = TEST_FLAG(definition->flags, _widget_pause_game_time_bit);
""" + initialize_pause + "\n}\nstatic void settings_widget_pause_delete(struct widget_instance *widget) {\n" + delete_pause + "\n}\n"
    source = source.replace("static struct widget_instance *instantiate(",
        "static void settings_widget_pause_initialize(struct widget_instance *,struct ui_widget_definition *);\n"
        "static void settings_widget_pause_delete(struct widget_instance *);\n"
        "static struct widget_instance *instantiate(", 1)
    source = source.replace("    return w;\n}", "    settings_widget_pause_initialize(w,d);\n    return w;\n}", 1)
    source = source.replace("static void dispose(struct widget_instance *w) {",
                            "static void dispose(struct widget_instance *w) {\n    settings_widget_pause_delete(w);", 1)
    enums = []
    for member in ("_widget_controller0", "_widget_pass_unhandled_events_to_children_bit =", "_event_handler_close_current_widget_bit", "_list_items_generated_in_code", "_text_justification_left", "_widget_event_b_button ="):
        start = ui.rfind("enum\n{", 0, ui.index(member))
        enums.append(c_block(ui[start:], "enum\n{") + ";")
    data = (ROOT / "source/interface/ui_widget_game_data_input_functions.c").read_text()
    preview = c_block(data, "static void settings_menu_update_extended_description(\n\tstruct widget_instance *list_widget)\n{")
    preview = preview.replace("description_definition->child_count", "description_definition->child_widgets.count")
    source += UI_STUBS.replace("/* NATIVE ENUMS */", "\n".join(enums)).replace("/* NATIVE PREVIEW CALLBACK */", preview).replace(
        "/* PRODUCTION WIDGET PAUSE LIFECYCLE */", pause_lifecycle)
    renderer = ui[ui.index("static void widget_instance_render_recursive(\n", ui.index("#define UI_MOUSE_MAXIMUM_TARGETS")):]
    dispatch = c_block(renderer, "for (input_index = 0;")
    source += """static void settings_render_inputs(struct widget_instance *widget) {
    struct ui_widget_definition *definition=ui_widget_definition_get(widget->definition_tag_index);
    long input_index;
""" + dispatch + "\n}\n"
    return source + UI_HARNESS


class NativeGameSettingsTests(unittest.TestCase):
    def test_resident_help_widths(self):
        """Use the shipped font advances to catch clipping that C layout mocks cannot."""
        from tools.verify_performance_sound_samples import Cache
        paths = [ROOT / f"assets/maps/{name}.map" for name in ("bloodgulch", "ui")]
        paths = [path for path in paths if path.exists()]
        if not paths:
            self.skipTest("owned Xbox cache assets required for font metrics")
        source = (ROOT / "source/interface/game_settings_menu.inc").read_text()
        strings = []
        for name in ("captions", "help"):
            array = source.split(f"static char const *const {name}[] = {{", 1)[1].split("};", 1)[0]
            strings.extend(ast.literal_eval(value) for value in re.findall(r'"(?:\\.|[^"\\])*"', array))
        for path in paths:
            cache = Cache(path)
            font = cache.by_path[r"ui\small_ui"]
            self.assertEqual(font["group"], "font")
            # font_header.characters follows the four 16-byte style references.
            count, address, _ = cache.unpack("<3I", font["address"] + 0x7C)
            glyphs = {}
            for index in range(count):
                code, advance, width, _, origin_x = cache.unpack("<H4h", address + index * 0x14)
                glyphs[chr(code)] = (advance, width, origin_x)
            for value in strings:
                lines = value.splitlines()
                self.assertLessEqual(len(lines), 3, value)
                for line in lines:
                    with self.subTest(map=path.stem, line=line):
                        cursor = ink_right = 0
                        for character in line:
                            advance, width, origin_x = glyphs[character]
                            ink_right = max(ink_right, cursor + origin_x + width)
                            cursor += advance
                        self.assertLessEqual(max(cursor, ink_right), 276)

    def test_native_menu(self):
        source = game_settings_fixture_source()
        with tempfile.TemporaryDirectory(prefix="halo-native-settings-") as folder:
            directory = Path(folder)
            (directory / "fixture.c").write_text(source)
            for platform in ("HALO_MACOS", "HALO_LINUX", "HALO_WINDOWS"):
                with self.subTest(platform=platform):
                    binary = directory / (platform + (".exe" if sys.platform == "win32" else ""))
                    subprocess.run(["clang", "-std=c99", "-Wall", "-Wextra", "-Werror", "-Wno-multichar", "-Wno-format",
                                    "-Wno-unused-function", "-D_CRT_SECURE_NO_WARNINGS", f"-D{platform}=1", "-I", str(ROOT / "source"), "-I", str(ROOT / "port/linux"), str(directory / "fixture.c"),
                                    "-o", str(binary)], check=True)
                    result = subprocess.run([str(binary)], text=True, capture_output=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual(result.stdout.strip(), "native game settings tests passed")


@unittest.skipUnless(shutil.which("clang") and (SDL / "include/SDL3/SDL.h").exists(), "clang and SDL3 headers required")
class ConfigBooleanPersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="halo-game-settings-config-")
        cls.directory = Path(cls.temporary.name)
        (cls.directory / "prefix.h").write_text(PREFIX)
        (cls.directory / "probe.c").write_text(CONFIG_HARNESS)
        cls.executables = {}
        for target, defines in (("mac", ["-DHALO_ANDROID=1", "-DHALO_MACOS=1"]),
                                ("other", ["-DHALO_ANDROID=1"]), ("desktop", [])):
            executable = cls.directory / target
            subprocess.run(["clang", "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror", "-pthread",
                            *defines, "-include", str(cls.directory / "prefix.h"), f"-I{PORT}",
                            f"-I{SDL / 'include'}", f"-I{ROOT / 'port/third_party/tomlc17'}",
                            str(cls.directory / "probe.c"), str(PORT / "port_config.c"),
                            str(ROOT / "port/third_party/tomlc17/tomlc17.c"), "-o", str(executable)], check=True)
            cls.executables[target] = executable

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_save(self, original, expected, *, mode="save", success=True, value=0, setting="audio.menu_music"):
        for target, executable in self.executables.items():
            with self.subTest(target=target), tempfile.TemporaryDirectory(dir=self.directory) as folder:
                directory = Path(folder)
                fixture = directory / "existing.toml"
                fixture.write_bytes(original.encode())
                environment = {k: v for k, v in os.environ.items() if not k.startswith("HALO_")}
                environment.update(HALO_SAVE_ROOT=folder, HALO_DATA_ROOT=folder)
                result = subprocess.run([str(executable), str(fixture), mode, setting, str(value)],
                                        env=environment, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stdout.strip(), f"1 {int(success)} {value if success else 1}")
                self.assertEqual((directory / "config.toml").read_bytes(), expected.encode())
                if success and setting == "audio.menu_music" and "[audio]" in expected:
                    reload = subprocess.run([str(executable), "read", mode, setting, str(value)],
                                            env=environment, text=True, capture_output=True)
                    self.assertEqual(reload.returncode, 0, reload.stderr)
                    self.assertEqual(reload.stdout.strip(), str(value))

    def test_comments_unknown_values_and_multiline_text_preserved(self):
        original = '# custom\n[unknown]\ntext = """\n[audio]\nmenu_music = false\n"""\n[ audio ] # note\n  menu_music\t= true # keep this\nenabled = true\nvolume = 0.125\ncustom = "keep"\n'
        self.run_save(original, original.replace('= true # keep this', '= false # keep this'))

    def test_existing_boolean_spelling_and_layout(self):
        for original in ('[audio]\r\nmenu_music = true\r\n', 'audio.menu_music=true # comment\n',
                         '["audio"]\n"menu_music" = true', 'audio={menu_music=true, custom="é"}\n'):
            with self.subTest(original=original):
                self.run_save(original, original.replace('true', 'false'))

    def test_enabling_false_value(self):
        self.run_save('[audio]\nmenu_music = false # no\n', '[audio]\nmenu_music = true # no\n', value=1)

    def test_missing_boolean_added_without_removing_existing_text(self):
        self.run_save('[audio] # note\nvolume = 0.5\n', '[audio] # note\nmenu_music = false\nvolume = 0.5\n')
        self.run_save('# comments only', '# comments only\n[audio]\nmenu_music = false\n')
        self.run_save('audio.volume=0.5\n', 'audio.menu_music = false\naudio.volume=0.5\n')

    def test_invalid_type_or_invalid_document_left_untouched(self):
        for original in ('[audio]\nmenu_music = "true"\n', '[audio]\nmenu_music = tru\n',
                         'audio={volume=0.5}\n'):
            with self.subTest(original=original):
                self.run_save(original, original, success=False)

    def test_save_failure_keeps_running_value_and_file(self):
        original = '[audio]\nmenu_music = true # preserve\n'
        self.run_save(original, original, mode="failure", success=False)

    def test_unknown_or_non_boolean_setting_is_rejected(self):
        original = '[audio]\nmenu_music = true\n'
        for setting in ('audio.unknown', 'audio.volume'):
            self.run_save(original, original, setting=setting, success=False)


if __name__ == "__main__":
    unittest.main()
