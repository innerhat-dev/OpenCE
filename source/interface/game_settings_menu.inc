/* Local Audio/Video preferences, staged until Accept. Main-menu pages clone
 * retail widgets; gameplay uses the smaller, resident pause-menu assets. */
#define DEVICE_SETTINGS_ENTRY "ui\\shell\\main_menu\\main_menu_item_settings"
#define DEVICE_PROFILE_PICKER "ui\\shell\\main_menu\\settings_select\\player_setup\\player_profile_select_screen"
#define DEVICE_OPTIONS_PREFIX "ui\\shell\\main_menu\\settings_select\\multiplayer_setup\\indicator_options_edit\\"
#define DEVICE_CHOOSER_PREFIX "ui\\shell\\main_menu\\multiplayer_type_select\\"
#define DEVICE_CONTROLS_PREFIX "ui\\shell\\main_menu\\settings_select\\player_setup\\player_profile_edit\\advanced_controls\\"
enum { _device_settings_initialize = 31990, _device_settings_accept,
    _device_settings_next, _device_settings_previous, _device_settings_enter_timer, _device_settings_cancel };
enum { _device_settings_chooser_preview = 31980, _device_settings_option_help };
enum { _ds_game, _ds_audio, _ds_video, _ds_timer, _ds_page_count };
enum { _ds_main, _ds_pause_1p, _ds_pause_2p, _ds_pause_4p, _ds_solo, _ds_coop, _ds_layout_count };
enum { _ds_settings_label, _ds_profile_label, _ds_game_label, _ds_audio_label,
    _ds_video_label, _ds_accept_label, _ds_back_help, _ds_audio_help,
    _ds_video_help, _ds_failure_help, _ds_partial_failure_help,
    _ds_timer_label, _ds_timer_help, _ds_timer_link_label, _ds_timer_link_help,
    _ds_select_key_label, _ds_accept_key_label, _ds_failure_brief, _ds_partial_failure_brief, _ds_row_label_start,
    _ds_help_start = _ds_row_label_start + NUMBER_OF_DEVICE_SETTINGS,
    _ds_value_start = _ds_help_start + NUMBER_OF_DEVICE_SETTINGS };
static short const device_settings_page_counts[_ds_page_count] = {2, 6, 5, 5};
static short const device_settings_page_rows[_ds_page_count][6] = {
    {NONE, NONE},
    {_device_setting_master_volume, _device_setting_music_volume, _device_setting_effects_volume,
     _device_setting_dialogue_volume, NONE, _device_setting_menu_music},
    {_device_setting_fullscreen, _device_setting_vsync, _device_setting_interpolation,
     _device_setting_timer_position, _device_setting_timer_scale},
    {_device_setting_timer_volume, _device_setting_timer_countdown, _device_setting_timer_beeps,
     _device_setting_timer_minutes, _device_setting_timer_items}};
static short const device_settings_page_titles[_ds_page_count] = {_ds_game_label, _ds_audio_label, _ds_video_label, _ds_timer_label};
static short const device_settings_page_help[_ds_page_count] = {_ds_back_help, _ds_audio_help, _ds_video_help, _ds_timer_help};
#define DEVICE_SETTINGS_STRING_COUNT (_ds_value_start + MAXIMUM_NUMBER_OF_LOCAL_PLAYERS * NUMBER_OF_DEVICE_SETTINGS)
static struct
{
    struct ui_widget_definition entry, settings_screen, settings_menu, settings_title;
    struct ui_widget_definition settings_preview, settings_picture, settings_description;
    struct ui_widget_definition settings_choice[2], screen[_ds_layout_count][_ds_page_count];
    struct ui_widget_definition column[_ds_layout_count][_ds_page_count], choice[_ds_layout_count][2];
    struct ui_widget_definition timer_link[_ds_layout_count];
    struct ui_widget_definition heading[_ds_page_count], footer[_ds_page_count], row[NUMBER_OF_DEVICE_SETTINGS], accept;
    struct ui_widget_child_reference settings_children[4], settings_menu_children[2], settings_preview_children[2];
    struct ui_widget_game_data_input_reference settings_menu_input;
    struct ui_widget_child_reference screen_children[_ds_layout_count][_ds_page_count][5];
    struct ui_widget_child_reference column_children[_ds_layout_count][_ds_page_count][7];
    struct ui_widget_event_handler_reference entry_events[2], settings_events[2][2];
    struct ui_widget_event_handler_reference choice_events[_ds_layout_count][2][2];
    struct ui_widget_event_handler_reference timer_events[_ds_layout_count][2];
    struct ui_widget_event_handler_reference root_events[3], accept_events[2], row_events[5];
    struct string_list strings;
    struct string_list descriptions;
    struct string_list_entry description_entries[2];
    struct string_list_entry string_entries[DEVICE_SETTINGS_STRING_COUNT];
    wchar_t text[DEVICE_SETTINGS_STRING_COUNT][128];
    long entry_tag, settings_tag, screen_tags[_ds_layout_count][_ds_page_count];
    long timer_tags[_ds_layout_count];
    char timer_names[_ds_layout_count][64];
    long row_tags[NUMBER_OF_DEVICE_SETTINGS], heading_tags[_ds_page_count], footer_tags[_ds_page_count], accept_tag;
    char screen_names[_ds_layout_count][_ds_page_count][64], column_names[_ds_layout_count][_ds_page_count][64];
    char choice_names[_ds_layout_count][2][64], row_names[NUMBER_OF_DEVICE_SETTINGS][64];
    boolean ready, native_pages;
} device_settings;
static struct
{
    struct ui_widget_definition row_labels[NUMBER_OF_DEVICE_SETTINGS], spinners[NUMBER_OF_DEVICE_SETTINGS];
    struct ui_widget_child_reference row_children[NUMBER_OF_DEVICE_SETTINGS][2];
    struct ui_widget_definition game_preview, game_picture[2], game_description;
    struct ui_widget_definition audio_key, audio_accept_label;
    struct ui_widget_child_reference audio_key_children[4];
    long audio_accept_tag, audio_key_tag;
    struct ui_widget_child_reference game_preview_children[3];
    struct ui_widget_game_data_input_reference game_input, option_input;
    struct ui_widget_event_handler_reference detail_events[5], spinner_events[4];
    struct string_list game_descriptions;
    struct string_list_entry game_description_entries[2];
    long game_menu_tag, spinner_tags[NUMBER_OF_DEVICE_SETTINGS];
    char label_names[NUMBER_OF_DEVICE_SETTINGS][64], value_names[NUMBER_OF_DEVICE_SETTINGS][64];
} device_settings_native;
static struct
{
    struct ui_widget_definition root[2], list[2], entry[2];
    struct ui_widget_child_reference root_children[2][5], list_children[2][5];
    struct ui_widget_event_handler_reference events[2][2];
    long tags[2];
    boolean ready;
} device_settings_campaign;
static char const *const device_settings_campaign_roots[2] = {
    "ui\\shell\\solo_game\\pause_game\\pause_game",
    "ui\\shell\\solo_game\\pause_game\\pause_game_split_screen"};
static struct device_settings_draft
{
    struct widget_instance *root;
    short page, layout;
    boolean audio_session, entering_timer, resume_audio;
    double timer_snapshot[NUMBER_OF_DEVICE_SETTINGS];
    double original[NUMBER_OF_DEVICE_SETTINGS], values[NUMBER_OF_DEVICE_SETTINGS];
} device_settings_drafts[MAXIMUM_NUMBER_OF_LOCAL_PLAYERS];

static struct tag_reference device_settings_reference(long group, long index)
{
    struct tag_reference reference = {0};
    reference.group_tag = group;
    reference.index = index;
    return reference;
}

static void device_settings_text(short index, char const *text)
{
    short i;
    for (i = 0; text[i] && i < 127; i++) device_settings.text[index][i] = (unsigned char)text[i];
    device_settings.text[index][i] = 0;
    device_settings.string_entries[index].string.address = device_settings.text[index];
    device_settings.string_entries[index].string.size = (i + 1) * sizeof(wchar_t);
}

static long device_settings_register(char const *name, struct ui_widget_definition *definition)
{
    return cache_files_register_runtime_ui_tag(UI_WIDGET_DEFINITION_TAG, name, definition);
}

