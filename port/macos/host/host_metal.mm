/* Native Metal command transport for the existing rebased game guest.
 * Resource generations protect address reuse; packet copies protect transient
 * streams/uploads. Validation precedes mutation. GPU failure poisons the
 * context until shutdown, rather than presenting an incomplete frame.
 */
#ifdef HALO_MACOS_NATIVE_METAL
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#import <QuartzCore/CAMetalLayer.h>
#import <CoreVideo/CoreVideo.h>
#import <AppKit/AppKit.h>
#include <mach/mach.h>
#include <mach/mach_vm.h>
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <map>
#include <memory>
#include <mutex>
#include <new>
#include <vector>
extern "C" {
#include "host.h"
}
#include "../include/halo_metal_abi.h"
#include "metal_function_cache.h"
#include "metal_warmup_cache.h"
#include "metal_packet_view.h"
#import "metal_draw_encoder.h"

namespace {
constexpr uint32_t capabilities = HALO_METAL_CAP_TARGETS | HALO_METAL_CAP_UPLOAD |
    HALO_METAL_CAP_CLEAR | HALO_METAL_CAP_COPY | HALO_METAL_CAP_READBACK |
    HALO_METAL_CAP_DRAW | HALO_METAL_CAP_VISIBILITY | HALO_METAL_CAP_CLEAR_CHANNELS |
    HALO_METAL_CAP_BLACK_BORDER | HALO_METAL_CAP_ALPHA_BORDER | HALO_METAL_CAP_COPY_SUBRESOURCE |
    HALO_METAL_CAP_VOLUME | HALO_METAL_CAP_VOLUME_BORDER;
struct Failure { int status; uint32_t index; };
using SamplerKey = std::array<uint32_t,11>;
constexpr size_t sampler_cache_capacity = 256;
SamplerKey sampler_key(const halo_metal_sampler &sampler, uint32_t border) {
    static_assert(sizeof(sampler) == 40,"Sampler key must include the complete wire record");
    SamplerKey key{};
    // Copy raw LOD bits as well as every integer field. Different border
    // companions and signed zero must never alias through float comparison.
    memcpy(key.data(),&sampler,sizeof(sampler)); key.back() = border; return key;
}
bool sampler_valid(const halo_metal_sampler &c) {
    return !c.reserved && c.min_filter <= 1 && c.mag_filter <= 1 && c.mip_filter <= 2 &&
        c.address_u <= 3 && c.address_v <= 3 && c.address_w <= 3 && c.max_anisotropy >= 1 && c.max_anisotropy <= 16 &&
        std::isfinite(c.lod_min) && std::isfinite(c.lod_max) && c.lod_min >= 0 && c.lod_min <= c.lod_max;
}
template<typename Value> bool sampler_cache_insert(std::map<SamplerKey,Value> &cache,
                                                  const SamplerKey &key, const Value &value) {
    // When full, preserve existing hot states and use the uncached original
    // allocation path. No valid sampler is rejected because the cache is full.
    return cache.size() < sampler_cache_capacity && cache.emplace(key,value).second;
}
struct Metrics {
    bool enabled = false;
    uint64_t submissions = 0, frames = 0, bytes = 0, draws = 0, render_passes = 0;
    uint64_t packet_copy_ns = 0, prepare_ns = 0, encode_ns = 0;
    uint64_t drawable_wait_ns = 0, commit_ns = 0, completion_wait_ns = 0, gpu_ns = 0, gpu_samples = 0;
    uint64_t packet_buffers = 0, sampler_hits = 0, sampler_misses = 0, sampler_allocations = 0;
    uint64_t upload_buffers = 0, visibility_buffers = 0;
    uint64_t shader_compile_hits = 0, shader_compile_misses = 0, shader_compile_ns = 0;
    uint64_t shader_compile_pairs = 0;
    uint64_t subresource_copies = 0;
};
void check_at(const char *file, int line, const char *expression, bool ok,
              int status = HALO_METAL_INVALID, uint32_t index = UINT32_MAX) {
    if (!ok) {
        host_logf(HOST_LOG_ERROR,"Native Metal validation check: %s:%d status %d index %u: %s",
            file,line,status,index,expression);
        throw Failure{status, index};
    }
}
#define check(...) check_at(__FILE__,__LINE__,#__VA_ARGS__,__VA_ARGS__)
struct Texture {
    id<MTLTexture> object;
    uint32_t generation, format, width, height, initialized = 0, version = 0;
    uint32_t type = HALO_METAL_TEXTURE_2D, mip_levels = 1;
    uint32_t usage = HALO_METAL_SHADER_READ | HALO_METAL_RENDER_TARGET;
    uint32_t depth = 1;
    std::vector<uint32_t> subresources{0};
};
struct Program {
    id<MTLFunction> vertex, fragment;
    uint32_t generation, contract, fragment_contract;
    uint64_t vertex_fingerprint = 0, fragment_fingerprint = 0;
};
struct Visibility {
    uint32_t generation, mode, version = 0;
    bool begun = false, ended = false;
    uint64_t end_sequence = 0;
    std::vector<id<MTLBuffer>> words;
};
struct PreparedFxaa { id<MTLTexture> scratch; id<MTLRenderPipelineState> pipeline; };
struct Prepared {
    std::map<size_t, Texture> textures;
    std::map<size_t, Program> programs;
    std::map<size_t, HaloMetalDraw> draws;
    std::map<size_t, PreparedFxaa> fxaa;
    // Validation, uploads and draws share this immutable host-owned packet.
    // Synchronous completion precedes release of its strong buffer reference.
    id<MTLBuffer> input_buffer = nil;
    // New successful functions remain private until every packet command has
    // passed validation. A rejected packet cannot publish compiler entries.
    HaloMetalFunctionCache<id<MTLFunction>> compiled_functions;
};
struct Context {
    id<MTLDevice> device;
    HaloMetalFunctionCache<id<MTLFunction>> compiled_functions;
    id<MTLCommandQueue> queue;
    // Submissions complete under the host mutex before another packet can
    // overwrite this storage. Bound retention to the guest's 16 MiB soft batch
    // size; larger valid packets still use a temporary, exact-size buffer.
    id<MTLBuffer> draw_input_buffer = nil;
    id<MTLLibrary> clear_library;
    id<MTLRenderPipelineState> present_pipeline;
    id<MTLSamplerState> present_sampler;
    id<MTLLibrary> fxaa_library;
    id<MTLTexture> fxaa_scratch;
    std::map<uint32_t, id<MTLRenderPipelineState>> fxaa_pipelines;
    CAMetalLayer *layer;
    std::map<uint32_t, Texture> textures;
    std::map<uint32_t, uint32_t> generations;
    std::map<uint32_t, Program> programs;
    std::map<uint32_t, uint32_t> program_generations;
    std::map<uint32_t, Visibility> queries;
    std::map<uint32_t, uint32_t> query_generations;
    halo_metal_ref active_query = {};
    HaloMetalDrawEncoder *draw_encoder;
    std::map<uint64_t, id<MTLRenderPipelineState>> clear_pipelines;
    std::map<SamplerKey, id<MTLSamplerState>> samplers;
    Metrics metrics;
    uint64_t submitted = 0, completed = 0;
    bool poisoned = false;
    bool fxaa_enabled = false;
    bool compact_vertices_enabled = false;
    HaloMetalWarmupCache warmup;
    NSString *warmup_path = nil;
    bool warmup_dirty = false;
};
Context context;
std::mutex lock;
/* One presented frame may be outstanding. The next present waits until that
 * frame is on screen, so the queue cannot fill and then stall. */
dispatch_semaphore_t present_slot;
int present_sync = -1;
std::atomic<uint64_t> display_vblank_tick{0};
std::atomic<uint64_t> gpu_completed{0};
std::atomic<int> gpu_failed{0};
CVDisplayLinkRef display_link;
CGDirectDisplayID display_link_id;
double vblank_next_seconds;
struct PacketSlot { id<MTLBuffer> buffer; id<MTLCommandBuffer> command; };
PacketSlot packet_slots[3];
int packet_cursor;
int packet_pending = -1;

extern "C" CVReturn display_link_output(CVDisplayLinkRef link, const CVTimeStamp *now, const CVTimeStamp *output,
    CVOptionFlags, CVOptionFlags *, void *) {
    (void)link; (void)now;
    if (!output || !output->hostTime) return kCVReturnSuccess;
    double now_seconds = (double)output->hostTime / CVGetHostClockFrequency();
    if (vblank_next_seconds == 0) vblank_next_seconds = now_seconds;
    if (now_seconds + 0.001 < vblank_next_seconds) return kCVReturnSuccess;
    display_vblank_tick.fetch_add(1, std::memory_order_release);
    vblank_next_seconds += 1.0 / 60.0;
    if (now_seconds > vblank_next_seconds) vblank_next_seconds = now_seconds + 1.0 / 60.0;
    return kCVReturnSuccess;
}
CGDirectDisplayID layer_display(void) {
    if (context.layer && [context.layer.delegate isKindOfClass:[NSView class]]) {
        NSView *view = (NSView *)context.layer.delegate;
        NSScreen *screen = view.window.screen;
        if (!screen) return CGMainDisplayID();
        NSNumber *number = screen.deviceDescription[@"NSScreenNumber"];
        if (number) return number.unsignedIntValue;
    }
    return CGMainDisplayID();
}
void display_link_stop(void);
void display_link_start(void) {
    CGDirectDisplayID display = layer_display();
    if (display_link && display_link_id == display) return;
    display_link_stop();
    CVDisplayLinkRef link = nullptr;
    if (CVDisplayLinkCreateWithCGDisplay(display, &link) != kCVReturnSuccess || !link) return;
    if (CVDisplayLinkSetOutputCallback(link, display_link_output, nullptr) != kCVReturnSuccess ||
        CVDisplayLinkStart(link) != kCVReturnSuccess) {
        CVDisplayLinkRelease(link);
        return;
    }
    display_link = link;
    display_link_id = display;
}
void note_gpu_sequence(uint64_t sequence, MTLCommandBufferStatus status) {
    if (status == MTLCommandBufferStatusCompleted) {
        uint64_t previous = gpu_completed.load(std::memory_order_relaxed);
        while (previous < sequence &&
            !gpu_completed.compare_exchange_weak(previous, sequence, std::memory_order_release)) {}
    } else {
        gpu_failed.store(1, std::memory_order_release);
    }
}
void present_drawable(id<MTLCommandBuffer> buffer, id<CAMetalDrawable> drawable) {
    double period = 1.0 / 60.0;
    if (display_link && present_sync != 0) {
        double actual = CVDisplayLinkGetActualOutputVideoRefreshPeriod(display_link);
        if (actual >= 1.0 / 240.0 && actual <= 1.0 / 30.0) period = actual;
        [buffer presentDrawable:drawable afterMinimumDuration:period];
    } else {
        [buffer presentDrawable:drawable];
    }
}
void display_link_stop(void) {
    if (!display_link) return;
    CVDisplayLinkStop(display_link);
    CVDisplayLinkRelease(display_link);
    display_link = nullptr;
    vblank_next_seconds = 0;
}
bool present_acquire(void) {
    if (!present_slot) present_slot = dispatch_semaphore_create(1);
    return dispatch_semaphore_wait(present_slot, dispatch_time(DISPATCH_TIME_NOW, 100 * NSEC_PER_MSEC)) == 0;
}
void present_schedule(id<CAMetalDrawable> drawable) {
    [drawable addPresentedHandler:^(id<MTLDrawable>) {
        if (present_slot) dispatch_semaphore_signal(present_slot);
    }];
}
void apply_display_sync(uint32_t flags) {
    int sync = (flags & HALO_METAL_DISPLAY_VSYNC) != 0;
    if (!context.layer || present_sync == sync) return;
    present_sync = sync;
    context.layer.displaySyncEnabled = sync;
}

uint64_t metrics_start(void) {
    if (!context.metrics.enabled) return 0;
    return std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
}
uint64_t metrics_elapsed(uint64_t started) {
    return started ? metrics_start() - started : 0;
}
void metrics_report(void) {
    const auto &m = context.metrics;
    if (!m.enabled || m.frames < 60) return;
    host_logf(HOST_LOG_INFO,"Native Metal host metrics: %llu frames, %llu submits, %llu draws, %llu bytes; "
        "packet-copy %llu us, prepare %llu us, encode %llu us, drawable-wait %llu us, commit %llu us, "
        "completion-wait %llu us, gpu %llu us/%llu samples; packet-buffers %llu, sampler-hits %llu, "
        "sampler-misses %llu, sampler-allocations %llu, sampler-cache %zu, upload-buffers %llu, visibility-buffers %llu, render-passes %llu, "
        "shader-compile-hits %llu, shader-compile-misses %llu, shader-compile-us %llu, shader-function-cache %zu, shader-function-source-bytes %zu",
        (unsigned long long)m.frames,(unsigned long long)m.submissions,(unsigned long long)m.draws,(unsigned long long)m.bytes,
        (unsigned long long)(m.packet_copy_ns/1000),(unsigned long long)(m.prepare_ns/1000),(unsigned long long)(m.encode_ns/1000),
        (unsigned long long)(m.drawable_wait_ns/1000),(unsigned long long)(m.commit_ns/1000),
        (unsigned long long)(m.completion_wait_ns/1000),(unsigned long long)(m.gpu_ns/1000),(unsigned long long)m.gpu_samples,
        (unsigned long long)m.packet_buffers,(unsigned long long)m.sampler_hits,(unsigned long long)m.sampler_misses,
        (unsigned long long)m.sampler_allocations,context.samplers.size(),(unsigned long long)m.upload_buffers,
        (unsigned long long)m.visibility_buffers,(unsigned long long)m.render_passes,
        (unsigned long long)m.shader_compile_hits,(unsigned long long)m.shader_compile_misses,
        (unsigned long long)(m.shader_compile_ns/1000),context.compiled_functions.size(),context.compiled_functions.sourceBytes());
    context.metrics = Metrics{}; context.metrics.enabled = true;
}

bool guest_range(uint32_t offset, uint32_t size) {
    return offset && size && uint64_t(offset) + size <= UINT64_C(0x100000000) &&
        host_low_owns((uintptr_t)guest_pointer(offset), size);
}
bool copy_guest(uint32_t offset, void *destination, uint32_t size) {
    if (!guest_range(offset, size)) return false;
    mach_vm_size_t copied = 0;
    return mach_vm_read_overwrite(mach_task_self(), (mach_vm_address_t)guest_pointer(offset), size,
        (mach_vm_address_t)destination, &copied) == KERN_SUCCESS && copied == size;
}
bool write_guest(uint32_t offset, const void *source, uint32_t size) {
    if (!guest_range(offset, size)) return false;
    host_memory_watch_prepare_write(offset, size);
    return mach_vm_write(mach_task_self(), (mach_vm_address_t)guest_pointer(offset),
        (vm_offset_t)source, size) == KERN_SUCCESS;
}
int reply(uint32_t offset, uint32_t size, int status, uint32_t failed = UINT32_MAX,
          uint32_t version = 0, uint32_t bytes = 0) {
    halo_metal_reply result = {HALO_METAL_ABI_VERSION, status, failed,
        capabilities | (context.layer ? HALO_METAL_CAP_PRESENT_EXACT | HALO_METAL_CAP_PRESENT_SCALED : 0) |
            (context.fxaa_enabled ? HALO_METAL_CAP_FXAA : 0) |
            (context.compact_vertices_enabled ? HALO_METAL_CAP_COMPACT_VERTICES : 0),
        context.submitted, gpu_completed.load(std::memory_order_acquire),
        (uint32_t)(context.textures.size() + context.programs.size() + context.queries.size()), version, bytes, 0};
    return size == sizeof(result) && write_guest(offset, &result, sizeof(result)) ? status : HALO_METAL_MEMORY;
}
void validate_reply(uint32_t offset, uint32_t size) {
    halo_metal_reply scratch;
    check(size == sizeof(scratch) && copy_guest(offset, &scratch, sizeof(scratch)), HALO_METAL_MEMORY);
    // Prove output writability before a GPU side effect, preserving its bytes.
    check(write_guest(offset, &scratch, sizeof(scratch)), HALO_METAL_MEMORY);
}
MTLPixelFormat format(uint32_t value) {
    switch (value) {
        case HALO_METAL_RGBA8: return MTLPixelFormatRGBA8Unorm;
        case HALO_METAL_BGRA8: return MTLPixelFormatBGRA8Unorm;
        case HALO_METAL_DEPTH32_STENCIL8: return MTLPixelFormatDepth32Float_Stencil8;
        case HALO_METAL_BC1: return MTLPixelFormatBC1_RGBA;
        case HALO_METAL_BC2: return MTLPixelFormatBC2_RGBA;
        case HALO_METAL_BC3: return MTLPixelFormatBC3_RGBA;
        default: throw Failure{HALO_METAL_UNSUPPORTED, UINT32_MAX};
    }
}
template<typename T> T record(const HaloMetalPacketView &packet, size_t position) {
    T result;
    check(packet.read(position,result));
    return result;
}
Texture &resource(std::map<uint32_t, Texture> &textures, halo_metal_ref ref) {
    auto found = textures.find(ref.id);
    check(ref.id && ref.generation && found != textures.end() && found->second.generation == ref.generation,
        HALO_METAL_STALE_RESOURCE);
    return found->second;
}
bool full(const Texture &texture, uint32_t x, uint32_t y, uint32_t w, uint32_t h) {
    return x == 0 && y == 0 && w == texture.width && h == texture.height;
}
void rectangle(const Texture &texture, uint32_t x, uint32_t y, uint32_t w, uint32_t h) {
    check(w && h && x <= texture.width && y <= texture.height &&
        w <= texture.width - x && h <= texture.height - y);
}
void initialized(Texture &texture, uint32_t planes, bool whole, uint32_t mip = 0, uint32_t slice = 0) {
    uint32_t &state = texture.subresources.at(slice * texture.mip_levels + mip);
    check(whole || (state & planes) == planes, HALO_METAL_UNDEFINED_CONTENT);
    state |= planes;
    texture.initialized = texture.subresources[0];
    check(texture.version != UINT32_MAX);
    texture.version++;
}
bool compressed(uint32_t format) { return format == HALO_METAL_BC1 || format == HALO_METAL_BC2 || format == HALO_METAL_BC3; }
uint32_t block_bytes(uint32_t format) { return format == HALO_METAL_BC1 ? 8u : 16u; }
bool target(const Texture &texture) {
    return texture.type == HALO_METAL_TEXTURE_2D && texture.mip_levels == 1 &&
        (texture.usage & HALO_METAL_RENDER_TARGET) && !compressed(texture.format);
}
uint32_t dimension(uint32_t size, uint32_t mip) { return std::max(1u, size >> mip); }
uint32_t slices(const Texture &texture) { return texture.type == HALO_METAL_TEXTURE_CUBE ? 6u : 1u; }
bool full_subresource(const Texture &texture, uint32_t mip, uint32_t x, uint32_t y, uint32_t w, uint32_t h) {
    return x == 0 && y == 0 && w == dimension(texture.width,mip) && h == dimension(texture.height,mip);
}
void subresource_rectangle(const Texture &texture, uint32_t mip, uint32_t slice,
                           uint32_t x, uint32_t y, uint32_t w, uint32_t h) {
    check(mip < texture.mip_levels && slice < slices(texture));
    uint32_t width = dimension(texture.width,mip), height = dimension(texture.height,mip);
    check(w && h && x <= width && y <= height && w <= width - x && h <= height - y);
}
void validate_copy_subresource(halo_metal_copy_subresource c, Texture &source, Texture &destination) {
    check(!c.reserved && c.planes == HALO_METAL_COLOR &&
        c.source.id != c.destination.id);
    check(source.type == HALO_METAL_TEXTURE_2D && destination.type == HALO_METAL_TEXTURE_2D &&
        source.format == destination.format &&
        (source.format == HALO_METAL_RGBA8 || source.format == HALO_METAL_BGRA8),HALO_METAL_UNSUPPORTED);
    subresource_rectangle(source,c.source_mip,c.source_slice,c.source_x,c.source_y,c.width,c.height);
    subresource_rectangle(destination,c.destination_mip,c.destination_slice,c.destination_x,c.destination_y,c.width,c.height);
    check(source.subresources.at(c.source_slice * source.mip_levels + c.source_mip) & HALO_METAL_COLOR,
        HALO_METAL_UNDEFINED_CONTENT);
    initialized(destination,HALO_METAL_COLOR,
        full_subresource(destination,c.destination_mip,c.destination_x,c.destination_y,c.width,c.height),
        c.destination_mip,c.destination_slice);
}
void inline_range(size_t position, uint32_t command_bytes, size_t fixed,
                  uint32_t offset, uint64_t bytes, uint32_t alignment = 1) {
    check(bytes && offset % alignment == 0 && offset >= position + fixed &&
        uint64_t(offset) + bytes <= position + command_bytes);
}
Texture make_texture(halo_metal_create_ex c) {
    check(!c.reserved && c.resource.id && c.resource.generation && c.width && c.height &&
        c.width <= 8192 && c.height <= 8192 && c.depth && c.mip_levels &&
        (c.type == HALO_METAL_TEXTURE_2D || c.type == HALO_METAL_TEXTURE_CUBE || c.type == HALO_METAL_TEXTURE_3D) &&
        c.usage && !(c.usage & ~3u));
    bool volume = c.type == HALO_METAL_TEXTURE_3D;
    if (volume) check(c.width <= 512 && c.height <= 512 && c.depth <= 512 &&
        c.usage == HALO_METAL_SHADER_READ && (c.format == HALO_METAL_RGBA8 || c.format == HALO_METAL_BGRA8),
        HALO_METAL_UNSUPPORTED);
    else check(c.depth == 1);
    uint32_t maximum = 1;
    for (uint32_t size = std::max(std::max(c.width,c.height),c.depth); size > 1; size >>= 1) maximum++;
    check(c.mip_levels <= maximum);
    check(c.type != HALO_METAL_TEXTURE_CUBE || c.width == c.height);
    auto pixel_format = format(c.format);
    if (compressed(c.format)) {
        check(context.device.supportsBCTextureCompression && !(c.width & 3) && !(c.height & 3) &&
            c.usage == HALO_METAL_SHADER_READ, HALO_METAL_UNSUPPORTED);
    }
    if ((c.usage & HALO_METAL_RENDER_TARGET) || c.format == HALO_METAL_DEPTH32_STENCIL8)
        check(c.type == HALO_METAL_TEXTURE_2D && c.mip_levels == 1 &&
            (c.usage & HALO_METAL_RENDER_TARGET), HALO_METAL_UNSUPPORTED);
    auto descriptor = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:pixel_format
        width:c.width height:c.height mipmapped:NO];
    descriptor.textureType = volume ? MTLTextureType3D :
        c.type == HALO_METAL_TEXTURE_CUBE ? MTLTextureTypeCube : MTLTextureType2D;
    descriptor.depth = c.depth;
    descriptor.mipmapLevelCount = c.mip_levels; descriptor.storageMode = MTLStorageModePrivate;
    descriptor.usage = ((c.usage & HALO_METAL_SHADER_READ) ? MTLTextureUsageShaderRead : 0) |
        ((c.usage & HALO_METAL_RENDER_TARGET) ? MTLTextureUsageRenderTarget : 0);
    auto object = [context.device newTextureWithDescriptor:descriptor]; check(object != nil,HALO_METAL_MEMORY);
    Texture texture{object,c.resource.generation,c.format,c.width,c.height};
    texture.type = c.type; texture.mip_levels = c.mip_levels; texture.usage = c.usage; texture.depth = c.depth;
    texture.subresources.assign(slices(texture) * c.mip_levels,0); return texture;
}
halo_metal_upload_ex extended_upload(halo_metal_upload c) {
    halo_metal_upload_ex result{};
    result.command = c.command; result.resource = c.resource; result.x = c.x; result.y = c.y;
    result.width = c.width; result.height = c.height; result.depth = 1;
    result.bytes_per_row = c.bytes_per_row; result.bytes_per_image = c.data_size;
    result.data_offset = c.data_offset; result.data_size = c.data_size;
    result.plane = HALO_METAL_COLOR; result.reserved = c.reserved; return result;
}
void validate_upload(const HaloMetalPacketView &packet, size_t position, size_t fixed,
                     halo_metal_upload_ex c, Texture &texture) {
    check(c.command.byte_size >= fixed && !c.reserved && c.mip < texture.mip_levels && c.slice < slices(texture) &&
        c.depth && c.width && c.height);
    uint32_t width = dimension(texture.width,c.mip), height = dimension(texture.height,c.mip),
        depth = dimension(texture.depth,c.mip);
    check(c.x <= width && c.y <= height && c.z <= depth && c.width <= width - c.x &&
        c.height <= height - c.y && c.depth <= depth - c.z);
    if (texture.type != HALO_METAL_TEXTURE_3D) check(!c.z && c.depth == 1);
    check(texture.format == HALO_METAL_DEPTH32_STENCIL8 ? (c.plane == HALO_METAL_DEPTH || c.plane == HALO_METAL_STENCIL) :
        c.plane == HALO_METAL_COLOR, HALO_METAL_UNSUPPORTED);
    uint64_t tight = uint64_t(c.width) * (c.plane == HALO_METAL_STENCIL ? 1 : 4), rows = c.height;
    if (compressed(texture.format)) {
        // Authored BC blocks are transferred directly. Partial compressed
        // updates are not yet part of the original-resource upload contract.
        check(!c.x && !c.y && c.width == width && c.height == height,HALO_METAL_UNSUPPORTED);
        tight = uint64_t((c.width + 3) / 4) * block_bytes(texture.format); rows = (c.height + 3) / 4;
        check(!(c.bytes_per_row & (block_bytes(texture.format) - 1)));
    }
    uint64_t image_bytes = uint64_t(c.bytes_per_row) * (rows - 1) + tight;
    uint64_t required = uint64_t(c.bytes_per_image) * (c.depth - 1) + image_bytes;
    check(c.bytes_per_row >= tight && c.bytes_per_image >= image_bytes && c.data_size == required);
    inline_range(position,c.command.byte_size,fixed,c.data_offset,c.data_size);
    if (c.plane == HALO_METAL_DEPTH) for (uint32_t y = 0; y < c.height; y++) for (uint32_t x = 0; x < c.width; x++) {
        float depth;
        memcpy(&depth,packet.data() + c.data_offset + uint64_t(c.bytes_per_row) * y + uint64_t(x) * 4,4);
        check(std::isfinite(depth) && depth >= 0 && depth <= 1);
    }
    initialized(texture,c.plane,!c.x && !c.y && !c.z && c.width == width && c.height == height &&
        c.depth == depth,c.mip,c.slice);
}
Program &program(std::map<uint32_t, Program> &programs, halo_metal_ref ref) {
    auto found = programs.find(ref.id);
    check(ref.id && ref.generation && found != programs.end() && found->second.generation == ref.generation,
        HALO_METAL_STALE_RESOURCE);
    return found->second;
}
Visibility &visibility(std::map<uint32_t, Visibility> &queries, halo_metal_ref ref) {
    auto found = queries.find(ref.id);
    check(ref.id && ref.generation && found != queries.end() && found->second.generation == ref.generation,
        HALO_METAL_STALE_RESOURCE);
    return found->second;
}
bool same_ref(halo_metal_ref a, halo_metal_ref b) {
    return a.id == b.id && a.generation == b.generation;
}
void begin_visibility(std::map<uint32_t, Visibility> &queries, halo_metal_ref &active, halo_metal_ref ref) {
    auto &query = visibility(queries,ref);
    check(!active.id && !query.begun);
    query.words.clear(); query.begun = true; query.ended = false; query.end_sequence = 0;
    active = ref;
}
void end_visibility(std::map<uint32_t, Visibility> &queries, halo_metal_ref &active,
                    halo_metal_ref ref, uint64_t sequence) {
    auto &query = visibility(queries,ref);
    check(same_ref(active,ref) && query.begun && query.version != UINT32_MAX);
    query.begun = false; query.ended = true; query.end_sequence = sequence; query.version++;
    active = {};
}
struct FunctionCompileInput {
    HaloMetalFunctionKey key; NSString *source;
    uint32_t command_index = UINT32_MAX, program = 0, generation = 0;
};
FunctionCompileInput compile_input(const HaloMetalPacketView &packet,uint32_t offset,uint32_t bytes,
                                   bool vertex,bool fast,bool invariant) {
    check(!memchr(packet.data() + offset,0,bytes));
    NSString *source = [[NSString alloc] initWithBytes:packet.data() + offset length:bytes encoding:NSUTF8StringEncoding];
    check(source != nil);
    return {{std::string((const char *)packet.data() + offset,bytes),vertex,fast,invariant},source};
}
id<MTLFunction> cached_function(Prepared &prepared,const FunctionCompileInput &input) {
    const auto *cached = context.compiled_functions.find(input.key);
    if (!cached) cached = prepared.compiled_functions.find(input.key);
    if (cached) {
        check((*cached).device == context.device && (*cached).functionType ==
            (input.key.vertex ? MTLFunctionTypeVertex : MTLFunctionTypeFragment),HALO_METAL_GPU_ERROR);
        if (context.metrics.enabled) context.metrics.shader_compile_hits++;
        return *cached;
    }
    return nil;
}
MTLCompileOptions *compile_options(const HaloMetalFunctionKey &key) {
    auto options = [MTLCompileOptions new]; options.preserveInvariance = key.preserveInvariance;
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
    options.fastMathEnabled = key.fastMath;
#pragma clang diagnostic pop
    if (@available(macOS 15.0, *)) {
        options.mathMode = key.fastMath ? MTLMathModeFast : MTLMathModeSafe;
        options.mathFloatingPointFunctions = key.fastMath ? MTLMathFloatingPointFunctionsFast : MTLMathFloatingPointFunctionsPrecise;
    }
    return options;
}
void record_compilation(const FunctionCompileInput &input,const HaloMetalPacketView &packet,
                        id<MTLLibrary> library,uint64_t started,uint64_t elapsed) {
    context.metrics.shader_compile_ns += elapsed;
    if (context.metrics.enabled) {
        const auto header = record<halo_metal_packet>(packet,0);
        host_logf(HOST_LOG_INFO,"Native Metal compile: sequence %llu, stage %s, source-bytes %u, fast %u, invariant %u, start %llu ns, end %llu ns, duration %llu ns, success %u",
            (unsigned long long)header.frame_sequence,input.key.vertex ? "vertex" : "fragment",(unsigned)input.key.source.size(),
            (unsigned)input.key.fastMath,(unsigned)input.key.preserveInvariance,
            (unsigned long long)started,(unsigned long long)(started+elapsed),(unsigned long long)elapsed,library ? 1u : 0u);
        if (input.command_index != UINT32_MAX)
            host_logf(HOST_LOG_INFO,"Native Metal compile identity: sequence %llu, command-index %u, program %u, generation %u, stage %s, source-hash %016llx, start %llu ns",
                (unsigned long long)header.frame_sequence,input.command_index,input.program,input.generation,
                input.key.vertex ? "vertex" : "fragment",
                (unsigned long long)halo_metal_source_fingerprint(input.key.source),(unsigned long long)started);
    }
}
id<MTLFunction> resolve_compilation(Prepared &prepared,FunctionCompileInput &input,id<MTLLibrary> library,NSError *error) {
    if (!library) host_logf(HOST_LOG_ERROR,"Native original %s compilation: %s",input.key.vertex ? "vertex" : "fragment",error.localizedDescription.UTF8String);
    check(library != nil,HALO_METAL_GPU_ERROR);
    auto function = [library newFunctionWithName:input.key.vertex ? @"xgpu_vertex" : @"xgpu_fragment"];
    check(function && function.functionType == (input.key.vertex ? MTLFunctionTypeVertex : MTLFunctionTypeFragment));
    prepared.compiled_functions.insert(std::move(input.key),function);
    return function;
}
id<MTLFunction> compile_uncached_function(Prepared &prepared,const HaloMetalPacketView &packet,FunctionCompileInput &input) {
    if (context.metrics.enabled) context.metrics.shader_compile_misses++;
    auto options = compile_options(input.key);
    NSError *error = nil;
    const uint64_t started = metrics_start();
    auto library = [context.device newLibraryWithSource:input.source options:options error:&error];
    record_compilation(input,packet,library,started,metrics_elapsed(started));
    return resolve_compilation(prepared,input,library,error);
}
[[maybe_unused]] id<MTLFunction> compile_function(Prepared &prepared,const HaloMetalPacketView &packet,uint32_t offset,
                                uint32_t bytes,bool vertex,bool fast,bool invariant) {
    auto input = compile_input(packet,offset,bytes,vertex,fast,invariant);
    auto cached = cached_function(prepared,input);
    return cached ?: compile_uncached_function(prepared,packet,input);
}
struct LibraryCompileRequest {
    id<MTLDevice> device;
    NSString *source;
    MTLCompileOptions *options;
    id<MTLLibrary> library = nil;
    NSError *error = nil;
    std::mutex mutex;
    std::condition_variable condition;
    bool completed = false;
    uint64_t started = 0, elapsed = 0;
    void wait() {
        std::unique_lock<std::mutex> guard(mutex);
        condition.wait(guard,[this] { return completed; });
    }
};
void start_compilation(std::shared_ptr<LibraryCompileRequest> request) {
    request->started = metrics_start();
    [request->device newLibraryWithSource:request->source options:request->options
        completionHandler:^(id<MTLLibrary> library,NSError *error) {
            // The submitting thread holds the host mutex. Completion only
            // touches this retained request, never context, metrics or caches.
            const uint64_t ended = request->started ? (uint64_t)std::chrono::duration_cast<std::chrono::nanoseconds>(
                std::chrono::steady_clock::now().time_since_epoch()).count() : 0;
            {
                std::lock_guard<std::mutex> guard(request->mutex);
                request->library = library; request->error = error;
                request->elapsed = request->started ? ended - request->started : 0;
                request->completed = true;
            }
            request->condition.notify_one();
        }];
}
Program compile_program(Prepared &prepared,const HaloMetalPacketView &packet,const halo_metal_program &command,
                        uint32_t command_index = UINT32_MAX) {
    // Bounds/contracts have already passed CREATE_PROGRAM validation. Both
    // sources must also pass NUL/UTF8 validation before issuing async requests.
    auto vertex_input = compile_input(packet,command.vertex_source_offset,command.vertex_source_size,
        true,command.vertex_compiler_contract == 1,true);
    auto fragment_input = compile_input(packet,command.fragment_source_offset,command.fragment_source_size,
        false,command.fragment_compiler_contract == 1,command.fragment_compiler_contract == 0);
    for (auto *input : {&vertex_input,&fragment_input}) {
        input->command_index = command_index; input->program = command.resource.id; input->generation = command.resource.generation;
    }
    const uint64_t vertex_hash = halo_metal_source_fingerprint(vertex_input.key.source);
    const uint64_t fragment_hash = halo_metal_source_fingerprint(fragment_input.key.source);
    auto vertex = cached_function(prepared,vertex_input);
    auto fragment = cached_function(prepared,fragment_input);
    if (vertex || fragment) {
        // A partial cache hit keeps one ordinary serial compiler call; do not
        // launch speculative work for a stage that already has its function.
        if (!vertex) vertex = compile_uncached_function(prepared,packet,vertex_input);
        if (!fragment) fragment = compile_uncached_function(prepared,packet,fragment_input);
    } else {
        // Allocate/retain all request inputs before either launch. At most two
        // requests are outstanding, confined to this program and submission.
        auto vertex_request = std::make_shared<LibraryCompileRequest>();
        auto fragment_request = std::make_shared<LibraryCompileRequest>();
        vertex_request->device = fragment_request->device = context.device;
        vertex_request->source = vertex_input.source; fragment_request->source = fragment_input.source;
        vertex_request->options = compile_options(vertex_input.key);
        fragment_request->options = compile_options(fragment_input.key);
        if (context.metrics.enabled) {
            context.metrics.shader_compile_misses += 2; context.metrics.shader_compile_pairs++;
        }
        start_compilation(vertex_request); start_compilation(fragment_request);
        // Drain both before checking either error or publishing any result.
        // Resolution keeps vertex-before-fragment error/function validation.
        vertex_request->wait(); fragment_request->wait();
        record_compilation(vertex_input,packet,vertex_request->library,vertex_request->started,vertex_request->elapsed);
        record_compilation(fragment_input,packet,fragment_request->library,fragment_request->started,fragment_request->elapsed);
        vertex = resolve_compilation(prepared,vertex_input,vertex_request->library,vertex_request->error);
        fragment = resolve_compilation(prepared,fragment_input,fragment_request->library,fragment_request->error);
    }
    return {vertex,fragment,command.resource.generation,command.vertex_compiler_contract,command.fragment_compiler_contract,
            vertex_hash,fragment_hash};
}
void warmup_save() noexcept {
    if (!context.warmup_dirty || !context.warmup_path) return;
    try {
        const auto bytes = context.warmup.encode();
        if (bytes.size() > HaloMetalWarmupCache::MaximumFileBytes) return;
        NSError *error = nil;
        [[NSFileManager defaultManager] createDirectoryAtPath:context.warmup_path.stringByDeletingLastPathComponent
            withIntermediateDirectories:YES attributes:nil error:&error];
        NSData *data = [NSData dataWithBytes:bytes.data() length:bytes.size()];
        if ([data writeToFile:context.warmup_path options:NSDataWritingAtomic error:&error]) context.warmup_dirty = false;
        else if (context.metrics.enabled) host_logf(HOST_LOG_INFO,"Native Metal warmup cache write skipped: %s",error.localizedDescription.UTF8String);
    } catch (...) { /* Optional cache I/O/allocation never changes transport success. */ }
}
void warmup_initialize() noexcept {
    try {
        if (!context.warmup_path) return;
        auto attributes = [[NSFileManager defaultManager] attributesOfItemAtPath:context.warmup_path error:nil];
        const uint64_t length = [attributes[NSFileSize] unsignedLongLongValue];
        if (!attributes || ![attributes[NSFileType] isEqualToString:NSFileTypeRegular] ||
            length > HaloMetalWarmupCache::MaximumFileBytes) return;
        NSData *data = [NSData dataWithContentsOfFile:context.warmup_path];
        if (!data || data.length != length) return;
        std::vector<uint8_t> bytes(data.length);
        if (data.length) memcpy(bytes.data(),data.bytes,data.length);
        if (!HaloMetalWarmupCache::decode(bytes,context.warmup)) return;
        struct DiagnosticsScope {
            HaloMetalDrawEncoder *encoder; BOOL enabled;
            ~DiagnosticsScope() { encoder.diagnosticsEnabled = enabled; }
        } diagnostics{context.draw_encoder,context.draw_encoder.diagnosticsEnabled};
        context.draw_encoder.diagnosticsEnabled = NO;
        const auto started = std::chrono::steady_clock::now();
        std::vector<id<MTLFunction>> functions(context.warmup.functions.size(),nil);
        std::vector<bool> eligible(functions.size(),false);
        for (const auto &p : context.warmup.pipelines) {
            if (p.compact && !context.compact_vertices_enabled) continue;
            eligible[p.vertex] = eligible[p.fragment] = true;
        }
        size_t ready = 0, pipelines = 0;
        for (size_t i = 0; i < context.warmup.functions.size(); i++) {
            // Keep manifest indices stable. Orphan functions have no known
            // draw mode; optional warming waits for a real eligible draw.
            if (!eligible[i]) continue;
            const auto &key = context.warmup.functions[i];
            NSString *source = [[NSString alloc] initWithBytes:key.source.data() length:key.source.size() encoding:NSUTF8StringEncoding];
            if (!source) continue;
            NSError *error = nil;
            auto library = [context.device newLibraryWithSource:source options:compile_options(key) error:&error];
            auto function = [library newFunctionWithName:key.vertex ? @"xgpu_vertex" : @"xgpu_fragment"];
            if (!function || function.device != context.device || function.functionType !=
                (key.vertex ? MTLFunctionTypeVertex : MTLFunctionTypeFragment)) continue;
            context.compiled_functions.insert(key,function); functions[i] = function; ready++;
        }
        for (const auto &p : context.warmup.pipelines) {
            if (!functions[p.vertex] || !functions[p.fragment]) continue;
            HaloMetalPipelineWarmup descriptor{functions[p.vertex],functions[p.fragment],p.color,p.depth,
                p.packed,p.mask,p.blend,p.source,p.destination,p.operation,p.compact};
            if (p.compact && !context.compact_vertices_enabled) continue;
            NSError *error = nil;
            if ([context.draw_encoder preparePipeline:descriptor error:&error]) pipelines++;
        }
        const uint64_t elapsed = (uint64_t)std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-started).count();
        host_logf(HOST_LOG_INFO,"Native Metal warmup: functions %zu/%zu, pipelines %zu/%zu, source-bytes %zu, duration %llu ns",
            ready,functions.size(),pipelines,context.warmup.pipelines.size(),context.warmup.sourceBytes,(unsigned long long)elapsed);
    } catch (...) { /* Stale, malformed or unavailable warmup is an ordinary miss. */ }
}
const HaloMetalFunctionKey *warmup_key(id<MTLFunction> function,const Prepared &prepared) {
    for (const auto &entry : prepared.compiled_functions.entries()) if (entry.second == function) return &entry.first;
    for (const auto &entry : context.compiled_functions.entries()) if (entry.second == function) return &entry.first;
    return nullptr;
}
void warmup_learn(const Prepared &prepared) noexcept {
    try {
        auto pipelines = [context.draw_encoder takeCreatedPipelines];
        if (!context.warmup_path) return;
        const uint64_t before_revision = context.warmup.revision;
        for (const auto &entry : prepared.compiled_functions.entries()) context.warmup.learn(entry.first);
        // This list contains misses alone. Warm packets never scan the complete
        // function/pipeline caches, copy shader sources or touch disk.
        for (const auto &p : pipelines) {
            const auto *vertex = warmup_key(p.vertex,prepared), *fragment = warmup_key(p.fragment,prepared);
            if (!vertex || !fragment) continue;
            context.warmup.learn(*vertex); context.warmup.learn(*fragment);
            // A newly learned fragment may have retired an old vertex at the
            // FIFO boundary. Both stages together fit the source budget.
            context.warmup.learn(*vertex);
            const uint32_t v = context.warmup.find(*vertex), f = context.warmup.find(*fragment);
            if (v == UINT32_MAX || f == UINT32_MAX) continue;
            context.warmup.learn({v,f,p.color,p.depth,p.packed,p.mask,p.blend,p.source,p.destination,p.operation,p.compact});
        }
        context.warmup_dirty |= before_revision != context.warmup.revision;
    } catch (...) { /* Learning is optional and cannot fail an accepted packet. */ }
}
void remove_unused_program_pipelines(const Program &program, uint32_t deleting_id = 0) {
    // Exact-source reuse can make two live programs share either stage. A
    // rejected candidate or deleted variant must not evict the other's PSOs.
    id<MTLFunction> vertex = program.vertex, fragment = program.fragment;
    for (const auto &entry : context.programs) {
        if (entry.first == deleting_id) continue;
        if (entry.second.vertex == vertex) vertex = nil;
        if (entry.second.fragment == fragment) fragment = nil;
        if (!vertex && !fragment) return;
    }
    [context.draw_encoder removePipelinesForVertexFunction:vertex fragmentFunction:fragment];
}
id<MTLSamplerState> sampler(halo_metal_sampler c,
                          MTLSamplerBorderColor border = MTLSamplerBorderColorTransparentBlack) {
    check(sampler_valid(c));
    const SamplerKey key = sampler_key(c,(uint32_t)border);
    auto existing = context.samplers.find(key);
    if (existing != context.samplers.end()) {
        if (context.metrics.enabled) context.metrics.sampler_hits++;
        return existing->second;
    }
    if (context.metrics.enabled) context.metrics.sampler_misses++;
    auto descriptor = [MTLSamplerDescriptor new];
    descriptor.minFilter = c.min_filter ? MTLSamplerMinMagFilterLinear : MTLSamplerMinMagFilterNearest;
    descriptor.magFilter = c.mag_filter ? MTLSamplerMinMagFilterLinear : MTLSamplerMinMagFilterNearest;
    descriptor.mipFilter = (MTLSamplerMipFilter)c.mip_filter;
    const MTLSamplerAddressMode addresses[] = {MTLSamplerAddressModeRepeat,MTLSamplerAddressModeMirrorRepeat,
        MTLSamplerAddressModeClampToEdge,MTLSamplerAddressModeClampToBorderColor};
    descriptor.sAddressMode = addresses[c.address_u]; descriptor.tAddressMode = addresses[c.address_v]; descriptor.rAddressMode = addresses[c.address_w];
    descriptor.normalizedCoordinates = YES; descriptor.maxAnisotropy = c.max_anisotropy;
    descriptor.borderColor = border;
    descriptor.lodMinClamp = c.lod_min; descriptor.lodMaxClamp = c.lod_max;
    auto result = [context.device newSamplerStateWithDescriptor:descriptor]; check(result != nil,HALO_METAL_MEMORY);
    if (context.metrics.enabled) context.metrics.sampler_allocations++;
    sampler_cache_insert(context.samplers,key,result); return result;
}
id<MTLBuffer> packet_input_buffer(size_t bytes) {
    constexpr size_t retained_limit = 16u * 1024u * 1024u;
    size_t capacity = bytes;
    if (bytes > retained_limit) {
        packet_pending = -1;
        id<MTLBuffer> buffer = [context.device newBufferWithLength:bytes options:MTLResourceStorageModeShared];
        check(buffer != nil,HALO_METAL_MEMORY);
        if (context.metrics.enabled) context.metrics.packet_buffers++;
        return buffer;
    }
    PacketSlot &slot = packet_slots[packet_cursor];
    if (slot.command) {
        MTLCommandBufferStatus status = slot.command.status;
        if (status != MTLCommandBufferStatusCompleted && status != MTLCommandBufferStatusError)
            [slot.command waitUntilCompleted];
    }
    if (!slot.buffer || slot.buffer.length < bytes) {
        capacity = 16384;
        while (capacity < bytes) capacity *= 2;
        slot.buffer = [context.device newBufferWithLength:capacity options:MTLResourceStorageModeShared];
        check(slot.buffer != nil,HALO_METAL_MEMORY);
        if (context.metrics.enabled) context.metrics.packet_buffers++;
    }
    packet_pending = packet_cursor;
    packet_cursor = (packet_cursor + 1) % 3;
    return slot.buffer;
}
HaloMetalDraw prepare_draw(const HaloMetalPacketView &packet, size_t position, halo_metal_draw c,
                          id<MTLBuffer> __strong &input_buffer,
                          std::map<uint32_t, Texture> &textures, std::map<uint32_t, Program> &programs,
                          Visibility *query, uint32_t alpha_border_mask = 0, uint32_t volume_border_mask = 0,
                          uint32_t command_index = UINT32_MAX, uint32_t compact_bytes = 0) {
    const bool compact = c.command.opcode == HALO_METAL_DRAW_COMPACT;
    const size_t fixed = compact ? sizeof(halo_metal_draw_compact) :
        c.command.opcode == HALO_METAL_DRAW ? sizeof(c) : sizeof(halo_metal_draw_volume_border);
    check(alpha_border_mask <= 15 && volume_border_mask <= 15 && !(alpha_border_mask & volume_border_mask));
    check(c.command.byte_size >= fixed && !c.reserved[0] && !c.reserved[1] && c.vertex_count && c.index_count && c.primitive <= 4);
    inline_range(position,c.command.byte_size,fixed,c.vertices_offset,
        compact ? compact_bytes : uint64_t(c.vertex_count) * HaloMetalVertexStride,16);
    inline_range(position,c.command.byte_size,fixed,c.indices_offset,uint64_t(c.index_count) * 4,16);
    inline_range(position,c.command.byte_size,fixed,c.vertex_uniforms_offset,HaloMetalVertexUniformSize,16);
    inline_range(position,c.command.byte_size,fixed,c.pixel_uniforms_offset,HaloMetalPixelUniformSize,16);
    check(c.packed_mask <= UINT16_MAX);
    // Packed input registers contain instruction-visible integer bits. Their
    // float interpretation may be NaN and must never be normalized or tested.
    for (uint32_t vertex = 0; !compact && vertex < c.vertex_count; vertex++) for (unsigned reg = 0; reg < 16; reg++) {
        if (c.packed_mask & (1u << reg)) continue;
        for (unsigned component = 0; component < 4; component++) {
            float value;
            memcpy(&value,packet.data() + c.vertices_offset + uint64_t(vertex) * HaloMetalVertexStride + reg * 16 + component * 4,4);
            const bool finite = std::isfinite(value);
            if (!finite) {
                uint32_t bits; memcpy(&bits,packet.data() + c.vertices_offset +
                    uint64_t(vertex) * HaloMetalVertexStride + reg * 16 + component * 4,sizeof(bits));
                host_logf(HOST_LOG_ERROR,"Native Metal nonfinite vertex: vertex %u register %u component %u packet offset %llu raw %08x packed mask %08x",
                    vertex,reg,component,(unsigned long long)(c.vertices_offset +
                    uint64_t(vertex) * HaloMetalVertexStride + reg * 16 + component * 4),bits,c.packed_mask);
            }
            check(finite);
        }
    }
    for (auto range : {std::pair<uint32_t,uint32_t>{c.vertex_uniforms_offset,HaloMetalVertexUniformSize},
                      std::pair<uint32_t,uint32_t>{c.pixel_uniforms_offset,HaloMetalPixelUniformSize}})
        // Original shader constants are raw register storage. Unread lanes may
        // contain nonfinite padding; preserve those bits for the NV2A program.
        // The appended native viewport/input controls remain strictly finite.
        for (uint32_t byte = range.second == HaloMetalVertexUniformSize ? 3072 : 0;
             byte < range.second; byte += 4) {
            float value; memcpy(&value,packet.data() + range.first + byte,4);
            const bool finite = std::isfinite(value);
            if (!finite) {
                uint32_t bits; memcpy(&bits,packet.data() + range.first + byte,sizeof(bits));
                host_logf(HOST_LOG_ERROR,"Native Metal nonfinite %s uniform: byte %u packet offset %llu raw %08x",
                    range.second == HaloMetalVertexUniformSize ? "vertex" : "pixel",byte,
                    (unsigned long long)(uint64_t(range.first)+byte),bits);
            }
            check(finite);
        }
    auto &p = program(programs,c.program); HaloMetalDraw draw;
    draw.vertexFunction = p.vertex; draw.fragmentFunction = p.fragment;
    draw.vertexCount = c.vertex_count; draw.indexCount = c.index_count; draw.packedMask = c.packed_mask;
    draw.compactVertices = compact; draw.vertexBytes = compact_bytes;
    draw.primitive = (MTLPrimitiveType)c.primitive; draw.state = c.state;
    draw.alphaBorderMask = alpha_border_mask;
    draw.volumeBorderMask = volume_border_mask;
    Texture *color = nullptr, *depth = nullptr;
    if (c.color.id) {
        color = &resource(textures,c.color); check(target(*color) && color->format != HALO_METAL_DEPTH32_STENCIL8,HALO_METAL_UNSUPPORTED);
        check(color->initialized & HALO_METAL_COLOR,HALO_METAL_UNDEFINED_CONTENT); draw.color = color->object;
    } else check(!c.color.generation);
    if (c.depth_stencil.id) {
        depth = &resource(textures,c.depth_stencil); check(target(*depth) && depth->format == HALO_METAL_DEPTH32_STENCIL8,HALO_METAL_UNSUPPORTED);
        check((depth->initialized & 6) == 6,HALO_METAL_UNDEFINED_CONTENT); draw.depthStencil = depth->object;
    } else check(!c.depth_stencil.generation);
    for (unsigned i = 0; i < 4; i++) {
        if (c.textures[i].id) {
            auto &t = resource(textures,c.textures[i]); check(t.usage & HALO_METAL_SHADER_READ,HALO_METAL_UNSUPPORTED);
            const auto &s = c.samplers[i];
            if (t.type == HALO_METAL_TEXTURE_3D) {
                check(s.max_anisotropy == 1,HALO_METAL_UNSUPPORTED);
                if (s.address_u == 3 || s.address_v == 3 || s.address_w == 3) {
                    check(s.mag_filter == 1 && ((s.min_filter == 0 && s.mip_filter == 1) ||
                        (s.min_filter == 1 && s.mip_filter == 2)),
                        HALO_METAL_UNSUPPORTED);
                    // PS608 texture_border_color begins at byte528. The
                    // legacy volume path remains literalRGBA0; op21 alone
                    // authorizes a same-footprint opaque-white companion.
                    float rgba[4]; memcpy(rgba,packet.data()+c.pixel_uniforms_offset+528+i*16,sizeof(rgba));
                    if (volume_border_mask & (1u << i)) {
                        check(t.mip_levels > 1 && t.object.textureType == MTLTextureType3D &&
                            (t.format == HALO_METAL_RGBA8 || t.format == HALO_METAL_BGRA8),HALO_METAL_UNSUPPORTED);
                        for (float value : rgba) check(value >= 0 && value <= 1,HALO_METAL_UNSUPPORTED);
                    } else
                        check(rgba[0] == 0 && rgba[1] == 0 && rgba[2] == 0 && rgba[3] == 0,
                            HALO_METAL_UNSUPPORTED);
                }
            } else {
                check(s.address_w <= 2);
                check((s.address_u != 3 && s.address_v != 3) || t.type == HALO_METAL_TEXTURE_2D,
                    HALO_METAL_UNSUPPORTED);
            }
            check(t.format != HALO_METAL_DEPTH32_STENCIL8,HALO_METAL_UNSUPPORTED);
            draw.textures[i] = t.object; draw.samplers[i] = sampler(c.samplers[i]);
            if (alpha_border_mask & (1u << i)) {
                const auto &s = c.samplers[i];
                check(t.type == HALO_METAL_TEXTURE_2D && t.mip_levels > 1 &&
                    (s.address_u == 3 || s.address_v == 3) && s.min_filter == 1 && s.mag_filter == 1 &&
                    (s.mip_filter == 1 || (s.mip_filter == 2 && t.format == HALO_METAL_RGBA8)) &&
                    s.max_anisotropy == 1,HALO_METAL_UNSUPPORTED);
                // HUD redraws use RGBA8 trilinear mips. Both border samplers
                // retain the same footprint through fractional mip blends.
                // PS608 layout: texture_border_color begins at byte 528.
                float rgba[4]; memcpy(rgba,packet.data()+c.pixel_uniforms_offset+528+i*16,sizeof(rgba));
                check(rgba[0] == 0 && rgba[1] == 0 && rgba[2] == 0 && rgba[3] >= 0 && rgba[3] <= 1,
                    HALO_METAL_UNSUPPORTED);
                draw.samplers[4+i] = sampler(s,MTLSamplerBorderColorOpaqueBlack);
            }
            if (volume_border_mask & (1u << i)) {
                check(t.type == HALO_METAL_TEXTURE_3D && t.mip_levels > 1 &&
                    (s.address_u == 3 || s.address_v == 3 || s.address_w == 3),HALO_METAL_UNSUPPORTED);
                draw.samplers[4+i] = sampler(s,MTLSamplerBorderColorOpaqueWhite);
            }
        } else {
            check(!((alpha_border_mask | volume_border_mask) & (1u << i)));
            halo_metal_sampler empty{};
            check(!c.textures[i].generation && !memcmp(&empty,&c.samplers[i],sizeof(empty)));
        }
    }
    check(input_buffer != nil && input_buffer.length >= packet.size() &&
        input_buffer.contents == packet.data(),HALO_METAL_MEMORY);
    draw.vertices = draw.indices = draw.vertexUniforms = draw.pixelUniforms = input_buffer;
    draw.vertexOffset = c.vertices_offset; draw.indexOffset = c.indices_offset;
    draw.vertexUniformOffset = c.vertex_uniforms_offset; draw.pixelUniformOffset = c.pixel_uniforms_offset;
    if (query) {
        check(query->begun && query->words.size() < 65536,HALO_METAL_UNSUPPORTED);
        // Each render encoder owns a fresh result word. Portable Reset mode
        // therefore cannot replace a prior draw's result across encoders.
        draw.visibilityBuffer = [context.device newBufferWithLength:sizeof(uint64_t) options:MTLResourceStorageModeShared];
        check(draw.visibilityBuffer != nil,HALO_METAL_MEMORY);
        if (context.metrics.enabled) context.metrics.visibility_buffers++;
        memset(draw.visibilityBuffer.contents,0,sizeof(uint64_t));
        draw.visibilityMode = query->mode == HALO_METAL_VISIBILITY_BOOLEAN ?
            MTLVisibilityResultModeBoolean : MTLVisibilityResultModeCounting;
    }
    NSError *error = nil; uint32_t used = 0;
    const uint64_t pipelines_before = context.metrics.enabled ? context.draw_encoder.pipelineCreationCount : 0;
    const BOOL prepared_ok = [context.draw_encoder usedTextureMaskForDraw:draw mask:&used error:&error];
    if (context.metrics.enabled && context.draw_encoder.pipelineCreationCount != pipelines_before) {
        const auto interval = context.draw_encoder.lastPipelineCreationInterval;
        const auto header = record<halo_metal_packet>(packet,0);
        host_logf(HOST_LOG_INFO,"Native Metal pipeline: sequence %llu, command-index %u, program %u, generation %u, vertex-hash %016llx, fragment-hash %016llx, packed %08x, color-format %llu, depth-format %llu, color-mask %u, blend %u/%u/%u/%u, start %llu ns, end %llu ns, duration %llu ns, success %u",
            (unsigned long long)header.frame_sequence,command_index,c.program.id,c.program.generation,
            (unsigned long long)p.vertex_fingerprint,(unsigned long long)p.fragment_fingerprint,c.packed_mask,
            (unsigned long long)(draw.color ? draw.color.pixelFormat : MTLPixelFormatInvalid),
            (unsigned long long)(draw.depthStencil ? draw.depthStencil.pixelFormat : MTLPixelFormatInvalid),
            c.state.color_write_mask,c.state.blend_enabled,c.state.blend_source,c.state.blend_destination,c.state.blend_operation,
            (unsigned long long)interval.started,(unsigned long long)interval.ended,
            (unsigned long long)(interval.ended-interval.started),interval.succeeded ? 1u : 0u);
    }
    if (!prepared_ok) {
        host_logf(HOST_LOG_ERROR,"Native original draw preparation: %s",error.localizedDescription.UTF8String);
        throw Failure{error.code == HaloMetalDrawUnsupported ? HALO_METAL_UNSUPPORTED :
            error.code == HaloMetalDrawPipelineFailure ? HALO_METAL_GPU_ERROR : HALO_METAL_INVALID,UINT32_MAX};
    }
    for (unsigned i = 0; i < 4; i++) if (used & (1u << i)) {
        auto &t = resource(textures,c.textures[i]);
        for (uint32_t initialized : t.subresources) check(initialized & HALO_METAL_COLOR,HALO_METAL_UNDEFINED_CONTENT);
    }
    if (color && c.state.color_write_mask) initialized(*color,HALO_METAL_COLOR,false);
    uint32_t written = (c.state.depth_enabled && c.state.depth_write) ? HALO_METAL_DEPTH : 0;
    if (c.state.stencil_enabled && c.state.stencil_write_mask &&
        (c.state.stencil_fail != 1 || c.state.stencil_depth_fail != 1 || c.state.stencil_pass != 1)) written |= HALO_METAL_STENCIL;
    if (depth && written) initialized(*depth,written,false);
    if (query) query->words.push_back(draw.visibilityBuffer);
    return draw;
}
/* Fixed, bounded directional FXAA: diagonal luma estimates the edge direction,
 * then two/four bilinear taps smooth only edges that exceed local contrast.
 * This optional post effect uses existing display-encoded RGB without adding
 * gamma conversion, temporal history, texture filtering or original shaders. */
