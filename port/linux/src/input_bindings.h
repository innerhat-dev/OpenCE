/* Configurable physical keys and mouse buttons, shared by SDL input and XInput. */
#ifndef HALO_INPUT_BINDINGS_H
#define HALO_INPUT_BINDINGS_H

#include <SDL3/SDL_scancode.h>

enum input_binding_action
{
#define BINDING(name, mac, other, comment) _binding_##name,
#include "input_bindings.def"
#undef BINDING
	_binding_count
};

struct input_binding
{
	unsigned char keys[SDL_SCANCODE_COUNT];
	unsigned mouse_buttons;
	int wheel;
};

/* Parse a complete binding; invalid tokens reject it without a partial result. */
int input_binding_parse(const char *text, struct input_binding *binding);
/* A held key/button or the wheel's short pulse holds its controller action. */
int input_binding_down(enum input_binding_action action, const unsigned char *keys,
	const unsigned char *mouse_buttons, int wheel);
/* For event-driven keyboard hotkeys; mouse/wheel bindings are not allowed there. */
int input_binding_matches_key(enum input_binding_action action, SDL_Scancode key);
/* Translate only the configured console key into the game's backquote key. */
unsigned char input_binding_console_key(SDL_Scancode key, unsigned char virtual_key);

#endif
