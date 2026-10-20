/* Immutable wire bytes with their current logical extent. Allocation capacity
 * never extends a command or record range. The caller owns the backing storage
 * for the entire view lifetime, including synchronous GPU completion. */
#ifdef HALO_MACOS_NATIVE_METAL
#ifndef HALO_METAL_PACKET_VIEW_H
#define HALO_METAL_PACKET_VIEW_H
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <type_traits>
#include <vector>

class HaloMetalPacketView {
public:
    HaloMetalPacketView(const void *bytes, size_t count) noexcept:
        bytes_(static_cast<const uint8_t *>(bytes)), count_(count) {}
    /* CPU/compiler fixtures also use owned vector packets. Do not permit a
     * temporary container to leave a dangling view. Production uses MTLBuffer. */
    HaloMetalPacketView(const std::vector<uint8_t> &bytes) noexcept:
        HaloMetalPacketView(bytes.data(),bytes.size()) {}
    HaloMetalPacketView(std::vector<uint8_t> &&) = delete;
    HaloMetalPacketView(const std::vector<uint8_t> &&) = delete;
    const uint8_t *data() const noexcept { return bytes_; }
    size_t size() const noexcept { return count_; }
    bool contains(size_t position, size_t count) const noexcept {
        return bytes_ && position <= count_ && count <= count_ - position;
    }
    template<typename T> bool read(size_t position, T &result) const noexcept {
        static_assert(std::is_trivially_copyable<T>::value,"Wire records must be trivially copyable");
        if (!contains(position,sizeof(result))) return false;
        memcpy(&result,bytes_ + position,sizeof(result));
        return true;
    }
private:
    const uint8_t *const bytes_;
    const size_t count_;
};
#endif
#endif
