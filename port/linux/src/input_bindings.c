/* Input bindings are read once from [bindings] in config.toml. No SDL objects
   or host calls are needed to turn their stable names into physical scancodes. */
#include "platform.h"
#include "input_bindings.h"
#include "port_config.h"

#include <SDL3/SDL_mouse.h>
#include <ctype.h>
#include <stdio.h>
#include <string.h>

struct named_key
{
	const char *name;
	SDL_Scancode key;
	SDL_Scancode second; /* Ctrl/Shift/Alt/Cmd mean either side. */
};

static const struct named_key named_keys[] =
{
	{ "space", SDL_SCANCODE_SPACE, 0 },
	{ "return", SDL_SCANCODE_RETURN, 0 }, { "enter", SDL_SCANCODE_RETURN, 0 },
	{ "escape", SDL_SCANCODE_ESCAPE, 0 }, { "esc", SDL_SCANCODE_ESCAPE, 0 },
	{ "tab", SDL_SCANCODE_TAB, 0 }, { "backspace", SDL_SCANCODE_BACKSPACE, 0 },
	{ "grave", SDL_SCANCODE_GRAVE, 0 }, { "backquote", SDL_SCANCODE_GRAVE, 0 },
	{ "backtick", SDL_SCANCODE_GRAVE, 0 },
	{ "ctrl", SDL_SCANCODE_LCTRL, SDL_SCANCODE_RCTRL },
	{ "control", SDL_SCANCODE_LCTRL, SDL_SCANCODE_RCTRL },
	{ "shift", SDL_SCANCODE_LSHIFT, SDL_SCANCODE_RSHIFT },
	{ "alt", SDL_SCANCODE_LALT, SDL_SCANCODE_RALT },
	{ "option", SDL_SCANCODE_LALT, SDL_SCANCODE_RALT },
	{ "cmd", SDL_SCANCODE_LGUI, SDL_SCANCODE_RGUI },
	{ "command", SDL_SCANCODE_LGUI, SDL_SCANCODE_RGUI },
	{ "gui", SDL_SCANCODE_LGUI, SDL_SCANCODE_RGUI },
	{ "leftctrl", SDL_SCANCODE_LCTRL, 0 }, { "rightctrl", SDL_SCANCODE_RCTRL, 0 },
	{ "leftcontrol", SDL_SCANCODE_LCTRL, 0 }, { "rightcontrol", SDL_SCANCODE_RCTRL, 0 },
	{ "leftshift", SDL_SCANCODE_LSHIFT, 0 }, { "rightshift", SDL_SCANCODE_RSHIFT, 0 },
	{ "leftalt", SDL_SCANCODE_LALT, 0 }, { "rightalt", SDL_SCANCODE_RALT, 0 },
	{ "leftoption", SDL_SCANCODE_LALT, 0 }, { "rightoption", SDL_SCANCODE_RALT, 0 },
	{ "leftcmd", SDL_SCANCODE_LGUI, 0 }, { "rightcmd", SDL_SCANCODE_RGUI, 0 },
	{ "leftgui", SDL_SCANCODE_LGUI, 0 }, { "rightgui", SDL_SCANCODE_RGUI, 0 },
	{ "up", SDL_SCANCODE_UP, 0 }, { "down", SDL_SCANCODE_DOWN, 0 },
	{ "left", SDL_SCANCODE_LEFT, 0 }, { "right", SDL_SCANCODE_RIGHT, 0 },
	{ "capslock", SDL_SCANCODE_CAPSLOCK, 0 },
	{ "home", SDL_SCANCODE_HOME, 0 }, { "end", SDL_SCANCODE_END, 0 },
	{ "pageup", SDL_SCANCODE_PAGEUP, 0 }, { "pagedown", SDL_SCANCODE_PAGEDOWN, 0 },
	{ "insert", SDL_SCANCODE_INSERT, 0 }, { "delete", SDL_SCANCODE_DELETE, 0 },
	{ "printscreen", SDL_SCANCODE_PRINTSCREEN, 0 },
	{ "scrolllock", SDL_SCANCODE_SCROLLLOCK, 0 }, { "pause", SDL_SCANCODE_PAUSE, 0 },
	{ "minus", SDL_SCANCODE_MINUS, 0 }, { "equals", SDL_SCANCODE_EQUALS, 0 },
	{ "leftbracket", SDL_SCANCODE_LEFTBRACKET, 0 },
	{ "rightbracket", SDL_SCANCODE_RIGHTBRACKET, 0 },
	{ "backslash", SDL_SCANCODE_BACKSLASH, 0 },
	{ "semicolon", SDL_SCANCODE_SEMICOLON, 0 },
	{ "apostrophe", SDL_SCANCODE_APOSTROPHE, 0 }, { "quote", SDL_SCANCODE_APOSTROPHE, 0 },
	{ "comma", SDL_SCANCODE_COMMA, 0 }, { "period", SDL_SCANCODE_PERIOD, 0 },
	{ "slash", SDL_SCANCODE_SLASH, 0 },
	{ "keypadenter", SDL_SCANCODE_KP_ENTER, 0 }, { "kpenter", SDL_SCANCODE_KP_ENTER, 0 },
	{ "keypadplus", SDL_SCANCODE_KP_PLUS, 0 },
	{ "keypadminus", SDL_SCANCODE_KP_MINUS, 0 },
	{ "keypadmultiply", SDL_SCANCODE_KP_MULTIPLY, 0 },
	{ "keypaddivide", SDL_SCANCODE_KP_DIVIDE, 0 },
	{ "keypadperiod", SDL_SCANCODE_KP_PERIOD, 0 },
	{ "numlock", SDL_SCANCODE_NUMLOCKCLEAR, 0 },
	{ "acback", SDL_SCANCODE_AC_BACK, 0 },
};

