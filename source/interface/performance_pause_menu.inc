/* Native multiplayer pause widgets. Included by ui_widget.c after its private
 * definitions and prototypes. All art and fonts stay in the current map; these
 * runtime DeLa/ustr tags do not alter the cache, its checksum, or retail tags. */

enum
{
	_performance_pause_created = 32010,
	_performance_pause_apply,
	_performance_pause_next,
};

enum
{
	_pp_pause_1p, _pp_pause_2p, _pp_pause_4p,
	_pp_list_1p, _pp_list_2p, _pp_list_4p,
	_pp_entry_1p, _pp_entry_2p, _pp_entry_4p,
	_pp_settings_1p, _pp_settings_2p, _pp_settings_4p,
	_pp_options_1p, _pp_options_2p, _pp_options_4p,
	_pp_column, _pp_preset, _pp_timer, _pp_markers, _pp_audio, _pp_movement, _pp_weapon,
	_pp_apply, _pp_title, _pp_footer,
	_pp_widget_count
};

static char const *const performance_pause_original_names[3] =
{
	"ui\\shell\\multiplayer_game\\pause_game\\1p_pause_game",
	"ui\\shell\\multiplayer_game\\pause_game\\2p_pause_game",
	"ui\\shell\\multiplayer_game\\pause_game\\4p_pause_game",
};

static char const *const performance_pause_names[_pp_widget_count] =
{
	"ui\\performance\\pause_1p", "ui\\performance\\pause_2p", "ui\\performance\\pause_4p",
	"ui\\performance\\pause_list_1p", "ui\\performance\\pause_list_2p", "ui\\performance\\pause_list_4p",
	"ui\\performance\\pause_entry_1p", "ui\\performance\\pause_entry_2p", "ui\\performance\\pause_entry_4p",
	"ui\\performance\\pause_settings_1p", "ui\\performance\\pause_settings_2p", "ui\\performance\\pause_settings_4p",
	"ui\\performance\\pause_options_1p", "ui\\performance\\pause_options_2p", "ui\\performance\\pause_options_4p",
	"ui\\performance\\pause_column", "ui\\performance\\pause_preset",
	"ui\\performance\\pause_timer", "ui\\performance\\pause_markers", "ui\\performance\\pause_audio",
	"ui\\performance\\pause_movement", "ui\\performance\\pause_weapon",
	"ui\\performance\\pause_apply", "ui\\performance\\pause_title", "ui\\performance\\pause_footer",
};

/* unicode_string_list_get_string writes the terminating NUL; keep these
 * writable, including on ports that place wide string literals in rodata. */
static wchar_t performance_pause_text[][64] =
{
	L"PB OPTIONS", L"APPLY", L"RETURN",
	L"Apply to change host settings.",
	L"Host settings (view only).",
	L"Preset: < Stock >", L"Preset: < Practice >", L"Preset: < Custom >",
	L"Match timer: < Off >", L"Match timer: < On >",
	L"Markers: < Off >", L"Markers: < On >",
	L"PB OPTIONS",
	L"Timer sounds: <Off>", L"Timer sounds: <On>", L"GAME SETTINGS",
	L"Movement: <Normal>", L"Movement: <Silent>",
	L"Weapon: < Normal >", L"Weapon: < Silent >",
	L"Movement sounds only:\r\nfootsteps, jumps and landings.",
	L"Equip and switch sounds only.\r\nFiring and reloading unchanged.",
	L"Spawn markers show player\r\nspawn locations.",
	L"The host controls timer sounds.\r\nLocal options are in Audio.",
};
static struct string_list_entry performance_pause_strings[24];
static struct string_list performance_pause_string_lists[7];
static char const *const performance_pause_string_names[7] =
{
	"ui\\performance\\pause_labels", "ui\\performance\\pause_presets",
	"ui\\performance\\pause_timer_values", "ui\\performance\\pause_marker_values",
	"ui\\performance\\pause_audio_values",
	"ui\\performance\\pause_movement_values", "ui\\performance\\pause_weapon_values",
};
static long performance_pause_string_tags[7];
static struct ui_widget_definition performance_pause_definitions[_pp_widget_count];
static long performance_pause_tags[_pp_widget_count];
static struct ui_widget_child_reference performance_pause_children[3][3];
static struct ui_widget_child_reference performance_pause_list_children[3][4];
static struct ui_widget_child_reference performance_pause_option_children[3][5];
static struct ui_widget_child_reference performance_pause_column_children[7];
static struct ui_widget_event_handler_reference performance_pause_entry_events[3][2];
static struct ui_widget_event_handler_reference performance_pause_settings_events[3][2];
static struct ui_widget_event_handler_reference performance_pause_root_events[3];
static struct ui_widget_event_handler_reference performance_pause_apply_events[2];
static struct ui_widget_event_handler_reference performance_pause_spinner_events[1];
static boolean performance_pause_ready;
static long game_settings_pause_tag(short layout);

