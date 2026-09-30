/* Pass Cocoa URL events to the guest without exposing a native pointer. */
#include "host.h"
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int host_invite_received(const char *text) {
    static const char prefix[] = "halo://join/";
    const size_t prefix_size = sizeof(prefix) - 1;
    if (!text || strncmp(text, prefix, prefix_size) || strlen(text) != prefix_size + 44 ||
        strspn(text + prefix_size, "0123456789abcdefABCDEF") != 44)
        return 0;
    const char *saves = getenv("HALO_SAVE_ROOT");
    if (!saves || !*saves)
        return 0;
    char destination[4096], temporary[4096];
    int destination_size = snprintf(destination, sizeof(destination), "%s/join_link.txt", saves);
    int temporary_size = snprintf(temporary, sizeof(temporary), "%s/join_link.XXXXXX", saves);
    if (destination_size < 0 || destination_size >= (int)sizeof(destination) ||
        temporary_size < 0 || temporary_size >= (int)sizeof(temporary))
        return 0;
    int descriptor = mkstemp(temporary);
    if (descriptor < 0)
        return 0;
    size_t length = strlen(text), written = 0;
    while (written < length) {
        ssize_t n = write(descriptor, text + written, length - written);
        if (n < 0 && errno == EINTR)
            continue;
        if (n <= 0)
            break;
        written += (size_t)n;
    }
    int result = close(descriptor) == 0 && written == length && rename(temporary, destination) == 0;
    if (!result)
        unlink(temporary);
    return result;
}
