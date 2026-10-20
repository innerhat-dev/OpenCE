/* Exact emitted-source function cache. Keys include every compile contract;
 * the owner scopes successful function values to one Metal device/context. */
#ifdef HALO_MACOS_NATIVE_METAL
#ifndef HALO_METAL_FUNCTION_CACHE_H
#define HALO_METAL_FUNCTION_CACHE_H
#include <cstddef>
#include <list>
#include <map>
#include <string>
#include <tuple>
#include <utility>

struct HaloMetalFunctionKey {
    std::string source;
    bool vertex, fastMath, preserveInvariance;
    bool operator<(const HaloMetalFunctionKey &other) const {
        return std::tie(vertex, fastMath, preserveInvariance, source) <
            std::tie(other.vertex, other.fastMath, other.preserveInvariance, other.source);
    }
};

template<class Value, size_t MaximumEntries = 256, size_t MaximumSourceBytes = 8u * 1024u * 1024u>
class HaloMetalFunctionCache {
    using Entries = std::map<HaloMetalFunctionKey, Value>;
    Entries entries_;
    std::list<typename Entries::iterator> insertionOrder_;
    size_t sourceBytes_ = 0;
public:
    HaloMetalFunctionCache() = default;
    HaloMetalFunctionCache(const HaloMetalFunctionCache &) = delete;
    HaloMetalFunctionCache &operator=(const HaloMetalFunctionCache &) = delete;
    HaloMetalFunctionCache(HaloMetalFunctionCache &&other)
        : entries_(std::move(other.entries_)), insertionOrder_(std::move(other.insertionOrder_)),
          sourceBytes_(std::exchange(other.sourceBytes_,0)) {}
    HaloMetalFunctionCache &operator=(HaloMetalFunctionCache &&other) {
        if (this != &other) {
            clear(); entries_ = std::move(other.entries_); insertionOrder_ = std::move(other.insertionOrder_);
            sourceBytes_ = std::exchange(other.sourceBytes_,0);
        }
        return *this;
    }
    const Value *find(const HaloMetalFunctionKey &key) const {
        auto found = entries_.find(key);
        return found == entries_.end() ? nullptr : &found->second;
    }
    bool insert(HaloMetalFunctionKey key, Value value) {
        const size_t bytes = key.source.size();
        if (!MaximumEntries || bytes > MaximumSourceBytes || find(key)) return false;
        while (entries_.size() >= MaximumEntries || bytes > MaximumSourceBytes - sourceBytes_) {
            auto oldest = insertionOrder_.front(); insertionOrder_.pop_front();
            sourceBytes_ -= oldest->first.source.size(); entries_.erase(oldest);
        }
        auto added = entries_.emplace(std::move(key), value).first;
        try { insertionOrder_.push_back(added); }
        catch (...) { entries_.erase(added); throw; }
        sourceBytes_ += bytes; return true;
    }
    void clear() { insertionOrder_.clear(); entries_.clear(); sourceBytes_ = 0; }
    size_t size() const { return entries_.size(); }
    size_t sourceBytes() const { return sourceBytes_; }
    const Entries &entries() const { return entries_; }
};
#endif
#endif