struct performance_pause_draft
{
	struct widget_instance *root;
	unsigned flags;
	short preset;
};
static struct performance_pause_draft performance_pause_drafts[MAXIMUM_NUMBER_OF_LOCAL_PLAYERS];

static void performance_pause_reference(struct tag_reference *reference, long group, long index)
{
	csmemset(reference, 0, sizeof(*reference));
	reference->group_tag = group;
	reference->index = index;
}

static void performance_pause_block(struct tag_block *block, long count, void *address)
{
	csmemset(block, 0, sizeof(*block));
	block->count = count;
	block->address = address;
}

static void performance_pause_event_definition(
	struct ui_widget_event_handler_reference *event, short type, short function,
	long flags, long widget_tag)
{
	csmemset(event, 0, sizeof(*event));
	event->event_type = type;
	event->function = function;
	event->flags = flags;
	performance_pause_reference(&event->widget_tag, UI_WIDGET_DEFINITION_TAG, widget_tag);
	performance_pause_reference(&event->sound_effect, 'snd!', NONE);
}

static void performance_pause_child(
	struct ui_widget_child_reference *child, long tag, short x, short y)
{
	csmemset(child, 0, sizeof(*child));
	performance_pause_reference(&child->widget_tag, UI_WIDGET_DEFINITION_TAG, tag);
	child->horizontal_offset = x;
	child->vertical_offset = y;
}

static void performance_pause_clear_definition(struct ui_widget_definition *definition)
{
	csmemset(definition, 0, sizeof(*definition));
	performance_pause_reference(&definition->background_bitmap, 'bitm', NONE);
	performance_pause_reference(&definition->text_label_string_list, UNICODE_STRING_LIST_TAG, NONE);
	performance_pause_reference(&definition->text_font, FONT_GROUP_TAG, NONE);
	performance_pause_reference(&definition->list_header_bitmap, 'bitm', NONE);
	performance_pause_reference(&definition->list_footer_bitmap, 'bitm', NONE);
	performance_pause_reference(&definition->extended_description_widget, UI_WIDGET_DEFINITION_TAG, NONE);
}

