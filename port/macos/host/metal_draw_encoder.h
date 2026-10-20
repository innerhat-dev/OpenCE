/* Shared original-draw encoder for the live guest bridge and ordered replay.
 * Callers own compilation, source-layout preparation, uploads, target history,
 * resource lifetimes, synchronization and presentation. This module only
 * validates and encodes draws against existing attachments using LOAD/STORE.
 */
#ifdef HALO_MACOS_NATIVE_METAL
#ifndef HALO_METAL_DRAW_ENCODER_H
#define HALO_METAL_DRAW_ENCODER_H
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include "../include/halo_metal_abi.h"
#include <vector>

#if !defined(__cplusplus)
#error "The native draw encoder requires Objective-C++."
#endif

constexpr NSUInteger HaloMetalVertexStride = 256;
constexpr NSUInteger HaloMetalVertexUniformSize = 3120;
constexpr NSUInteger HaloMetalPixelUniformSize = 608;

struct HaloMetalDraw {
    id<MTLFunction> vertexFunction = nil, fragmentFunction = nil;
    id<MTLTexture> color = nil, depthStencil = nil;
    id<MTLTexture> textures[4] = {};
    id<MTLSamplerState> samplers[8] = {};
    uint32_t alphaBorderMask = 0;
    uint32_t volumeBorderMask = 0;
    id<MTLBuffer> vertices = nil, indices = nil;
    id<MTLBuffer> vertexUniforms = nil, pixelUniforms = nil;
    NSUInteger vertexOffset = 0, indexOffset = 0;
    NSUInteger vertexUniformOffset = 0, pixelUniformOffset = 0;
    NSUInteger vertexCount = 0, indexCount = 0;
    bool compactVertices = false;
    NSUInteger vertexBytes = 0;
    /* Active queries only. The caller owns a zeroed, fresh 8-byte result word
     * for each draw/encoder and aggregates words after GPU completion. There
     * is no implicit accumulation or CPU result-availability policy here. */
    id<MTLBuffer> visibilityBuffer = nil;
    NSUInteger visibilityOffset = 0;
    MTLVisibilityResultMode visibilityMode = MTLVisibilityResultModeDisabled;
    uint32_t packedMask = 0;
    MTLPrimitiveType primitive = MTLPrimitiveTypeTriangle;
    halo_metal_draw_state state = {};
};

FOUNDATION_EXPORT NSString *const HaloMetalDrawErrorDomain;
struct HaloMetalPipelineWarmup {
    id<MTLFunction> vertex = nil, fragment = nil;
    uint64_t color = 0, depth = 0;
    uint32_t packed = 0, mask = 0, blend = 0, source = 1, destination = 1, operation = 1;
    uint32_t compact = 0;
};
struct HaloMetalPipelineInterval { uint64_t started = 0, ended = 0; bool succeeded = false; };
typedef NS_ENUM(NSInteger, HaloMetalDrawError) {
    HaloMetalDrawInvalid = 1,
    HaloMetalDrawUnsupported = 2,
    HaloMetalDrawPipelineFailure = 3,
    HaloMetalDrawEncoderFailure = 4
};

@interface HaloMetalDrawEncoder : NSObject
- (instancetype)initWithDevice:(id<MTLDevice>)device;
/* Allows a packet caller to validate every draw before encoding mutations.
 * Pipeline/cache preparation may occur here; no GPU command is encoded. */
- (BOOL)prepareDraw:(const HaloMetalDraw &)draw error:(NSError **)error;
- (BOOL)usedTextureMaskForDraw:(const HaloMetalDraw &)draw mask:(uint32_t *)mask error:(NSError **)error;
- (BOOL)encodeDraw:(const HaloMetalDraw &)draw
     commandBuffer:(id<MTLCommandBuffer>)commandBuffer error:(NSError **)error;
/* Optional reuse is restricted to consecutive non-query, blend-disabled draws on the same
 * command buffer and exact attachment objects. Every original draw state is
 * still rebound. Blended draws preserve their original per-draw LOAD/STORE
 * rounding boundary. The caller must endEncoding before other GPU operations,
 * resource mutations, command-buffer submission or abandoning a packet.
 * The original encodeDraw overload always closes its pass before returning. */
- (BOOL)encodeDraw:(const HaloMetalDraw &)draw
     commandBuffer:(id<MTLCommandBuffer>)commandBuffer reusePass:(BOOL)reusePass error:(NSError **)error;
- (void)endEncoding;
/* Cumulative successfully created draw passes, including isolated queries. */
@property(nonatomic, readonly) NSUInteger renderPassCount;
/* Defaults off. Counters cover only synchronous pipeline creation attempts
 * while enabled, including failed attempts; cache hits do no timing work.
 * Disabling diagnostics or clearing caches preserves cumulative counters. */
@property(nonatomic) BOOL diagnosticsEnabled;
@property(nonatomic, readonly) NSUInteger pipelineCreationCount;
@property(nonatomic, readonly) uint64_t pipelineCreationNanoseconds;
@property(nonatomic, readonly) HaloMetalPipelineInterval lastPipelineCreationInterval;
/* Startup preparation validates the complete immutable PSO contract and uses
 * compatible 1x1 attachments. It encodes no draw and bypasses no draw checks. */
- (BOOL)preparePipeline:(const HaloMetalPipelineWarmup &)pipeline error:(NSError **)error;
/* Off by default. Only new successful PSOs are queued, bounded to 1024 per
 * packet; the transport learns them only after successful GPU completion. */
@property(nonatomic) BOOL warmupLearningEnabled;
- (std::vector<HaloMetalPipelineWarmup>)takeCreatedPipelines;
- (void)clearCaches;
/* Retained functions prevent identity reuse in cached pipeline keys. Program
 * deletion can remove its pipelines without resetting other programs. */
- (void)removePipelinesForVertexFunction:(id<MTLFunction>)vertex
                      fragmentFunction:(id<MTLFunction>)fragment;
@end
#endif
#endif
