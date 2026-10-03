/* Discover v5 multiplayer maps through the existing platform file API.
   Cache loading uses the basename and the cache's scenario tag index, so a
   custom map does not need to pretend its source scenario used a stock path. */
#include "cseries.h"
#include "cache/cache_files.h"
#include "halo_custom_maps.h"
#include <xtl.h>

static char *map_list[HALO_CUSTOM_MAP_LIMIT];
static char custom_names[HALO_CUSTOM_MAP_LIMIT][HALO_CUSTOM_MAP_NAME_SIZE];
static short map_count;

static char const *stock_names[] = {
    "beavercreek", "sidewinder", "damnation", "ratrace", "prisoner",
    "hangemhigh", "chillout", "carousel", "boardingaction", "bloodgulch",
    "wizard", "putput", "longest"
};

char const *native_map_basename(char const *map)
{
    char const *p, *name = map;
    if (!map) return "";
    for (p = map; *p; p++)
        if (*p == '\\' || *p == '/') name = p + 1;
    return name;
}

int native_map_is_custom(char const *map)
{
    unsigned int i;
    char const *name = native_map_basename(map);
    for (i = 0; i < NUMBEROF(stock_names); i++)
        if (!_stricmp(name, stock_names[i])) return FALSE;
    return name[0] != 0;
}

static unsigned long little_u32(unsigned char const *p)
{
    return (unsigned long)p[0] | (unsigned long)p[1] << 8 |
        (unsigned long)p[2] << 16 | (unsigned long)p[3] << 24;
}

int native_map_header_valid(unsigned char const *header, char const *filename)
{
    char name[32], build[32];
    unsigned long length;
    unsigned int i, name_length;
    if (memcmp(header, "daeh", 4) || memcmp(header + 0x7FC, "toof", 4) ||
        little_u32(header + 4) != 5 || header[0x60] != 1 || header[0x61] != 0 ||
        !memchr(header + 0x20, 0, 32) || !memchr(header + 0x40, 0, 32))
        return FALSE;
    memcpy(name, header + 0x20, 32);
    memcpy(build, header + 0x40, 32);
    length = little_u32(header + 8);
    if (length < 2048 || length > HALO_PORT_MULTIPLAYER_CACHE_SIZE ||
        !cache_files_build_region(build)) return FALSE;
    name_length = (unsigned int)strlen(name);
    if (!name_length || strlen(filename) != name_length + 4 ||
        _strnicmp(filename, name, name_length) ||
        _stricmp(filename + name_length, ".map")) return FALSE;
    for (i = 0; i < name_length; i++) {
        unsigned char c = (unsigned char)name[i];
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
            (c >= '0' && c <= '9') || c == '_' || c == '-' || c == ' '))
            return FALSE;
    }
    return TRUE;
}

static int map_compare(void const *a, void const *b)
{
    return _stricmp(*(char *const *)a, *(char *const *)b);
}

#ifdef HALO_MACOS
static int map_can_download(char const *map)
{
    static char const *retail[] = {
        "ui", "a10", "a30", "a50", "b30", "b40", "c10", "c20", "c40", "d20", "d40"
    };
    unsigned int i;
    unsigned int length = (unsigned int)strlen(map);
    if (!native_map_is_custom(map) || !length || length >= HALO_CUSTOM_MAP_NAME_SIZE) return FALSE;
    for (i = 0; i < NUMBEROF(retail); i++)
        if (!_stricmp(map, retail[i])) return FALSE;
    for (i = 0; i < length; i++) {
        unsigned char c = (unsigned char)map[i];
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
            (c >= '0' && c <= '9') || c == '_' || c == '-' || c == ' ')) return FALSE;
    }
    return TRUE;
}
#endif

int native_map_get_path(char const *map, char *path, unsigned int capacity)
{
    char const *name = native_map_basename(map);
    int length = snprintf(path, capacity, "%s%s.map", cache_files_map_directory(), name);
    if (length < 0 || (unsigned int)length >= capacity) return FALSE;
#ifdef HALO_MACOS
    HANDLE file = CreateFileA(path, GENERIC_READ, 0, NULL, OPEN_EXISTING, 0, NULL);
    if (file != INVALID_HANDLE_VALUE) {
        CloseHandle(file);
        return TRUE;
    }
    if (map_can_download(name)) {
        char directory[1024], overlay[256], canonical[HALO_CUSTOM_MAP_NAME_SIZE];
        unsigned int i;
        for (i = 0; name[i]; i++)
            canonical[i] = name[i] >= 'A' && name[i] <= 'Z' ? name[i] + ('a' - 'A') : name[i];
        canonical[i] = 0;
        if (halo_map_download_directory(directory, sizeof(directory)) &&
            halo_map_download_request(canonical) == 1) {
            length = snprintf(overlay, sizeof(overlay), "m:\\%s.map", canonical);
            if (length > 0 && (unsigned int)length < sizeof(overlay) &&
                (unsigned int)length < capacity) {
                file = CreateFileA(overlay, GENERIC_READ, 0, NULL, OPEN_EXISTING, 0, NULL);
                if (file != INVALID_HANDLE_VALUE) {
                    CloseHandle(file);
                    memcpy(path, overlay, (unsigned int)length + 1);
                }
            }
        }
    }
#endif
    return TRUE;
}