static boolean performance_pause_build(void)
{
	struct ui_widget_definition *original_roots[3];
	struct ui_widget_definition *original_list;
	struct ui_widget_definition *original_resume;
	struct ui_widget_child_reference *original_list_children;
	long list_tag, font, frame_tag, legend_tag, index, layout;
	static short const string_starts[7] = {0, 5, 8, 10, 13, 16, 18};
	static short const string_counts[7] = {24, 3, 2, 2, 2, 2, 2};

	/* Runtime registrations are invalidated at every scenario unload. A tag
	 * name lookup avoids dereferencing stale map definitions after a reload. */
	if (performance_pause_ready &&
		tag_loaded(UI_WIDGET_DEFINITION_TAG, performance_pause_names[_pp_pause_1p]) ==
			performance_pause_tags[_pp_pause_1p])
		return TRUE;
	performance_pause_ready = FALSE;
	csmemset(performance_pause_drafts, 0, sizeof(performance_pause_drafts));
	list_tag = tag_loaded(UI_WIDGET_DEFINITION_TAG,
		"ui\\shell\\multiplayer_game\\pause_game\\mp_pause_list");
	font = tag_loaded(FONT_GROUP_TAG, "ui\\small_ui");
	if (list_tag == NONE || font == NONE)
		return FALSE;
	original_list = ui_widget_definition_get(list_tag);
	if (original_list->child_widgets.count != 2)
		return FALSE;
	original_list_children = original_list->child_widgets.address;
	if (original_list_children[0].widget_tag.index == NONE)
		return FALSE;
	original_resume = ui_widget_definition_get(original_list_children[0].widget_tag.index);
	for (layout = 0; layout < 3; layout++)
	{
		long root_tag = tag_loaded(UI_WIDGET_DEFINITION_TAG, performance_pause_original_names[layout]);
		if (root_tag == NONE)
			return FALSE;
		original_roots[layout] = ui_widget_definition_get(root_tag);
		if (original_roots[layout]->child_widgets.count != 3)
			return FALSE;
	}
	frame_tag = native_pause_frame_tag(240);
	legend_tag = native_pause_legend_tag();
	if (frame_tag == NONE || legend_tag == NONE) return FALSE;
	for (index = 0; index < 24; index++)
	{
		csmemset(&performance_pause_strings[index], 0, sizeof(performance_pause_strings[index]));
		performance_pause_strings[index].string.address = performance_pause_text[index];
		performance_pause_strings[index].string.size =
			(ustrlen(performance_pause_text[index]) + 1) * sizeof(wchar_t);
	}
	for (index = 0; index < 7; index++)
	{
		performance_pause_block(&performance_pause_string_lists[index].strings,
			string_counts[index], &performance_pause_strings[string_starts[index]]);
		performance_pause_string_tags[index] = cache_files_register_runtime_ui_tag(
			UNICODE_STRING_LIST_TAG, performance_pause_string_names[index],
			&performance_pause_string_lists[index]);
		if (performance_pause_string_tags[index] == NONE)
			return FALSE;
	}
	for (index = 0; index < _pp_widget_count; index++)
	{
		performance_pause_clear_definition(&performance_pause_definitions[index]);
		performance_pause_tags[index] = cache_files_register_runtime_ui_tag(
			UI_WIDGET_DEFINITION_TAG, performance_pause_names[index],
			&performance_pause_definitions[index]);
		if (performance_pause_tags[index] == NONE)
			return FALSE;
	}

	/* Native pause entries retain Resume, Quit, their actions and all three
	 * original viewport placements. The list gains PB and local settings. */
	for (layout = 0; layout < 3; layout++)
	{
		struct ui_widget_definition *pause = &performance_pause_definitions[_pp_pause_1p + layout];
		struct ui_widget_definition *list = &performance_pause_definitions[_pp_list_1p + layout];
		struct ui_widget_definition *entry = &performance_pause_definitions[_pp_entry_1p + layout];
		struct ui_widget_definition *settings = &performance_pause_definitions[_pp_settings_1p + layout];
		struct ui_widget_definition *options = &performance_pause_definitions[_pp_options_1p + layout];
		struct ui_widget_child_reference *children = original_roots[layout]->child_widgets.address;
		boolean found_list = FALSE;
		short x = (original_roots[layout]->bounds.x1 - 202) / 2;
		short y = (original_roots[layout]->bounds.y1 - 240) / 2;
		*pause = *original_roots[layout];
		csmemcpy(performance_pause_children[layout], children, sizeof(performance_pause_children[layout]));
		for (index = 0; index < 3; index++)
		{
			if (performance_pause_children[layout][index].widget_tag.index == list_tag)
			{
				performance_pause_children[layout][index].widget_tag.index = performance_pause_tags[_pp_list_1p + layout];
				performance_pause_children[layout][index].vertical_offset -= 28;
				found_list = TRUE;
			}
		}
		if (!found_list)
			return FALSE;
		performance_pause_block(&pause->child_widgets, 3, performance_pause_children[layout]);
		*list = *original_list;
		list->bounds.y1 = list->bounds.y0 + 111;
		performance_pause_list_children[layout][0] = original_list_children[0];
		performance_pause_list_children[layout][3] = original_list_children[1];
		performance_pause_list_children[layout][0].vertical_offset = 0;
		performance_pause_list_children[layout][3].vertical_offset = 84;
		performance_pause_child(&performance_pause_list_children[layout][1],
			performance_pause_tags[_pp_entry_1p + layout], 0, 28);
		performance_pause_child(&performance_pause_list_children[layout][2],
			performance_pause_tags[_pp_settings_1p + layout], 0, 56);
		performance_pause_block(&list->child_widgets, 4, performance_pause_list_children[layout]);
		*entry = *original_resume;
		performance_pause_reference(&entry->text_label_string_list, UNICODE_STRING_LIST_TAG,
			performance_pause_string_tags[0]);
		entry->string_list_index = 0;
		performance_pause_event_definition(&performance_pause_entry_events[layout][0],
			_gamepad_analog_button_a, 0, FLAG(_event_handler_open_widget_bit), performance_pause_tags[_pp_options_1p + layout]);
		performance_pause_event_definition(&performance_pause_entry_events[layout][1],
			_gamepad_binary_button_start, 0, FLAG(_event_handler_open_widget_bit), performance_pause_tags[_pp_options_1p + layout]);
		performance_pause_block(&entry->event_handlers, 2, performance_pause_entry_events[layout]);
		*settings = *entry;
		settings->string_list_index = 15;
		{
			long settings_tag = game_settings_pause_tag((short)layout);
			if (settings_tag == NONE) return FALSE;
			performance_pause_event_definition(&performance_pause_settings_events[layout][0],
				_gamepad_analog_button_a, 0, FLAG(_event_handler_open_widget_bit), settings_tag);
			performance_pause_event_definition(&performance_pause_settings_events[layout][1],
				_gamepad_binary_button_start, 0, FLAG(_event_handler_open_widget_bit), settings_tag);
			performance_pause_block(&settings->event_handlers, 2, performance_pause_settings_events[layout]);
		}

		options->type = _ui_widget_type_container;
		/* Opening a submenu must keep the local player who invoked it. The
		 * launch path treats a zero controller index as an explicit player 0. */
		options->controller_index = _widget_controller_any;
		options->bounds = pause->bounds;
		options->flags = FLAG(_widget_pass_unhandled_events_to_children_bit);
		options->background_bitmap = pause->background_bitmap;
		performance_pause_block(&options->event_handlers, 3, performance_pause_root_events);
		/* The non-interactive frame draws first. Native 27-pixel buttons end
		 * at the original footer divider; split-screen keeps its full legend. */
		performance_pause_child(&performance_pause_option_children[layout][0], frame_tag, x - 8, y);
		performance_pause_child(&performance_pause_option_children[layout][1], performance_pause_tags[_pp_column], x, y + 22);
		performance_pause_child(&performance_pause_option_children[layout][2], performance_pause_tags[_pp_title], x, y);
		performance_pause_child(&performance_pause_option_children[layout][3], legend_tag, x + 17, y + 215);
		performance_pause_child(&performance_pause_option_children[layout][4], performance_pause_tags[_pp_footer], x - 41, y + 242);
		performance_pause_block(&options->child_widgets, layout == 0 ? 5 : 4, performance_pause_option_children[layout]);
	}
	performance_pause_event_definition(&performance_pause_root_events[0],
		_widget_event_created, _performance_pause_created, FLAG(_event_handler_run_function_bit), NONE);
	performance_pause_event_definition(&performance_pause_root_events[1],
		_widget_event_b_button, 0, FLAG(_event_handler_go_back_to_previous_widget_bit), NONE);
	performance_pause_event_definition(&performance_pause_root_events[2],
		_widget_event_back_button, 0, FLAG(_event_handler_go_back_to_previous_widget_bit), NONE);
	performance_pause_event_definition(&performance_pause_apply_events[0],
		_gamepad_analog_button_a, _performance_pause_apply,
		FLAG(_event_handler_run_function_bit) | FLAG(_event_handler_go_back_to_previous_widget_bit), NONE);
	performance_pause_event_definition(&performance_pause_apply_events[1],
		_gamepad_binary_button_start, _performance_pause_apply,
		FLAG(_event_handler_run_function_bit) | FLAG(_event_handler_go_back_to_previous_widget_bit), NONE);
	performance_pause_event_definition(&performance_pause_spinner_events[0],
		_gamepad_analog_button_a, _performance_pause_next, FLAG(_event_handler_run_function_bit), NONE);

	performance_pause_definitions[_pp_column].type = _ui_widget_type_column_list;
	performance_pause_definitions[_pp_column].flags =
		FLAG(_widget_pass_unhandled_events_to_children_bit) | FLAG(_widget_dpad_updown_tabs_thru_list_items_bit);
	performance_pause_definitions[_pp_column].bounds.x1 = 202;
	performance_pause_definitions[_pp_column].bounds.y1 = 189;
	performance_pause_block(&performance_pause_definitions[_pp_column].child_widgets, 7, performance_pause_column_children);
	for (index = _pp_preset; index <= _pp_footer; index++)
	{
		struct ui_widget_definition *definition = &performance_pause_definitions[index];
		definition->type = _ui_widget_type_text_box;
		definition->bounds.x1 = 202;
		definition->bounds.y1 = 27;
		definition->text_font = original_resume->text_font;
		definition->horizontal_offset = original_resume->horizontal_offset;
		definition->vertical_offset = original_resume->vertical_offset;
		definition->text_color = original_resume->text_color;
		definition->justification = _text_justification_center;
		performance_pause_reference(&definition->text_label_string_list,
			UNICODE_STRING_LIST_TAG, performance_pause_string_tags[0]);
		if (index <= _pp_apply)
		{
			definition->background_bitmap = original_resume->background_bitmap;
			performance_pause_child(&performance_pause_column_children[index - _pp_preset],
				performance_pause_tags[index], 0, (index - _pp_preset) * 27);
		}
		if (index <= _pp_weapon)
		{
			definition->type = _ui_widget_type_spinner_list;
			definition->flags = FLAG(_widget_dpad_leftright_tabs_thru_list_items_bit);
			definition->list_flags = FLAG(_list_items_generated_from_string_list_tag);
			definition->text_label_string_list.index = performance_pause_string_tags[index - _pp_preset + 1];
			performance_pause_block(&definition->event_handlers, 1, performance_pause_spinner_events);
		}
	}
	performance_pause_definitions[_pp_apply].string_list_index = 1;
	performance_pause_block(&performance_pause_definitions[_pp_apply].event_handlers, 2, performance_pause_apply_events);
	performance_pause_definitions[_pp_title].text_font = original_resume->text_font;
	/* large_ui has a 21-pixel line advance; these uppercase glyphs occupy
	 * y4..17, leaving the authored top border visible in the 22-pixel title. */
	performance_pause_definitions[_pp_title].bounds.y1 = 22;
	performance_pause_definitions[_pp_title].horizontal_offset = 0;
	performance_pause_definitions[_pp_title].vertical_offset = 0;
	performance_pause_definitions[_pp_title].string_list_index = 12;
	/* The native small_ui font has a 20-pixel line advance. */
	performance_pause_definitions[_pp_footer].bounds.y1 = 40;
	performance_pause_definitions[_pp_footer].bounds.x1 = 284;
	performance_pause_definitions[_pp_footer].text_font.index = font;
	performance_pause_definitions[_pp_footer].horizontal_offset = 0;
	performance_pause_definitions[_pp_footer].vertical_offset = 0;
	performance_pause_definitions[_pp_footer].string_list_index = 3;
	performance_pause_ready = TRUE;
	return TRUE;
}