static void device_settings_text_definition(struct ui_widget_definition *definition,
    struct ui_widget_definition const *style, long strings, short label, boolean interactive)
{
    performance_pause_clear_definition(definition);
    definition->type = _ui_widget_type_text_box;
    definition->controller_index = _widget_controller_any;
    definition->bounds = (rectangle2d){0, 0, 23, 284};
    definition->text_label_string_list = device_settings_reference(UNICODE_STRING_LIST_TAG, strings);
    definition->text_font = style->text_font;
    definition->text_color = style->text_color;
    definition->justification = _text_justification_center;
    definition->string_list_index = label;
    if (interactive) definition->background_bitmap = style->background_bitmap;
}

/* Pause buttons are authored for the resident 202 by 27 crop. Changing that
 * rectangle changes the bitmap's UVs, not merely the layout's available space. */
static void device_settings_pause_text_definition(struct ui_widget_definition *definition,
    struct ui_widget_definition const *style, long strings, short label, boolean interactive)
{
    device_settings_text_definition(definition, style, strings, label, interactive);
    definition->bounds = style->bounds;
    definition->horizontal_offset = style->horizontal_offset;
    definition->vertical_offset = style->vertical_offset;
}

static boolean device_settings_build_chooser(long strings, long profile_tag)
{
    static char const *const templates[] = {
        DEVICE_CHOOSER_PREFIX "multiplayer_type_select_screen",
        DEVICE_CHOOSER_PREFIX "multiplayer_type_select_list",
        DEVICE_CHOOSER_PREFIX "multiplayer_type_list_ext_desc",
        "ui\\shell\\main_menu\\settings_select\\player_setup\\player_profile_edit\\profile_edit_extended_desc_pic",
        DEVICE_CHOOSER_PREFIX "multiplayer_options_txt"};
    static char const *const choices[] = {"ui\\native_settings\\profile", "ui\\native_settings\\game"};
    static wchar_t descriptions[2][96] = {
        L"Choose a player profile to\r\nchange its name, controls\r\nand multiplayer color.",
        L"Adjust audio and video\r\nsettings for this Mac."};
    struct ui_widget_definition *base[NUMBEROF(templates)];
    long i, event, tag;
    for (i = 0; i < (long)NUMBEROF(templates); i++)
    {
        tag = tag_loaded(UI_WIDGET_DEFINITION_TAG, templates[i]);
        if (tag == NONE) return FALSE;
        base[i] = ui_widget_definition_get(tag);
    }
    if (base[0]->child_widgets.count != 4 || base[1]->child_widgets.count != 4 ||
        base[2]->child_widgets.count != 2) return FALSE;
    device_settings.settings_screen = *base[0];
    device_settings.settings_menu = *base[1];
    device_settings.settings_preview = *base[2];
    device_settings.settings_picture = *base[3];
    device_settings.settings_description = *base[4];
    csmemcpy(device_settings.settings_children, base[0]->child_widgets.address, sizeof(device_settings.settings_children));
    csmemcpy(device_settings.settings_menu_children, base[1]->child_widgets.address, sizeof(device_settings.settings_menu_children));
    csmemcpy(device_settings.settings_preview_children, base[2]->child_widgets.address, sizeof(device_settings.settings_preview_children));
    /* Retain the stock list artwork and layout without its multiplayer setup
     * callbacks, which would change the number of local players. */
    performance_pause_block(&device_settings.settings_screen.event_handlers, 2, &device_settings.root_events[1]);
    for (i = 0; i < 2; i++)
    {
        device_settings.settings_choice[i] = *ui_widget_definition_get(device_settings.settings_menu_children[i].widget_tag.index);
        device_settings.settings_choice[i].text_label_string_list = device_settings_reference(UNICODE_STRING_LIST_TAG, strings);
        device_settings.settings_choice[i].string_list_index = (short)(_ds_profile_label + i);
        for (event = 0; event < 2; event++)
            performance_pause_event_definition(&device_settings.settings_events[i][event], event ? _gamepad_binary_button_start : _gamepad_analog_button_a,
                0, FLAG(_event_handler_open_widget_bit), i ? device_settings.screen_tags[_ds_main][_ds_game] : profile_tag);
        performance_pause_block(&device_settings.settings_choice[i].event_handlers, 2, device_settings.settings_events[i]);
        tag = device_settings_register(choices[i], &device_settings.settings_choice[i]);
        if (tag == NONE) return FALSE;
        device_settings.settings_menu_children[i].widget_tag.index = tag;
        device_settings.description_entries[i].string.address = descriptions[i];
        device_settings.description_entries[i].string.size = (ustrlen(descriptions[i]) + 1) * sizeof(wchar_t);
    }
    performance_pause_block(&device_settings.descriptions.strings, 2, device_settings.description_entries);
    tag = cache_files_register_runtime_ui_tag(UNICODE_STRING_LIST_TAG, "ui\\native_settings\\descriptions", &device_settings.descriptions);
    if (tag == NONE) return FALSE;
    device_settings.settings_description.text_label_string_list = device_settings_reference(UNICODE_STRING_LIST_TAG, tag);
    tag = device_settings_register("ui\\native_settings\\preview_text", &device_settings.settings_description);
    if (tag == NONE) return FALSE;
    device_settings.settings_preview_children[1].widget_tag.index = tag;
    tag = device_settings_register("ui\\native_settings\\preview_pic", &device_settings.settings_picture);
    if (tag == NONE) return FALSE;
    device_settings.settings_preview_children[0].widget_tag.index = tag;
    performance_pause_block(&device_settings.settings_preview.child_widgets, 2, device_settings.settings_preview_children);
    tag = device_settings_register("ui\\native_settings\\preview", &device_settings.settings_preview);
    if (tag == NONE) return FALSE;
    device_settings.settings_menu.extended_description_widget = device_settings_reference(UI_WIDGET_DEFINITION_TAG, tag);
    csmemset(&device_settings.settings_menu_input, 0, sizeof(device_settings.settings_menu_input));
    device_settings.settings_menu_input.function = 1; /* Native settings picture/text focus handler. */
    performance_pause_block(&device_settings.settings_menu.game_data_inputs, 1, &device_settings.settings_menu_input);
    performance_pause_block(&device_settings.settings_menu.child_widgets, 2, device_settings.settings_menu_children);
    tag = device_settings_register("ui\\native_settings\\menu", &device_settings.settings_menu);
    if (tag == NONE) return FALSE;
    device_settings.settings_children[1].widget_tag.index = tag;
    device_settings_text_definition(&device_settings.settings_title, &device_settings.settings_choice[0], strings, _ds_settings_label, FALSE);
    device_settings.settings_title.bounds = (rectangle2d){30, 64, 62, 595};
    device_settings.settings_title.justification = _text_justification_left;
    device_settings.settings_title.text_color = (real_argb_color){1, 1, 1, 1};
    tag = device_settings_register("ui\\native_settings\\title", &device_settings.settings_title);
    if (tag == NONE) return FALSE;
    device_settings.settings_children[0].widget_tag.index = tag;
    /* The stock separator follows three multiplayer rows; put it beneath two. */
    device_settings.settings_children[3].vertical_offset -= 33;
    performance_pause_block(&device_settings.settings_screen.child_widgets, 4, device_settings.settings_children);
    device_settings.settings_tag = device_settings_register("ui\\native_settings\\settings", &device_settings.settings_screen);
    return device_settings.settings_tag != NONE;
}

/* Reuse the stock chooser and Advanced Controls editor. A zero-child spinner
 * renders its selected dynamic string directly, keeping exact configured values
 * and avoiding a separate widget allocation for each possible volume step. */
