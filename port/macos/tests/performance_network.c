/* Portable protocol regression checks. No game data, engine, or network needed.
 * cc -std=c11 -Wall -Wextra -Werror -Isource port/macos/tests/performance_network.c -o /tmp/performance-network-test
 */
#include "networking/network_performance_protocol.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

int main(void)
{
    unsigned char message[NETWORK_PERFORMANCE_MESSAGE_SIZE];
    unsigned char damaged[NETWORK_PERFORMANCE_MESSAGE_SIZE];
    unsigned flags, supported, kind, index;

    /* Stock v10 retains admission in either direction with every option off;
     * every enabled combination requires precisely its supported bits. */
    for (flags = 0; flags <= 31; ++flags) {
        unsigned version = network_performance_advertised_version(flags, 10);
        assert((version == 10) == (flags == 0));
        assert(network_performance_version_compatible(version, 3, 10));
        assert(network_performance_version_compatible(10, 1, 10));
        if (flags) assert(!network_performance_version_compatible(version, 1, 10));
        for (supported = 0; supported <= 31; ++supported)
            assert(network_performance_can_join(flags, supported) == ((flags & supported) == flags));
    }
    assert(!network_performance_can_join(32, 255));
    /* The prior timer/marker client can still join those modes, but cannot
     * join or remain in a session where the host enables timer audio. */
    assert(network_performance_can_join(3, 3));
    assert(!network_performance_can_join(4, 3));
    assert(!network_performance_can_join(7, 3));
    assert(network_performance_can_join(7, 7));
    assert(!network_performance_can_join(8, 7));
    assert(!network_performance_can_join(16, 7));
    assert(network_performance_can_join(24, 31));
    assert(!network_performance_version_compatible(9, 3, 10));
    assert(!network_performance_version_compatible(11, 3, 10));

    /* The reliable pre-join sequence gives a prior PB host the supported
     * subset before current capabilities. The earlier v1 decoder has the
     * same packet format but rejects any payload flag outside mask 3. */
    {
        const unsigned capabilities[] = {3, 7, NETWORK_PERFORMANCE_SUPPORTED_FLAGS};
        unsigned prior_host_support = 0, audio_host_support = 0, current_host_support = 0;
        for (index = 0; index < sizeof(capabilities) / sizeof(capabilities[0]); ++index) {
            network_performance_encode(message, NETWORK_PERFORMANCE_CAPABILITY, capabilities[index]);
            assert(network_performance_decode(message, sizeof(message), NETWORK_PERFORMANCE_CAPABILITY,
                &current_host_support));
            if (!(message[13] & ~7u)) {
                assert(network_performance_decode(message, sizeof(message), NETWORK_PERFORMANCE_CAPABILITY,
                    &audio_host_support));
            }
            if (!(message[13] & ~3u)) {
                assert(network_performance_decode(message, sizeof(message), NETWORK_PERFORMANCE_CAPABILITY,
                    &prior_host_support));
            }
        }
        assert(prior_host_support == 3 && audio_host_support == 7 && current_host_support == 31);
    }

    for (kind = NETWORK_PERFORMANCE_CAPABILITY; kind <= NETWORK_PERFORMANCE_SETTINGS; ++kind) {
        for (flags = 0; flags <= 31; ++flags) {
            unsigned decoded = 99;
            network_performance_encode(message, kind, flags);
            assert(network_performance_decode(message, sizeof(message), kind, &decoded));
            assert(decoded == flags);
            /* Capability never grants host-setting authority, or vice versa. */
            assert(!network_performance_decode(message, sizeof(message), 3 - kind, &decoded));
            assert(!network_performance_decode(message, sizeof(message), 3, &decoded));
            for (index = 0; index < sizeof(message); ++index)
                assert(!network_performance_decode(message, index, kind, &decoded));
            assert(!network_performance_decode(message, sizeof(message) + 1, kind, &decoded));
            /* Every fixed header, magic/version, kind and reserved byte is
             * checked; damaged packets leave the caller's flags unchanged. */
            for (index = 0; index < sizeof(message); ++index) {
                if (index == 13) continue;
                memcpy(damaged, message, sizeof(message));
                damaged[index] ^= 0x80;
                decoded = 99;
                assert(!network_performance_decode(damaged, sizeof(damaged), kind, &decoded));
                assert(decoded == 99);
            }
            for (index = 32; index <= 255; ++index) {
                message[13] = (unsigned char)index;
                assert(!network_performance_decode(message, sizeof(message), kind, &decoded));
            }
        }
    }
    assert(!network_performance_decode(NULL, sizeof(message), 1, &flags));
    assert(!network_performance_decode(message, sizeof(message), 1, NULL));
    puts("performance network protocol: PASS");
    return 0;
}
