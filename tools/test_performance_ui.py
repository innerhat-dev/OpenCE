"""Compile native PB editor code with stock-shaped widget fixtures.

Uses production UI declarations, cache registry, tree lookup and help callback.
Checks cloning, profile staging, selectors, registration failure and map lifetime.
Rendering and actual platform event delivery remain app smoke-test concerns.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.test_runtime_ui_tags import c_block, PREFIX as CACHE_PREFIX

ROOT = Path(__file__).resolve().parents[1]

PREFIX = r'''
#include <wchar.h>
#define NUMBEROF(a) (sizeof(a)/sizeof((a)[0]))
typedef unsigned char byte;
typedef unsigned short word;
typedef float real;
typedef struct { short y0,x0,y1,x1; } rectangle2d;
typedef struct { float alpha,red,green,blue; } real_argb_color;
enum { UI_WIDGET_DEFINITION_TAG='DeLa', UNICODE_STRING_LIST_TAG='ustr',
       _ui_widget_type_container=0, _ui_widget_type_text_box=1,
       _ui_widget_type_spinner_list=2, _ui_widget_type_column_list=3 };
/* STRUCTURES */
#define ui_widget_definition_get(i) ((struct ui_widget_definition *)tag_get(UI_WIDGET_DEFINITION_TAG,(i)))
#define unicode_string_list_definition_get(i) ((struct string_list *)tag_get(UNICODE_STRING_LIST_TAG,(i)))
struct game_variant { unsigned flags; };
static struct game_variant edited;
static boolean editing=TRUE;
static unsigned mutation_calls,help_calls;
enum { _performance_option_match_timer=1, _performance_option_spawn_markers=2, _performance_option_timer_audio=4,
       _performance_option_silent_movement=8, _performance_option_silent_weapon_ready=16,
       PERFORMANCE_PRACTICE_FLAGS=7, PERFORMANCE_OPTIONS_MASK=31 };
static struct game_variant *player_ui_get_edit_playlist_profile(void) { return editing ? &edited : NULL; }
static unsigned performance_variant_get_flags(const struct game_variant *v) { return v->flags; }
static void performance_variant_set_flags(struct game_variant *v,unsigned f) { mutation_calls++; v->flags=f; }
/* TREE HELPERS */
static void ui_widget_game_data_function_invoke(struct widget_instance *w,short f) {
    assert(f==17); help_calls++; game_options_menu_update_text_desc(w);
}
static unsigned register_calls,fail_registration;
static long cache_files_register_runtime_ui_tag(long group,const char *name,void *definition) {
    register_calls++;
    if (register_calls==fail_registration) return NONE;
    return real_register_runtime_ui_tag(group,name,definition);
}
#include "interface/performance_editor_menu.inc"
'''

HARNESS = r'''
#define EDIT_PREFIX "ui\\shell\\main_menu\\settings_select\\multiplayer_setup\\"
enum { ROOT_TAG,LIST_TAG,ENTRY_TAG,SCREEN_TAG,MENU_TAG,HELP_TAG,ROW_TAG,LABEL_TAG,SPINNER_TAG,
       PREVIEW_TAG,PREVIEW_TEXT_TAG,PREVIEW_PIC_TAG,SAVE_TAG,OTHER_TAG,STOCK_WIDGET_COUNT,STRINGS_TAG=STOCK_WIDGET_COUNT };
static const char *stock_names[]={
    EDIT_PREFIX "playlist_edit\\gametype_edit_screen",
    EDIT_PREFIX "playlist_edit\\edit_playlist_select_list",
    EDIT_PREFIX "playlist_edit\\playlist_edit_indicators_item",
    EDIT_PREFIX "indicator_options_edit\\indicator_options_screen",
    EDIT_PREFIX "indicator_options_edit\\indicator_options_menu",
    EDIT_PREFIX "indicator_options_edit\\indicator_options_help",
    EDIT_PREFIX "indicator_options_edit\\op_players_on_radar",
    EDIT_PREFIX "indicator_options_edit\\indicator_options_players_on_radar_label",
    EDIT_PREFIX "indicator_options_edit\\indicator_options_players_on_radar_spinner",
    "ui\\fixture\\preview", "ui\\fixture\\preview_text", "ui\\fixture\\preview_pic",
    EDIT_PREFIX "playlist_edit\\save_settings_item", "ui\\fixture\\other", "ui\\fixture\\strings"
};
static struct {
    struct ui_widget_definition defs[STOCK_WIDGET_COUNT];
    struct ui_widget_child_reference root[8],list[6],screen[3],menu[3],row[2],preview[2];
    struct ui_widget_event_handler_reference root_events[1],entry_events[2],menu_events[3],save_events[2];
    struct ui_widget_game_data_input_reference list_input,menu_input;
    struct string_list strings;
    struct string_list_entry entries[6];
    wchar_t captions[6][16];
} stock,snapshot;
static struct cache_file_tag_instance stock_tags[STOCK_WIDGET_COUNT+1];
static struct cache_file_tag_header tag_header={STOCK_WIDGET_COUNT+1,0x18181818};
static long stock_id(unsigned slot) { return 0x12340000 | slot; }
static struct tag_reference ref(unsigned slot) {
    return (struct tag_reference){slot==STRINGS_TAG ? 'ustr' : 'DeLa',NULL,0,stock_id(slot)};
}
static void setup(void) {
    if(cache_file_globals.tags_loaded) {
        unsigned previous_unloads=unload_calls;
        scenario_tags_unload();
        assert(unload_calls==previous_unloads+5);
        assert(!cache_file_globals.tags_loaded && !global_tag_instances);
    }
    memset(&stock,0,sizeof(stock)); memset(&pb_editor,0,sizeof(pb_editor));
    memset(stock_tags,0,sizeof(stock_tags));
    editing=TRUE; edited.flags=mutation_calls=register_calls=fail_registration=help_calls=0;
    for(unsigned i=0;i<STOCK_WIDGET_COUNT;i++) {
        struct ui_widget_definition *d=&stock.defs[i];
        d->background_bitmap.index=d->text_label_string_list.index=d->text_font.index=NONE;
        d->list_header_bitmap.index=d->list_footer_bitmap.index=d->extended_description_widget.index=NONE;
        d->controller_index=4;
        snprintf(d->name,sizeof(d->name),"original_%u",i);
        stock_tags[i]=(struct cache_file_tag_instance){'DeLa',{NONE,NONE},stock_id(i),(char *)stock_names[i],d,{0,0}};
    }
    for(unsigned i=0;i<8;i++) stock.root[i].widget_tag=ref(OTHER_TAG);
    stock.root[1].widget_tag=ref(LIST_TAG); stock.root[7].vertical_offset=252;
    stock.defs[ROOT_TAG].child_widgets=(struct tag_block){8,stock.root,NULL};
    stock.root_events[0]=(struct ui_widget_event_handler_reference){.flags=0x80,.event_type=24,.function=94};
    stock.defs[ROOT_TAG].event_handlers=(struct tag_block){1,stock.root_events,NULL};
    for(unsigned i=0;i<6;i++) stock.list[i].widget_tag=ref(i==4 ? ENTRY_TAG : i==5 ? SAVE_TAG : OTHER_TAG);
    stock.list[5].vertical_offset=20;
    stock.defs[LIST_TAG].type=3; stock.defs[LIST_TAG].flags=9;
    stock.defs[LIST_TAG].child_widgets=(struct tag_block){6,stock.list,NULL};
    stock.defs[LIST_TAG].extended_description_widget=ref(PREVIEW_TAG);
    stock.list_input.function=3; stock.defs[LIST_TAG].game_data_inputs=(struct tag_block){1,&stock.list_input,NULL};
    stock.defs[ENTRY_TAG].type=1; stock.defs[ENTRY_TAG].bounds=(rectangle2d){210,51,242,283};
    stock.defs[SAVE_TAG].type=1; stock.defs[SAVE_TAG].bounds=(rectangle2d){243,51,275,283};
    for(unsigned i=0;i<2;i++) {
        stock.entry_events[i]=(struct ui_widget_event_handler_reference){.flags=8,.event_type=i ? 12:0,.widget_tag=ref(SCREEN_TAG)};
        stock.save_events[i]=(struct ui_widget_event_handler_reference){.flags=0x88,.event_type=i ? 12:0,.function=60};
    }
    stock.defs[ENTRY_TAG].event_handlers=(struct tag_block){2,stock.entry_events,NULL};
    stock.defs[SAVE_TAG].event_handlers=(struct tag_block){2,stock.save_events,NULL};
    stock.screen[0].widget_tag=stock.screen[2].widget_tag=ref(OTHER_TAG); stock.screen[1].widget_tag=ref(MENU_TAG);
    stock.defs[SCREEN_TAG].child_widgets=(struct tag_block){3,stock.screen,NULL};
    stock.defs[MENU_TAG].type=3; stock.defs[MENU_TAG].flags=9;
    for(unsigned i=0;i<3;i++) {
        stock.menu[i].widget_tag=ref(ROW_TAG); stock.menu[i].vertical_offset=73+30*i; stock.menu[i].horizontal_offset=54;
        stock.menu_events[i]=(struct ui_widget_event_handler_reference){.flags=i ? 0x280:0x80,.event_type=i==0 ? 24 : i==1 ? 0:12,.function=i ? 49:59};
    }
    stock.defs[MENU_TAG].child_widgets=(struct tag_block){3,stock.menu,NULL};
    stock.defs[MENU_TAG].event_handlers=(struct tag_block){3,stock.menu_events,NULL};
    stock.defs[MENU_TAG].extended_description_widget=ref(HELP_TAG);
    stock.menu_input.function=17; stock.defs[MENU_TAG].game_data_inputs=(struct tag_block){1,&stock.menu_input,NULL};
    stock.defs[HELP_TAG].type=1;
    stock.row[0].widget_tag=ref(LABEL_TAG); stock.row[1].widget_tag=ref(SPINNER_TAG);
    stock.row[1].vertical_offset=1; stock.row[1].horizontal_offset=366;
    stock.defs[ROW_TAG].child_widgets=(struct tag_block){2,stock.row,NULL}; stock.defs[ROW_TAG].flags=1;
    stock.defs[LABEL_TAG].type=1; stock.defs[LABEL_TAG].text_font.index=0x45670000;
    stock.defs[LABEL_TAG].text_color=(real_argb_color){1,.156863f,.588235f,1};
    stock.defs[LABEL_TAG].horizontal_offset=13; stock.defs[LABEL_TAG].vertical_offset=4;
    stock.defs[SPINNER_TAG].type=2; stock.defs[SPINNER_TAG].flags=0x41; stock.defs[SPINNER_TAG].list_flags=2;
    stock.defs[SPINNER_TAG].bounds=(rectangle2d){2,2,22,48}; stock.defs[SPINNER_TAG].list_footer_bounds=(rectangle2d){7,48,19,54};
    stock.defs[SPINNER_TAG].text_label_string_list=ref(STRINGS_TAG);
    stock.preview[0].widget_tag=ref(PREVIEW_TEXT_TAG); stock.preview[1].widget_tag=ref(PREVIEW_PIC_TAG);
    stock.defs[PREVIEW_TAG].child_widgets=(struct tag_block){2,stock.preview,NULL};
    stock.defs[PREVIEW_TEXT_TAG].type=1; stock.defs[PREVIEW_TEXT_TAG].text_label_string_list=ref(STRINGS_TAG);
    for(unsigned i=0;i<6;i++) {
        swprintf(stock.captions[i],16,L"original-%u",i);
        stock.entries[i].string.address=stock.captions[i]; stock.entries[i].string.size=12*sizeof(wchar_t);
    }
    stock.strings.strings=(struct tag_block){6,stock.entries,NULL};
    stock_tags[STRINGS_TAG]=(struct cache_file_tag_instance){'ustr',{NONE,NONE},stock_id(STRINGS_TAG),(char *)stock_names[STRINGS_TAG],&stock.strings,{0,0}};
    cache_file_globals.tags_loaded=TRUE; cache_file_globals.tag_header=&tag_header; global_tag_instances=stock_tags;
    snapshot=stock;
}
static struct widget_instance *instantiate(long tag,struct widget_instance *parent) {
    struct ui_widget_definition *d=ui_widget_definition_get(tag);
    struct widget_instance *w=calloc(1,sizeof(*w)),*last=NULL;
    assert(w); w->definition_tag_index=tag; w->type=d->type; w->name=d->name; w->parent=parent;
    for(long i=0;i<d->child_widgets.count;i++) {
        struct ui_widget_child_reference *c=(struct ui_widget_child_reference *)d->child_widgets.address+i;
        struct widget_instance *child=instantiate(c->widget_tag.index,w);
        if(last) last->next=child; else w->child=child;
        child->previous=last; last=child;
    }
    w->focused_child=w->child;
    if(w->type==2 && d->text_label_string_list.index!=NONE)
        w->parameters.list.number_of_items=unicode_string_list_definition_get(d->text_label_string_list.index)->strings.count;
    if(d->extended_description_widget.index!=NONE)
        w->parameters.list.extended_description=instantiate(d->extended_description_widget.index,NULL);
    return w;
}
static void dispose(struct widget_instance *w) {
    struct widget_instance *c=w->child;
    while(c) { struct widget_instance *next=c->next; dispose(c); c=next; }
    if((w->type==2 || w->type==3) && w->parameters.list.extended_description) dispose(w->parameters.list.extended_description);
    free(w);
}
static wchar_t *string_at(struct ui_widget_definition *d,unsigned index) {
    struct string_list *s=unicode_string_list_definition_get(d->text_label_string_list.index);
    assert(index<(unsigned)s->strings.count); return ((struct string_list_entry *)s->strings.address)[index].string.address;
}
static void shapes_and_preservation(void) {
    setup(); long mapped=performance_editor_remap_tag(stock_id(ROOT_TAG)); assert(mapped!=stock_id(ROOT_TAG));
    assert(performance_editor_remap_tag(stock_id(ROOT_TAG))==mapped);
    assert(performance_editor_remap_tag(stock_id(OTHER_TAG))==stock_id(OTHER_TAG));
    assert(!memcmp(&snapshot,&stock,sizeof(stock)));
    assert(pb_editor.root.child_widgets.count==8 && pb_editor.list.child_widgets.count==7);
    assert(pb_editor.root_children[1].widget_tag.index==pb_editor.list_tag && pb_editor.root_children[7].vertical_offset==285);
    for(unsigned i=0;i<5;i++) assert(!memcmp(&pb_editor.list_children[i],&stock.list[i],sizeof(stock.list[0])));
    assert(ui_widget_definition_get(pb_editor.list_children[5].widget_tag.index)==&pb_editor.entry);
    assert(!wcscmp(string_at(&pb_editor.entry,0),L"PB OPTIONS"));
    assert(unicode_string_list_definition_get(pb_editor.heading.text_label_string_list.index)->strings.count==8);
    assert(pb_editor.heading.string_list_index==7);
    assert(!wcscmp(string_at(&pb_editor.heading,pb_editor.heading.string_list_index),L"PERFORMANCE OPTIONS"));
    assert(pb_editor.entry.bounds.y0==243 && pb_editor.entry.bounds.y1==275);
    assert(pb_editor.list_children[6].widget_tag.index==stock_id(SAVE_TAG) && pb_editor.list_children[6].vertical_offset==53);
    assert(pb_editor.entry.bounds.y1<stock.defs[SAVE_TAG].bounds.y0+pb_editor.list_children[6].vertical_offset);
    for(unsigned i=0;i<2;i++) {
        assert(pb_editor.entry_events[i].event_type==(i ? 12:0) && pb_editor.entry_events[i].flags==8);
        assert(ui_widget_definition_get(pb_editor.entry_events[i].widget_tag.index)==&pb_editor.screen);
    }
    assert(pb_editor.menu_events[0].event_type==24 && pb_editor.menu_events[0].function==_pb_editor_initialize);
    for(unsigned i=1;i<3;i++) assert(pb_editor.menu_events[i].event_type==(i==1 ? 0:12) && pb_editor.menu_events[i].flags==0x280 && pb_editor.menu_events[i].function==_pb_editor_accept);
    assert(pb_editor.menu.child_widgets.count==6);
    assert(!performance_editor_is_spinner(NULL));
    for(unsigned i=0;i<6;i++) {
        struct widget_instance spinner={0}; spinner.definition_tag_index=pb_editor.spinner_tag[i];
        assert(performance_editor_is_spinner(&spinner));
        spinner.definition_tag_index=pb_editor.menu_children[i].widget_tag.index;
        assert(!performance_editor_is_spinner(&spinner));
        assert(pb_editor.menu_children[i].vertical_offset==(short)(73+30*i) && pb_editor.menu_children[i].horizontal_offset==54);
        assert(pb_editor.row[i].child_widgets.count==2 && pb_editor.spinner[i].type==2 && pb_editor.spinner[i].list_flags==2);
        assert(pb_editor.label[i].text_font.index==stock.defs[LABEL_TAG].text_font.index);
        assert(!memcmp(&pb_editor.label[i].text_color,&stock.defs[LABEL_TAG].text_color,sizeof(real_argb_color)));
        assert(pb_editor.label[i].string_list_index==(short)i+1);
        assert(pb_editor.spinner_tag[i]!=NONE && pb_editor.row_children[i][1].horizontal_offset==300);
        assert(pb_editor.spinner[i].bounds.x1==142 && pb_editor.spinner[i].list_footer_bounds.x1==148);
    }
    assert(!wcscmp(string_at(&pb_editor.spinner[0],0),L"STOCK") && !wcscmp(string_at(&pb_editor.spinner[0],1),L"PRACTICE") && !wcscmp(string_at(&pb_editor.spinner[0],2),L"CUSTOM"));
    assert(!wcscmp(string_at(&pb_editor.spinner[1],0),L"OFF") && !wcscmp(string_at(&pb_editor.spinner[1],1),L"ON"));
    for(unsigned i=4;i<6;i++) assert(!wcscmp(string_at(&pb_editor.spinner[i],0),L"NORMAL") && !wcscmp(string_at(&pb_editor.spinner[i],1),L"SILENT"));
    assert(pb_editor.menu_children[5].vertical_offset+28<321); /* Clear of stock help. */
    for(unsigned i=0;i<7;i++) {
        if(i==5) assert(!wcscmp(string_at(&pb_editor.preview_text,i),
            L"Performance options like\r\ntimers, spawn markers,\r\nand more.\r\n\r\nThis gametype:"));
        else assert(!wcscmp(string_at(&pb_editor.preview_text,i),stock.captions[i==6 ? 5:i]));
    }
}
static void selection_and_staging(void) {
    setup(); assert(pb_editor_build());
    for(unsigned flags=0;flags<=PERFORMANCE_OPTIONS_MASK;flags++) {
        struct widget_instance *menu=instantiate(pb_editor.menu_tag,NULL); edited.flags=flags;
        assert(performance_editor_event(menu,_pb_editor_initialize));
        assert(pb_editor_spinner(menu,0)->parameters.list.selected_index==(flags==0 ? 0:flags==7 ? 1:2));
        assert(pb_editor_spinner(menu,1)->parameters.list.selected_index==!!(flags&1));
        assert(pb_editor_spinner(menu,2)->parameters.list.selected_index==!!(flags&2));
        assert(pb_editor_spinner(menu,3)->parameters.list.selected_index==!!(flags&4));
        assert(pb_editor_spinner(menu,4)->parameters.list.selected_index==!!(flags&8));
        assert(pb_editor_spinner(menu,5)->parameters.list.selected_index==!!(flags&16)); dispose(menu);
    }
    struct widget_instance *menu=instantiate(pb_editor.menu_tag,NULL); edited.flags=0;
    assert(performance_editor_event(menu,_pb_editor_initialize));
    struct widget_instance *p=pb_editor_spinner(menu,0),*t=pb_editor_spinner(menu,1),*m=pb_editor_spinner(menu,2),*a=pb_editor_spinner(menu,3);
    p->parameters.list.selected_index=1; performance_editor_input(menu,32001);
    assert(t->parameters.list.selected_index==1 && m->parameters.list.selected_index==1 && a->parameters.list.selected_index==1 && edited.flags==0 && mutation_calls==0);
    t->parameters.list.selected_index=0; performance_editor_input(menu,32001); assert(p->parameters.list.selected_index==2);
    m->parameters.list.selected_index=0; performance_editor_input(menu,32001); assert(p->parameters.list.selected_index==2);
    a->parameters.list.selected_index=0; performance_editor_input(menu,32001); assert(p->parameters.list.selected_index==0);
    t->parameters.list.selected_index=1; performance_editor_input(menu,32001); assert(p->parameters.list.selected_index==2);
    p->parameters.list.selected_index=0; performance_editor_input(menu,32001); assert(!t->parameters.list.selected_index && !m->parameters.list.selected_index && !a->parameters.list.selected_index);
    p->parameters.list.selected_index=1; performance_editor_input(menu,32001);
    assert(!performance_editor_event(menu,999)); assert(edited.flags==0);
    /* B has no accept callback: discarding the submenu leaves the profile unchanged. */
    dispose(menu); menu=instantiate(pb_editor.menu_tag,NULL); assert(performance_editor_event(menu,_pb_editor_initialize));
    assert(pb_editor_spinner(menu,0)->parameters.list.selected_index==0 && edited.flags==0);
    pb_editor_spinner(menu,1)->parameters.list.selected_index=1;
    assert(performance_editor_event(menu,_pb_editor_accept)); assert(edited.flags==1 && mutation_calls==1);
    dispose(menu); menu=instantiate(pb_editor.menu_tag,NULL); assert(performance_editor_event(menu,_pb_editor_initialize));
    assert(pb_editor_spinner(menu,0)->parameters.list.selected_index==2 && pb_editor_spinner(menu,1)->parameters.list.selected_index==1 && pb_editor_spinner(menu,2)->parameters.list.selected_index==0);
    editing=FALSE; assert(!performance_editor_event(menu,_pb_editor_accept)); assert(mutation_calls==1); editing=TRUE;
    dispose(menu); assert(!memcmp(&snapshot,&stock,sizeof(stock)));
}
static void sound_rules_and_presets(void) {
    setup(); assert(pb_editor_build());
    for(unsigned flags=0;flags<=PERFORMANCE_OPTIONS_MASK;flags++) {
        edited.flags=flags;
        struct widget_instance *menu=instantiate(pb_editor.menu_tag,NULL);
        assert(performance_editor_event(menu,_pb_editor_initialize));
        assert(performance_editor_event(menu,_pb_editor_accept));
        assert(edited.flags==flags); /* Every sound-rule combination survives Accept unchanged. */
        dispose(menu);
    }
    edited.flags=0; mutation_calls=0;
    struct widget_instance *menu=instantiate(pb_editor.menu_tag,NULL);
    assert(performance_editor_event(menu,_pb_editor_initialize));
    struct widget_instance *p=pb_editor_spinner(menu,0),*movement=pb_editor_spinner(menu,4),*weapon=pb_editor_spinner(menu,5);
    movement->parameters.list.selected_index=1; performance_editor_input(menu,32001);
    assert(p->parameters.list.selected_index==2 && pb_editor.last_flags==8 && !edited.flags && !mutation_calls);
    weapon->parameters.list.selected_index=1; performance_editor_input(menu,32001);
    assert(pb_editor.last_flags==24 && !edited.flags && !mutation_calls);
    dispose(menu); menu=instantiate(pb_editor.menu_tag,NULL); assert(performance_editor_event(menu,_pb_editor_initialize));
    assert(!pb_editor_spinner(menu,4)->parameters.list.selected_index && !pb_editor_spinner(menu,5)->parameters.list.selected_index);
    pb_editor_spinner(menu,4)->parameters.list.selected_index=1;
    pb_editor_spinner(menu,5)->parameters.list.selected_index=1;
    assert(performance_editor_event(menu,_pb_editor_accept) && edited.flags==24 && mutation_calls==1);
    p=pb_editor_spinner(menu,0); p->parameters.list.selected_index=1; performance_editor_input(menu,32001);
    assert(pb_editor.last_flags==PERFORMANCE_PRACTICE_FLAGS && edited.flags==24 && mutation_calls==1);
    assert(!pb_editor_spinner(menu,4)->parameters.list.selected_index && !pb_editor_spinner(menu,5)->parameters.list.selected_index);
    assert(performance_editor_event(menu,_pb_editor_accept) && edited.flags==7 && mutation_calls==2);
    pb_editor_spinner(menu,4)->parameters.list.selected_index=1; performance_editor_input(menu,32001);
    p->parameters.list.selected_index=0; performance_editor_input(menu,32001);
    assert(pb_editor.last_flags==0 && !pb_editor_spinner(menu,4)->parameters.list.selected_index && !pb_editor_spinner(menu,5)->parameters.list.selected_index);
    dispose(menu);
}
static void preview_and_help(void) {
    setup(); assert(pb_editor_build());
    struct widget_instance *list=instantiate(pb_editor.list_tag,NULL);
    struct widget_instance *entry=list->child,*desc=list->parameters.list.extended_description;
    for(short i=0;i<7;i++,entry=entry->next) {
        list->focused_child=entry; performance_editor_input(list,32000);
        assert(desc->child->parameters.text_box.string_list_index==i);
        assert(desc->child->next->animation.current_frame_index==(i==6 ? 5:i==5 ? 4:i));
    }
    dispose(list);
    struct widget_instance *menu=instantiate(pb_editor.menu_tag,NULL); assert(performance_editor_event(menu,_pb_editor_initialize));
    entry=menu->child;
    for(short row=0;row<6;row++,entry=entry->next) {
        menu->focused_child=entry;
        struct widget_instance *spinner=pb_editor_spinner(menu,row);
        for(short selected=0;selected<(row ? 2:3);selected++) {
            spinner->parameters.list.selected_index=selected; performance_editor_input(menu,32001);
            assert(menu->parameters.list.extended_description->parameters.text_box.string_list_index==(row==0 ? selected:1+2*row+selected));
        }
    }
    assert(help_calls==13); menu->focused_child=NULL; performance_editor_input(menu,32001); assert(help_calls==13);
    dispose(menu);
}
static void registration_and_reload(void) {
    setup(); assert(pb_editor_build()); unsigned total=register_calls; assert(total>20 && total<64);
    long previous_root=pb_editor.root_tag;
    scenario_tags_unload(); assert(tag_loaded('DeLa',"ui\\native_pb\\editor")==NONE && !tag_index_is_group(previous_root,'DeLa'));
    cache_file_globals.tags_loaded=TRUE; global_tag_instances=stock_tags;
    long next_root=performance_editor_remap_tag(stock_id(ROOT_TAG)); assert(next_root!=stock_id(ROOT_TAG) && next_root!=previous_root);
    assert(!tag_index_is_group(previous_root,'DeLa')); assert(!memcmp(&snapshot,&stock,sizeof(stock)));
    for(unsigned fail=1;fail<=total;fail++) {
        setup(); fail_registration=fail;
        assert(performance_editor_remap_tag(stock_id(ROOT_TAG))==stock_id(ROOT_TAG));
        assert(tag_loaded('DeLa',"ui\\native_pb\\editor")==NONE);
        assert(!memcmp(&snapshot,&stock,sizeof(stock)));
        fail_registration=0;
        assert(performance_editor_remap_tag(stock_id(ROOT_TAG))!=stock_id(ROOT_TAG));
    }
    setup(); stock.defs[ROOT_TAG].child_widgets.count=7;
    assert(performance_editor_remap_tag(stock_id(ROOT_TAG))==stock_id(ROOT_TAG) && !register_calls);
    setup(); stock.defs[PREVIEW_TEXT_TAG].type=0;
    assert(performance_editor_remap_tag(stock_id(ROOT_TAG))==stock_id(ROOT_TAG) && !register_calls);
    setup(); stock.strings.strings.count=5;
    assert(performance_editor_remap_tag(stock_id(ROOT_TAG))==stock_id(ROOT_TAG) && !register_calls);
}
int main(void) {
    shapes_and_preservation(); selection_and_staging(); sound_rules_and_presets(); preview_and_help(); registration_and_reload();
    puts("native PB editor tests passed"); return 0;
}
'''


def fixture_source():
    cache = (ROOT / "source/cache/cache_files.c").read_text()
    ui = (ROOT / "source/interface/ui_widget.c").read_text()
    tags = (ROOT / "source/tag_files/tag_groups.h").read_text()
    strings = (ROOT / "source/text/text_group.h").read_text()
    data = (ROOT / "source/interface/ui_widget_game_data_input_functions.c").read_text()
    start = cache.index("#ifdef HALO_PORT_MAXIMUM_NETWORK_PLAYERS\nenum\n{\n\tRUNTIME_UI_TAG_INDEX_BITS")
    declarations = cache[start:cache.index("#endif", start) + len("#endif")]
    signatures = [
        "static struct cache_file_tag_instance *cache_runtime_ui_tag_instance(\n",
        "static void cache_runtime_ui_tags_clear(\n",
        "static struct cache_file_tag_instance *cache_get_tag_instance(\n\tlong tag_index)\n{",
        "long cache_files_register_runtime_ui_tag(\n", "void scenario_tags_unload(\n",
        "long tag_loaded(\n", "void *tag_get(\n", "boolean tag_index_is_group(\n", "char *tag_get_name(\n"]
    production = declarations + "\n" + "\n".join(c_block(cache, s) for s in signatures)
    production = production.replace("cache_files_register_runtime_ui_tag(", "real_register_runtime_ui_tag(")
    cache_prefix = CACHE_PREFIX.replace("/* INSTANCE */", c_block(cache, "struct cache_file_tag_instance\n{") + ";")
    cache_prefix = cache_prefix.replace("/* PRODUCTION */", production)
    structures = []
    for source, names in [
        (tags, ["tag_block", "tag_reference", "tag_data"]),
        (strings, ["string_list", "string_list_entry"]),
        (ui, ["ui_widget_event_handler_reference", "ui_widget_child_reference", "ui_widget_conditional_reference",
              "ui_widget_game_data_input_reference", "ui_widget_search_and_replace_reference", "ui_widget_definition",
              "widget_animation_data", "widget_instance"])]:
        structures.extend(c_block(source, "struct " + name + "\n{") + ";" for name in names)
    tree = c_block(ui, "static struct widget_instance *widget_instance_find_by_tag_index_recursive(\n\tstruct widget_instance *widget,\n\tlong tag_index)\n{")
    tree += "\n" + c_block(ui, "int widget_instance_get_child_index_from_parent(\n")
    generic_help = c_block(data, "static void game_options_menu_update_text_desc(\n\tstruct widget_instance *widget)\n{")
    # These translation units name the same ABI fields differently.
    # The retail callback has a preserved no-focus bug; PB must guard that call.
    tree += '\n#pragma clang diagnostic push\n#pragma clang diagnostic ignored "-Wsometimes-uninitialized"\n'
    tree += generic_help.replace("definition->child_count", "definition->child_widgets.count").replace("selected_list_item_index", "selected_index")
    tree += "\n#pragma clang diagnostic pop\n"
    return cache_prefix + PREFIX.replace("/* STRUCTURES */", "\n".join(structures)).replace("/* TREE HELPERS */", tree) + HARNESS


class NativePerformanceEditorTests(unittest.TestCase):
    def test_native_editor(self):
        with tempfile.TemporaryDirectory(prefix="halo-native-pb-editor-") as temporary:
            folder = Path(temporary)
            (folder / "fixture.c").write_text(fixture_source())
            subprocess.run(["clang", "-std=c99", "-Wall", "-Wextra", "-Werror", "-Wno-multichar", "-Wno-format",
                            "-I", str(ROOT / "source"), str(folder / "fixture.c"), "-o", str(folder / "fixture")], check=True)
            result = subprocess.run([str(folder / "fixture")], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0,
                             f"Native editor fixture exited {result.returncode}.\n{result.stdout}{result.stderr}")
            self.assertEqual(result.stdout.strip(), "native PB editor tests passed")


if __name__ == "__main__":
    unittest.main()