static long performance_pause_remap_tag(long tag)
{
	short layout;
	if (tag == NONE)
		return tag;
	for (layout = 0; layout < 3; layout++)
	{
		if (tag == tag_loaded(UI_WIDGET_DEFINITION_TAG, performance_pause_original_names[layout]))
			return performance_pause_build() ? performance_pause_tags[_pp_pause_1p + layout] : tag;
	}
	return tag;
}

static boolean performance_pause_is_spinner(struct widget_instance *widget)
{
	short index;
	if (!performance_pause_ready || !widget || widget->definition_tag_index == NONE) return FALSE;
	for (index = _pp_preset; index <= _pp_weapon; index++)
		if (widget->definition_tag_index == performance_pause_tags[index]) return TRUE;
	return FALSE;
}

static short performance_pause_preset(unsigned flags)
{
	return flags == 0 ? 0 : (flags == PERFORMANCE_PRACTICE_FLAGS ? 1 : 2);
}

static struct performance_pause_draft *performance_pause_draft_for(struct widget_instance *widget)
{
	short local;
	while (widget && widget->parent)
		widget = widget->parent;
	if (!widget || !performance_pause_ready ||
		(widget->definition_tag_index != performance_pause_tags[_pp_options_1p] &&
		 widget->definition_tag_index != performance_pause_tags[_pp_options_2p] &&
		 widget->definition_tag_index != performance_pause_tags[_pp_options_4p]))
		return NULL;
	local = widget->local_player_index;
	if (local == NONE)
		local = 0;
	if (local < 0 || local >= MAXIMUM_NUMBER_OF_LOCAL_PLAYERS)
		return NULL;
	return &performance_pause_drafts[local];
}