static boolean device_settings_build_native_pages(long strings, long const *heading_tags, long const *column_tags)
{
    static char const *const templates[] = {
        DEVICE_CONTROLS_PREFIX "advanced_controls_screen",
        DEVICE_CONTROLS_PREFIX "advanced_controls_menu",
        DEVICE_CONTROLS_PREFIX "advanced_controls_help",
        DEVICE_CONTROLS_PREFIX "op_controller_sensitivity",
        DEVICE_CONTROLS_PREFIX "controller_sensitivity_label",
        DEVICE_CONTROLS_PREFIX "controller_sensitivity_spinner",
        DEVICE_CHOOSER_PREFIX "multiplayer_options_pic"};
    static wchar_t descriptions[2][96] = {
        L"Adjust music, sound effects,\r\ndialogue and overall volume.",
        L"Choose fullscreen, VSync\r\nand smooth motion settings."};
    struct ui_widget_definition *base[NUMBEROF(templates)];
    long i, tag, page, row;
    for (i = 0; i < (long)NUMBEROF(templates); i++)
    {
        tag = tag_loaded(UI_WIDGET_DEFINITION_TAG, templates[i]);
        if (tag == NONE) return FALSE;
        base[i] = ui_widget_definition_get(tag);
    }
    if (base[0]->child_widgets.count != 3 || base[1]->child_widgets.count != 5 ||
        base[3]->child_widgets.count != 2 || base[5]->type != _ui_widget_type_spinner_list) return FALSE;
    device_settings.screen[_ds_main][_ds_game] = device_settings.settings_screen;
    device_settings.column[_ds_main][_ds_game] = device_settings.settings_menu;
    device_settings.heading[_ds_game] = device_settings.settings_title;
    device_settings.heading[_ds_game].string_list_index = _ds_game_label;
    csmemcpy(device_settings.screen_children[_ds_main][_ds_game], device_settings.settings_children,
        sizeof(device_settings.settings_children));
    device_settings.screen_children[_ds_main][_ds_game][0].widget_tag.index = heading_tags[_ds_game];
    device_settings.screen_children[_ds_main][_ds_game][1].widget_tag.index = column_tags[_ds_game];
    performance_pause_block(&device_settings.screen[_ds_main][_ds_game].child_widgets, 4,
        device_settings.screen_children[_ds_main][_ds_game]);
    for (i = 0; i < 2; i++)
    {
        tag = tag_loaded(UI_WIDGET_DEFINITION_TAG, device_settings.choice_names[_ds_main][i]);
        if (tag == NONE) return FALSE;
        device_settings.choice[_ds_main][i] = device_settings.settings_choice[i];
        device_settings.choice[_ds_main][i].string_list_index = (short)(_ds_audio_label + i);
        performance_pause_block(&device_settings.choice[_ds_main][i].event_handlers, 2, device_settings.choice_events[_ds_main][i]);
        device_settings.column_children[_ds_main][_ds_game][i] = device_settings.settings_menu_children[i];
        device_settings.column_children[_ds_main][_ds_game][i].widget_tag.index = tag;
        device_settings_native.game_description_entries[i].string.address = descriptions[i];
        device_settings_native.game_description_entries[i].string.size = (ustrlen(descriptions[i]) + 1) * sizeof(wchar_t);
    }
    performance_pause_block(&device_settings_native.game_descriptions.strings, 2, device_settings_native.game_description_entries);
    tag = cache_files_register_runtime_ui_tag(UNICODE_STRING_LIST_TAG, "ui\\native_settings\\game_descriptions", &device_settings_native.game_descriptions);
    if (tag == NONE) return FALSE;
    device_settings_native.game_description = device_settings.settings_description;
    device_settings_native.game_description.text_label_string_list = device_settings_reference(UNICODE_STRING_LIST_TAG, tag);
    device_settings_native.game_preview_children[2] = device_settings.settings_preview_children[1];
    tag = device_settings_register("ui\\native_settings\\game_preview_text", &device_settings_native.game_description);
    if (tag == NONE) return FALSE;
    device_settings_native.game_preview_children[2].widget_tag.index = tag;
    device_settings_native.game_picture[0] = device_settings.settings_picture;
    device_settings_native.game_picture[1] = *base[6];
    for (i = 0; i < 2; i++)
    {
        tag = device_settings_register(i ? "ui\\native_settings\\video_picture" : "ui\\native_settings\\audio_picture",
            &device_settings_native.game_picture[i]);
        if (tag == NONE) return FALSE;
        device_settings_native.game_preview_children[i] = device_settings.settings_preview_children[0];
        device_settings_native.game_preview_children[i].widget_tag.index = tag;
    }
    device_settings_native.game_preview = device_settings.settings_preview;
    performance_pause_block(&device_settings_native.game_preview.child_widgets, 3, device_settings_native.game_preview_children);
    tag = device_settings_register("ui\\native_settings\\game_preview", &device_settings_native.game_preview);
    if (tag == NONE) return FALSE;
    device_settings.column[_ds_main][_ds_game].extended_description_widget = device_settings_reference(UI_WIDGET_DEFINITION_TAG, tag);
    device_settings_native.game_input.function = _device_settings_chooser_preview;
    device_settings_native.game_menu_tag = column_tags[_ds_game];
    performance_pause_block(&device_settings.column[_ds_main][_ds_game].game_data_inputs, 1, &device_settings_native.game_input);
    performance_pause_block(&device_settings.column[_ds_main][_ds_game].child_widgets, 2,
        device_settings.column_children[_ds_main][_ds_game]);
    csmemcpy(device_settings_native.detail_events, device_settings.root_events, sizeof(device_settings.root_events));
    csmemcpy(&device_settings_native.detail_events[3], device_settings.accept_events, sizeof(device_settings.accept_events));
    for (i = 0; i < 4; i++) device_settings_native.spinner_events[i] = device_settings.row_events[i < 2 ? i : i + 1];
    for (row = 0; row < NUMBER_OF_DEVICE_SETTINGS; row++)
    {
        device_settings.row[row] = *base[3];
        device_settings_native.row_labels[row] = *base[4];
        device_settings_native.spinners[row] = *base[5];
        csmemcpy(device_settings_native.row_children[row], base[3]->child_widgets.address,
            sizeof(device_settings_native.row_children[row]));
        device_settings_native.row_labels[row].text_label_string_list = device_settings_reference(UNICODE_STRING_LIST_TAG, strings);
        device_settings_native.row_labels[row].string_list_index = (short)(_ds_row_label_start + row);
        snprintf(device_settings_native.label_names[row], sizeof(device_settings_native.label_names[row]), "ui\\native_settings\\label_%ld", row);
        tag = device_settings_register(device_settings_native.label_names[row], &device_settings_native.row_labels[row]);
        if (tag == NONE) return FALSE;
        device_settings_native.row_children[row][0].widget_tag.index = tag;
        /* Built-in left/right navigation assumes child items. Custom handlers
         * own these value-only spinners, including the arrow animation. */
        device_settings_native.spinners[row].flags = 0;
        device_settings_native.spinners[row].list_flags = 0;
        device_settings_native.spinners[row].text_label_string_list = device_settings_reference(UNICODE_STRING_LIST_TAG, strings);
        device_settings_native.spinners[row].bounds.x1 = row == _device_setting_timer_position ? 136 : 112;
        device_settings_native.spinners[row].list_footer_bounds.x0 = device_settings_native.spinners[row].bounds.x1;
        device_settings_native.spinners[row].list_footer_bounds.x1 = device_settings_native.spinners[row].bounds.x1 + 6;
        performance_pause_block(&device_settings_native.spinners[row].event_handlers, 4, device_settings_native.spinner_events);
        performance_pause_block(&device_settings_native.spinners[row].game_data_inputs, 0, NULL);
        performance_pause_block(&device_settings_native.spinners[row].child_widgets, 0, NULL);
        snprintf(device_settings_native.value_names[row], sizeof(device_settings_native.value_names[row]), "ui\\native_settings\\value_%ld", row);
        tag = device_settings_register(device_settings_native.value_names[row], &device_settings_native.spinners[row]);
        if (tag == NONE) return FALSE;
        device_settings_native.spinner_tags[row] = tag;
        device_settings_native.row_children[row][1].widget_tag.index = tag;
        device_settings_native.row_children[row][1].horizontal_offset = 366;
        performance_pause_block(&device_settings.row[row].child_widgets, 2, device_settings_native.row_children[row]);
    }
    device_settings.timer_link[_ds_main] = *base[4];
    device_settings.timer_link[_ds_main].bounds = base[3]->bounds;
    device_settings.timer_link[_ds_main].background_bitmap = base[3]->background_bitmap;
    device_settings.timer_link[_ds_main].text_label_string_list = device_settings_reference(UNICODE_STRING_LIST_TAG, strings);
    device_settings.timer_link[_ds_main].string_list_index = _ds_timer_link_label;
    performance_pause_block(&device_settings.timer_link[_ds_main].event_handlers, 2, device_settings.timer_events[_ds_main]);
    {
        struct ui_widget_child_reference *children = base[0]->child_widgets.address;
        struct ui_widget_definition *key = ui_widget_definition_get(children[2].widget_tag.index);
        if (key->child_widgets.count != 4) return FALSE;
        device_settings_native.audio_key = *key;
        csmemcpy(device_settings_native.audio_key_children, key->child_widgets.address,
            sizeof(device_settings_native.audio_key_children));
        device_settings_native.audio_accept_label = *ui_widget_definition_get(device_settings_native.audio_key_children[3].widget_tag.index);
        device_settings_native.audio_accept_label.text_label_string_list = device_settings_reference(UNICODE_STRING_LIST_TAG, strings);
        device_settings_native.audio_accept_label.string_list_index = _ds_accept_key_label;
        device_settings_native.audio_accept_tag = device_settings_register("ui\\native_settings\\audio_accept_label", &device_settings_native.audio_accept_label);
        if (device_settings_native.audio_accept_tag == NONE) return FALSE;
        device_settings_native.audio_key_children[3].widget_tag.index = device_settings_native.audio_accept_tag;
        performance_pause_block(&device_settings_native.audio_key.child_widgets, 4, device_settings_native.audio_key_children);
        device_settings_native.audio_key_tag = device_settings_register("ui\\native_settings\\audio_key", &device_settings_native.audio_key);
        if (device_settings_native.audio_key_tag == NONE) return FALSE;
    }
    device_settings_native.option_input.function = _device_settings_option_help;
    for (page = _ds_audio; page < _ds_page_count; page++)
    {
        short count = device_settings_page_counts[page];
        short first = device_settings_page_rows[page][0];
        device_settings.screen[_ds_main][page] = *base[0];
        device_settings.column[_ds_main][page] = *base[1];
        device_settings.heading[page] = device_settings.settings_title;
        device_settings.heading[page].string_list_index = device_settings_page_titles[page];
        device_settings.heading[page].bounds = (rectangle2d){30, 67, 62, 566};
        device_settings.footer[page] = *base[2];
        device_settings.footer[page].text_label_string_list = device_settings_reference(UNICODE_STRING_LIST_TAG, strings);
        device_settings.footer[page].string_list_index = (short)(_ds_help_start + first);
        csmemcpy(device_settings.screen_children[_ds_main][page], base[0]->child_widgets.address,
            3 * sizeof(struct ui_widget_child_reference));
        if (page == _ds_audio) device_settings.screen_children[_ds_main][page][2].widget_tag.index = device_settings_native.audio_key_tag;
        device_settings.screen_children[_ds_main][page][0].widget_tag.index = column_tags[page];
        device_settings.screen_children[_ds_main][page][1].widget_tag.index = heading_tags[page];
        performance_pause_child(&device_settings.screen_children[_ds_main][page][3], device_settings.footer_tags[page], 0, 0);
        performance_pause_block(&device_settings.screen[_ds_main][page].child_widgets, 4, device_settings.screen_children[_ds_main][page]);
        performance_pause_block(&device_settings.screen[_ds_main][page].event_handlers, 5, device_settings_native.detail_events);
        /* Keep the original help position as a root child so save failures
         * remain addressable independently of the currently focused row. */
        device_settings.column[_ds_main][page].extended_description_widget.index = NONE;
        performance_pause_block(&device_settings.column[_ds_main][page].event_handlers, 0, NULL);
        performance_pause_block(&device_settings.column[_ds_main][page].game_data_inputs, 1, &device_settings_native.option_input);
        for (row = 0; row < count; row++)
            performance_pause_child(&device_settings.column_children[_ds_main][page][row], device_settings_page_rows[page][row] == NONE ? device_settings.timer_tags[_ds_main] :
                device_settings.row_tags[device_settings_page_rows[page][row]], 54, (short)(73 + row * 30));
        performance_pause_block(&device_settings.column[_ds_main][page].child_widgets, count, device_settings.column_children[_ds_main][page]);
    }
    device_settings.native_pages = TRUE;
    return TRUE;
}

