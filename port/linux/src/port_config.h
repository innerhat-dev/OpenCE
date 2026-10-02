/*
PORT_CONFIG.H

The native ports' settings, read from config.toml (port_config.c): next to
the executable on the desktop, in the data folder (the one holding maps/)
on Android. A missing file is written with the defaults. Each setting can
also be set for one run with its HALO_* environment variable when it has one, which wins
over the file (the tools and the Android app pass settings that way).

Settings are named "section.key", as in the file: "display.vsync".
*/

#ifndef PORT_CONFIG_H
#define PORT_CONFIG_H

int config_boolean(const char *name);
long config_integer(const char *name);
double config_real(const char *name);
/* never NULL; "" when unset */
const char *config_string(const char *name);
/* saves a boolean token into config.toml, preserving other text, and applies
it to this session only after a successful write; 1 on success */
int config_write_boolean(const char *name, int value);
/* Save registered boolean, integer and real settings as one atomic file update,
then apply all values to this session. Boolean values must be 0 or 1; numeric
values must be finite and integers exact. Returns 0 without applying any value
if validation or persistence fails. Other keys and comments are preserved. */
int config_write_numbers(const char *const *names, const double *values, unsigned count);

#endif