static int parse_token(const char *token, size_t length, struct input_binding *binding)
{
	char name[64];
	size_t index, used = 0;
	SDL_Scancode key = SDL_SCANCODE_UNKNOWN;
	int number, consumed = 0;

	while (length && isspace((unsigned char)*token)) { token++; length--; }
	while (length && isspace((unsigned char)token[length - 1])) length--;
	if (!length || length >= sizeof(name))
		return 0;
	if (length == 1)
	{
		unsigned char c = (unsigned char)tolower((unsigned char)*token);

		if (c >= 'a' && c <= 'z') key = (SDL_Scancode)(SDL_SCANCODE_A + c - 'a');
		else if (c >= '1' && c <= '9') key = (SDL_Scancode)(SDL_SCANCODE_1 + c - '1');
		else switch (c)
		{
		case '0': key = SDL_SCANCODE_0; break;
		case '`': key = SDL_SCANCODE_GRAVE; break;
		case '-': key = SDL_SCANCODE_MINUS; break;
		case '=': key = SDL_SCANCODE_EQUALS; break;
		case '[': key = SDL_SCANCODE_LEFTBRACKET; break;
		case ']': key = SDL_SCANCODE_RIGHTBRACKET; break;
		case '\\': key = SDL_SCANCODE_BACKSLASH; break;
		case ';': key = SDL_SCANCODE_SEMICOLON; break;
		case '\'': key = SDL_SCANCODE_APOSTROPHE; break;
		case '.': key = SDL_SCANCODE_PERIOD; break;
		case '/': key = SDL_SCANCODE_SLASH; break;
		}
		if (key != SDL_SCANCODE_UNKNOWN)
		{
			binding->keys[key] = 1;
			return 1;
		}
	}
	/* Ignore spaces/underscores/hyphens in names: Left Ctrl = left_ctrl. */
	for (index = 0; index < length; index++)
	{
		unsigned char c = (unsigned char)token[index];
		if (isspace(c) || c == '_' || c == '-') continue;
		name[used++] = (char)tolower(c);
	}
	name[used] = 0;
	for (index = 0; index < sizeof(named_keys) / sizeof(named_keys[0]); index++)
	{
		if (strcmp(name, named_keys[index].name)) continue;
		binding->keys[named_keys[index].key] = 1;
		if (named_keys[index].second) binding->keys[named_keys[index].second] = 1;
		return 1;
	}
	if (sscanf(name, "f%d%n", &number, &consumed) == 1 && name[consumed] == 0 && number >= 1 && number <= 24)
	{
		key = (SDL_Scancode)(number <= 12 ? SDL_SCANCODE_F1 + number - 1 : SDL_SCANCODE_F13 + number - 13);
		binding->keys[key] = 1;
		return 1;
	}
	consumed = 0;
	if ((sscanf(name, "keypad%d%n", &number, &consumed) == 1 ||
		sscanf(name, "kp%d%n", &number, &consumed) == 1) && name[consumed] == 0 && number >= 0 && number <= 9)
	{
		binding->keys[number ? SDL_SCANCODE_KP_1 + number - 1 : SDL_SCANCODE_KP_0] = 1;
		return 1;
	}
	if (!strcmp(name, "wheel") || !strcmp(name, "mousewheel"))
	{
		binding->wheel = 1;
		return 1;
	}
	{
		static const char *mouse_names[] = { "mouseleft", "mousemiddle", "mouseright", "mousex1", "mousex2" };
		for (index = 0; index < sizeof(mouse_names) / sizeof(mouse_names[0]); index++)
		{
			if (!strcmp(name, mouse_names[index]))
			{
				binding->mouse_buttons |= 1U << (index + 1);
				return 1;
			}
		}
	}
	return 0;
}