static boolean device_settings_build(void)
{
    static char const *const captions[] = {
        "SETTINGS", "PROFILE SETTINGS", "GAME SETTINGS", "AUDIO", "VIDEO", "ACCEPT",
        "A: Select    B: Back", "Effects includes announcer.\r\nLeft/Right: Adjust    B: Cancel",
        "Left/Right: Adjust\r\nAccept saves. B: Cancel",
        "Could not apply settings.\r\nYour changes remain here.",
        "Could not restore all settings.\r\nReview values and try again.",
        "TIMER AUDIO", "Host Timer Sounds must be on.\r\nAccept keeps changes. B: Cancel",
        "TIMER AUDIO...", "Choose timer volume and cues.\r\nHost Timer Sounds must be on.",
        "=SELECT", "=ACCEPT", "COULD NOT SAVE", "REVIEW SETTINGS"};
    static char const *const row_labels[] = {
        "MASTER VOLUME:", "MUSIC VOLUME:", "EFFECTS VOLUME:", "DIALOGUE VOLUME:", "TIMER VOLUME:",
        "MENU MUSIC:", "FULLSCREEN:", "VSYNC:", "SMOOTH MOTION:",
        "COUNTDOWN:", "BEEPS:", "MINUTE ANNOUNCEMENTS:", "ITEM CUES:", "TIMER POSITION:", "TIMER SIZE:"};
    static char const *const help[] = {
        "Adjust the volume of all game audio.",
        "Adjust the volume of music.",
        "Adjust sound effects, ambience and\r\nmultiplayer announcer volume.",
        "Adjust spoken dialogue volume.",
        "Adjust PB timer announcements volume.\r\nHost Timer Sounds must be on.\r\nAudio Accept saves all changes.",
        "Turn main-menu music on or off.",
        "Switch between fullscreen and\r\nwindowed play.",
        "Sync presentation with the display\r\nto reduce screen tearing.",
        "Smooth motion between game updates.\r\nOriginal game timing stays the same.",
        "Play timer countdown announcements.\r\nHost Timer Sounds must be on.",
        "Play timer countdown beeps.\r\nHost Timer Sounds must be on.",
        "Announce elapsed minutes.\r\nHost Timer Sounds must be on.",
        "Play scheduled rocket and powerup cues\r\nwhen supported by this map.\r\nHost Timer Sounds must be on.",
        "Choose where the PB timer appears.\r\nThe host must enable the timer.",
        "Adjust PB timer size from 50% to 100%.\r\nThe host must enable the timer."};
    static char const *const heading_names[] = {"ui\\native_settings\\game_title", "ui\\native_settings\\audio_title", "ui\\native_settings\\video_title", "ui\\native_settings\\timer_title"};
    static char const *const footer_names[] = {"ui\\native_settings\\game_help", "ui\\native_settings\\audio_help", "ui\\native_settings\\video_help", "ui\\native_settings\\timer_help"};
    struct ui_widget_definition *bases[_ds_layout_count] = {0};
    struct ui_widget_definition *style;
    long tag, strings, font, layout, page, row, i, profile_tag = NONE;
    long *heading_tags = device_settings.heading_tags;
    long column_tags[_ds_layout_count][_ds_page_count];
    long choice_tags[_ds_layout_count][2];
    void (*text_definition)(struct ui_widget_definition *, struct ui_widget_definition const *, long, short, boolean);
    boolean main_menu;
    device_settings.ready = FALSE;
    device_settings.native_pages = FALSE;
    device_settings_native.game_menu_tag = NONE;
    for (row = 0; row < NUMBER_OF_DEVICE_SETTINGS; row++) device_settings_native.spinner_tags[row] = NONE;
    for (layout = 0; layout < _ds_layout_count; layout++)
        for (page = 0; page < _ds_page_count; page++) device_settings.screen_tags[layout][page] = NONE;
    font = tag_loaded(FONT_GROUP_TAG, "ui\\small_ui");
    tag = tag_loaded(UI_WIDGET_DEFINITION_TAG, DEVICE_OPTIONS_PREFIX "indicator_options_screen");
    main_menu = tag != NONE;
    if (font == NONE) return FALSE;
    if (main_menu)
    {
        bases[_ds_main] = ui_widget_definition_get(tag);
        tag = tag_loaded(UI_WIDGET_DEFINITION_TAG, DEVICE_OPTIONS_PREFIX "indicator_options_players_on_radar_label");
        profile_tag = tag_loaded(UI_WIDGET_DEFINITION_TAG, DEVICE_PROFILE_PICKER);
        if (tag == NONE || profile_tag == NONE) return FALSE;
        style = ui_widget_definition_get(tag);
    }
    else
    {
        boolean multiplayer = tag_loaded(UI_WIDGET_DEFINITION_TAG, performance_pause_original_names[0]) != NONE;
        for (layout = multiplayer ? _ds_pause_1p : _ds_solo; layout < (multiplayer ? _ds_solo : _ds_layout_count); layout++)
        {
            tag = tag_loaded(UI_WIDGET_DEFINITION_TAG, multiplayer ? performance_pause_original_names[layout - 1] : device_settings_campaign_roots[layout - _ds_solo]);
            if (tag == NONE) return FALSE;
            bases[layout] = ui_widget_definition_get(tag);
        }
        tag = tag_loaded(UI_WIDGET_DEFINITION_TAG, multiplayer ? "ui\\shell\\multiplayer_game\\pause_game\\resume_game_button" : "ui\\shell\\solo_game\\pause_game\\resume_game_button");
        if (tag == NONE) return FALSE;
        style = ui_widget_definition_get(tag);
    }
    text_definition = main_menu ? device_settings_text_definition : device_settings_pause_text_definition;
    csmemset(device_settings_drafts, 0, sizeof(device_settings_drafts));
    for (i = 0; i < DEVICE_SETTINGS_STRING_COUNT; i++) device_settings_text((short)i, i < (long)NUMBEROF(captions) ? captions[i] : "");
    for (i = 0; i < NUMBER_OF_DEVICE_SETTINGS; i++)
    {
        device_settings_text((short)(_ds_row_label_start + i), row_labels[i]);
        device_settings_text((short)(_ds_help_start + i), help[i]);
    }
    performance_pause_block(&device_settings.strings.strings, DEVICE_SETTINGS_STRING_COUNT, device_settings.string_entries);
    strings = cache_files_register_runtime_ui_tag(UNICODE_STRING_LIST_TAG, "ui\\native_settings\\strings", &device_settings.strings);
    if (strings == NONE) return FALSE;
    for (page = 0; page < _ds_page_count; page++)
    {
        text_definition(&device_settings.heading[page], style, strings, device_settings_page_titles[page], FALSE);
        if (main_menu) device_settings.heading[page].text_font.index = font;
        else
        {
            device_settings.heading[page].bounds.y1 = 22;
            device_settings.heading[page].vertical_offset = 0;
        }
        device_settings.heading[page].text_color = (real_argb_color){1, 1, 1, 1};
        heading_tags[page] = device_settings_register(heading_names[page], &device_settings.heading[page]);
        device_settings_text_definition(&device_settings.footer[page], style, strings, device_settings_page_help[page], FALSE);
        device_settings.footer[page].text_font.index = font;
        device_settings.footer[page].bounds.y1 = main_menu ? 40 : 60;
        device_settings.footer_tags[page] = device_settings_register(footer_names[page], &device_settings.footer[page]);
        if (heading_tags[page] == NONE || device_settings.footer_tags[page] == NONE) return FALSE;
    }
    performance_pause_event_definition(&device_settings.root_events[0], _widget_event_created,
        _device_settings_initialize, FLAG(_event_handler_run_function_bit), NONE);
    performance_pause_event_definition(&device_settings.root_events[1], _widget_event_b_button,
        _device_settings_cancel, FLAG(_event_handler_run_function_bit) | FLAG(_event_handler_go_back_to_previous_widget_bit), NONE);
    performance_pause_event_definition(&device_settings.root_events[2], _widget_event_back_button,
        _device_settings_cancel, FLAG(_event_handler_run_function_bit) | FLAG(_event_handler_go_back_to_previous_widget_bit), NONE);
    performance_pause_event_definition(&device_settings.accept_events[0], _gamepad_analog_button_a,
        _device_settings_accept, FLAG(_event_handler_run_function_bit) | FLAG(_event_handler_go_back_to_previous_widget_bit), NONE);
    performance_pause_event_definition(&device_settings.accept_events[1], _gamepad_binary_button_start,
        _device_settings_accept, FLAG(_event_handler_run_function_bit) | FLAG(_event_handler_go_back_to_previous_widget_bit), NONE);
    performance_pause_event_definition(&device_settings.row_events[0], _widget_event_dpad_left,
        _device_settings_previous, FLAG(_event_handler_run_function_bit), NONE);
    performance_pause_event_definition(&device_settings.row_events[1], _widget_event_dpad_right,
        _device_settings_next, FLAG(_event_handler_run_function_bit), NONE);
    performance_pause_event_definition(&device_settings.row_events[2], _gamepad_analog_button_a,
        _device_settings_next, FLAG(_event_handler_run_function_bit), NONE);
    performance_pause_event_definition(&device_settings.row_events[3], _widget_event_left_stick_left,
        _device_settings_previous, FLAG(_event_handler_run_function_bit), NONE);
    performance_pause_event_definition(&device_settings.row_events[4], _widget_event_left_stick_right,
        _device_settings_next, FLAG(_event_handler_run_function_bit), NONE);
    device_settings_native.option_input.function = _device_settings_option_help;
    for (row = 0; row < NUMBER_OF_DEVICE_SETTINGS; row++)
    {
        text_definition(&device_settings.row[row], style, strings, (short)(_ds_value_start + row), TRUE);
        if (main_menu || row == _device_setting_interpolation || row == _device_setting_timer_position)
            device_settings.row[row].text_font.index = font;
        performance_pause_block(&device_settings.row[row].event_handlers, NUMBEROF(device_settings.row_events), device_settings.row_events);
        snprintf(device_settings.row_names[row], sizeof(device_settings.row_names[row]), "ui\\native_settings\\row_%ld", row);
        device_settings.row_tags[row] = device_settings_register(device_settings.row_names[row], &device_settings.row[row]);
        if (device_settings.row_tags[row] == NONE) return FALSE;
    }
    text_definition(&device_settings.accept, style, strings, _ds_accept_label, TRUE);
    if (main_menu) device_settings.accept.text_font.index = font;
    performance_pause_block(&device_settings.accept.event_handlers, 2, device_settings.accept_events);
    device_settings.accept_tag = device_settings_register("ui\\native_settings\\accept", &device_settings.accept);
    if (device_settings.accept_tag == NONE) return FALSE;
    /* Register every root before wiring the Audio/Video links. */
    for (layout = 0; layout < _ds_layout_count; layout++)
    {
        if (!bases[layout]) continue;
        for (page = 0; page < _ds_page_count; page++)
        {
            snprintf(device_settings.screen_names[layout][page], sizeof(device_settings.screen_names[layout][page]), "ui\\native_settings\\screen_%ld_%ld", layout, page);
            device_settings.screen_tags[layout][page] = device_settings_register(device_settings.screen_names[layout][page], &device_settings.screen[layout][page]);
            snprintf(device_settings.column_names[layout][page], sizeof(device_settings.column_names[layout][page]), "ui\\native_settings\\column_%ld_%ld", layout, page);
            column_tags[layout][page] = device_settings_register(device_settings.column_names[layout][page], &device_settings.column[layout][page]);
            if (device_settings.screen_tags[layout][page] == NONE || column_tags[layout][page] == NONE) return FALSE;
        }
        text_definition(&device_settings.timer_link[layout], style, strings, _ds_timer_link_label, TRUE);
        if (main_menu) device_settings.timer_link[layout].text_font.index = font;
        for (i = 0; i < 2; i++)
            performance_pause_event_definition(&device_settings.timer_events[layout][i], i ? _gamepad_binary_button_start : _gamepad_analog_button_a,
                _device_settings_enter_timer, FLAG(_event_handler_run_function_bit) | FLAG(_event_handler_open_widget_bit),
                device_settings.screen_tags[layout][_ds_timer]);
        performance_pause_block(&device_settings.timer_link[layout].event_handlers, 2, device_settings.timer_events[layout]);
        snprintf(device_settings.timer_names[layout], sizeof(device_settings.timer_names[layout]), "ui\\native_settings\\timer_link_%ld", layout);
        device_settings.timer_tags[layout] = device_settings_register(device_settings.timer_names[layout], &device_settings.timer_link[layout]);
        if (device_settings.timer_tags[layout] == NONE) return FALSE;
        for (i = 0; i < 2; i++)
        {
            text_definition(&device_settings.choice[layout][i], style, strings, (short)(_ds_audio_label + i), TRUE);
            if (main_menu) device_settings.choice[layout][i].text_font.index = font;
            for (row = 0; row < 2; row++)
                performance_pause_event_definition(&device_settings.choice_events[layout][i][row], row ? _gamepad_binary_button_start : _gamepad_analog_button_a,
                    0, FLAG(_event_handler_open_widget_bit), device_settings.screen_tags[layout][i + 1]);
            performance_pause_block(&device_settings.choice[layout][i].event_handlers, 2, device_settings.choice_events[layout][i]);
            snprintf(device_settings.choice_names[layout][i], sizeof(device_settings.choice_names[layout][i]), "ui\\native_settings\\choice_%ld_%ld", layout, i);
            choice_tags[layout][i] = device_settings_register(device_settings.choice_names[layout][i], &device_settings.choice[layout][i]);
            if (choice_tags[layout][i] == NONE) return FALSE;
        }
        for (page = 0; page < _ds_page_count; page++)
        {
            struct ui_widget_definition *root = &device_settings.screen[layout][page];
            struct ui_widget_definition *column = &device_settings.column[layout][page];
            short count = device_settings_page_counts[page];
            short rows = count + (page != _ds_game);
            short pitch = main_menu ? 24 : 27;
            short width = main_menu ? 284 : 202;
            short height = main_menu ? 28 + rows * pitch + 40 : page == _ds_game ? 159 : 27 + rows * pitch + 24;
            short x = (bases[layout]->bounds.x1 - bases[layout]->bounds.x0 - width) / 2;
            short y = (bases[layout]->bounds.y1 - bases[layout]->bounds.y0 - height) / 2;
            short column_y = main_menu ? 28 : 22;
            if (!main_menu && page == _ds_game)
                column_y += (height - 29 - column_y - rows * pitch) / 2;
            performance_pause_clear_definition(root);
            root->type = _ui_widget_type_container;
            root->controller_index = _widget_controller_any;
            root->bounds = bases[layout]->bounds;
            root->background_bitmap = bases[layout]->background_bitmap;
            root->flags = FLAG(_widget_pass_unhandled_events_to_children_bit) |
                (bases[layout]->flags & FLAG(_widget_pause_game_time_bit));
            performance_pause_block(&root->event_handlers, 3, device_settings.root_events);
            performance_pause_clear_definition(column);
            column->type = _ui_widget_type_column_list;
            column->controller_index = _widget_controller_any;
            column->bounds = (rectangle2d){0, 0, (short)(rows * pitch), width};
            column->flags = FLAG(_widget_pass_unhandled_events_to_children_bit) | FLAG(_widget_dpad_updown_tabs_thru_list_items_bit);
            if (!main_menu && page != _ds_game)
                performance_pause_block(&column->game_data_inputs, 1, &device_settings_native.option_input);
            for (row = 0; row < count; row++)
                performance_pause_child(&device_settings.column_children[layout][page][row],
                    page == _ds_game ? choice_tags[layout][row] :
                    device_settings_page_rows[page][row] == NONE ? device_settings.timer_tags[layout] :
                    device_settings.row_tags[device_settings_page_rows[page][row]], 0, (short)(row * pitch));
            if (page != _ds_game)
                performance_pause_child(&device_settings.column_children[layout][page][count], device_settings.accept_tag, 0, count * pitch);
            performance_pause_block(&column->child_widgets, rows, device_settings.column_children[layout][page]);
            if (main_menu)
            {
                performance_pause_child(&device_settings.screen_children[layout][page][0], column_tags[layout][page], x, y + column_y);
                performance_pause_child(&device_settings.screen_children[layout][page][1], heading_tags[page], x, y);
                performance_pause_child(&device_settings.screen_children[layout][page][2], device_settings.footer_tags[page], x, y + column_y + rows * pitch);
                performance_pause_block(&root->child_widgets, 3, device_settings.screen_children[layout][page]);
            }
            else
            {
                long frame = native_pause_frame_tag(height), legend = native_pause_legend_tag();
                short children = 4;
                if (frame == NONE || legend == NONE) return FALSE;
                /* The frame renders first. The original legend uses its
                 * original inset and keeps Select/Back semantics. */
                performance_pause_child(&device_settings.screen_children[layout][page][0], frame, x - 8, y);
                performance_pause_child(&device_settings.screen_children[layout][page][1], column_tags[layout][page], x, y + column_y);
                performance_pause_child(&device_settings.screen_children[layout][page][2], heading_tags[page], x, y);
                performance_pause_child(&device_settings.screen_children[layout][page][3], legend, x + 17, y + height - 25);
                if (page != _ds_game && bases[layout]->bounds.y1 - bases[layout]->bounds.y0 >= 480)
                {
                    performance_pause_child(&device_settings.screen_children[layout][page][4], device_settings.footer_tags[page], x - 41, y + height + 6);
                    children++;
                }
                performance_pause_block(&root->child_widgets, children, device_settings.screen_children[layout][page]);
            }
        }
    }
    if (!main_menu) { device_settings.ready = TRUE; return TRUE; }
    tag = tag_loaded(UI_WIDGET_DEFINITION_TAG, DEVICE_SETTINGS_ENTRY);
    if (tag == NONE) return FALSE;
    device_settings.entry = *ui_widget_definition_get(tag);
    if (device_settings.entry.event_handlers.count != 2) return FALSE;
    if (!device_settings_build_chooser(strings, profile_tag)) return FALSE;
    if (!device_settings_build_native_pages(strings, heading_tags, column_tags[_ds_main])) return FALSE;
    csmemcpy(device_settings.entry_events, device_settings.entry.event_handlers.address, sizeof(device_settings.entry_events));
    for (i = 0; i < 2; i++) device_settings.entry_events[i].widget_tag = device_settings_reference(UI_WIDGET_DEFINITION_TAG, device_settings.settings_tag);
    device_settings.entry.event_handlers.address = device_settings.entry_events;
    /* This final marker is published only when the complete main-menu tree exists. */
    device_settings.entry_tag = device_settings_register("ui\\native_settings\\entry", &device_settings.entry);
    device_settings.ready = device_settings.entry_tag != NONE;
    return device_settings.ready;
}