NSString *fxaa_source = @R"MSL(
#include <metal_stdlib>
using namespace metal;
struct FxaaVaryings { float4 position [[position]]; };
struct FxaaBounds { uint2 origin; uint2 extent; };
vertex FxaaVaryings fxaa_vertex(uint id [[vertex_id]]) {
    float2 p = id == 0 ? float2(-1,-1) : id == 1 ? float2(-1,3) : float2(3,-1);
    FxaaVaryings v; v.position = float4(p,0,1); return v;
}
float3 fxaa_read(texture2d<float> source, int2 p, int2 low, int2 high) {
    return source.read(uint2(clamp(p,low,high))).rgb;
}
float3 fxaa_sample(texture2d<float> source, float2 p, float2 low, float2 high) {
    constexpr sampler linear_sampler(min_filter::linear,mag_filter::linear,address::clamp_to_edge);
    float2 size = float2(source.get_width(),source.get_height());
    return source.sample(linear_sampler,clamp(p,low,high)/size,level(0)).rgb;
}
fragment float4 fxaa_fragment(FxaaVaryings v [[stage_in]], texture2d<float> source [[texture(0)]],
                              constant FxaaBounds &bounds [[buffer(0)]]) {
    int2 p = int2(v.position.xy), low = int2(bounds.origin), high = low + int2(bounds.extent) - 1;
    const float3 luma = float3(0.299f,0.587f,0.114f);
    float3 center = source.read(uint2(p)).rgb;
    float nw = dot(fxaa_read(source,p+int2(-1,-1),low,high),luma);
    float ne = dot(fxaa_read(source,p+int2( 1,-1),low,high),luma);
    float sw = dot(fxaa_read(source,p+int2(-1, 1),low,high),luma);
    float se = dot(fxaa_read(source,p+int2( 1, 1),low,high),luma);
    float mid = dot(center,luma), minimum = min(mid,min(min(nw,ne),min(sw,se)));
    float maximum = max(mid,max(max(nw,ne),max(sw,se)));
    if (maximum-minimum < max(1.0f/32.0f,maximum/8.0f)) return float4(center,1);
    float2 direction = float2(-((nw+ne)-(sw+se)),(nw+sw)-(ne+se));
    float reduction = max((nw+ne+sw+se)*(1.0f/32.0f),1.0f/128.0f);
    direction = clamp(direction/(min(abs(direction.x),abs(direction.y))+reduction),float2(-8),float2(8));
    float2 pixel = float2(p)+0.5f, first = float2(low)+0.5f, last = float2(high)+0.5f;
    float3 a = 0.5f*(fxaa_sample(source,pixel-direction/6.0f,first,last)+
                     fxaa_sample(source,pixel+direction/6.0f,first,last));
    float3 b = 0.5f*a+0.25f*(fxaa_sample(source,pixel-direction/2.0f,first,last)+
                            fxaa_sample(source,pixel+direction/2.0f,first,last));
    float candidate = dot(b,luma);
    return float4(candidate < minimum || candidate > maximum ? a : b,1);
}
)MSL";
id<MTLRenderPipelineState> make_fxaa_pipeline(id<MTLDevice> device, id<MTLLibrary> library, uint32_t color_format) {
    auto descriptor = [MTLRenderPipelineDescriptor new];
    descriptor.vertexFunction = [library newFunctionWithName:@"fxaa_vertex"];
    descriptor.fragmentFunction = [library newFunctionWithName:@"fxaa_fragment"];
    descriptor.colorAttachments[0].pixelFormat = format(color_format);
    // Leave original alpha bytes in place instead of round-tripping them.
    descriptor.colorAttachments[0].writeMask = MTLColorWriteMaskRed | MTLColorWriteMaskGreen | MTLColorWriteMaskBlue;
    NSError *error = nil;
    auto pipeline = [device newRenderPipelineStateWithDescriptor:descriptor error:&error];
    if (!pipeline) host_logf(HOST_LOG_ERROR,"Native FXAA pipeline: %s",error.localizedDescription.UTF8String);
    check(pipeline != nil,HALO_METAL_GPU_ERROR);
    return pipeline;
}
PreparedFxaa prepare_fxaa(const Texture &source) {
    auto existing = context.fxaa_pipelines.find(source.format);
    check(existing != context.fxaa_pipelines.end(),HALO_METAL_GPU_ERROR);
    auto scratch = context.fxaa_scratch;
    if (!scratch || scratch.width != source.width || scratch.height != source.height ||
        scratch.pixelFormat != source.object.pixelFormat) {
        auto descriptor = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:source.object.pixelFormat
            width:source.width height:source.height mipmapped:NO];
        descriptor.storageMode = MTLStorageModePrivate; descriptor.usage = MTLTextureUsageShaderRead;
        scratch = [context.device newTextureWithDescriptor:descriptor]; check(scratch != nil,HALO_METAL_MEMORY);
        context.fxaa_scratch = scratch;
    }
    // Prepared retains older shapes until this synchronous submission completes.
    // The context itself caches only one shape and the two accepted formats.
    return {scratch,existing->second};
}
void validate(const HaloMetalPacketView &packet, Prepared &prepared) {
    auto header = record<halo_metal_packet>(packet, 0);
    check(header.magic == HALO_METAL_MAGIC && header.abi_version == HALO_METAL_ABI_VERSION &&
        header.byte_size == packet.size() && header.command_count && header.command_count <= 65536 &&
        header.frame_sequence > context.submitted);
    auto textures = context.textures;
    auto generations = context.generations;
    auto programs = context.programs;
    auto program_generations = context.program_generations;
    auto queries = context.queries;
    auto query_generations = context.query_generations;
    auto active_query = context.active_query;
    size_t position = sizeof(header);
    for (uint32_t i = 0; i < header.command_count; i++) {
        halo_metal_command command{};
        try {
            command = record<halo_metal_command>(packet, position);
            check(command.byte_size >= sizeof(command) && !(command.byte_size & 7) &&
                command.byte_size <= packet.size() - position);
            switch (command.opcode) {
                case HALO_METAL_CREATE_TEXTURE: {
                    auto c = record<halo_metal_create>(packet, position);
                    check(command.byte_size == sizeof(c) && !c.reserved && c.width && c.height &&
                        c.width <= 8192 && c.height <= 8192 && c.resource.id && c.resource.generation && textures.size() < 4096);
                    format(c.format);
                    check(!compressed(c.format),HALO_METAL_UNSUPPORTED);
                    check(!textures.count(c.resource.id) && c.resource.generation > generations[c.resource.id], HALO_METAL_STALE_RESOURCE);
                    halo_metal_create_ex ex{{HALO_METAL_CREATE_TEXTURE_EX,sizeof(halo_metal_create_ex)},c.resource,
                        c.format,c.width,c.height,1,HALO_METAL_TEXTURE_2D,1,3,0};
                    Texture t = make_texture(ex); textures.emplace(c.resource.id,t); prepared.textures.emplace(position,t);
                    generations[c.resource.id] = c.resource.generation;
                    break;
                }
                case HALO_METAL_CREATE_TEXTURE_EX: {
                    auto c = record<halo_metal_create_ex>(packet,position);
                    check(command.byte_size == sizeof(c) && textures.size() < 4096);
                    check(!textures.count(c.resource.id) && c.resource.generation > generations[c.resource.id],HALO_METAL_STALE_RESOURCE);
                    Texture t = make_texture(c); textures.emplace(c.resource.id,t); prepared.textures.emplace(position,t);
                    generations[c.resource.id] = c.resource.generation; break;
                }
                case HALO_METAL_DELETE_TEXTURE: {
                    auto c = record<halo_metal_delete>(packet, position);
                    check(command.byte_size == sizeof(c)); resource(textures, c.resource);
                    textures.erase(c.resource.id); break;
                }
                case HALO_METAL_UPLOAD: {
                    auto c = record<halo_metal_upload>(packet, position);
                    check(command.byte_size >= sizeof(c) && !c.reserved);
                    auto &t = resource(textures, c.resource);
                    check(t.type == HALO_METAL_TEXTURE_2D && t.mip_levels == 1 &&
                        t.format != HALO_METAL_DEPTH32_STENCIL8 && !compressed(t.format),HALO_METAL_UNSUPPORTED);
                    validate_upload(packet,position,sizeof(c),extended_upload(c),t); break;
                }
                case HALO_METAL_UPLOAD_EX: {
                    auto c = record<halo_metal_upload_ex>(packet,position);
                    auto &t = resource(textures,c.resource); validate_upload(packet,position,sizeof(c),c,t); break;
                }
                case HALO_METAL_CLEAR:
                case HALO_METAL_CLEAR_CHANNELS: {
                    auto c = record<halo_metal_clear>(packet, position);
                    uint32_t mask = 15;
                    if (command.opcode == HALO_METAL_CLEAR_CHANNELS) {
                        auto extended = record<halo_metal_clear_channels>(packet,position);
                        check(command.byte_size == sizeof(extended) && !extended.reserved &&
                            extended.color_write_mask <= 15);
                        mask = extended.color_write_mask;
                        check((c.planes & HALO_METAL_COLOR) ? mask != 0 : mask == 0);
                    } else check(command.byte_size == sizeof(c));
                    check(true && !c.reserved && c.planes && !(c.planes & ~7u) && c.stencil <= 255);
                    for (float value : c.rgba) check(std::isfinite(value));
                    check(std::isfinite(c.depth) && c.depth >= 0 && c.depth <= 1);
                    Texture *color = nullptr, *depth = nullptr;
                    if (c.planes & HALO_METAL_COLOR) {
                        color = &resource(textures,c.color);
                        check(target(*color) && color->format != HALO_METAL_DEPTH32_STENCIL8,HALO_METAL_UNSUPPORTED);
                        rectangle(*color,c.x,c.y,c.width,c.height);
                        initialized(*color,HALO_METAL_COLOR,mask == 15 && full(*color,c.x,c.y,c.width,c.height));
                    } else check(!c.color.id && !c.color.generation);
                    if (c.planes & (HALO_METAL_DEPTH | HALO_METAL_STENCIL)) {
                        depth = &resource(textures,c.depth_stencil);
                        check(target(*depth) && depth->format == HALO_METAL_DEPTH32_STENCIL8,HALO_METAL_UNSUPPORTED);
                        rectangle(*depth,c.x,c.y,c.width,c.height);
                        check(!color || (color->width <= depth->width && color->height <= depth->height));
                        initialized(*depth,c.planes & 6,full(*depth,c.x,c.y,c.width,c.height));
                    } else check(!c.depth_stencil.id && !c.depth_stencil.generation);
                    break;
                }
                case HALO_METAL_COPY: {
                    auto c = record<halo_metal_copy>(packet, position);
                    check(command.byte_size == sizeof(c) && c.source.id != c.destination.id);
                    auto &source = resource(textures,c.source); auto &destination = resource(textures,c.destination);
                    check(target(source) && target(destination) && source.format == destination.format &&
                        source.format != HALO_METAL_DEPTH32_STENCIL8, HALO_METAL_UNSUPPORTED);
                    check(source.initialized & HALO_METAL_COLOR, HALO_METAL_UNDEFINED_CONTENT);
                    rectangle(source,c.source_x,c.source_y,c.width,c.height);
                    rectangle(destination,c.destination_x,c.destination_y,c.width,c.height);
                    initialized(destination,HALO_METAL_COLOR,full(destination,c.destination_x,c.destination_y,c.width,c.height));
                    break;
                }
                case HALO_METAL_COPY_SUBRESOURCE: {
                    auto c = record<halo_metal_copy_subresource>(packet,position);
                    check(command.byte_size == sizeof(c));
                    auto &source = resource(textures,c.source); auto &destination = resource(textures,c.destination);
                    validate_copy_subresource(c,source,destination); break;
                }
                case HALO_METAL_FXAA: {
                    auto c = record<halo_metal_fxaa>(packet,position);
                    check(command.byte_size == sizeof(c) && context.fxaa_enabled && !active_query.id,
                        HALO_METAL_UNSUPPORTED);
                    auto &t = resource(textures,c.source);
                    check(target(t) && (t.usage & HALO_METAL_SHADER_READ) &&
                        (t.format == HALO_METAL_RGBA8 || t.format == HALO_METAL_BGRA8),HALO_METAL_UNSUPPORTED);
                    rectangle(t,c.x,c.y,c.width,c.height);
                    initialized(t,HALO_METAL_COLOR,false);
                    prepared.fxaa.emplace(position,prepare_fxaa(t)); break;
                }
                case HALO_METAL_PRESENT: {
                    auto c = record<halo_metal_present>(packet, position);
                    check(command.byte_size == sizeof(c) && context.layer && !active_query.id &&
                        i + 1 == header.command_count, HALO_METAL_UNSUPPORTED);
                    auto &t = resource(textures,c.source);
                    check(target(t) && (t.initialized & HALO_METAL_COLOR) && t.format == HALO_METAL_BGRA8 &&
                        context.layer.drawableSize.width == t.width && context.layer.drawableSize.height == t.height, HALO_METAL_UNSUPPORTED);
                    break;
                }
                case HALO_METAL_DISPLAY_SETTINGS: {
                    auto c = record<halo_metal_display_settings>(packet,position);
                    check(command.byte_size == sizeof(c) && context.layer && !c.reserved &&
                        !(c.display_flags & ~HALO_METAL_DISPLAY_VSYNC),HALO_METAL_UNSUPPORTED);
                    break;
                }
                case HALO_METAL_PRESENT_SCALED: {
                    auto c = record<halo_metal_present_scaled>(packet,position);
                    check(command.byte_size == sizeof(c) && context.layer && !active_query.id &&
                        i + 1 == header.command_count && !c.reserved &&
                        !(c.display_flags & ~HALO_METAL_DISPLAY_VSYNC),HALO_METAL_UNSUPPORTED);
                    auto &t = resource(textures,c.source);
                    check(target(t) && (t.initialized & HALO_METAL_COLOR) && (t.usage & HALO_METAL_SHADER_READ) &&
                        t.format != HALO_METAL_DEPTH32_STENCIL8 &&
                        context.layer.drawableSize.width > 0 && context.layer.drawableSize.height > 0,
                        HALO_METAL_UNSUPPORTED);
                    break;
                }
                case HALO_METAL_CREATE_PROGRAM: {
                    auto c = record<halo_metal_program>(packet,position);
                    check(command.byte_size >= sizeof(c) && c.resource.id && c.resource.generation && programs.size() < 4096);
                    check(c.vertex_compiler_contract <= 1 && c.fragment_compiler_contract <= 1,HALO_METAL_UNSUPPORTED);
                    check(c.vertex_source_size <= 4u * 1024u * 1024u && c.fragment_source_size <= 4u * 1024u * 1024u);
                    inline_range(position,command.byte_size,sizeof(c),c.vertex_source_offset,c.vertex_source_size,16);
                    inline_range(position,command.byte_size,sizeof(c),c.fragment_source_offset,c.fragment_source_size,16);
                    check(!programs.count(c.resource.id) && c.resource.generation > program_generations[c.resource.id],HALO_METAL_STALE_RESOURCE);
                    Program p = compile_program(prepared,packet,c,i);
                    programs.emplace(c.resource.id,p); prepared.programs.emplace(position,p);
                    program_generations[c.resource.id] = c.resource.generation; break;
                }
                case HALO_METAL_DELETE_PROGRAM: {
                    auto c = record<halo_metal_delete>(packet,position);
                    check(command.byte_size == sizeof(c)); program(programs,c.resource); programs.erase(c.resource.id); break;
                }
                case HALO_METAL_DRAW:
                case HALO_METAL_DRAW_ALPHA_BORDER:
                case HALO_METAL_DRAW_VOLUME_BORDER:
                case HALO_METAL_DRAW_COMPACT: {
                    auto c = record<halo_metal_draw>(packet,position);
                    uint32_t mask = 0, volume_mask = 0, compact_bytes = 0;
                    if (command.opcode == HALO_METAL_DRAW_ALPHA_BORDER) {
                        auto extended = record<halo_metal_draw_alpha_border>(packet,position);
                        check(command.byte_size >= sizeof(extended) && !extended.reserved &&
                            extended.stage_mask && extended.stage_mask <= 15);
                        mask = extended.stage_mask;
                    }
                    if (command.opcode == HALO_METAL_DRAW_VOLUME_BORDER) {
                        auto extended = record<halo_metal_draw_volume_border>(packet,position);
                        check(command.byte_size >= sizeof(extended) && extended.volume_stage_mask &&
                            extended.volume_stage_mask <= 15 && extended.alpha_stage_mask <= 15 &&
                            !(extended.volume_stage_mask & extended.alpha_stage_mask));
                        volume_mask = extended.volume_stage_mask; mask = extended.alpha_stage_mask;
                    }
                    if (command.opcode == HALO_METAL_DRAW_COMPACT) {
                        check(context.compact_vertices_enabled,HALO_METAL_UNSUPPORTED);
                        auto extended = record<halo_metal_draw_compact>(packet,position);
                        check(command.byte_size >= sizeof(extended) && !extended.reserved &&
                            extended.vertex_bytes && extended.volume_stage_mask <= 15 &&
                            extended.alpha_stage_mask <= 15 &&
                            !(extended.volume_stage_mask & extended.alpha_stage_mask));
                        compact_bytes = extended.vertex_bytes;
                        volume_mask = extended.volume_stage_mask; mask = extended.alpha_stage_mask;
                    }
                    auto *query = active_query.id ? &visibility(queries,active_query) : nullptr;
                    prepared.draws.emplace(position,prepare_draw(packet,position,c,prepared.input_buffer,textures,programs,
                        query,mask,volume_mask,i,compact_bytes)); break;
                }
                case HALO_METAL_CREATE_VISIBILITY: {
                    auto c = record<halo_metal_create_visibility>(packet,position);
                    check(command.byte_size == sizeof(c) && !c.reserved && c.resource.id && c.resource.generation && queries.size() < 4096);
                    check(c.mode == HALO_METAL_VISIBILITY_BOOLEAN || c.mode == HALO_METAL_VISIBILITY_COUNTING,HALO_METAL_UNSUPPORTED);
                    check(!queries.count(c.resource.id) && c.resource.generation > query_generations[c.resource.id],HALO_METAL_STALE_RESOURCE);
                    queries.emplace(c.resource.id,Visibility{c.resource.generation,c.mode,0,false,false,0,{}});
                    query_generations[c.resource.id] = c.resource.generation; break;
                }
                case HALO_METAL_DELETE_VISIBILITY: {
                    auto c = record<halo_metal_visibility>(packet,position);
                    check(command.byte_size == sizeof(c)); visibility(queries,c.resource);
                    check(!same_ref(active_query,c.resource)); queries.erase(c.resource.id); break;
                }
                case HALO_METAL_BEGIN_VISIBILITY:
                case HALO_METAL_END_VISIBILITY: {
                    auto c = record<halo_metal_visibility>(packet,position);
                    check(command.byte_size == sizeof(c));
                    if (command.opcode == HALO_METAL_BEGIN_VISIBILITY) begin_visibility(queries,active_query,c.resource);
                    else end_visibility(queries,active_query,c.resource,header.frame_sequence);
                    break;
                }
                default: throw Failure{HALO_METAL_UNSUPPORTED, i};
            }
            position += command.byte_size;
        } catch (Failure f) {
            host_logf(HOST_LOG_ERROR,"Native Metal preflight rejection: sequence %llu index %u opcode %u offset %zu extent %u packet bytes %zu commands %u status %d",
                (unsigned long long)header.frame_sequence,i,command.opcode,position,
                command.byte_size,packet.size(),header.command_count,f.status);
            f.index = i; throw f;
        }
    }
    check(position == packet.size());
}