static void performance_pause_update(struct widget_instance *widget)
{
	struct performance_pause_draft *draft = performance_pause_draft_for(widget);
	struct widget_instance *preset, *timer, *markers, *audio, *movement, *weapon, *apply, *footer, *focus;
	boolean editable = global_network_game_server_get() != NULL;
	unsigned flags;
	if (!draft || !draft->root)
		return;
	widget = draft->root;
	preset = widget_instance_find_by_tag_index_recursive(widget, performance_pause_tags[_pp_preset]);
	timer = widget_instance_find_by_tag_index_recursive(widget, performance_pause_tags[_pp_timer]);
	markers = widget_instance_find_by_tag_index_recursive(widget, performance_pause_tags[_pp_markers]);
	audio = widget_instance_find_by_tag_index_recursive(widget, performance_pause_tags[_pp_audio]);
	movement = widget_instance_find_by_tag_index_recursive(widget, performance_pause_tags[_pp_movement]);
	weapon = widget_instance_find_by_tag_index_recursive(widget, performance_pause_tags[_pp_weapon]);
	apply = widget_instance_find_by_tag_index_recursive(widget, performance_pause_tags[_pp_apply]);
	footer = widget_instance_find_by_tag_index_recursive(widget, performance_pause_tags[_pp_footer]);
	if (!preset || !timer || !markers || !audio || !movement || !weapon || !apply)
		return;
	if (!editable)
	{
		draft->flags = performance_options_get_flags() & PERFORMANCE_OPTIONS_MASK;
		draft->preset = performance_pause_preset(draft->flags);
	}
	else if (preset->parameters.list.selected_index != draft->preset)
	{
		draft->preset = preset->parameters.list.selected_index;
		if (draft->preset == 0)
			draft->flags = 0;
		else if (draft->preset == 1)
			draft->flags = PERFORMANCE_PRACTICE_FLAGS;
	}
	else
	{
		flags = (timer->parameters.list.selected_index ? _performance_option_match_timer : 0) |
			(markers->parameters.list.selected_index ? _performance_option_spawn_markers : 0) |
			(audio->parameters.list.selected_index ? _performance_option_timer_audio : 0) |
			(movement->parameters.list.selected_index ? _performance_option_silent_movement : 0) |
			(weapon->parameters.list.selected_index ? _performance_option_silent_weapon_ready : 0);
		if (flags != draft->flags)
		{
			draft->flags = flags;
			draft->preset = performance_pause_preset(flags);
		}
	}
	preset->parameters.list.selected_index = draft->preset;
	timer->parameters.list.selected_index = (draft->flags & _performance_option_match_timer) != 0;
	markers->parameters.list.selected_index = (draft->flags & _performance_option_spawn_markers) != 0;
	audio->parameters.list.selected_index = (draft->flags & _performance_option_timer_audio) != 0;
	movement->parameters.list.selected_index = (draft->flags & _performance_option_silent_movement) != 0;
	weapon->parameters.list.selected_index = (draft->flags & _performance_option_silent_weapon_ready) != 0;
	preset->disabled = timer->disabled = markers->disabled = audio->disabled = movement->disabled = weapon->disabled = !editable;
	apply->parameters.text_box.string_list_index = editable ? 1 : 2;
	if (footer) footer->parameters.text_box.string_list_index = editable ? 3 : 4;
	if (footer && editable)
		for (focus = widget; focus; focus = focus->focused_child)
		{
			if (focus == markers) footer->parameters.text_box.string_list_index = 22;
			if (focus == audio) footer->parameters.text_box.string_list_index = 23;
			if (focus == movement) footer->parameters.text_box.string_list_index = 20;
			if (focus == weapon) footer->parameters.text_box.string_list_index = 21;
		}
}

