"""Exercise actual PB mouse targeting and dispatch with native widget fixtures."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.test_performance_ui import fixture_source
from tools.test_runtime_ui_tags import c_block

ROOT = Path(__file__).resolve().parents[1]

STUBS = r'''
#define FLAG(bit) (1UL<<(bit))
#define TEST_FLAG(value,bit) (((value)&FLAG(bit))!=0)
#define ABS(value) ((value)<0 ? -(value):(value))
#define MIN(a,b) ((a)<(b) ? (a):(b))
#define MAX(a,b) ((a)>(b) ? (a):(b))
#define csmemmove memmove
#define MAXIMUM_NUMBER_OF_LOCAL_PLAYERS 4
typedef struct {short x,y;} point2d;
struct event_record {int unused;};
enum {_gamepad_analog_button_a=0,_gamepad_analog_button_b,_gamepad_analog_button_x,
      _gamepad_analog_button_y,_gamepad_analog_button_black,_gamepad_analog_button_white,
      _gamepad_binary_button_dpad_up=8,_gamepad_binary_button_dpad_down,
      _gamepad_binary_button_dpad_left,_gamepad_binary_button_dpad_right,
      _gamepad_binary_button_start=12,_gamepad_binary_button_back=13,NUMBER_OF_GAMEPAD_BUTTONS=16,
      _ui_audio_feedback_cursor=1,_error_silent=0};
/* PRODUCTION ENUMS */
#include "halo_ui_pointer.h"
static struct {struct widget_instance *active_widgets[4]; int initialization_thread;} widget_globals;
static struct halo_ui_pointer input;
static short posted_button=NONE;
static unsigned posted_count;
static boolean game_settings_is_native_spinner(struct widget_instance *widget) {(void)widget; return FALSE;}
static boolean game_settings_is_adjustable(struct widget_instance *widget) {(void)widget; return FALSE;}
static boolean progress_bar_is_active(void) {return FALSE;}
static boolean virtual_keyboard_active(void) {return FALSE;}
int halo_ui_pointer_update(int active,struct halo_ui_pointer *pointer) {
    *pointer=input; memset(&input,0,sizeof(input)); return active;
}
static void event_manager_post_button(short controller,short button) {
    assert(controller==0); posted_button=button; posted_count++;
}
static void ui_play_audio_feedback_sound(short sound) {assert(sound==_ui_audio_feedback_cursor);}
static boolean widget_instance_can_handle_events(struct widget_instance *widget) {return !widget->disabled;}
static void error(short severity,const char *message,...) {(void)severity; (void)message; assert(0);}
/* PRODUCTION FOCUS */
static struct widget_instance *widget_instance_get_nth_child(struct widget_instance *widget,long index) {
    struct widget_instance *child=widget->child;
    while(child && index--) child=child->next;
    return child;
}
static void widget_instance_give_focus_by_tag(struct widget_instance *widget,long tag,short local) {
    (void)local;
    struct widget_instance *target=widget_instance_find_by_tag_index_recursive(widget,tag);
    assert(target); widget_instance_give_focus_directly(widget,target);
}
/* PRODUCTION LIST */
/* PRODUCTION MOUSE */
'''

CHECKS = r'''
/* Only the render traversal is modeled: each production mouse target receives
 * the same cumulative child-reference offset used by the actual renderer. */
static void draw_targets(struct widget_instance *widget,point2d offset) {
    struct ui_widget_definition *definition=ui_widget_definition_get(widget->definition_tag_index);
    offset.x+=widget->horizontal_offset; offset.y+=widget->vertical_offset;
    ui_mouse_note_target(widget,definition,offset);
    struct widget_instance *child=widget->child;
    struct ui_widget_child_reference *references=definition->child_widgets.address;
    for(long i=0;i<definition->child_widgets.count;i++,child=child->next) {
        assert(child); child->horizontal_offset=references[i].horizontal_offset;
        child->vertical_offset=references[i].vertical_offset;
        draw_targets(child,offset);
    }
}
static struct widget_instance *open_pb(void) {
    struct widget_instance *root=instantiate(pb_editor.entry_events[0].widget_tag.index,NULL);
    root->local_player_index=0; root->visible=TRUE;
    widget_globals.active_widgets[0]=root;
    struct widget_instance *menu=widget_instance_find_by_tag_index_recursive(root,pb_editor.menu_tag);
    assert(menu && performance_editor_event(menu,_pb_editor_initialize));
    ui_mouse_press_count=ui_mouse_target_count=0;
    ui_mouse_hover_pending=ui_mouse_click_pending=FALSE;
    return root;
}
static void close_pb(struct widget_instance *root) {widget_globals.active_widgets[0]=NULL; dispose(root);}
static void render_pb(struct widget_instance *root) {
    ui_mouse_target_count=0; ui_mouse_noting_targets=TRUE;
    draw_targets(root,(point2d){0,0}); ui_mouse_noting_targets=FALSE;
}
static short click_at(struct widget_instance *root,short x,short y) {
    render_pb(root); input=(struct halo_ui_pointer){.left_clicks=1,.click_x=x,.click_y=y};
    unsigned before=posted_count; posted_button=NONE; ui_widgets_process_mouse();
    assert(posted_count==before+1 && !ui_mouse_target_count);
    return posted_button;
}
static void arrow(struct widget_instance *root,short row,boolean right) {
    struct widget_instance *menu=widget_instance_find_by_tag_index_recursive(root,pb_editor.menu_tag);
    struct widget_instance *spinner=pb_editor_spinner(menu,row);
    struct ui_widget_definition *definition=ui_widget_definition_get(spinner->definition_tag_index);
    short x=(short)(54+300+(right ? 145:-3)),y=(short)(73+30*row+1+10);
    assert((right ? 145:-3)<definition->bounds.x0 || (right ? 145:-3)>=definition->bounds.x1);
    render_pb(root);
    struct ui_mouse_target *target=ui_mouse_target_at(x,y);
    assert(target && target->widget==spinner && target->kind==_ui_mouse_target_value);
    short selected=spinner->parameters.list.selected_index;
    short button=click_at(root,x,y);
    assert(button==(right ? _widget_event_dpad_right:_widget_event_dpad_left));
    assert(button!=_gamepad_analog_button_a && ui_mouse_widget_has_focus(spinner));
    assert(menu->parameters.list.selected_index==row);
    boolean deleted=FALSE;
    if(right) assert(widget_event_function_list_widget_goto_next_item(spinner,NULL,&deleted));
    else assert(widget_event_function_list_widget_goto_previous_item(spinner,NULL,&deleted));
    short count=spinner->parameters.list.number_of_items;
    assert(spinner->parameters.list.selected_index==(selected+(right ? 1:count-1))%count && !deleted);
    performance_editor_input(menu,32001);
}
static void fixture_setup(void) {
    setup();
    stock.defs[SCREEN_TAG].bounds=(rectangle2d){0,0,480,640};
    stock.defs[ROW_TAG].bounds=(rectangle2d){0,0,28,512};
    /* The owned ui.map uses external arrow rectangles. The shared fixture
     * leaves the header unspecified; supply it locally for mouse coverage. */
    stock.defs[SPINNER_TAG].list_header_bounds=(rectangle2d){7,-6,19,0};
    stock.defs[OTHER_TAG].bounds=(rectangle2d){414,520,440,544};
    stock_tags[OTHER_TAG].name="ui\\shell\\main_menu\\a_butn";
    snapshot=stock;
    assert(pb_editor_build());
}
static void all_arrow_rows_and_staging(void) {
    fixture_setup(); struct widget_instance *root=open_pb();
    for(short row=0;row<6;row++) {
        arrow(root,row,TRUE); assert(edited.flags==0 && mutation_calls==0);
        arrow(root,row,FALSE); assert(edited.flags==0 && mutation_calls==0);
    }
    arrow(root,4,TRUE); arrow(root,5,TRUE);
    assert(pb_editor.last_flags==24 && !edited.flags && !mutation_calls);
    input=(struct halo_ui_pointer){.right_clicks=1};
    unsigned before=posted_count; ui_widgets_process_mouse();
    assert(posted_count==before+1 && posted_button==_widget_event_b_button);
    close_pb(root); /* Standard B history return discards this staged menu. */
    root=open_pb();
    struct widget_instance *menu=widget_instance_find_by_tag_index_recursive(root,pb_editor.menu_tag);
    assert(!pb_editor_spinner(menu,4)->parameters.list.selected_index && !pb_editor_spinner(menu,5)->parameters.list.selected_index);
    assert(!edited.flags && !mutation_calls);
    arrow(root,4,TRUE); arrow(root,5,TRUE);
    assert(click_at(root,530,426)==_gamepad_analog_button_a);
    assert(pb_editor.menu_events[1].event_type==posted_button);
    assert(performance_editor_event(menu,pb_editor.menu_events[1].function));
    assert(edited.flags==24 && mutation_calls==1);
    close_pb(root);
    root=open_pb(); menu=widget_instance_find_by_tag_index_recursive(root,pb_editor.menu_tag);
    assert(pb_editor_spinner(menu,4)->parameters.list.selected_index==1 && pb_editor_spinner(menu,5)->parameters.list.selected_index==1);
    close_pb(root); assert(!memcmp(&snapshot,&stock,sizeof(stock)));
}
static void stock_fallback_and_disabled(void) {
    fixture_setup();
    struct widget_instance *root=instantiate(stock_id(SCREEN_TAG),NULL);
    root->local_player_index=0; widget_globals.active_widgets[0]=root;
    struct widget_instance *menu=widget_instance_find_by_tag_index_recursive(root,stock_id(MENU_TAG));
    struct widget_instance *spinner=widget_instance_find_by_tag_index_recursive(root,stock_id(SPINNER_TAG));
    assert(menu && spinner);
    render_pb(root);
    struct ui_mouse_target *target=ui_mouse_target_at(54+366-3,73+1+10);
    assert(target && target->kind==_ui_mouse_target_item && target->widget==spinner->parent);
    assert(click_at(root,54+366-3,73+1+10)==_gamepad_analog_button_a);
    /* Existing stock value halves still generate their ordinary d-pad input. */
    assert(click_at(root,54+366+45,73+1+10)==_widget_event_dpad_right);
    close_pb(root);
    root=open_pb(); menu=widget_instance_find_by_tag_index_recursive(root,pb_editor.menu_tag);
    spinner=pb_editor_spinner(menu,4); spinner->disabled=TRUE;
    render_pb(root); target=ui_mouse_target_at(54+300+145,73+30*4+1+10);
    assert(!target || target->widget!=spinner);
    close_pb(root);
}
int main(void) {
    all_arrow_rows_and_staging(); stock_fallback_and_disabled();
    puts("All PB arrow targets, mouse buttons, list adjustments and staging passed");
}
'''


class PerformanceMouse(unittest.TestCase):
    def test_production_mouse_arrow_dispatch(self):
        source = fixture_source().split("static void shapes_and_preservation(void)", 1)[0]
        ui = (ROOT / "source/interface/ui_widget.c").read_text()
        enums = []
        for member in ("_widget_pass_unhandled_events_to_children_bit =", "_list_items_generated_in_code", "_widget_event_b_button ="):
            start = ui.rfind("enum\n{", 0, ui.index(member))
            enums.append(c_block(ui[start:], "enum\n{") + ";")
        focus = "\n".join(c_block(ui, signature) for signature in (
            "struct widget_instance *widget_instance_get_topmost_parent(\n",
            "static boolean widget_instance_can_receive_events(\n\tstruct widget_instance *widget)\n{",
            "static void widget_instance_give_focus_directly(\n\tstruct widget_instance *widget,\n\tstruct widget_instance *new_focus)\n{",
        ))
        lists = "\n".join(c_block(ui, signature) for signature in (
            "boolean widget_event_function_list_widget_goto_next_item(\n",
            "boolean widget_event_function_list_widget_goto_previous_item(\n",
        ))
        mouse = ui[ui.index("#define UI_MOUSE_MAXIMUM_TARGETS"):ui.index("static void widget_instance_render_recursive(\n", ui.index("#define UI_MOUSE_MAXIMUM_TARGETS"))]
        source += STUBS.replace("/* PRODUCTION ENUMS */", "\n".join(enums)).replace("/* PRODUCTION FOCUS */", focus).replace("/* PRODUCTION LIST */", lists).replace("/* PRODUCTION MOUSE */", mouse) + CHECKS
        self.compile_platforms(source)

    def test_settings_mouse_arrows_and_wheel(self):
        from tools.test_game_settings import game_settings_fixture_source
        source = game_settings_fixture_source().split("int main(void)", 1)[0]
        ui = (ROOT / "source/interface/ui_widget.c").read_text()
        # Reuse the OS pointer/event boundary. Settings recognition and value
        # handlers come from the actual native page builder above.
        stubs = STUBS.split("/* PRODUCTION ENUMS */", 1)[1].split("/* PRODUCTION FOCUS */", 1)[0]
        stubs = stubs.replace("static struct {struct widget_instance *active_widgets[4]; int initialization_thread;} widget_globals;", "")
        for name in ("game_settings_is_native_spinner", "game_settings_is_adjustable", "ui_play_audio_feedback_sound"):
            stubs = stubs.replace(c_block(stubs, ("static void " if name.startswith("ui_play") else "static boolean ") + name + "("), "")
        source += """