int native_map_download_pending(char const *map)
{
#ifdef HALO_MACOS
    char path[256];
    HANDLE file;
    int status;
    if (!map_can_download(native_map_basename(map)) || !native_map_get_path(map, path, sizeof(path))) return 0;
    file = CreateFileA(path, GENERIC_READ, 0, NULL, OPEN_EXISTING, 0, NULL);
    if (file != INVALID_HANDLE_VALUE) {
        CloseHandle(file);
        return 0;
    }
    status = halo_map_download_request(native_map_basename(map));
    return status == 2 || status == -1 ? status : 0;
#else
    (void)map;
    return 0;
#endif
}

static void discover_maps(char const *directory, int managed)
{
    WIN32_FIND_DATAA entry;
    HANDLE search;
    char pattern[256];
    short i;
#ifndef HALO_MACOS
    (void)managed;
#endif
    snprintf(pattern, sizeof(pattern), "%s*.map", directory);
    search = FindFirstFileA(pattern, &entry);
    if (search != INVALID_HANDLE_VALUE) {
        do {
            unsigned char header[2048];
            unsigned long read;
            HANDLE file;
            char path[256];
            int duplicate = FALSE;
            if ((entry.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) ||
                strlen(entry.cFileName) + strlen(directory) >= sizeof(path))
                continue;
            snprintf(path, sizeof(path), "%s%s", directory, entry.cFileName);
            file = CreateFileA(path, GENERIC_READ, 0, NULL, OPEN_EXISTING, 0, NULL);
            if (file == INVALID_HANDLE_VALUE) continue;
            read = 0;
            if (!ReadFile(file, header, sizeof(header), &read, NULL)) read = 0;
            CloseHandle(file);
            if (read != sizeof(header) || !native_map_header_valid(header, entry.cFileName)) continue;
#ifdef HALO_MACOS
            /* Only names whose complete bytes the host has verified against
               the approved catalog can enter the managed-map namespace. */
            if (managed) {
                unsigned int j;
                int canonical = TRUE;
                for (j = 0; entry.cFileName[j]; j++)
                    if (entry.cFileName[j] >= 'A' && entry.cFileName[j] <= 'Z') canonical = FALSE;
                if (!canonical || halo_map_download_request((char *)header + 0x20) != 1) continue;
            }
#endif
            for (i = 0; i < map_count; i++)
                if (!_stricmp(native_map_basename(map_list[i]), (char *)header + 0x20)) duplicate = TRUE;
            if (duplicate) continue;
            if (map_count == HALO_CUSTOM_MAP_LIMIT) {
                fprintf(stderr, "[maps] multiplayer map list is full (%d)\n", HALO_CUSTOM_MAP_LIMIT);
                break;
            }
            memcpy(custom_names[map_count], header + 0x20, HALO_CUSTOM_MAP_NAME_SIZE);
            map_list[map_count] = custom_names[map_count];
            map_count++;
        } while (FindNextFileA(search, &entry));
        CloseHandle(search);
    }
}

char **native_multiplayer_map_list(char **stock, short stock_count, short *count)
{
    short i;
    /* The menu calls this on reopening. Only complete, atomically published
       files are visible; no worker thread mutates these guest-side arrays. */
    map_count = stock_count;
    for (i = 0; i < stock_count; i++) map_list[i] = stock[i];
    discover_maps(cache_files_map_directory(), FALSE);
#ifdef HALO_MACOS
    {
        char directory[1024];
        if (halo_map_download_directory(directory, sizeof(directory)))
            discover_maps("m:\\", TRUE);
    }
#endif
    qsort(map_list + stock_count, map_count - stock_count, sizeof(map_list[0]), map_compare);
    *count = map_count;
    return map_list;
}
