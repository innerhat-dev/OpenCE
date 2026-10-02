/* Native cache-local DeLa clones; retail maps and saved-game navigation stay intact. */
#define PB_EDIT_PREFIX "ui\\shell\\main_menu\\settings_select\\multiplayer_setup\\"
#define PB_EDIT_PATH PB_EDIT_PREFIX "playlist_edit\\gametype_edit_screen"
#define PB_EDIT_RUNTIME "ui\\native_pb\\editor"
enum { _pb_editor_initialize = 32000, _pb_editor_accept = 32001 };
enum { _pb_editor_row_count = 6 };
static unsigned const pb_editor_option_flags[_pb_editor_row_count - 1] = {
    _performance_option_match_timer, _performance_option_spawn_markers,
    _performance_option_timer_audio, _performance_option_silent_movement,
    _performance_option_silent_weapon_ready};
static struct
{
    struct ui_widget_definition root, list, entry, screen, heading, menu, help;
    struct ui_widget_definition row[_pb_editor_row_count], label[_pb_editor_row_count], spinner[_pb_editor_row_count], preview, preview_text;
    struct ui_widget_child_reference root_children[8], list_children[7], screen_children[3];
    struct ui_widget_child_reference menu_children[_pb_editor_row_count], row_children[_pb_editor_row_count][2], preview_children[2];
    struct ui_widget_event_handler_reference entry_events[2], menu_events[3];
    struct ui_widget_game_data_input_reference list_input, menu_input;
    struct string_list strings[7];
    struct string_list_entry string_entries[7][13];
    wchar_t string_text[7][13][256];
    long root_tag, list_tag, menu_tag, spinner_tag[_pb_editor_row_count];
    short last_preset;
    unsigned last_flags;
    boolean ready;
} pb_editor;

static long pb_editor_strings(short set, char const *name, char const *const *text, short count)
{
    short i;
    struct string_list *list = &pb_editor.strings[set];
    memset(list, 0, sizeof(*list));
    list->strings.count = count;
    list->strings.address = pb_editor.string_entries[set];
    for (i = 0; i < count; i++)
    {
        long c;
        struct string_list_entry *entry = &pb_editor.string_entries[set][i];
        memset(entry, 0, sizeof(*entry));
        for (c = 0; text[i][c] && c < 255; c++)
            pb_editor.string_text[set][i][c] = (unsigned char)text[i][c];
        pb_editor.string_text[set][i][c] = 0;
        entry->string.size = (c + 1) * sizeof(wchar_t);
        entry->string.address = pb_editor.string_text[set][i];
    }
    return cache_files_register_runtime_ui_tag(UNICODE_STRING_LIST_TAG, name, list);
}

static struct tag_reference pb_editor_reference(long group, long index)
{
    struct tag_reference reference = {0};
    reference.group_tag = group;
    reference.index = index;
    return reference;
}

static boolean pb_editor_clone(struct ui_widget_definition *definition, char const *name)
{
    long tag = tag_loaded(UI_WIDGET_DEFINITION_TAG, name);
    if (tag == NONE) return FALSE;
    *definition = *ui_widget_definition_get(tag);
    return TRUE;
}

static long pb_editor_register(char const *name, struct ui_widget_definition *definition)
{
    return cache_files_register_runtime_ui_tag(UI_WIDGET_DEFINITION_TAG, name, definition);
}