static boolean device_settings_campaign_build(void)
{
    static char const *const list_names[2] = {
        "ui\\shell\\solo_game\\pause_game\\pause_list", "ui\\shell\\solo_game\\pause_game\\coop_pause_list"};
    static char const *const root_names[2] = {"ui\\native_settings\\campaign_pause", "ui\\native_settings\\coop_pause"};
    static char const *const native_lists[2] = {"ui\\native_settings\\campaign_list", "ui\\native_settings\\coop_list"};
    static char const *const entry_names[2] = {"ui\\native_settings\\campaign_entry", "ui\\native_settings\\coop_entry"};
    long layout, row, root_tag, list_tag, entry_tag, cloned_list, resume_tag;
    long settings_tag = tag_loaded(UI_WIDGET_DEFINITION_TAG, "ui\\native_settings\\screen_4_0");
    device_settings_campaign.ready = FALSE;
    /* A preceding UI or multiplayer map has no solo root, so both the name
     * lookup and its saved tag can be NONE. That is not a reusable tree. */
    if ((!device_settings.ready || settings_tag == NONE || settings_tag != device_settings.screen_tags[_ds_solo][_ds_game]) && !device_settings_build()) return FALSE;
    resume_tag = tag_loaded(UI_WIDGET_DEFINITION_TAG, "ui\\shell\\solo_game\\pause_game\\resume_game_button");
    if (resume_tag == NONE) return FALSE;
    for (layout = 0; layout < 2; layout++)
    {
        boolean found_list = FALSE;
        root_tag = tag_loaded(UI_WIDGET_DEFINITION_TAG, device_settings_campaign_roots[layout]);
        list_tag = tag_loaded(UI_WIDGET_DEFINITION_TAG, list_names[layout]);
        if (root_tag == NONE || list_tag == NONE) return FALSE;
        device_settings_campaign.root[layout] = *ui_widget_definition_get(root_tag);
        device_settings_campaign.list[layout] = *ui_widget_definition_get(list_tag);
        device_settings_campaign.entry[layout] = *ui_widget_definition_get(resume_tag);
        if (device_settings_campaign.root[layout].child_widgets.count != 5 ||
            device_settings_campaign.list[layout].child_widgets.count != 4) return FALSE;
        device_settings_campaign.entry[layout].text_label_string_list = device_settings.heading[_ds_game].text_label_string_list;
        device_settings_campaign.entry[layout].string_list_index = _ds_game_label;
        for (row = 0; row < 2; row++)
            performance_pause_event_definition(&device_settings_campaign.events[layout][row],
                row ? _gamepad_binary_button_start : _gamepad_analog_button_a, 0,
                FLAG(_event_handler_open_widget_bit), device_settings.screen_tags[_ds_solo + layout][_ds_game]);
        performance_pause_block(&device_settings_campaign.entry[layout].event_handlers, 2, device_settings_campaign.events[layout]);
        entry_tag = device_settings_register(entry_names[layout], &device_settings_campaign.entry[layout]);
        if (entry_tag == NONE) return FALSE;
        csmemcpy(device_settings_campaign.list_children[layout], device_settings_campaign.list[layout].child_widgets.address,
            4 * sizeof(struct ui_widget_child_reference));
        for (row = 0; row < 4; row++) device_settings_campaign.list_children[layout][row].vertical_offset = row * 24;
        performance_pause_child(&device_settings_campaign.list_children[layout][4], entry_tag, 0, 96);
        performance_pause_block(&device_settings_campaign.list[layout].child_widgets, 5, device_settings_campaign.list_children[layout]);
        cloned_list = device_settings_register(native_lists[layout], &device_settings_campaign.list[layout]);
        if (cloned_list == NONE) return FALSE;
        csmemcpy(device_settings_campaign.root_children[layout], device_settings_campaign.root[layout].child_widgets.address,
            sizeof(device_settings_campaign.root_children[layout]));
        for (row = 0; row < 5; row++)
            if (device_settings_campaign.root_children[layout][row].widget_tag.index == list_tag)
            {
                device_settings_campaign.root_children[layout][row].widget_tag.index = cloned_list;
                /* Five 27px selectors at 24px pitch fit above the original
                 * divider when the list starts 6px below the frame top. */
                device_settings_campaign.root_children[layout][row].vertical_offset -= 3;
                found_list = TRUE;
            }
        if (!found_list) return FALSE;
        performance_pause_block(&device_settings_campaign.root[layout].child_widgets, 5, device_settings_campaign.root_children[layout]);
        device_settings_campaign.tags[layout] = device_settings_register(root_names[layout], &device_settings_campaign.root[layout]);
        if (device_settings_campaign.tags[layout] == NONE) return FALSE;
    }
    device_settings_campaign.ready = TRUE;
    return TRUE;
}