NSString *clear_source = @"#include <metal_stdlib>\nusing namespace metal;\n"
    "struct V { float4 position [[position]]; };\n"
    "vertex V clear_vertex(uint i [[vertex_id]]) { V v; const float2 p[3] = {float2(-1,-1),float2(3,-1),float2(-1,3)}; v.position=float4(p[i],0,1); return v; }\n"
    "struct C { float4 color; float depth; };\n"
    "struct F { float4 color [[color(0)]]; float depth [[depth(any)]]; };\n"
    "fragment F clear_fragment(constant C &c [[buffer(0)]]) { F f; f.color=c.color; f.depth=c.depth; return f; }\n"
    "fragment float4 clear_color(constant C &c [[buffer(0)]]) { return c.color; }\n"
    "struct D { float depth [[depth(any)]]; };\n"
    "fragment D clear_depth(constant C &c [[buffer(0)]]) { D d; d.depth=c.depth; return d; }\n";

id<MTLRenderPipelineState> clear_pipeline(uint32_t color_format, uint32_t planes, uint32_t mask) {
    uint64_t key = uint64_t(color_format) << 32 | (uint64_t(mask) << 8) | planes;
    auto existing = context.clear_pipelines.find(key);
    if (existing != context.clear_pipelines.end()) return existing->second;
    auto description = [MTLRenderPipelineDescriptor new];
    description.vertexFunction = [context.clear_library newFunctionWithName:@"clear_vertex"];
    NSString *fragment = color_format ? (planes & 6 ? @"clear_fragment" : @"clear_color") : @"clear_depth";
    description.fragmentFunction = [context.clear_library newFunctionWithName:fragment];
    if (color_format) {
        description.colorAttachments[0].pixelFormat = format(color_format);
        description.colorAttachments[0].writeMask = (MTLColorWriteMask)(
            (mask & 1 ? MTLColorWriteMaskRed : 0) | (mask & 2 ? MTLColorWriteMaskGreen : 0) |
            (mask & 4 ? MTLColorWriteMaskBlue : 0) | (mask & 8 ? MTLColorWriteMaskAlpha : 0));
    }
    if (planes & (HALO_METAL_DEPTH | HALO_METAL_STENCIL)) {
        // Metal requires both format declarations for a combined attachment;
        // write enable/load/store below independently preserve each aspect.
        description.depthAttachmentPixelFormat = MTLPixelFormatDepth32Float_Stencil8;
        description.stencilAttachmentPixelFormat = MTLPixelFormatDepth32Float_Stencil8;
    }
    NSError *error = nil;
    auto result = [context.device newRenderPipelineStateWithDescriptor:description error:&error];
    if (!result) host_logf(HOST_LOG_ERROR,"Native clear pipeline: %s",error.localizedDescription.UTF8String);
    check(result != nil, HALO_METAL_GPU_ERROR);
    context.clear_pipelines.emplace(key,result); return result;
}
void clear(id<MTLCommandBuffer> buffer, halo_metal_clear c, uint32_t mask = 15) {
    Texture *color = c.color.id ? &resource(context.textures,c.color) : nullptr;
    Texture *depth = c.depth_stencil.id ? &resource(context.textures,c.depth_stencil) : nullptr;
    bool whole = (!color || (mask == 15 && full(*color,c.x,c.y,c.width,c.height))) &&
        (!depth || full(*depth,c.x,c.y,c.width,c.height));
    auto pass = [MTLRenderPassDescriptor renderPassDescriptor];
    const Texture &footprint = color ? *color : *depth;
    pass.renderTargetWidth = footprint.width; pass.renderTargetHeight = footprint.height;
    if (color) {
        pass.colorAttachments[0].texture = color->object;
        pass.colorAttachments[0].loadAction = whole ? MTLLoadActionClear : MTLLoadActionLoad;
        pass.colorAttachments[0].storeAction = MTLStoreActionStore;
        pass.colorAttachments[0].clearColor = MTLClearColorMake(c.rgba[0],c.rgba[1],c.rgba[2],c.rgba[3]);
    }
    if (depth) {
        pass.depthAttachment.texture = depth->object; pass.stencilAttachment.texture = depth->object;
        pass.depthAttachment.loadAction = whole && (c.planes & HALO_METAL_DEPTH) ? MTLLoadActionClear :
            (depth->initialized & HALO_METAL_DEPTH) ? MTLLoadActionLoad : MTLLoadActionDontCare;
        pass.stencilAttachment.loadAction = whole && (c.planes & HALO_METAL_STENCIL) ? MTLLoadActionClear :
            (depth->initialized & HALO_METAL_STENCIL) ? MTLLoadActionLoad : MTLLoadActionDontCare;
        pass.depthAttachment.storeAction = pass.stencilAttachment.storeAction = MTLStoreActionStore;
        pass.depthAttachment.clearDepth = c.depth; pass.stencilAttachment.clearStencil = c.stencil;
    }
    auto encoder = [buffer renderCommandEncoderWithDescriptor:pass]; check(encoder != nil, HALO_METAL_GPU_ERROR);
    if (!whole) {
        [encoder setRenderPipelineState:clear_pipeline(color ? color->format : 0,c.planes,mask)];
        auto state = [MTLDepthStencilDescriptor new]; state.depthCompareFunction = MTLCompareFunctionAlways;
        state.depthWriteEnabled = (c.planes & HALO_METAL_DEPTH) != 0;
        if (c.planes & HALO_METAL_STENCIL) {
            auto stencil = [MTLStencilDescriptor new]; stencil.stencilCompareFunction = MTLCompareFunctionAlways;
            stencil.depthStencilPassOperation = MTLStencilOperationReplace;
            stencil.readMask = stencil.writeMask = 255; state.frontFaceStencil = state.backFaceStencil = stencil;
        }
        auto depth_state = [context.device newDepthStencilStateWithDescriptor:state]; check(depth_state != nil,HALO_METAL_GPU_ERROR);
        [encoder setDepthStencilState:depth_state];
        [encoder setStencilReferenceValue:c.stencil];
        const Texture &t = color ? *color : *depth;
        [encoder setViewport:MTLViewport{0,0,(double)t.width,(double)t.height,0,1}];
        [encoder setScissorRect:MTLScissorRect{c.x,c.y,c.width,c.height}];
        struct alignas(16) Constants { float rgba[4]; float depth; float pad[3]; } constants = {};
        memcpy(constants.rgba,c.rgba,sizeof(c.rgba)); constants.depth = c.depth;
        [encoder setFragmentBytes:&constants length:sizeof(constants) atIndex:0];
        [encoder drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:3];
    }
    [encoder endEncoding];
    if (color) initialized(*color,HALO_METAL_COLOR,mask == 15 && full(*color,c.x,c.y,c.width,c.height));
    if (depth) initialized(*depth,c.planes & 6,full(*depth,c.x,c.y,c.width,c.height));
}
void complete(id<MTLCommandBuffer> buffer, bool measured = false, bool wait = false) {
    if (gpu_failed.load(std::memory_order_acquire)) {
        context.poisoned = true; throw Failure{HALO_METAL_GPU_ERROR,UINT32_MAX};
    }
    uint64_t sequence = context.submitted;
    if (packet_pending >= 0) {
        packet_slots[packet_pending].command = buffer;
        packet_pending = -1;
    }
    [buffer addCompletedHandler:^(id<MTLCommandBuffer> done) {
        if (done.status != MTLCommandBufferStatusCompleted)
            host_logf(HOST_LOG_ERROR,"Native Metal command failure: %s",done.error.localizedDescription.UTF8String);
        note_gpu_sequence(sequence, done.status);
    }];
    uint64_t started = measured ? metrics_start() : 0;
    [buffer commit];
    if (measured) context.metrics.commit_ns += metrics_elapsed(started);
    if (!wait) return;
    started = measured ? metrics_start() : 0;
    [buffer waitUntilCompleted];
    if (measured) context.metrics.completion_wait_ns += metrics_elapsed(started);
    if (buffer.status != MTLCommandBufferStatusCompleted) {
        context.poisoned = true; throw Failure{HALO_METAL_GPU_ERROR,UINT32_MAX};
    }
}
void upload(id<MTLCommandBuffer> buffer, const HaloMetalPacketView &packet, halo_metal_upload_ex c, Texture &texture) {
    NSUInteger tight = c.width * (c.plane == HALO_METAL_STENCIL ? 1u : 4u), rows = c.height;
    if (compressed(texture.format)) { tight = ((c.width + 3) / 4) * block_bytes(texture.format); rows = (c.height + 3) / 4; }
    NSUInteger row = (tight + 255) & ~NSUInteger(255);
    NSUInteger image = row * rows;
    auto staging = [context.device newBufferWithLength:image * c.depth options:MTLResourceStorageModeShared];
    check(staging != nil,HALO_METAL_MEMORY);
    if (context.metrics.enabled) context.metrics.upload_buffers++;
    for (NSUInteger z = 0; z < c.depth; z++) for (NSUInteger y = 0; y < rows; y++)
        memcpy((uint8_t *)staging.contents + image * z + row * y,
            packet.data() + c.data_offset + uint64_t(c.bytes_per_image) * z + uint64_t(c.bytes_per_row) * y,tight);
    auto blit = [buffer blitCommandEncoder]; check(blit != nil,HALO_METAL_GPU_ERROR);
    MTLBlitOption option = c.plane == HALO_METAL_DEPTH ? MTLBlitOptionDepthFromDepthStencil :
        c.plane == HALO_METAL_STENCIL ? MTLBlitOptionStencilFromDepthStencil : MTLBlitOptionNone;
    [blit copyFromBuffer:staging sourceOffset:0 sourceBytesPerRow:row sourceBytesPerImage:image
        sourceSize:MTLSizeMake(c.width,c.height,c.depth) toTexture:texture.object destinationSlice:c.slice destinationLevel:c.mip
        destinationOrigin:MTLOriginMake(c.x,c.y,c.z) options:option];
    [blit endEncoding];
    initialized(texture,c.plane,!c.x && !c.y && !c.z && c.width == dimension(texture.width,c.mip) &&
        c.height == dimension(texture.height,c.mip) && c.depth == dimension(texture.depth,c.mip),c.mip,c.slice);
}
NSString *present_source = @R"MSL(
#include <metal_stdlib>
using namespace metal;
struct PresentVaryings { float4 position [[position]]; float2 uv; };
vertex PresentVaryings present_vertex(uint id [[vertex_id]]) {
    float2 p = id == 0 ? float2(-1,-1) : id == 1 ? float2(-1,3) : float2(3,-1);
    return {float4(p,0,1),float2(p.x * 0.5 + 0.5,0.5 - p.y * 0.5)};
}
fragment float4 present_fragment(PresentVaryings v [[stage_in]],
    texture2d<float> source [[texture(0)]],sampler linear_sampler [[sampler(0)]]) {
    float4 value=source.sample(linear_sampler,v.uv,level(0)); value.a=1.0; return value;
}
)MSL";
void present_scaled(id<MTLCommandBuffer> buffer, const Texture &t,uint32_t flags,uint32_t index) {
    display_link_start();
    apply_display_sync(flags);
    struct PresentHold {
        bool held;
        bool armed = false;
        ~PresentHold() { if (held && !armed && present_slot) dispatch_semaphore_signal(present_slot); }
    } hold{present_acquire()};
    if (!context.present_pipeline) {
        NSError *error=nil;
        auto options=[MTLCompileOptions new];
        auto library=[context.device newLibraryWithSource:present_source options:options error:&error];
        check(library != nil,HALO_METAL_GPU_ERROR,index);
        auto descriptor=[MTLRenderPipelineDescriptor new];
        descriptor.vertexFunction=[library newFunctionWithName:@"present_vertex"];
        descriptor.fragmentFunction=[library newFunctionWithName:@"present_fragment"];
        descriptor.colorAttachments[0].pixelFormat=MTLPixelFormatBGRA8Unorm;
        context.present_pipeline=[context.device newRenderPipelineStateWithDescriptor:descriptor error:&error];
        check(context.present_pipeline != nil,HALO_METAL_GPU_ERROR,index);
        auto sampler=[MTLSamplerDescriptor new];
        sampler.minFilter=sampler.magFilter=MTLSamplerMinMagFilterLinear;
        sampler.sAddressMode=sampler.tAddressMode=MTLSamplerAddressModeClampToEdge;
        context.present_sampler=[context.device newSamplerStateWithDescriptor:sampler];
        check(context.present_sampler != nil,HALO_METAL_GPU_ERROR,index);
    }
    uint64_t drawable_started = metrics_start();
    auto drawable=[context.layer nextDrawable];
    context.metrics.drawable_wait_ns += metrics_elapsed(drawable_started);
    check(drawable != nil,HALO_METAL_GPU_ERROR,index);
    NSUInteger pixel_width=drawable.texture.width,pixel_height=drawable.texture.height;
    NSUInteger width=pixel_width,height=pixel_width * t.height / t.width;
    if (height>pixel_height) { height=pixel_height;width=pixel_height * t.width / t.height; }
    check(width && height,HALO_METAL_GPU_ERROR,index);
    auto pass=[MTLRenderPassDescriptor renderPassDescriptor];
    pass.colorAttachments[0].texture=drawable.texture;
    pass.colorAttachments[0].loadAction=MTLLoadActionClear;
    pass.colorAttachments[0].storeAction=MTLStoreActionStore;
    pass.colorAttachments[0].clearColor=MTLClearColorMake(0,0,0,1);
    auto encoder=[buffer renderCommandEncoderWithDescriptor:pass];check(encoder != nil,HALO_METAL_GPU_ERROR,index);
    [encoder setRenderPipelineState:context.present_pipeline];
    [encoder setViewport:MTLViewport{double((pixel_width-width)/2),double((pixel_height-height)/2),double(width),double(height),0,1}];
    [encoder setFragmentTexture:t.object atIndex:0];[encoder setFragmentSamplerState:context.present_sampler atIndex:0];
    [encoder drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:3];[encoder endEncoding];
    present_schedule(drawable);
    hold.armed = true;
    present_drawable(buffer, drawable);
}
void fxaa(id<MTLCommandBuffer> buffer, Texture &source, const halo_metal_fxaa &c,
          const PreparedFxaa &prepared) {
    auto blit = [buffer blitCommandEncoder]; check(blit != nil,HALO_METAL_GPU_ERROR);
    // Only the clamped viewport is read by the filter. Snapshot it before the
    // RGB-only render pass, avoiding read/write feedback on the guest target.
    [blit copyFromTexture:source.object sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(c.x,c.y,0)
        sourceSize:MTLSizeMake(c.width,c.height,1) toTexture:prepared.scratch destinationSlice:0 destinationLevel:0
        destinationOrigin:MTLOriginMake(c.x,c.y,0)];
    [blit endEncoding];
    auto pass = [MTLRenderPassDescriptor renderPassDescriptor];
    pass.colorAttachments[0].texture = source.object;
    pass.colorAttachments[0].loadAction = MTLLoadActionLoad;
    pass.colorAttachments[0].storeAction = MTLStoreActionStore;
    auto encoder = [buffer renderCommandEncoderWithDescriptor:pass]; check(encoder != nil,HALO_METAL_GPU_ERROR);
    [encoder setRenderPipelineState:prepared.pipeline];
    [encoder setViewport:MTLViewport{0,0,(double)source.width,(double)source.height,0,1}];
    [encoder setScissorRect:MTLScissorRect{c.x,c.y,c.width,c.height}];
    [encoder setFragmentTexture:prepared.scratch atIndex:0];
    const uint32_t bounds[] = {c.x,c.y,c.width,c.height};
    [encoder setFragmentBytes:bounds length:sizeof(bounds) atIndex:0];
    [encoder drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:3];
    [encoder endEncoding];
    initialized(source,HALO_METAL_COLOR,false);
}
void execute(const HaloMetalPacketView &packet, const Prepared &prepared) {
    // A failed packet must close its retained draw pass before command-buffer
    // ownership is released. Normal execution closes it before every boundary.
    struct DrawPassScope {
        HaloMetalDrawEncoder *encoder;
        ~DrawPassScope() { [encoder endEncoding]; }
    } draw_scope{context.draw_encoder};
    auto header = record<halo_metal_packet>(packet,0);
    auto buffer = [context.queue commandBuffer]; check(buffer != nil,HALO_METAL_GPU_ERROR);
    buffer.label = [NSString stringWithFormat:@"Halo guest native frame %llu",header.frame_sequence];
    const uint64_t drawable_before = context.metrics.drawable_wait_ns;
    const NSUInteger passes_before = context.draw_encoder.renderPassCount;
    uint64_t encode_started = metrics_start();
    size_t position = sizeof(header);
    for (uint32_t i = 0; i < header.command_count; i++) {
        auto command = record<halo_metal_command>(packet,position);
        // Contiguous original draws alone may share a pass. Keep uploads,
        // clears, copies, queries, resource changes and presentation in their
        // exact original order with a completed attachment store boundary.
        if (command.opcode != HALO_METAL_DRAW && command.opcode != HALO_METAL_DRAW_ALPHA_BORDER &&
            command.opcode != HALO_METAL_DRAW_VOLUME_BORDER && command.opcode != HALO_METAL_DRAW_COMPACT)
            [context.draw_encoder endEncoding];
        switch (command.opcode) {
            case HALO_METAL_CREATE_TEXTURE:
            case HALO_METAL_CREATE_TEXTURE_EX: {
                auto c = record<halo_metal_delete>(packet,position);
                context.textures.emplace(c.resource.id,prepared.textures.at(position));
                context.generations[c.resource.id] = c.resource.generation; break;
            }
            case HALO_METAL_DELETE_TEXTURE: {
                auto c = record<halo_metal_delete>(packet,position); context.textures.erase(c.resource.id); break;
            }
            case HALO_METAL_UPLOAD: {
                auto c = record<halo_metal_upload>(packet,position); auto &t = resource(context.textures,c.resource);
                upload(buffer,packet,extended_upload(c),t); break;
            }
            case HALO_METAL_UPLOAD_EX: {
                auto c = record<halo_metal_upload_ex>(packet,position); auto &t = resource(context.textures,c.resource);
                upload(buffer,packet,c,t); break;
            }
            case HALO_METAL_CLEAR: clear(buffer,record<halo_metal_clear>(packet,position)); break;
            case HALO_METAL_CLEAR_CHANNELS: {
                auto c = record<halo_metal_clear_channels>(packet,position);
                clear(buffer,c.clear,c.color_write_mask); break;
            }
            case HALO_METAL_DISPLAY_SETTINGS: {
                auto c = record<halo_metal_display_settings>(packet,position);
                apply_display_sync(c.display_flags);
                break;
            }
            case HALO_METAL_PRESENT_SCALED: {
                auto c = record<halo_metal_present_scaled>(packet,position);
                present_scaled(buffer,resource(context.textures,c.source),c.display_flags,i);
                if (context.metrics.enabled) context.metrics.frames++;
                break;
            }
            case HALO_METAL_COPY: {
                auto c = record<halo_metal_copy>(packet,position); auto &s = resource(context.textures,c.source); auto &d = resource(context.textures,c.destination);
                auto blit = [buffer blitCommandEncoder];
                check(blit != nil,HALO_METAL_GPU_ERROR,i);
                [blit copyFromTexture:s.object sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(c.source_x,c.source_y,0)
                    sourceSize:MTLSizeMake(c.width,c.height,1) toTexture:d.object destinationSlice:0 destinationLevel:0 destinationOrigin:MTLOriginMake(c.destination_x,c.destination_y,0)];
                [blit endEncoding]; initialized(d,HALO_METAL_COLOR,full(d,c.destination_x,c.destination_y,c.width,c.height)); break;
            }
            case HALO_METAL_COPY_SUBRESOURCE: {
                auto c = record<halo_metal_copy_subresource>(packet,position);
                auto &s = resource(context.textures,c.source); auto &d = resource(context.textures,c.destination);
                auto blit = [buffer blitCommandEncoder]; check(blit != nil,HALO_METAL_GPU_ERROR,i);
                [blit copyFromTexture:s.object sourceSlice:c.source_slice sourceLevel:c.source_mip
                    sourceOrigin:MTLOriginMake(c.source_x,c.source_y,0) sourceSize:MTLSizeMake(c.width,c.height,1)
                    toTexture:d.object destinationSlice:c.destination_slice destinationLevel:c.destination_mip
                    destinationOrigin:MTLOriginMake(c.destination_x,c.destination_y,0)];
                [blit endEncoding];
                if (context.metrics.enabled) context.metrics.subresource_copies++;
                initialized(d,HALO_METAL_COLOR,
                    full_subresource(d,c.destination_mip,c.destination_x,c.destination_y,c.width,c.height),
                    c.destination_mip,c.destination_slice); break;
            }
            case HALO_METAL_FXAA: {
                auto c = record<halo_metal_fxaa>(packet,position);
                fxaa(buffer,resource(context.textures,c.source),c,prepared.fxaa.at(position)); break;
            }
            case HALO_METAL_PRESENT: {
                auto c = record<halo_metal_present>(packet,position); auto &t = resource(context.textures,c.source);
                struct PresentHold {
                    bool held;
                    bool armed = false;
                    ~PresentHold() { if (held && !armed && present_slot) dispatch_semaphore_signal(present_slot); }
                } hold{present_acquire()};
                uint64_t drawable_started = metrics_start();
                auto drawable = [context.layer nextDrawable];
                context.metrics.drawable_wait_ns += metrics_elapsed(drawable_started);
                check(drawable && drawable.texture.width == t.width && drawable.texture.height == t.height && drawable.texture.pixelFormat == t.object.pixelFormat,HALO_METAL_GPU_ERROR,i);
                auto blit = [buffer blitCommandEncoder];
                check(blit != nil,HALO_METAL_GPU_ERROR,i);
                [blit copyFromTexture:t.object sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0,0,0)
                    sourceSize:MTLSizeMake(t.width,t.height,1) toTexture:drawable.texture destinationSlice:0 destinationLevel:0 destinationOrigin:MTLOriginMake(0,0,0)];
                [blit endEncoding];
                present_schedule(drawable);
                hold.armed = true;
                present_drawable(buffer, drawable);
                if (context.metrics.enabled) context.metrics.frames++;
                break;
            }
            case HALO_METAL_CREATE_PROGRAM: {
                auto c = record<halo_metal_program>(packet,position);
                context.programs.emplace(c.resource.id,prepared.programs.at(position));
                context.program_generations[c.resource.id] = c.resource.generation; break;
            }
            case HALO_METAL_DELETE_PROGRAM: {
                auto c = record<halo_metal_delete>(packet,position); auto &p = program(context.programs,c.resource);
                remove_unused_program_pipelines(p,c.resource.id);
                context.programs.erase(c.resource.id); break;
            }
            case HALO_METAL_DRAW:
            case HALO_METAL_DRAW_ALPHA_BORDER:
            case HALO_METAL_DRAW_VOLUME_BORDER:
            case HALO_METAL_DRAW_COMPACT: {
                auto c = record<halo_metal_draw>(packet,position); NSError *error = nil;
                const auto &draw = prepared.draws.at(position);
                check([context.draw_encoder encodeDraw:draw commandBuffer:buffer reusePass:YES error:&error],HALO_METAL_GPU_ERROR,i);
                if (context.metrics.enabled) context.metrics.draws++;
                if (context.active_query.id)
                    visibility(context.queries,context.active_query).words.push_back(draw.visibilityBuffer);
                if (c.color.id && c.state.color_write_mask) initialized(resource(context.textures,c.color),HALO_METAL_COLOR,false);
                uint32_t written = (c.state.depth_enabled && c.state.depth_write) ? HALO_METAL_DEPTH : 0;
                if (c.state.stencil_enabled && c.state.stencil_write_mask &&
                    (c.state.stencil_fail != 1 || c.state.stencil_depth_fail != 1 || c.state.stencil_pass != 1)) written |= HALO_METAL_STENCIL;
                if (c.depth_stencil.id && written) initialized(resource(context.textures,c.depth_stencil),written,false);
                break;
            }
            case HALO_METAL_CREATE_VISIBILITY: {
                auto c = record<halo_metal_create_visibility>(packet,position);
                context.queries.emplace(c.resource.id,Visibility{c.resource.generation,c.mode,0,false,false,0,{}});
                context.query_generations[c.resource.id] = c.resource.generation; break;
            }
            case HALO_METAL_DELETE_VISIBILITY: {
                auto c = record<halo_metal_visibility>(packet,position); context.queries.erase(c.resource.id); break;
            }
            case HALO_METAL_BEGIN_VISIBILITY:
            case HALO_METAL_END_VISIBILITY: {
                auto c = record<halo_metal_visibility>(packet,position);
                if (command.opcode == HALO_METAL_BEGIN_VISIBILITY)
                    begin_visibility(context.queries,context.active_query,c.resource);
                else end_visibility(context.queries,context.active_query,c.resource,header.frame_sequence);
                break;
            }
        }
        position += command.byte_size;
    }
    [context.draw_encoder endEncoding];
    if (context.metrics.enabled) context.metrics.render_passes += context.draw_encoder.renderPassCount - passes_before;
    const uint64_t elapsed = metrics_elapsed(encode_started);
    const uint64_t drawable_elapsed = context.metrics.drawable_wait_ns - drawable_before;
    if (context.metrics.enabled) context.metrics.encode_ns += elapsed >= drawable_elapsed ? elapsed - drawable_elapsed : 0;
    context.submitted = header.frame_sequence; complete(buffer,true,false);
    context.completed = gpu_completed.load(std::memory_order_acquire);
}
}

