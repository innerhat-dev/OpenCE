/* Validate the immutable compact input before a vertex function may read it.
 * Offsets are relative to this buffer slice, never guest addresses. */
#ifdef HALO_MACOS_NATIVE_METAL
#ifndef HALO_METAL_COMPACT_VERTEX_H
#define HALO_METAL_COMPACT_VERTEX_H
#include "../include/halo_metal_vertex_input.h"
#include <cmath>
#include <cstring>

inline uint32_t halo_metal_compact_element_bytes(uint32_t type) {
    switch (type) {
    case 0x12: case 0x40: case 0x16: case 0x21: case 0x25: case 0x44: return 4;
    case 0x22: case 0x41: case 0x45: return 8;
    case 0x32: case 0x72: return 12;
    case 0x42: return 16;
    case 0x11: case 0x15: case 0x24: return 2;
    case 0x31: case 0x35: return 6;
    case 0x14: return 1;
    case 0x34: return 3;
    default: return 0;
    }
}
inline bool halo_metal_compact_vertices_valid(const void *data, size_t byte_count,
                                             uint32_t vertex_count, uint32_t packed_mask) {
    if (!data || byte_count < sizeof(halo_metal_compact_vertex_input) ||
        !vertex_count || packed_mask > UINT16_MAX) return false;
    halo_metal_compact_vertex_input input;
    memcpy(&input,data,sizeof(input));
    if (input.version != HALO_METAL_COMPACT_VERTEX_VERSION || input.element_count > 16 ||
        input.vertex_count != vertex_count || input.packed_mask != packed_mask) return false;
    uint32_t seen = 0;
    const auto *bytes = (const uint8_t *)data;
    for (uint32_t i = 0; i < 16; i++) {
        const auto &e = input.elements[i];
        if (i >= input.element_count) {
            if (e.reg || e.type || e.offset || e.stride) return false;
            continue;
        }
        const uint32_t size = halo_metal_compact_element_bytes(e.type);
        if (!size || e.reg >= 16 || (seen & (1u << e.reg)) ||
            ((e.type == 0x16) != bool(packed_mask & (1u << e.reg))) ||
            e.offset < sizeof(input) || e.offset > byte_count ||
            uint64_t(vertex_count - 1) * e.stride + size > byte_count - e.offset) return false;
        seen |= 1u << e.reg;
        // Only original FLOAT lanes can introduce nonfinite effective input.
        // Packed integers are instruction-visible raw bits, including NaNs
        // when interpreted as floats, and must bypass this check.
        if ((e.type & 15) == 2) {
            const uint32_t sources = e.stride ? vertex_count : 1;
            for (uint32_t v = 0; v < sources; v++) for (uint32_t lane = 0; lane < size / 4; lane++) {
                float value;
                memcpy(&value,bytes + e.offset + uint64_t(v) * e.stride + lane * 4,4);
                if (!std::isfinite(value)) return false;
            }
        }
    }
    for (uint32_t reg = 0; reg < 16; reg++) {
        if (packed_mask & (1u << reg)) {
            const uint8_t zero[16] = {};
            if (memcmp(input.fixed[reg],zero,sizeof(zero))) return false;
        } else if (!(seen & (1u << reg))) {
            for (float value : input.fixed[reg]) if (!std::isfinite(value)) return false;
        }
    }
    return true;
}
#endif
#endif
