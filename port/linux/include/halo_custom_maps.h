/* Native-port extensions for compatible Xbox v5 multiplayer caches. */
#ifndef HALO_CUSTOM_MAPS_H
#define HALO_CUSTOM_MAPS_H

#define HALO_CUSTOM_MAP_LIMIT 128
#define HALO_CUSTOM_MAP_NAME_SIZE 32
/* -1 already means the tag's default string; -2 uses the widget's own text. */
#define HALO_CUSTOM_MAP_TEXT (-2)

char **native_multiplayer_map_list(char **stock, short stock_count, short *count);
int native_map_is_custom(char const *map);
char const *native_map_basename(char const *map);
int native_map_header_valid(unsigned char const *header, char const *filename);

#endif