static boolean performance_pause_event(struct widget_instance *widget, short function)
{
	struct performance_pause_draft *draft = performance_pause_draft_for(widget);
	if (!draft)
		return FALSE;
	if (function == _performance_pause_created)
	{
		struct widget_instance *preset = widget_instance_find_by_tag_index_recursive(widget, performance_pause_tags[_pp_preset]);
		struct widget_instance *timer = widget_instance_find_by_tag_index_recursive(widget, performance_pause_tags[_pp_timer]);
		struct widget_instance *markers = widget_instance_find_by_tag_index_recursive(widget, performance_pause_tags[_pp_markers]);
		struct widget_instance *audio = widget_instance_find_by_tag_index_recursive(widget, performance_pause_tags[_pp_audio]);
		struct widget_instance *movement = widget_instance_find_by_tag_index_recursive(widget, performance_pause_tags[_pp_movement]);
		struct widget_instance *weapon = widget_instance_find_by_tag_index_recursive(widget, performance_pause_tags[_pp_weapon]);
		if (!preset || !timer || !markers || !audio || !movement || !weapon)
		{
			draft->root = NULL;
			return FALSE;
		}
		draft->root = widget;
		draft->flags = performance_options_get_flags() & PERFORMANCE_OPTIONS_MASK;
		draft->preset = performance_pause_preset(draft->flags);
		/* Set all selections before update so opening never treats the native
		 * default zero selection as an edit of the host's current settings. */
		preset->parameters.list.selected_index = draft->preset;
		timer->parameters.list.selected_index = (draft->flags & _performance_option_match_timer) != 0;
		markers->parameters.list.selected_index = (draft->flags & _performance_option_spawn_markers) != 0;
		audio->parameters.list.selected_index = (draft->flags & _performance_option_timer_audio) != 0;
		movement->parameters.list.selected_index = (draft->flags & _performance_option_silent_movement) != 0;
		weapon->parameters.list.selected_index = (draft->flags & _performance_option_silent_weapon_ready) != 0;
		performance_pause_update(widget);
		return TRUE;
	}
	if (function == _performance_pause_apply)
	{
		if (!draft->root)
			return FALSE;
		performance_pause_update(widget);
		/* Guests can return with A but cannot write; the server setter also
		 * rechecks authority and peer capability at the moment of Apply. */
		return global_network_game_server_get() == NULL || performance_options_set_host_flags(draft->flags);
	}
	if (function == _performance_pause_next && global_network_game_server_get() != NULL)
	{
		boolean deleted = FALSE;
		struct event_record event = {0};
		if (widget->type != _ui_widget_type_spinner_list || widget->parameters.list.number_of_items == 0)
			return FALSE;
		widget_event_function_list_widget_goto_next_item(widget, &event, &deleted);
		performance_pause_update(widget);
		return TRUE;
	}
	return FALSE;
}