static long game_settings_remap_tag(long tag)
{
    short layout;
    char const *name = tag == NONE ? NULL : tag_get_name(tag);
    if (!name) return tag;
    for (layout = 0; layout < 2; layout++)
        if (!strcmp(name, device_settings_campaign_roots[layout]))
        {
            if ((!device_settings_campaign.ready || tag_loaded(UI_WIDGET_DEFINITION_TAG, "ui\\native_settings\\campaign_pause") != device_settings_campaign.tags[0]) &&
                !device_settings_campaign_build()) return tag;
            return device_settings_campaign.tags[layout];
        }
    if (strcmp(name, DEVICE_SETTINGS_ENTRY)) return tag;
    if ((!device_settings.ready || tag_loaded(UI_WIDGET_DEFINITION_TAG, "ui\\native_settings\\entry") != device_settings.entry_tag) && !device_settings_build()) return tag;
    return device_settings.entry_tag;
}

static long game_settings_pause_tag(short layout)
{
    long tag;
    if (layout < 0 || layout >= 3) return NONE;
    tag = tag_loaded(UI_WIDGET_DEFINITION_TAG, "ui\\native_settings\\screen_1_0");
    /* The pause builder calls us before publishing its finished root. */
    if (!device_settings.ready || tag == NONE || tag != device_settings.screen_tags[_ds_pause_1p][_ds_game])
        if (!device_settings_build()) return NONE;
    return device_settings.screen_tags[layout + 1][_ds_game];
}

