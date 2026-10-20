/* Learned startup work only. Full emitted bytes and all compiler/pipeline
 * contracts are retained; fingerprints never authorize a cache hit. */
#ifdef HALO_MACOS_NATIVE_METAL
#ifndef HALO_METAL_WARMUP_CACHE_H
#define HALO_METAL_WARMUP_CACHE_H
#include "metal_function_cache.h"
#include <algorithm>
#include <cstdint>
#include <limits>
#include <vector>

inline uint64_t halo_metal_source_fingerprint(const std::string &source) {
    uint64_t value = UINT64_C(14695981039346656037);
    for (unsigned char byte : source) { value ^= byte; value *= UINT64_C(1099511628211); }
    return value;
}
struct HaloMetalWarmupPipeline {
    uint32_t vertex = 0, fragment = 0;
    uint64_t color = 0, depth = 0;
    uint32_t packed = 0, mask = 0, blend = 0, source = 1, destination = 1, operation = 1;
    uint32_t compact = 0;
    bool operator==(const HaloMetalWarmupPipeline &other) const {
        return std::tie(vertex,fragment,color,depth,packed,mask,blend,source,destination,operation,compact) ==
            std::tie(other.vertex,other.fragment,other.color,other.depth,other.packed,other.mask,
                     other.blend,other.source,other.destination,other.operation,other.compact);
    }
};
struct HaloMetalWarmupCache {
    static constexpr size_t MaximumFunctions = 256, MaximumSourceBytes = 8u * 1024u * 1024u;
    static constexpr size_t MaximumPipelines = 1024;
    static constexpr size_t MaximumFileBytes = MaximumSourceBytes + MaximumFunctions * 12u + MaximumPipelines * 52u + 32u;
    std::vector<HaloMetalFunctionKey> functions;
    std::vector<HaloMetalWarmupPipeline> pipelines;
    size_t sourceBytes = 0;
    uint64_t revision = 0;
    uint32_t find(const HaloMetalFunctionKey &key) const {
        for (size_t i = 0; i < functions.size(); i++)
            if (!(functions[i] < key) && !(key < functions[i])) return (uint32_t)i;
        return UINT32_MAX;
    }
    uint32_t learn(const HaloMetalFunctionKey &key) {
        uint32_t existing = find(key);
        if (existing != UINT32_MAX) return existing;
        if (key.source.empty() || key.source.size() > 4u * 1024u * 1024u || key.source.find('\0') != std::string::npos)
            return UINT32_MAX;
        // FIFO retirement also removes dependent PSOs and repairs their
        // indexes. New maps continue learning when an older corpus fills up.
        while (functions.size() >= MaximumFunctions || key.source.size() > MaximumSourceBytes - sourceBytes) {
            sourceBytes -= functions.front().source.size(); functions.erase(functions.begin());
            pipelines.erase(std::remove_if(pipelines.begin(),pipelines.end(),[](const auto &p) {
                return !p.vertex || !p.fragment;
            }),pipelines.end());
            for (auto &p : pipelines) { p.vertex--; p.fragment--; }
        }
        functions.push_back(key); sourceBytes += key.source.size(); revision++; return (uint32_t)functions.size() - 1;
    }
    bool valid(const HaloMetalWarmupPipeline &p) const {
        return p.vertex < functions.size() && p.fragment < functions.size() && functions[p.vertex].vertex &&
            !functions[p.fragment].vertex && p.packed <= UINT16_MAX && p.mask <= 15 && p.blend <= 1 &&
            (p.color == 0 || p.color == 70 || p.color == 80) && (p.depth == 0 || p.depth == 260) &&
            p.source >= 1 && p.source <= 15 && p.destination >= 1 && p.destination <= 15 &&
            p.operation >= 1 && p.operation <= 5 && p.compact <= 1 && (p.color || p.depth) && (p.color || (!p.mask && !p.blend));
    }
    bool learn(const HaloMetalWarmupPipeline &pipeline) {
        if (!valid(pipeline) || std::find(pipelines.begin(),pipelines.end(),pipeline) != pipelines.end()) return false;
        if (pipelines.size() >= MaximumPipelines) pipelines.erase(pipelines.begin());
        pipelines.push_back(pipeline); revision++; return true;
    }
    std::vector<uint8_t> encode() const {
        std::vector<uint8_t> bytes;
        auto word = [&](uint64_t value, unsigned count) { for (unsigned i = 0; i < count; i++) bytes.push_back((uint8_t)(value >> (i * 8))); };
        word(UINT32_C(0x57504d48),4); word(2,4); word(functions.size(),4); word(pipelines.size(),4);
        for (const auto &key : functions) {
            word(key.source.size(),4); word((key.vertex ? 1u : 0u) | (key.fastMath ? 2u : 0u) | (key.preserveInvariance ? 4u : 0u),4);
            bytes.insert(bytes.end(),key.source.begin(),key.source.end());
        }
        for (const auto &p : pipelines) {
            word(p.vertex,4); word(p.fragment,4); word(p.color,8); word(p.depth,8);
            for (uint32_t value : {p.packed,p.mask,p.blend,p.source,p.destination,p.operation,p.compact}) word(value,4);
        }
        word(halo_metal_source_fingerprint(std::string((const char *)bytes.data(),bytes.size())),8);
        return bytes;
    }
    static bool decode(const std::vector<uint8_t> &bytes, HaloMetalWarmupCache &result) {
        if (bytes.size() < 24 || bytes.size() > MaximumFileBytes) return false;
        size_t offset = 0;
        auto word = [&](unsigned count, uint64_t &value) {
            if (count > bytes.size() - offset) return false;
            value = 0; for (unsigned i = 0; i < count; i++) value |= uint64_t(bytes[offset++]) << (i * 8); return true;
        };
        uint64_t magic,version,count,pipelines;
        if (!word(4,magic) || !word(4,version) || !word(4,count) || !word(4,pipelines) ||
            magic != UINT32_C(0x57504d48) || (version != 1 && version != 2) || count > MaximumFunctions || pipelines > MaximumPipelines) return false;
        HaloMetalWarmupCache candidate;
        for (uint64_t i = 0; i < count; i++) {
            uint64_t size,flags;
            if (!word(4,size) || !word(4,flags) || !size || size > 4u * 1024u * 1024u || flags > 7 || size > bytes.size() - offset) return false;
            HaloMetalFunctionKey key{std::string((const char *)bytes.data()+offset,(size_t)size),bool(flags & 1),bool(flags & 2),bool(flags & 4)};
            offset += (size_t)size;
            if (candidate.learn(key) != i) return false;
        }
        for (uint64_t i = 0; i < pipelines; i++) {
            HaloMetalWarmupPipeline p; uint64_t value;
            if (!word(4,value)) return false;
            p.vertex = (uint32_t)value;
            if (!word(4,value)) return false;
            p.fragment = (uint32_t)value;
            if (!word(8,p.color) || !word(8,p.depth)) return false;
            for (uint32_t *field : {&p.packed,&p.mask,&p.blend,&p.source,&p.destination,&p.operation}) {
                if (!word(4,value)) return false;
                *field = (uint32_t)value;
            }
            // Version1 recorded expanded stage-in pipelines only.
            if (version == 2) {
                if (!word(4,value)) return false;
                p.compact = (uint32_t)value;
            }
            if (!candidate.learn(p)) return false;
        }
        uint64_t checksum;
        if (offset + 8 != bytes.size() || !word(8,checksum) || checksum !=
            halo_metal_source_fingerprint(std::string((const char *)bytes.data(),bytes.size()-8))) return false;
        result = std::move(candidate); return true;
    }
};
#endif
#endif