extern "C" int host_metal_initialize(uint32_t window,uint32_t flags,uint32_t output,uint32_t size) {
    @autoreleasepool { std::lock_guard<std::mutex> guard(lock);
        try {
            validate_reply(output,size);
            check(!context.device && !(flags & ~(HALO_METAL_OFFSCREEN | HALO_METAL_ENABLE_FXAA |
                HALO_METAL_ENABLE_COMPACT_VERTICES)) &&
                ((flags & HALO_METAL_OFFSCREEN) ? !window : window != 0));
            auto device = MTLCreateSystemDefaultDevice(); check(device != nil,HALO_METAL_GPU_ERROR);
            CAMetalLayer *layer = nil;
            auto queue = [device newCommandQueue]; check(queue != nil,HALO_METAL_GPU_ERROR);
            auto options = [MTLCompileOptions new];
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
            options.fastMathEnabled = NO;
#pragma clang diagnostic pop
            if (@available(macOS 15.0, *)) { options.mathMode = MTLMathModeSafe; options.mathFloatingPointFunctions = MTLMathFloatingPointFunctionsPrecise; }
            NSError *error = nil; auto library = [device newLibraryWithSource:clear_source options:options error:&error];
            if (!library) host_logf(HOST_LOG_ERROR,"Native clear shader: %s",error.localizedDescription.UTF8String);
            check(library != nil,HALO_METAL_GPU_ERROR);
            auto draw_encoder = [[HaloMetalDrawEncoder alloc] initWithDevice:device]; check(draw_encoder != nil,HALO_METAL_MEMORY);
            id<MTLLibrary> fxaa_library = nil;
            std::map<uint32_t,id<MTLRenderPipelineState>> fxaa_pipelines;
            if (flags & HALO_METAL_ENABLE_FXAA) {
                fxaa_library = [device newLibraryWithSource:fxaa_source options:options error:&error];
                if (!fxaa_library) host_logf(HOST_LOG_ERROR,"Native FXAA shader: %s",error.localizedDescription.UTF8String);
                check(fxaa_library != nil,HALO_METAL_GPU_ERROR);
                for (uint32_t color_format : {HALO_METAL_RGBA8,HALO_METAL_BGRA8})
                    fxaa_pipelines.emplace(color_format,make_fxaa_pipeline(device,fxaa_library,color_format));
            }
            if (window) { layer = (__bridge CAMetalLayer *)host_sdl_native_metal_layer(window); check(layer != nil,HALO_METAL_INVALID); }
            context.device = device; context.queue = queue; context.clear_library = library; context.layer = layer;
            context.draw_encoder = draw_encoder;
            context.fxaa_library = fxaa_library; context.fxaa_enabled = (flags & HALO_METAL_ENABLE_FXAA) != 0;
            context.compact_vertices_enabled = (flags & HALO_METAL_ENABLE_COMPACT_VERTICES) != 0;
            context.fxaa_pipelines = std::move(fxaa_pipelines);
            // Reuse the existing gpu_stats environment override. Config-only
            // diagnostics can request this same established override in their
            // isolated launch environment; no ABI or application setting is added.
            context.metrics.enabled = getenv("HALO_GPU_STATS") != nullptr;
            context.draw_encoder.diagnosticsEnabled = context.metrics.enabled;
            if (layer) {
                layer.device = device; layer.pixelFormat = MTLPixelFormatBGRA8Unorm; layer.framebufferOnly = NO;
                layer.maximumDrawableCount = 3;
            }
            display_link_start();
            // host_main publishes this established, canonical per-app saves
            // root before guest startup. Headless fixtures skip persistence.
            const char *saves = getenv("HALO_SAVE_ROOT");
            if (!(flags & HALO_METAL_OFFSCREEN) && saves && *saves) {
                NSString *root = [[NSString alloc] initWithUTF8String:saves];
                if (root.length) context.warmup_path = [root stringByAppendingPathComponent:@"Cache/MetalWarmup-v1.bin"];
                warmup_initialize();
                context.draw_encoder.warmupLearningEnabled = context.warmup_path != nil;
                static bool exit_registered = false;
                if (!exit_registered && std::atexit([] {
                    @autoreleasepool { std::lock_guard<std::mutex> guard(lock); warmup_save(); }
                }) == 0) exit_registered = true;
            }
            host_logf(HOST_LOG_INFO,"Native Metal guest command interface: %s",device.name.UTF8String);
            return reply(output,size,HALO_METAL_OK);
        } catch (Failure f) { return reply(output,size,f.status,f.index); }
        catch (const std::bad_alloc &) { return reply(output,size,HALO_METAL_MEMORY); }
    }
}
extern "C" int host_metal_submit(uint32_t input,uint32_t bytes,uint32_t output,uint32_t size) {
    @autoreleasepool { std::lock_guard<std::mutex> guard(lock);
        bool executing = false;
        Prepared prepared;
        try {
            validate_reply(output,size); check(context.device != nil,HALO_METAL_NOT_INITIALIZED);
            check(!context.poisoned,HALO_METAL_GPU_ERROR);
            check(bytes >= sizeof(halo_metal_packet) && bytes <= HALO_METAL_MAX_PACKET);
            const Metrics before = context.metrics;
            const uint64_t pipelines_before = context.metrics.enabled ? context.draw_encoder.pipelineCreationCount : 0;
            const uint64_t pipeline_ns_before = context.metrics.enabled ? context.draw_encoder.pipelineCreationNanoseconds : 0;
            const uint64_t packet_started = metrics_start();
            uint64_t started = packet_started;
            prepared.input_buffer = packet_input_buffer(bytes);
            check(copy_guest(input,prepared.input_buffer.contents,bytes),HALO_METAL_MEMORY);
            // Keep the current wire extent distinct from retained capacity.
            // This is the only guest packet copy; preflight and GPU draws use
            // the same owned bytes under the existing synchronous host lock.
            const HaloMetalPacketView packet(prepared.input_buffer.contents,bytes);
            context.metrics.packet_copy_ns += metrics_elapsed(started);
            started = metrics_start(); validate(packet,prepared);
            for (const auto &entry : prepared.compiled_functions.entries())
                context.compiled_functions.insert(entry.first,entry.second);
            context.metrics.prepare_ns += metrics_elapsed(started);
            executing = true; execute(packet,prepared);
            warmup_learn(prepared);
            if (context.metrics.enabled) {
                const uint64_t ended = metrics_start();
                const auto header = record<halo_metal_packet>(packet,0);
                const auto &after = context.metrics;
                // GPU execution overlaps completion waiting. Shader and PSO
                // creation are contained in prepare; these are attribution
                // counters, not independent terms to add into frame time.
                // Async vertex/fragment compile durations can overlap and sum
                // beyond prepare wall time. Callback intervals retain overlap;
                // prepare/packet wall time measures the actual submission cost.
                host_logf(HOST_LOG_INFO,"Native Metal packet: sequence %llu, commands %u, bytes %u, start %llu ns, end %llu ns, copy %llu ns, prepare %llu ns, encode %llu ns, drawable %llu ns, commit %llu ns, completion %llu ns, gpu %llu ns, shader-misses %llu, shader-compile %llu ns, pipelines %llu, pipeline-create %llu ns, draws %llu, passes %llu, subresource-copies %u",
                    (unsigned long long)header.frame_sequence,header.command_count,bytes,
                    (unsigned long long)packet_started,(unsigned long long)ended,
                    (unsigned long long)(after.packet_copy_ns-before.packet_copy_ns),
                    (unsigned long long)(after.prepare_ns-before.prepare_ns),
                    (unsigned long long)(after.encode_ns-before.encode_ns),
                    (unsigned long long)(after.drawable_wait_ns-before.drawable_wait_ns),
                    (unsigned long long)(after.commit_ns-before.commit_ns),
                    (unsigned long long)(after.completion_wait_ns-before.completion_wait_ns),
                    (unsigned long long)(after.gpu_ns-before.gpu_ns),
                    (unsigned long long)(after.shader_compile_misses-before.shader_compile_misses),
                    (unsigned long long)(after.shader_compile_ns-before.shader_compile_ns),
                    (unsigned long long)(context.draw_encoder.pipelineCreationCount-pipelines_before),
                    (unsigned long long)(context.draw_encoder.pipelineCreationNanoseconds-pipeline_ns_before),
                    (unsigned long long)(after.draws-before.draws),
                    (unsigned long long)(after.render_passes-before.render_passes),(unsigned)(after.subresource_copies-before.subresource_copies));
                context.metrics.submissions++; context.metrics.bytes += bytes; metrics_report();
            }
            return reply(output,size,HALO_METAL_OK);
        } catch (Failure f) {
            [context.draw_encoder takeCreatedPipelines];
            if (executing) context.poisoned = true;
            else for (const auto &entry : prepared.programs)
                remove_unused_program_pipelines(entry.second);
            return reply(output,size,f.status,f.index);
        } catch (const std::bad_alloc &) {
            [context.draw_encoder takeCreatedPipelines];
            if (executing) context.poisoned = true;
            else for (const auto &entry : prepared.programs)
                remove_unused_program_pipelines(entry.second);
            return reply(output,size,HALO_METAL_MEMORY);
        }
    }
}
extern "C" int host_metal_readback(uint32_t id,uint32_t generation,uint32_t plane,uint32_t destination,
                                    uint32_t bytes,uint32_t output,uint32_t size) {
    @autoreleasepool { std::lock_guard<std::mutex> guard(lock);
        try {
            validate_reply(output,size); check(context.device != nil,HALO_METAL_NOT_INITIALIZED); check(!context.poisoned,HALO_METAL_GPU_ERROR);
            if (plane == HALO_METAL_VISIBILITY) {
                auto &query = visibility(context.queries,{id,generation});
                if (gpu_failed.load(std::memory_order_acquire))
                    return reply(output,size,HALO_METAL_GPU_ERROR);
                if (!query.ended || query.begun || gpu_completed.load(std::memory_order_acquire) < query.end_sequence)
                    return reply(output,size,HALO_METAL_UNDEFINED_CONTENT);
                check(bytes == sizeof(uint64_t) && guest_range(destination,bytes),HALO_METAL_MEMORY);
                uint64_t result = 0;
                for (const auto &word : query.words) {
                    uint64_t value; memcpy(&value,word.contents,sizeof(value));
                    if (query.mode == HALO_METAL_VISIBILITY_BOOLEAN) result |= value != 0;
                    else { check(value <= UINT64_MAX - result,HALO_METAL_GPU_ERROR); result += value; }
                }
                check(write_guest(destination,&result,sizeof(result)),HALO_METAL_MEMORY);
                return reply(output,size,HALO_METAL_OK,UINT32_MAX,query.version,bytes);
            }
            auto &t = resource(context.textures,{id,generation});
            check(target(t),HALO_METAL_UNSUPPORTED);
            check(plane == HALO_METAL_COLOR || plane == HALO_METAL_DEPTH || plane == HALO_METAL_STENCIL);
            check(t.format == HALO_METAL_DEPTH32_STENCIL8 ? plane != HALO_METAL_COLOR : plane == HALO_METAL_COLOR);
            check(t.initialized & plane,HALO_METAL_UNDEFINED_CONTENT);
            NSUInteger pixel = plane == HALO_METAL_STENCIL ? 1 : 4, tight = t.width * pixel, row = (tight + 255) & ~NSUInteger(255);
            check(bytes == tight * t.height && guest_range(destination,bytes),HALO_METAL_MEMORY);
            auto staging = [context.device newBufferWithLength:row * t.height options:MTLResourceStorageModeShared]; check(staging != nil,HALO_METAL_GPU_ERROR);
            auto command = [context.queue commandBuffer]; auto blit = [command blitCommandEncoder];
            check(command && blit,HALO_METAL_GPU_ERROR);
            MTLBlitOption option = plane == HALO_METAL_DEPTH ? MTLBlitOptionDepthFromDepthStencil :
                plane == HALO_METAL_STENCIL ? MTLBlitOptionStencilFromDepthStencil : MTLBlitOptionNone;
            [blit copyFromTexture:t.object sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0,0,0) sourceSize:MTLSizeMake(t.width,t.height,1)
                toBuffer:staging destinationOffset:0 destinationBytesPerRow:row destinationBytesPerImage:row * t.height options:option];
            [blit endEncoding]; complete(command,false,true);
            std::vector<uint8_t> result(bytes);
            for (uint32_t y = 0; y < t.height; y++) memcpy(result.data() + tight * y,(uint8_t *)staging.contents + row * y,tight);
            check(write_guest(destination,result.data(),bytes),HALO_METAL_MEMORY);
            return reply(output,size,HALO_METAL_OK,UINT32_MAX,t.version,bytes);
        } catch (Failure f) { return reply(output,size,f.status,f.index); }
        catch (const std::bad_alloc &) { return reply(output,size,HALO_METAL_MEMORY); }
    }
}
extern "C" void host_metal_pace_vblank(void) {
    if (!display_link) {
        struct timespec step = {0, 16666667};
        nanosleep(&step, nullptr);
        return;
    }
    uint64_t seen = display_vblank_tick.load(std::memory_order_acquire);
    for (int spin = 0; spin < 50; spin++) {
        if (display_vblank_tick.load(std::memory_order_acquire) != seen) return;
        struct timespec step = {0, 1000000};
        nanosleep(&step, nullptr);
    }
}
extern "C" void host_metal_shutdown(void) {
    @autoreleasepool { std::lock_guard<std::mutex> guard(lock);
        warmup_save();
        display_link_stop();
        bool owned_view = context.layer != nil; context = Context{};
        present_sync = -1;
        if (owned_view) host_sdl_native_metal_release();
    }
}
#endif