static boolean pb_editor_build(void)
{
    static char const *const labels[] = {"PB OPTIONS", "PRESET:", "MATCH TIMER:", "SPAWN MARKERS:", "TIMER SOUNDS:",
        "MOVEMENT SOUNDS:", "WEAPON SOUNDS:", "PERFORMANCE OPTIONS"};
    static char const *const presets[] = {"STOCK", "PRACTICE", "CUSTOM"};
    static char const *const toggles[] = {"OFF", "ON"};
    static char const *const sounds[] = {"NORMAL", "SILENT"};
    static char const *const help[] = {
        "Original game settings.\r\nAll performance options are off.",
        "Practice with a timer, sounds and spawn markers.\r\nThe host controls these options for all players.",
        "Choose each performance option individually.",
        "The match timer is hidden.",
        "Show elapsed match time using\r\nthe host's game clock.",
        "Spawn markers are hidden.",
        "Show spawn locations, including on stock maps.",
        "Timer announcements are silent.",
        "Play NHE countdowns and minute announcements.\r\nWorks independently of the visible match timer.",
        "Normal footsteps, jumps and landings.\r\nCombat sounds are unchanged.",
        "Silent footsteps, jumps and landings.\r\nCombat sounds are unchanged.",
        "Normal equip and switch sounds.\r\nFiring and reloading are unchanged.",
        "Silent equip and switch sounds.\r\nFiring and reloading are unchanged."};
    static char const *const row_names[] = {"ui\\native_pb\\preset_row", "ui\\native_pb\\timer_row", "ui\\native_pb\\markers_row", "ui\\native_pb\\audio_row", "ui\\native_pb\\movement_row", "ui\\native_pb\\weapon_row"};
    static char const *const label_names[] = {"ui\\native_pb\\preset_label", "ui\\native_pb\\timer_label", "ui\\native_pb\\markers_label", "ui\\native_pb\\audio_label", "ui\\native_pb\\movement_label", "ui\\native_pb\\weapon_label"};
    static char const *const spinner_names[] = {"ui\\native_pb\\preset_spinner", "ui\\native_pb\\timer_spinner", "ui\\native_pb\\markers_spinner", "ui\\native_pb\\audio_spinner", "ui\\native_pb\\movement_spinner", "ui\\native_pb\\weapon_spinner"};
    long labels_tag, presets_tag, toggles_tag, sounds_tag, help_tag, i, tag;
    struct ui_widget_definition *preview_text;
    struct string_list *original_strings;
    pb_editor.ready = FALSE;
    if (!pb_editor_clone(&pb_editor.root, PB_EDIT_PATH) ||
        !pb_editor_clone(&pb_editor.list, PB_EDIT_PREFIX "playlist_edit\\edit_playlist_select_list") ||
        !pb_editor_clone(&pb_editor.entry, PB_EDIT_PREFIX "playlist_edit\\playlist_edit_indicators_item") ||
        !pb_editor_clone(&pb_editor.screen, PB_EDIT_PREFIX "indicator_options_edit\\indicator_options_screen") ||
        !pb_editor_clone(&pb_editor.menu, PB_EDIT_PREFIX "indicator_options_edit\\indicator_options_menu") ||
        !pb_editor_clone(&pb_editor.help, PB_EDIT_PREFIX "indicator_options_edit\\indicator_options_help") ||
        !pb_editor_clone(&pb_editor.row[0], PB_EDIT_PREFIX "indicator_options_edit\\op_players_on_radar") ||
        !pb_editor_clone(&pb_editor.label[0], PB_EDIT_PREFIX "indicator_options_edit\\indicator_options_players_on_radar_label") ||
        !pb_editor_clone(&pb_editor.spinner[0], PB_EDIT_PREFIX "indicator_options_edit\\indicator_options_players_on_radar_spinner"))
        return FALSE;
    if (pb_editor.root.child_widgets.count != 8 || pb_editor.list.child_widgets.count != 6 ||
        pb_editor.screen.child_widgets.count != 3 || pb_editor.menu.child_widgets.count != 3 ||
        pb_editor.row[0].child_widgets.count != 2 || pb_editor.menu.event_handlers.count != 3 ||
        pb_editor.entry.event_handlers.count != 2 || pb_editor.list.extended_description_widget.index == NONE)
        return FALSE;
    pb_editor.preview = *ui_widget_definition_get(pb_editor.list.extended_description_widget.index);
    if (pb_editor.preview.child_widgets.count != 2) return FALSE;
    memcpy(pb_editor.preview_children, pb_editor.preview.child_widgets.address, sizeof(pb_editor.preview_children));
    preview_text = ui_widget_definition_get(pb_editor.preview_children[0].widget_tag.index);
    if (preview_text->type != _ui_widget_type_text_box || preview_text->text_label_string_list.index == NONE)
        return FALSE;
    original_strings = unicode_string_list_definition_get(preview_text->text_label_string_list.index);
    if (original_strings->strings.count != 6) return FALSE;
    labels_tag = pb_editor_strings(0, "ui\\native_pb\\labels", labels, NUMBEROF(labels));
    presets_tag = pb_editor_strings(1, "ui\\native_pb\\presets", presets, NUMBEROF(presets));
    toggles_tag = pb_editor_strings(2, "ui\\native_pb\\toggles", toggles, NUMBEROF(toggles));
    help_tag = pb_editor_strings(3, "ui\\native_pb\\help_strings", help, NUMBEROF(help));
    sounds_tag = pb_editor_strings(6, "ui\\native_pb\\sound_values", sounds, NUMBEROF(sounds));
    if (labels_tag == NONE || presets_tag == NONE || toggles_tag == NONE || sounds_tag == NONE || help_tag == NONE) return FALSE;
    /* PB has a new caption, but reuses the Indicators preview image. */
    {
        static char const *const caption[] = {"Performance options like\r\ntimers, spawn markers,\r\nand more.\r\n\r\nThis gametype:"};
        if (pb_editor_strings(4, "ui\\native_pb\\preview_caption", caption, 1) == NONE) return FALSE;
        for (i = 0; i < 7; i++)
            pb_editor.string_entries[5][i] = i == 5 ? pb_editor.string_entries[4][0] :
                ((struct string_list_entry *)original_strings->strings.address)[i == 6 ? 5 : i];
        pb_editor.strings[5].strings = (struct tag_block){7, pb_editor.string_entries[5], NULL};
        tag = cache_files_register_runtime_ui_tag(UNICODE_STRING_LIST_TAG, "ui\\native_pb\\preview_strings", &pb_editor.strings[5]);
        if (tag == NONE) return FALSE;
    }
    pb_editor.preview_text = *preview_text;
    pb_editor.preview_text.text_label_string_list = pb_editor_reference(UNICODE_STRING_LIST_TAG, tag);
    tag = pb_editor_register("ui\\native_pb\\preview_text", &pb_editor.preview_text);
    if (tag == NONE) return FALSE;
    pb_editor.preview_children[0].widget_tag = pb_editor_reference(UI_WIDGET_DEFINITION_TAG, tag);
    pb_editor.preview.child_widgets.address = pb_editor.preview_children;
    tag = pb_editor_register("ui\\native_pb\\preview", &pb_editor.preview);
    if (tag == NONE) return FALSE;
    pb_editor.list.extended_description_widget = pb_editor_reference(UI_WIDGET_DEFINITION_TAG, tag);
    pb_editor.help.text_label_string_list = pb_editor_reference(UNICODE_STRING_LIST_TAG, help_tag);
    tag = pb_editor_register("ui\\native_pb\\help", &pb_editor.help);
    if (tag == NONE) return FALSE;
    pb_editor.menu.extended_description_widget = pb_editor_reference(UI_WIDGET_DEFINITION_TAG, tag);
    memcpy(pb_editor.menu_children, pb_editor.menu.child_widgets.address, 3 * sizeof(pb_editor.menu_children[0]));
    for (i = 3; i < _pb_editor_row_count; i++)
    {
        pb_editor.menu_children[i] = pb_editor.menu_children[i - 1];
        pb_editor.menu_children[i].vertical_offset += 30;
    }
    pb_editor.menu.child_widgets.count = _pb_editor_row_count;
    memcpy(pb_editor.menu_events, pb_editor.menu.event_handlers.address, sizeof(pb_editor.menu_events));
    pb_editor.menu_events[0].function = _pb_editor_initialize;
    pb_editor.menu_events[1].function = pb_editor.menu_events[2].function = _pb_editor_accept;
    pb_editor.menu.event_handlers.address = pb_editor.menu_events;
    pb_editor.menu.child_widgets.address = pb_editor.menu_children;
    pb_editor.menu_input.function = 32001;
    pb_editor.menu.game_data_inputs = (struct tag_block){1, &pb_editor.menu_input, NULL};
    for (i = 0; i < _pb_editor_row_count; i++)
    {
        if (i) { pb_editor.row[i] = pb_editor.row[0]; pb_editor.label[i] = pb_editor.label[0]; pb_editor.spinner[i] = pb_editor.spinner[0]; }
        memcpy(pb_editor.row_children[i], pb_editor.row[0].child_widgets.address, sizeof(pb_editor.row_children[i]));
        pb_editor.label[i].text_label_string_list = pb_editor_reference(UNICODE_STRING_LIST_TAG, labels_tag);
        pb_editor.label[i].string_list_index = i + 1;
        tag = pb_editor_register(label_names[i], &pb_editor.label[i]);
        if (tag == NONE) return FALSE;
        pb_editor.row_children[i][0].widget_tag = pb_editor_reference(UI_WIDGET_DEFINITION_TAG, tag);
        pb_editor.spinner[i].text_label_string_list = pb_editor_reference(UNICODE_STRING_LIST_TAG,
            i == 0 ? presets_tag : i < 4 ? toggles_tag : sounds_tag);
        pb_editor.spinner[i].bounds.x1 = 142;
        pb_editor.spinner[i].list_footer_bounds.x0 = 142;
        pb_editor.spinner[i].list_footer_bounds.x1 = 148;
        pb_editor.row_children[i][1].horizontal_offset = 300;
        pb_editor.spinner_tag[i] = pb_editor_register(spinner_names[i], &pb_editor.spinner[i]);
        if (pb_editor.spinner_tag[i] == NONE) return FALSE;
        pb_editor.row_children[i][1].widget_tag = pb_editor_reference(UI_WIDGET_DEFINITION_TAG, pb_editor.spinner_tag[i]);
        pb_editor.row[i].child_widgets.address = pb_editor.row_children[i];
        tag = pb_editor_register(row_names[i], &pb_editor.row[i]);
        if (tag == NONE) return FALSE;
        pb_editor.menu_children[i].widget_tag = pb_editor_reference(UI_WIDGET_DEFINITION_TAG, tag);
    }
    pb_editor.menu_tag = pb_editor_register("ui\\native_pb\\menu", &pb_editor.menu);
    if (pb_editor.menu_tag == NONE) return FALSE;
    pb_editor.heading = pb_editor.label[0];
    pb_editor.heading.bounds = (rectangle2d){24, 54, 60, 566};
    pb_editor.heading.string_list_index = 7;
    pb_editor.heading.horizontal_offset = pb_editor.heading.vertical_offset = 0;
    pb_editor.heading.text_color = (real_argb_color){1, 1, 1, 1};
    tag = pb_editor_register("ui\\native_pb\\heading", &pb_editor.heading);
    if (tag == NONE) return FALSE;
    memcpy(pb_editor.screen_children, pb_editor.screen.child_widgets.address, sizeof(pb_editor.screen_children));
    pb_editor.screen_children[0].widget_tag = pb_editor_reference(UI_WIDGET_DEFINITION_TAG, tag);
    pb_editor.screen_children[1].widget_tag = pb_editor_reference(UI_WIDGET_DEFINITION_TAG, pb_editor.menu_tag);
    pb_editor.screen.child_widgets.address = pb_editor.screen_children;
    tag = pb_editor_register("ui\\native_pb\\screen", &pb_editor.screen);
    if (tag == NONE) return FALSE;
    pb_editor.entry.text_label_string_list = pb_editor_reference(UNICODE_STRING_LIST_TAG, labels_tag);
    pb_editor.entry.string_list_index = 0;
    pb_editor.entry.bounds.y0 += 33; pb_editor.entry.bounds.y1 += 33;
    memcpy(pb_editor.entry_events, pb_editor.entry.event_handlers.address, sizeof(pb_editor.entry_events));
    for (i = 0; i < 2; i++) pb_editor.entry_events[i].widget_tag = pb_editor_reference(UI_WIDGET_DEFINITION_TAG, tag);
    pb_editor.entry.event_handlers.address = pb_editor.entry_events;
    tag = pb_editor_register("ui\\native_pb\\entry", &pb_editor.entry);
    if (tag == NONE) return FALSE;
    memcpy(pb_editor.list_children, pb_editor.list.child_widgets.address, 6 * sizeof(pb_editor.list_children[0]));
    pb_editor.list_children[6] = pb_editor.list_children[5];
    pb_editor.list_children[6].vertical_offset += 33;
    pb_editor.list_children[5] = pb_editor.list_children[4];
    pb_editor.list_children[5].widget_tag = pb_editor_reference(UI_WIDGET_DEFINITION_TAG, tag);
    pb_editor.list.child_widgets = (struct tag_block){7, pb_editor.list_children, NULL};
    pb_editor.list_input.function = 32000;
    pb_editor.list.game_data_inputs = (struct tag_block){1, &pb_editor.list_input, NULL};
    pb_editor.list_tag = pb_editor_register("ui\\native_pb\\list", &pb_editor.list);
    if (pb_editor.list_tag == NONE) return FALSE;
    memcpy(pb_editor.root_children, pb_editor.root.child_widgets.address, sizeof(pb_editor.root_children));
    pb_editor.root_children[1].widget_tag = pb_editor_reference(UI_WIDGET_DEFINITION_TAG, pb_editor.list_tag);
    pb_editor.root_children[7].vertical_offset += 33;
    pb_editor.root.child_widgets.address = pb_editor.root_children;
    pb_editor.root_tag = pb_editor_register(PB_EDIT_RUNTIME, &pb_editor.root);
    pb_editor.ready = pb_editor.root_tag != NONE;
    return pb_editor.ready;
}