int input_binding_parse(const char *text, struct input_binding *binding)
{
	struct input_binding parsed = { { 0 }, 0, 0 };
	const char *token = text;

	/* Empty (including whitespace-only) explicitly unbinds the action. */
	while (isspace((unsigned char)*token)) token++;
	if (*token)
	{
		for (;;)
		{
			size_t length = strcspn(token, ",");
			if (!parse_token(token, length, &parsed))
			{
				memset(binding, 0, sizeof(*binding));
				return 0;
			}
			if (!token[length]) break;
			token += length + 1;
		}
	}
	*binding = parsed;
	return 1;
}

static struct input_binding bindings[_binding_count];
static pthread_mutex_t bindings_lock = PTHREAD_MUTEX_INITIALIZER;
static int bindings_loaded;

static void load_bindings(void)
{
	static const struct { const char *name, *fallback; } settings[] =
	{
#if defined(HALO_MACOS) && !defined(HALO_IOS)
#define BINDING(name, mac, other, comment) { "bindings." #name, mac },
#else
#define BINDING(name, mac, other, comment) { "bindings." #name, other },
#endif
#include "input_bindings.def"
#undef BINDING
	};
	int action;

	for (action = 0; action < _binding_count; action++)
	{
		const char *text = config_string(settings[action].name);
		int valid = input_binding_parse(text, &bindings[action]);

		if (action == _binding_console || action == _binding_release_mouse)
			valid = valid && !bindings[action].mouse_buttons && !bindings[action].wheel;
		if (!valid)
		{
			platform_log("%s: invalid binding '%s'; using '%s'", settings[action].name, text, settings[action].fallback);
			input_binding_parse(settings[action].fallback, &bindings[action]);
		}
	}
}

/* The rebased guest supplies mutexes, but not pthread_once's cancellation
   cleanup helpers. Publish the immutable table with an acquire/release guard. */
static void ensure_bindings(void)
{
	if (__atomic_load_n(&bindings_loaded, __ATOMIC_ACQUIRE)) return;
	pthread_mutex_lock(&bindings_lock);
	if (!__atomic_load_n(&bindings_loaded, __ATOMIC_RELAXED))
	{
		load_bindings();
		__atomic_store_n(&bindings_loaded, 1, __ATOMIC_RELEASE);
	}
	pthread_mutex_unlock(&bindings_lock);
}

int input_binding_down(enum input_binding_action action, const unsigned char *keys,
	const unsigned char *mouse_buttons, int wheel)
{
	const struct input_binding *binding;
	int index;

	ensure_bindings();
	if (action < 0 || action >= _binding_count) return 0;
	binding = &bindings[action];
	if (keys)
		for (index = 1; index < SDL_SCANCODE_COUNT; index++)
			if (binding->keys[index] && keys[index]) return 1;
	if (mouse_buttons)
		for (index = SDL_BUTTON_LEFT; index <= SDL_BUTTON_X2; index++)
			if ((binding->mouse_buttons & (1U << index)) && mouse_buttons[index]) return 1;
	return binding->wheel && wheel;
}

int input_binding_matches_key(enum input_binding_action action, SDL_Scancode key)
{
	ensure_bindings();
	return action >= 0 && action < _binding_count && key > 0 && key < SDL_SCANCODE_COUNT && bindings[action].keys[key];
}

unsigned char input_binding_console_key(SDL_Scancode key, unsigned char virtual_key)
{
	if (input_binding_matches_key(_binding_console, key)) return 0xc0;
	/* A physical backtick bound to Select must not also open/close the console. */
	return virtual_key == 0xc0 ? 0 : virtual_key;
}
