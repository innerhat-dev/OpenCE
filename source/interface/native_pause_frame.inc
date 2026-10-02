/* The larger native option pages retain the pause dialog's authored corners.
 * Its three resident textures have a 159-pixel panel in a 256-pixel texture;
 * ordinary widget bounds crop texture coordinates instead of stretching it.
 * Only this runtime tag is rendered through the explicit source rectangles. */
#define NATIVE_PAUSE_FRAME_NAME "ui\\native_settings\\pause_frame_"
static char const *const native_pause_frame_names[3] = {
	NATIVE_PAUSE_FRAME_NAME "159", NATIVE_PAUSE_FRAME_NAME "213", NATIVE_PAUSE_FRAME_NAME "240"};
static short const native_pause_frame_heights[3] = {159, 213, 240};
static struct ui_widget_definition native_pause_frame_definitions[3];
static long native_pause_frame_indices[3];
static long native_pause_frame_bitmaps[3];
static boolean native_pause_frame_ready;

static long native_pause_legend_tag(void)
{
	return tag_loaded(UI_WIDGET_DEFINITION_TAG, "ui\\shell\\main_menu\\button_key_sm");
}

static long native_pause_frame_tag(short height)
{
	static char const *const names[3] = {
		"ui\\shell\\bitmaps\\pausebox2_left",
		"ui\\shell\\bitmaps\\pausebox2_center",
		"ui\\shell\\bitmaps\\pausebox2_right"};
	struct ui_widget_definition *definition;
	short index, frame;
	for (frame = 0; frame < 3; frame++)
		if (height == native_pause_frame_heights[frame]) break;
	if (frame == 3) return NONE;
	if (native_pause_frame_ready &&
		tag_loaded(UI_WIDGET_DEFINITION_TAG, native_pause_frame_names[0]) == native_pause_frame_indices[0])
		return native_pause_frame_indices[frame];
	native_pause_frame_ready = FALSE;
	for (index = 0; index < 3; index++)
	{
		native_pause_frame_bitmaps[index] = tag_loaded('bitm', names[index]);
		if (native_pause_frame_bitmaps[index] == NONE) return NONE;
	}
	if (native_pause_legend_tag() == NONE) return NONE;
	for (index = 0; index < 3; index++)
	{
		definition = &native_pause_frame_definitions[index];
		csmemset(definition, 0, sizeof(*definition));
		definition->type = _ui_widget_type_container;
		definition->controller_index = _widget_controller_any;
		definition->bounds.x0 = -4;
		definition->bounds.x1 = 222;
		definition->bounds.y1 = native_pause_frame_heights[index];
		definition->background_bitmap.group_tag = 'bitm';
		definition->background_bitmap.index = NONE;
		definition->text_label_string_list.group_tag = UNICODE_STRING_LIST_TAG;
		definition->text_label_string_list.index = NONE;
		definition->text_font.group_tag = FONT_GROUP_TAG;
		definition->text_font.index = NONE;
		definition->list_header_bitmap.group_tag = definition->list_footer_bitmap.group_tag = 'bitm';
		definition->list_header_bitmap.index = definition->list_footer_bitmap.index = NONE;
		definition->extended_description_widget.group_tag = UI_WIDGET_DEFINITION_TAG;
		definition->extended_description_widget.index = NONE;
		native_pause_frame_indices[index] = cache_files_register_runtime_ui_tag(
			UI_WIDGET_DEFINITION_TAG, native_pause_frame_names[index], definition);
		if (native_pause_frame_indices[index] == NONE) return NONE;
	}
	native_pause_frame_ready = TRUE;
	return native_pause_frame_indices[frame];
}

static boolean native_pause_frame_is_widget(long tag)
{
	short index;
	if (!native_pause_frame_ready || tag == NONE) return FALSE;
	for (index = 0; index < 3; index++)
		if (tag == native_pause_frame_indices[index]) return TRUE;
	return FALSE;
}

static void native_pause_frame_slice(short piece, short band, short height, point2d origin,
	rectangle2d *destination, rectangle2d *source)
{
	static short const x[3] = {-4, 12, 206};
	static short const widths[3] = {16, 194, 16};
	static short const source_y[4] = {0, 16, 128, 159};
	short destination_y[4] = {0, 16, height - 31, height};
	destination->x0 = origin.x + x[piece];
	destination->x1 = destination->x0 + widths[piece];
	destination->y0 = origin.y + destination_y[band];
	destination->y1 = origin.y + destination_y[band + 1];
	source->x0 = 0;
	source->x1 = piece == 1 ? 4 : 16;
	source->y0 = source_y[band];
	source->y1 = source_y[band + 1];
}