static boolean performance_editor_is_spinner(struct widget_instance *widget)
{
    short row;
    if (!pb_editor.ready || !widget || widget->definition_tag_index == NONE) return FALSE;
    for (row = 0; row < _pb_editor_row_count; row++)
        if (widget->definition_tag_index == pb_editor.spinner_tag[row]) return TRUE;
    return FALSE;
}

static long performance_editor_remap_tag(long tag)
{
    char const *name = tag_get_name(tag);
    if (!name || strcmp(name, PB_EDIT_PATH)) return tag;
    if (tag_loaded(UI_WIDGET_DEFINITION_TAG, PB_EDIT_RUNTIME) == NONE && !pb_editor_build()) return tag;
    return pb_editor.root_tag;
}

static struct widget_instance *pb_editor_spinner(struct widget_instance *menu, short row)
{
    return widget_instance_find_by_tag_index_recursive(menu, pb_editor.spinner_tag[row]);
}

static void pb_editor_sync(struct widget_instance *menu)
{
    struct widget_instance *spinners[_pb_editor_row_count];
    unsigned flags = 0;
    short row;
    for (row = 0; row < _pb_editor_row_count; row++)
    {
        spinners[row] = pb_editor_spinner(menu, row);
        if (!spinners[row]) return;
        if (row && spinners[row]->parameters.list.selected_index)
            flags |= pb_editor_option_flags[row - 1];
    }
    if (spinners[0]->parameters.list.selected_index != pb_editor.last_preset)
    {
        short preset = spinners[0]->parameters.list.selected_index;
        if (preset < 2)
        {
            flags = preset ? PERFORMANCE_PRACTICE_FLAGS : 0;
            for (row = 1; row < _pb_editor_row_count; row++)
                spinners[row]->parameters.list.selected_index = (flags & pb_editor_option_flags[row - 1]) != 0;
        }
    }
    else if (flags != pb_editor.last_flags)
        spinners[0]->parameters.list.selected_index = flags == 0 ? 0 : flags == PERFORMANCE_PRACTICE_FLAGS ? 1 : 2;
    pb_editor.last_preset = spinners[0]->parameters.list.selected_index;
    pb_editor.last_flags = flags;
}