static struct device_settings_draft *device_settings_draft_for(struct widget_instance *widget)
{
    short local;
    while (widget && widget->parent) widget = widget->parent;
    if (!widget) return NULL;
    local = widget->local_player_index;
    if (local == NONE) local = 0;
    if (local < 0 || local >= MAXIMUM_NUMBER_OF_LOCAL_PLAYERS) return NULL;
    return &device_settings_drafts[local];
}

static boolean game_settings_is_adjustable(struct widget_instance *widget)
{
    short row;
    if (!widget || !device_settings.ready) return FALSE;
    for (row = 0; row < NUMBER_OF_DEVICE_SETTINGS; row++)
        if (widget->definition_tag_index == device_settings.row_tags[row]) return TRUE;
    return FALSE;
}

static boolean game_settings_is_native_spinner(struct widget_instance *widget)
{
    short row;
    if (!widget || widget->definition_tag_index == NONE || !device_settings.ready || !device_settings.native_pages) return FALSE;
    for (row = 0; row < NUMBER_OF_DEVICE_SETTINGS; row++)
        if (widget->definition_tag_index == device_settings_native.spinner_tags[row]) return TRUE;
    return FALSE;
}

static void device_settings_render_draft(struct device_settings_draft *draft)
{
    static char const *const names[NUMBER_OF_DEVICE_SETTINGS] = {
        "Master", "Music", "Effects", "Dialogue", "Volume",
        "Menu Music", "Fullscreen", "VSync", "Smooth Motion",
        "Countdown", "Beeps", "Minutes", "Item Cues", "Position", "Timer Size"};
    short row, local = (short)(draft - device_settings_drafts);
    for (row = 0; row < NUMBER_OF_DEVICE_SETTINGS; row++)
    {
        struct widget_instance *widget = widget_instance_find_by_tag_index_recursive(draft->root, device_settings.row_tags[row]);
        char text[128];
        short index = (short)(_ds_value_start + local * NUMBER_OF_DEVICE_SETTINGS + row);
        if (!widget) continue;
        char value[32];
        if (device_settings.native_pages)
        {
            widget = widget_instance_find_by_tag_index_recursive(widget, device_settings_native.spinner_tags[row]);
            if (!widget) continue;
        }
        if (row < _device_setting_menu_music || row == _device_setting_timer_scale)
            snprintf(value, sizeof(value), "%.4g%%", draft->values[row] * 100.0);
        else if (row == _device_setting_timer_position)
        {
            static char const *const positions[] = {"Top Center", "Bottom Center", "Bottom Right"};
            short position = (short)draft->values[row];
            snprintf(value, sizeof(value), "%s", positions[position >= 0 && position <= 2 ? position : 0]);
        }
        else snprintf(value, sizeof(value), "%s", draft->values[row] != 0.0 ? "ON" : "OFF");
        if (device_settings.native_pages) snprintf(text, sizeof(text), "%s", value);
        else snprintf(text, sizeof(text), "%s: < %s >", names[row], value);
        device_settings_text(index, text);
        if (device_settings.native_pages) widget->parameters.list.selected_index = index;
        else widget->parameters.text_box.string_list_index = index;
    }
}

/* Event dispatch copies this handler so the standard engine owns widget
 * deletion and history. Changing a shared definition would affect other users. */
static struct ui_widget_event_handler_reference *game_settings_route_handler(
    struct widget_instance **dispatch_widget, struct ui_widget_event_handler_reference *handler,
    struct ui_widget_event_handler_reference *copy)
{
    struct widget_instance *widget = *dispatch_widget;
    struct device_settings_draft *draft;
    struct widget_instance *column;
    if (!device_settings.ready || !device_settings.native_pages || !widget ||
        handler->function != _device_settings_accept || handler->event_type != _gamepad_analog_button_a)
        return handler;
    draft = device_settings_draft_for(widget);
    column = widget->child;
    if (draft && draft->root == widget && draft->page == _ds_audio &&
        column && column->focused_child &&
        column->focused_child->definition_tag_index == device_settings.timer_tags[_ds_main])
    {
        *copy = device_settings.timer_events[_ds_main][0];
        /* Launch from the focused link so history restores this row. */
        *dispatch_widget = column->focused_child;
        return copy;
    }
    return handler;
}

