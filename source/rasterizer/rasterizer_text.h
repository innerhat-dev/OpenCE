/*
RASTERIZER_TEXT.H
*/

#ifndef __RASTERIZER_TEXT_H
#define __RASTERIZER_TEXT_H
#pragma once

/* ---------- headers */

#include "cseries.h"
#include "math/integer_math.h"

/* ---------- structures */

struct bitmap_data;
struct dynamic_screen_vertex;
struct font_character;
struct font_header;
struct parse_string_state;
struct rasterizer_dynamic_screen_geometry_parameters;

/* ---------- prototypes/RASTERIZER_TEXT.C */

void lock_rasterizer_text_data(
	void);
void unlock_rasterizer_text_data(
	void);
boolean rasterizer_text_cache_initialize(
	void);
void rasterizer_text_draw_character(
	struct dynamic_screen_vertex const *vertices);
void rasterizer_text_begin(
	struct rasterizer_dynamic_screen_geometry_parameters const *parameters);
void rasterizer_text_end(
	void);

#ifdef HALO_PORT_MAXIMUM_NETWORK_PLAYERS
/* Scale only this text's glyph quads and stock shadows, leaving font layout,
 * texture coordinates, projection and later text draws unchanged. */
void rasterizer_draw_string_scaled(
	rectangle2d const *bounds,
	rectangle2d const *clip,
	char const *string,
	float scale,
	float anchor_x,
	float anchor_y);
#endif

#endif // __RASTERIZER_TEXT_H