static boolean performance_editor_event(struct widget_instance *widget, short function)
{
    struct game_variant *variant = player_ui_get_edit_playlist_profile();
    if (widget->definition_tag_index != pb_editor.menu_tag || !variant) return FALSE;
    if (function == _pb_editor_initialize)
    {
        unsigned flags = performance_variant_get_flags(variant);
        short i;
        pb_editor.last_preset = flags == 0 ? 0 : flags == PERFORMANCE_PRACTICE_FLAGS ? 1 : 2;
        pb_editor.last_flags = flags;
        for (i = 0; i < _pb_editor_row_count; i++)
        {
            struct widget_instance *spinner = pb_editor_spinner(widget, i);
            if (!spinner) return FALSE;
            spinner->parameters.list.selected_index = i == 0 ? pb_editor.last_preset : (flags & pb_editor_option_flags[i - 1]) != 0;
        }
        return TRUE;
    }
    if (function == _pb_editor_accept)
    {
        pb_editor_sync(widget);
        performance_variant_set_flags(variant, pb_editor.last_flags);
        return TRUE;
    }
    return FALSE;
}

static void performance_editor_input(struct widget_instance *widget, short function)
{
    if (function == 32001 && widget->definition_tag_index == pb_editor.menu_tag)
    {
        pb_editor_sync(widget);
        if (widget->focused_child) ui_widget_game_data_function_invoke(widget, 17);
    }
    else if (function == 32000 && widget->definition_tag_index == pb_editor.list_tag)
    {
        struct widget_instance *description = widget->parameters.list.extended_description;
        short index = widget->focused_child ? widget_instance_get_child_index_from_parent(widget->focused_child) : 0;
        if (description && description->child && description->child->next)
        {
            description->child->parameters.text_box.string_list_index = index;
            description->child->next->animation.current_frame_index = index == 6 ? 5 : index == 5 ? 4 : index;
        }
    }
}
#undef PB_EDIT_PREFIX
#undef PB_EDIT_PATH
#undef PB_EDIT_RUNTIME