static boolean game_settings_event(struct widget_instance *widget, short function)
{
    struct widget_instance *root = widget, *footer, *heading;
    struct device_settings_draft *draft = device_settings_draft_for(widget);
    short layout, active_layout = NONE, page = NONE, row;
    if (!draft) return FALSE;
    while (root->parent) root = root->parent;
    for (layout = 0; layout < _ds_layout_count; layout++)
        for (row = 0; row < _ds_page_count; row++)
            if (root->definition_tag_index != NONE && root->definition_tag_index == device_settings.screen_tags[layout][row])
            { page = row; active_layout = layout; }
    /* The outer Settings chooser also uses these Back events. */
    if (page == NONE) return function == _device_settings_cancel;
    if (function == _device_settings_initialize)
    {
        if (page == _ds_game)
        {
            draft->audio_session = draft->entering_timer = draft->resume_audio = FALSE;
            return TRUE;
        }
        if (!((page == _ds_audio && draft->audio_session && draft->resume_audio) ||
              (page == _ds_timer && draft->audio_session && draft->entering_timer)))
        {
            for (row = 0; row < NUMBER_OF_DEVICE_SETTINGS; row++)
                draft->original[row] = draft->values[row] = device_settings_get(row);
            if (page == _ds_timer)
                csmemcpy(draft->timer_snapshot, draft->values, sizeof(draft->timer_snapshot));
        }
        draft->root = root;
        draft->page = page;
        draft->layout = active_layout;
        draft->audio_session = page == _ds_audio || page == _ds_timer;
        draft->entering_timer = draft->resume_audio = FALSE;
        heading = widget_instance_find_by_tag_index_recursive(root, device_settings.heading_tags[page]);
        if (heading) heading->parameters.text_box.string_list_index = device_settings_page_titles[page];
        device_settings_render_draft(draft);
        return TRUE;
    }
    if (function == _device_settings_cancel && page == _ds_game) return TRUE;
    if (draft->root != root || page == _ds_game) return FALSE;
    if (function == _device_settings_enter_timer)
    {
        if (page != _ds_audio || !draft->audio_session) return FALSE;
        csmemcpy(draft->timer_snapshot, draft->values, sizeof(draft->timer_snapshot));
        draft->entering_timer = TRUE;
        return TRUE;
    }
    if (function == _device_settings_cancel)
    {
        if (page == _ds_timer)
        {
            for (row = 0; row < device_settings_page_counts[_ds_timer]; row++)
            {
                short setting = device_settings_page_rows[_ds_timer][row];
                draft->values[setting] = draft->timer_snapshot[setting];
            }
            draft->resume_audio = TRUE;
        }
        else draft->audio_session = draft->resume_audio = FALSE;
        draft->entering_timer = FALSE;
        return TRUE;
    }
    footer = widget_instance_find_by_tag_index_recursive(root, device_settings.footer_tags[page]);
    heading = widget_instance_find_by_tag_index_recursive(root, device_settings.heading_tags[page]);
    if (function == _device_settings_accept)
    {
        unsigned long changed = 0;
        int result;
        if (page == _ds_timer)
        {
            draft->resume_audio = TRUE;
            draft->entering_timer = FALSE;
            return TRUE;
        }
        for (row = 0; row < NUMBER_OF_DEVICE_SETTINGS; row++)
            if (draft->values[row] != draft->original[row]) changed |= 1UL << row;
        result = device_settings_apply(changed, draft->values);
        if (result <= 0)
        {
            if (result < 0)
            {
                for (row = 0; row < NUMBER_OF_DEVICE_SETTINGS; row++)
                    draft->original[row] = draft->values[row] = device_settings_get(row);
                device_settings_render_draft(draft);
            }
            if (footer) footer->parameters.text_box.string_list_index = result < 0 ? _ds_partial_failure_help : _ds_failure_help;
            else if (heading) heading->parameters.text_box.string_list_index = result < 0 ? _ds_partial_failure_brief : _ds_failure_brief;
            ui_play_audio_feedback_sound(_ui_audio_feedback_flag_failure);
            return FALSE;
        }
        for (row = 0; row < NUMBER_OF_DEVICE_SETTINGS; row++) draft->original[row] = draft->values[row];
        draft->audio_session = draft->entering_timer = draft->resume_audio = FALSE;
        return TRUE;
    }
    if (function != _device_settings_next && function != _device_settings_previous) return FALSE;
    for (row = 0; row < NUMBER_OF_DEVICE_SETTINGS; row++)
        if (widget->definition_tag_index == device_settings.row_tags[row] ||
            (device_settings.native_pages && widget->definition_tag_index == device_settings_native.spinner_tags[row])) break;
    if (row == NUMBER_OF_DEVICE_SETTINGS) return FALSE;
    if (row < _device_setting_menu_music || row == _device_setting_timer_scale)
    {
        /* Preserve exact off-step values until their row is edited. */
        double grid = row == _device_setting_timer_scale ? 20.0 : 10.0;
        double steps = draft->values[row] * grid;
        short step = (short)(steps + 0.000001);
        short minimum = row == _device_setting_timer_scale ? 10 : 0;
        short maximum = (short)grid;
        if (function == _device_settings_next) step++;
        else if (steps - step < 0.000001) step--;
        if (step < minimum) step = minimum;
        if (step > maximum) step = maximum;
        draft->values[row] = step / grid;
    }
    else if (row == _device_setting_timer_position)
        draft->values[row] = ((short)draft->values[row] + (function == _device_settings_next ? 1 : 2)) % 3;
    else draft->values[row] = draft->values[row] == 0.0 ? 1.0 : 0.0;
    if (footer) footer->parameters.text_box.string_list_index = device_settings_page_help[page];
    if (heading) heading->parameters.text_box.string_list_index = device_settings_page_titles[page];
    device_settings_render_draft(draft);
    if (game_settings_is_native_spinner(widget))
        widget->parameters.list.last_list_tab_direction = function == _device_settings_next ? 15 : -15;
    return TRUE;
}

static void game_settings_input(struct widget_instance *widget, short function)
{
    short index = widget->focused_child ? (short)widget_instance_get_child_index_from_parent(widget->focused_child) : 0;
    if (!device_settings.ready) return;
    if (function == _device_settings_chooser_preview && widget->definition_tag_index == device_settings_native.game_menu_tag)
    {
        struct widget_instance *preview = widget->parameters.list.extended_description;
        if (preview && preview->child && preview->child->next && preview->child->next->next)
        {
            preview->child->visible = index == 0;
            preview->child->animation.current_frame_index = 2;
            preview->child->next->visible = index == 1;
            preview->child->next->animation.current_frame_index = 0;
            preview->child->next->next->parameters.text_box.string_list_index = index == 1 ? 1 : 0;
        }
    }
    else if (function == _device_settings_option_help)
    {
        struct device_settings_draft *draft = device_settings_draft_for(widget);
        struct widget_instance *footer;
        short count, setting;
        if (!draft || !draft->root || widget->parent != draft->root || draft->page <= _ds_game || draft->page >= _ds_page_count) return;
        if (device_settings.native_pages && draft->page == _ds_audio)
        {
            struct widget_instance *caption = widget_instance_find_by_tag_index_recursive(draft->root, device_settings_native.audio_accept_tag);
            if (caption) caption->parameters.text_box.string_list_index = index == 4 ? _ds_select_key_label : _ds_accept_key_label;
        }
        footer = widget_instance_find_by_tag_index_recursive(draft->root, device_settings.footer_tags[draft->page]);
        if (!footer || footer->parameters.text_box.string_list_index == _ds_failure_help ||
            footer->parameters.text_box.string_list_index == _ds_partial_failure_help) return;
        count = device_settings_page_counts[draft->page];
        if (index >= 0 && index < count)
        {
            setting = device_settings_page_rows[draft->page][index];
            footer->parameters.text_box.string_list_index = setting == NONE ? _ds_timer_link_help : (short)(_ds_help_start + setting);
        }
        else if (!device_settings.native_pages && index == count)
            footer->parameters.text_box.string_list_index = device_settings_page_help[draft->page];
    }
}
#undef DEVICE_SETTINGS_STRING_COUNT
#undef DEVICE_SETTINGS_ENTRY
#undef DEVICE_PROFILE_PICKER
#undef DEVICE_OPTIONS_PREFIX
#undef DEVICE_CHOOSER_PREFIX
#undef DEVICE_CONTROLS_PREFIX