#define ABS(value) ((value)<0 ? -(value):(value))
#define MIN(a,b) ((a)<(b) ? (a):(b))
#define MAX(a,b) ((a)>(b) ? (a):(b))
#define csmemmove memmove
typedef struct {short x,y;} point2d;
enum {_gamepad_analog_button_x=2,_gamepad_analog_button_y,_gamepad_analog_button_black,
      _gamepad_analog_button_white,_ui_audio_feedback_cursor=1,_error_silent=0};
""" + stubs
        source += "\n".join(c_block(ui, signature) for signature in (
            "struct widget_instance *widget_instance_get_topmost_parent(\n",
            "static boolean widget_instance_can_receive_events(\n\tstruct widget_instance *widget)\n{",
            "static void widget_instance_give_focus_directly(\n\tstruct widget_instance *widget,\n\tstruct widget_instance *new_focus)\n{",
        ))
        source += "\n" + ui[ui.index("#define UI_MOUSE_MAXIMUM_TARGETS"):ui.index("static void widget_instance_render_recursive(\n", ui.index("#define UI_MOUSE_MAXIMUM_TARGETS"))]
        source += "\n".join(c_block(CHECKS, signature) for signature in (
            "static void draw_targets(", "static void render_pb(", "static short click_at("))
        source += r'''
static void apply_posted_setting(struct widget_instance *spinner) {
    struct ui_widget_definition *definition=ui_widget_definition_get(spinner->definition_tag_index);
    struct ui_widget_event_handler_reference *handlers=definition->event_handlers.address;
    for(long i=0;i<definition->event_handlers.count;i++) if(handlers[i].event_type==posted_button) {
        assert(handlers[i].function==_device_settings_previous || handlers[i].function==_device_settings_next);
        assert(game_settings_event(spinner,handlers[i].function)); return;
    }
    assert(0);
}
int main(void) {
    settings_setup(0); assert(device_settings_build() && device_settings.native_pages);
    for(short page=_ds_audio;page<=_ds_timer;page++) {
        struct widget_instance *root=open_settings(_ds_main,page,0);
        root->visible=TRUE; widget_globals.active_widgets[0]=root;
        ui_mouse_press_count=ui_mouse_target_count=0;
        ui_mouse_hover_pending=ui_mouse_click_pending=FALSE;
        for(short row=0;row<device_settings_page_counts[page];row++) {
            short setting=device_settings_page_rows[page][row]; if(setting==NONE) continue;
            struct widget_instance *spinner=setting_control(root,setting);
            struct ui_widget_definition *definition=ui_widget_definition_get(spinner->definition_tag_index);
            assert(game_settings_is_native_spinner(spinner) && !definition->flags);
            for(short right=0;right<2;right++) {
                rectangle2d arrow=right ? definition->list_footer_bounds:definition->list_header_bounds;
                short local_x=(arrow.x0+arrow.x1)/2;
                assert(local_x<definition->bounds.x0 || local_x>=definition->bounds.x1);
                render_pb(root);
                short x=local_x,y=(arrow.y0+arrow.y1)/2;
                for(struct widget_instance *ancestor=spinner;ancestor;ancestor=ancestor->parent) {
                    x+=ancestor->horizontal_offset; y+=ancestor->vertical_offset;
                }
                struct ui_mouse_target *target=ui_mouse_target_at(x,y);
                assert(target && target->widget==spinner && target->kind==_ui_mouse_target_value);
                assert(click_at(root,x,y)==(right ? _widget_event_dpad_right:_widget_event_dpad_left));
                assert(ui_mouse_widget_has_focus(spinner) && ui_mouse_wheel_widget(root)==spinner);
                apply_posted_setting(spinner); assert(!writes);
                render_pb(root);
                input=(struct halo_ui_pointer){.wheel_steps=right ? -1:1};
                unsigned before=posted_count; ui_widgets_process_mouse();
                assert(posted_count==before+1 && posted_button==(right ? _widget_event_dpad_right:_widget_event_dpad_left));
                apply_posted_setting(spinner); assert(!writes);
            }
        }
        widget_globals.active_widgets[0]=NULL; dispose(root);
    }
    puts("Settings arrows and wheel use actual shared native widgets on every platform");
}
'''
        self.compile_platforms(source)

    def compile_platforms(self, source):
        with tempfile.TemporaryDirectory(prefix="halo-pb-mouse-") as folder:
            path = Path(folder) / "fixture.c"
            path.write_text(source)
            for platform in ("HALO_MACOS", "HALO_LINUX", "HALO_WINDOWS"):
                with self.subTest(platform=platform):
                    binary = Path(folder) / (platform + (".exe" if sys.platform == "win32" else ""))
                    compiled = subprocess.run(["clang", "-std=c99", "-Wall", "-Wextra", "-Werror", "-Wno-multichar",
                                               "-Wno-format", "-Wno-unused-function", "-Wno-unused-parameter", "-Wno-sign-compare",
                                               "-D_CRT_SECURE_NO_WARNINGS", f"-D{platform}=1", "-I", str(ROOT / "source"), "-I", str(ROOT / "port/linux"),
                                               "-iquote", str(ROOT / "port/linux/include"), str(path), "-o", str(binary)], text=True, capture_output=True)
                    self.assertEqual(compiled.returncode, 0, compiled.stderr)
                    result = subprocess.run([str(binary)], text=True, capture_output=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
