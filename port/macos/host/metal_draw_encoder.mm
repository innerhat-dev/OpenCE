#ifdef HALO_MACOS_NATIVE_METAL
#import "metal_draw_encoder.h"
#include "metal_compact_vertex.h"
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <vector>

NSString *const HaloMetalDrawErrorDomain = @"HaloMetalDraw";

namespace {
BOOL fail(NSError **error, HaloMetalDrawError code, NSString *message) {
    if (error) *error = [NSError errorWithDomain:HaloMetalDrawErrorDomain code:code
        userInfo:@{NSLocalizedDescriptionKey: message}];
    return NO;
}
MTLCompareFunction compare(uint32_t value) {
    static const MTLCompareFunction values[] = {MTLCompareFunctionNever,
        MTLCompareFunctionNever, MTLCompareFunctionLess, MTLCompareFunctionEqual,
        MTLCompareFunctionLessEqual, MTLCompareFunctionGreater, MTLCompareFunctionNotEqual,
        MTLCompareFunctionGreaterEqual, MTLCompareFunctionAlways};
    return values[value];
}
MTLStencilOperation stencil(uint32_t value) {
    static const MTLStencilOperation values[] = {MTLStencilOperationKeep,
        MTLStencilOperationKeep, MTLStencilOperationZero, MTLStencilOperationReplace,
        MTLStencilOperationIncrementClamp, MTLStencilOperationDecrementClamp,
        MTLStencilOperationInvert, MTLStencilOperationIncrementWrap, MTLStencilOperationDecrementWrap};
    return values[value];
}
MTLBlendFactor blend(uint32_t value) {
    static const MTLBlendFactor values[] = {MTLBlendFactorZero, MTLBlendFactorZero,
        MTLBlendFactorOne, MTLBlendFactorSourceColor, MTLBlendFactorOneMinusSourceColor,
        MTLBlendFactorSourceAlpha, MTLBlendFactorOneMinusSourceAlpha, MTLBlendFactorDestinationAlpha,
        MTLBlendFactorOneMinusDestinationAlpha, MTLBlendFactorDestinationColor,
        MTLBlendFactorOneMinusDestinationColor, MTLBlendFactorSourceAlphaSaturated,
        MTLBlendFactorBlendColor, MTLBlendFactorOneMinusBlendColor,
        MTLBlendFactorBlendAlpha, MTLBlendFactorOneMinusBlendAlpha};
    return values[value];
}
MTLBlendOperation blendOperation(uint32_t value) {
    static const MTLBlendOperation values[] = {MTLBlendOperationAdd, MTLBlendOperationAdd,
        MTLBlendOperationSubtract, MTLBlendOperationReverseSubtract, MTLBlendOperationMin, MTLBlendOperationMax};
    return values[value];
}
MTLColorWriteMask writeMask(uint32_t value) {
    return (MTLColorWriteMask)(((value & 1) ? MTLColorWriteMaskRed : 0) |
        ((value & 2) ? MTLColorWriteMaskGreen : 0) | ((value & 4) ? MTLColorWriteMaskBlue : 0) |
        ((value & 8) ? MTLColorWriteMaskAlpha : 0));
}
bool range(id<MTLBuffer> buffer, NSUInteger offset, NSUInteger count,
           NSUInteger stride, NSUInteger alignment, id<MTLDevice> device) {
    return buffer && buffer.device == device && offset % alignment == 0 &&
        offset <= buffer.length && count <= (buffer.length - offset) / stride;
}
bool finite(const float *values, size_t count) {
    for (size_t i = 0; i < count; i++) if (!std::isfinite(values[i])) return false;
    return true;
}
struct PipelineKey {
    uintptr_t vertex, fragment;
    uint64_t color, depth;
    uint32_t packed, mask, blendEnabled, source, destination, operation, compact;
};
struct DepthKey {
    uint32_t enabled, write, compare, stencilEnabled, stencilCompare, readMask,
        writeMask, fail, depthFail, pass;
};
enum class BindingRequirementKind {
    Texture, Sampler, UnsupportedBuffer, OversizedBuffer, UnsupportedTexture,
    InvalidSampler, UnsupportedResource
};
struct BindingRequirement {
    BindingRequirementKind kind;
    NSUInteger index = 0;
    MTLTextureType textureType = MTLTextureType2D;
};
}

@interface HaloMetalPipelineEntry : NSObject {
@public
    std::vector<BindingRequirement> requirements;
    uint32_t usedTextureMask, usedAuxiliarySamplerMask;
}
@property(nonatomic, strong) id<MTLRenderPipelineState> pipeline;
@property(nonatomic, strong) id<MTLFunction> vertex, fragment;
@end
@implementation HaloMetalPipelineEntry
@end

@implementation HaloMetalDrawEncoder {
    id<MTLDevice> _device;
    NSMutableDictionary<NSData *, HaloMetalPipelineEntry *> *_pipelines;
    NSMutableDictionary<NSData *, id<MTLDepthStencilState>> *_depthStates;
    id<MTLRenderCommandEncoder> _activeEncoder;
    id<MTLCommandBuffer> _activeCommandBuffer;
    id<MTLTexture> _activeColor, _activeDepthStencil;
    NSUInteger _renderPassCount;
    BOOL _diagnosticsEnabled;
    NSUInteger _pipelineCreationCount;
    uint64_t _pipelineCreationNanoseconds;
    HaloMetalPipelineInterval _lastPipelineCreationInterval;
    BOOL _warmupLearningEnabled;
    std::vector<HaloMetalPipelineWarmup> _createdPipelines;
}
- (instancetype)initWithDevice:(id<MTLDevice>)device {
    if (!device) return nil;
    if ((self = [super init])) {
        _device = device; _pipelines = [NSMutableDictionary new];
        _depthStates = [NSMutableDictionary new];
    }
    return self;
}
- (void)endEncoding {
    @synchronized(self) {
        if (_activeEncoder) [_activeEncoder endEncoding];
        _activeEncoder = nil; _activeCommandBuffer = nil;
        _activeColor = nil; _activeDepthStencil = nil;
    }
}
- (NSUInteger)renderPassCount { @synchronized(self) { return _renderPassCount; } }
- (BOOL)diagnosticsEnabled { @synchronized(self) { return _diagnosticsEnabled; } }
- (void)setDiagnosticsEnabled:(BOOL)enabled { @synchronized(self) { _diagnosticsEnabled = enabled; } }
- (NSUInteger)pipelineCreationCount { @synchronized(self) { return _pipelineCreationCount; } }
- (uint64_t)pipelineCreationNanoseconds { @synchronized(self) { return _pipelineCreationNanoseconds; } }
- (HaloMetalPipelineInterval)lastPipelineCreationInterval { @synchronized(self) { return _lastPipelineCreationInterval; } }
- (BOOL)warmupLearningEnabled { @synchronized(self) { return _warmupLearningEnabled; } }
- (void)setWarmupLearningEnabled:(BOOL)enabled { @synchronized(self) { _warmupLearningEnabled = enabled; } }
- (std::vector<HaloMetalPipelineWarmup>)takeCreatedPipelines {
    @synchronized(self) { auto result = std::move(_createdPipelines); _createdPipelines.clear(); return result; }
}
- (BOOL)preparePipeline:(const HaloMetalPipelineWarmup &)p error:(NSError **)error {
    @synchronized(self) {
        if (error) *error = nil;
        if (!p.vertex || !p.fragment || p.vertex.device != _device || p.fragment.device != _device ||
            p.vertex.functionType != MTLFunctionTypeVertex || p.fragment.functionType != MTLFunctionTypeFragment ||
            (p.color != MTLPixelFormatInvalid && p.color != MTLPixelFormatRGBA8Unorm && p.color != MTLPixelFormatBGRA8Unorm) ||
            (p.depth != MTLPixelFormatInvalid && p.depth != MTLPixelFormatDepth32Float_Stencil8) ||
            (!p.color && !p.depth) || (!p.color && (p.mask || p.blend)) || p.packed > UINT16_MAX ||
            p.mask > 15 || p.blend > 1 || p.source < 1 || p.source > 15 || p.destination < 1 ||
            p.destination > 15 || p.operation < 1 || p.operation > 5 || p.compact > 1)
            return fail(error,HaloMetalDrawInvalid,@"Invalid original pipeline warmup contract");
        HaloMetalDraw draw;
        draw.vertexFunction = p.vertex; draw.fragmentFunction = p.fragment; draw.packedMask = p.packed;
        draw.compactVertices = p.compact != 0;
        draw.state.color_write_mask = p.mask; draw.state.blend_enabled = p.blend;
        draw.state.blend_source = p.source; draw.state.blend_destination = p.destination; draw.state.blend_operation = p.operation;
        for (unsigned i = 0; i < 2; i++) {
            uint64_t pixelFormat = i ? p.depth : p.color;
            if (!pixelFormat) continue;
            auto descriptor = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:(MTLPixelFormat)pixelFormat width:1 height:1 mipmapped:NO];
            descriptor.storageMode = MTLStorageModePrivate; descriptor.usage = MTLTextureUsageRenderTarget;
            auto texture = [_device newTextureWithDescriptor:descriptor];
            if (!texture) return fail(error,HaloMetalDrawPipelineFailure,@"Original pipeline warmup attachment allocation failed");
            if (i) draw.depthStencil = texture; else draw.color = texture;
        }
        return [self pipelineForDraw:draw error:error] != nil;
    }
}
- (void)dealloc { [self endEncoding]; }
- (void)clearCaches { @synchronized(self) { [self endEncoding]; [_pipelines removeAllObjects]; [_depthStates removeAllObjects]; } }
- (void)removePipelinesForVertexFunction:(id<MTLFunction>)vertex fragmentFunction:(id<MTLFunction>)fragment {
    @synchronized(self) {
        [self endEncoding];
        for (NSData *key in [_pipelines.allKeys copy]) {
            HaloMetalPipelineEntry *entry = _pipelines[key];
            if ((vertex && entry.vertex == vertex) || (fragment && entry.fragment == fragment))
                [_pipelines removeObjectForKey:key];
        }
    }
}
- (BOOL)validateDraw:(const HaloMetalDraw &)draw error:(NSError **)error {
    const halo_metal_draw_state &s = draw.state;
    if (!draw.visibilityBuffer) {
        if (draw.visibilityOffset || draw.visibilityMode != MTLVisibilityResultModeDisabled)
            return fail(error, HaloMetalDrawInvalid, @"Inactive query must not supply a visibility offset or mode");
    } else if ((draw.visibilityMode != MTLVisibilityResultModeBoolean &&
                draw.visibilityMode != MTLVisibilityResultModeCounting) ||
               draw.visibilityBuffer.storageMode != MTLStorageModeShared ||
               !range(draw.visibilityBuffer, draw.visibilityOffset, 1, sizeof(uint64_t), sizeof(uint64_t), _device)) {
        return fail(error, HaloMetalDrawInvalid, @"Active query requires Boolean/Counting and an aligned shared 8-byte result word on the encoder device");
    }
    if (!draw.vertexFunction || !draw.fragmentFunction || draw.vertexFunction.device != _device ||
        draw.fragmentFunction.device != _device || draw.vertexFunction.functionType != MTLFunctionTypeVertex ||
        draw.fragmentFunction.functionType != MTLFunctionTypeFragment)
        return fail(error, HaloMetalDrawInvalid, @"Draw requires vertex and fragment functions on the encoder device");
    if (!draw.color && !draw.depthStencil)
        return fail(error, HaloMetalDrawInvalid, @"Draw has no original attachment");
    id<MTLTexture> target = draw.color ?: draw.depthStencil;
    for (id<MTLTexture> texture in @[draw.color ?: (id)NSNull.null, draw.depthStencil ?: (id)NSNull.null]) {
        if ((id)texture == NSNull.null) continue;
        if (texture.device != _device || texture.textureType != MTLTextureType2D || texture.sampleCount != 1 ||
            !(texture.usage & MTLTextureUsageRenderTarget) || texture.width < target.width || texture.height < target.height)
            return fail(error, HaloMetalDrawUnsupported, @"Original attachments must be single-sample 2D targets covering the color footprint");
    }
    if (draw.color && draw.color.pixelFormat != MTLPixelFormatRGBA8Unorm && draw.color.pixelFormat != MTLPixelFormatBGRA8Unorm)
        return fail(error, HaloMetalDrawUnsupported, @"Unsupported original color attachment format");
    if (draw.depthStencil && draw.depthStencil.pixelFormat != MTLPixelFormatDepth32Float_Stencil8)
        return fail(error, HaloMetalDrawUnsupported, @"Unsupported original native depth/stencil attachment format");
    if (s.color_write_mask > 15 || s.blend_enabled > 1 || s.blend_source < 1 || s.blend_source > 15 ||
        s.blend_destination < 1 || s.blend_destination > 15 || s.blend_operation < 1 || s.blend_operation > 5 ||
        s.depth_enabled > 1 || s.depth_write > 1 || s.depth_compare < 1 || s.depth_compare > 8 ||
        s.stencil_enabled > 1 || s.stencil_compare < 1 || s.stencil_compare > 8 ||
        s.stencil_fail < 1 || s.stencil_fail > 8 || s.stencil_depth_fail < 1 || s.stencil_depth_fail > 8 ||
        s.stencil_pass < 1 || s.stencil_pass > 8 || s.front_winding > 1 || s.cull_mode > 2 ||
        s.depth_clip_mode > 1 || s.fill_mode > 1 || s.reserved_float != 0 || !finite(s.viewport, 6) ||
        !finite(s.blend_color, 4) || !std::isfinite(s.depth_bias) || !std::isfinite(s.slope_depth_bias) ||
        !std::isfinite(s.depth_bias_clamp))
        return fail(error, HaloMetalDrawInvalid, @"Invalid or unsupported numeric original draw state");
    if ((!draw.color && (s.color_write_mask || s.blend_enabled)) ||
        (!draw.depthStencil && (s.depth_enabled || s.stencil_enabled)))
        return fail(error, HaloMetalDrawInvalid, @"Enabled original write/test has no matching attachment");
    if (s.viewport[2] <= 0 || s.viewport[3] <= 0 || s.viewport[4] < 0 ||
        s.viewport[5] > 1 || s.viewport[4] > s.viewport[5] ||
        !s.scissor[2] || !s.scissor[3] || s.scissor[0] > target.width || s.scissor[1] > target.height ||
        s.scissor[2] > target.width - s.scissor[0] || s.scissor[3] > target.height - s.scissor[1])
        return fail(error, HaloMetalDrawInvalid, @"Original viewport/depth range/scissor exceeds the target contract");
    for (unsigned i = 0; i < 4; i++) if (s.blend_color[i] < 0 || s.blend_color[i] > 1)
        return fail(error, HaloMetalDrawInvalid, @"Original blend color lies outside 0..1");
    if (!draw.vertexCount || !draw.indexCount || draw.packedMask > UINT16_MAX ||
        draw.primitive > MTLPrimitiveTypeTriangleStrip ||
        (draw.primitive == MTLPrimitiveTypeLine && draw.indexCount % 2) ||
        (draw.primitive == MTLPrimitiveTypeTriangle && draw.indexCount % 3) ||
        (draw.primitive == MTLPrimitiveTypeLineStrip && draw.indexCount < 2) ||
        (draw.primitive == MTLPrimitiveTypeTriangleStrip && draw.indexCount < 3))
        return fail(error, HaloMetalDrawInvalid, @"Invalid original geometry/topology");
    if ((draw.compactVertices ?
            (draw.vertexBytes > HALO_METAL_MAX_PACKET ||
             !range(draw.vertices,draw.vertexOffset,draw.vertexBytes,1,16,_device) ||
             draw.indices.storageMode == MTLStorageModePrivate ||
             draw.vertices.storageMode == MTLStorageModePrivate || draw.vertexCount > UINT32_MAX ||
             !halo_metal_compact_vertices_valid((const uint8_t *)draw.vertices.contents + draw.vertexOffset,
                 draw.vertexBytes,(uint32_t)draw.vertexCount,draw.packedMask)) :
            (draw.vertexBytes || !range(draw.vertices,draw.vertexOffset,draw.vertexCount,HaloMetalVertexStride,16,_device))) ||
        !range(draw.indices, draw.indexOffset, draw.indexCount, 4, 4, _device) ||
        !range(draw.vertexUniforms, draw.vertexUniformOffset, 1, HaloMetalVertexUniformSize, 16, _device) ||
        !range(draw.pixelUniforms, draw.pixelUniformOffset, 1, HaloMetalPixelUniformSize, 16, _device))
        return fail(error, HaloMetalDrawInvalid, @"Original input/uniform buffer range, alignment or device is invalid");
    if (draw.indices.storageMode != MTLStorageModePrivate) {
        const uint8_t *bytes = (const uint8_t *)draw.indices.contents + draw.indexOffset;
        for (NSUInteger i = 0; i < draw.indexCount; i++) {
            uint32_t index; memcpy(&index, bytes + i * 4, 4);
            if (index >= draw.vertexCount)
                return fail(error, HaloMetalDrawInvalid, @"Original index exceeds its vertex range");
        }
    }
    return YES;
}
- (HaloMetalPipelineEntry *)pipelineForDraw:(const HaloMetalDraw &)draw error:(NSError **)error {
    const halo_metal_draw_state &s = draw.state;
    PipelineKey key = {};
    key.vertex = (uintptr_t)(__bridge void *)draw.vertexFunction;
    key.fragment = (uintptr_t)(__bridge void *)draw.fragmentFunction;
    key.color = draw.color ? draw.color.pixelFormat : MTLPixelFormatInvalid;
    key.depth = draw.depthStencil ? draw.depthStencil.pixelFormat : MTLPixelFormatInvalid;
    key.packed = draw.packedMask; key.mask = s.color_write_mask; key.blendEnabled = s.blend_enabled;
    key.compact = draw.compactVertices;
    key.source = s.blend_source; key.destination = s.blend_destination; key.operation = s.blend_operation;
    NSData *bytes = [NSData dataWithBytes:&key length:sizeof(key)];
    HaloMetalPipelineEntry *entry = _pipelines[bytes];
    if (entry) return entry;
    MTLRenderPipelineDescriptor *description = [MTLRenderPipelineDescriptor new];
    description.vertexFunction = draw.vertexFunction; description.fragmentFunction = draw.fragmentFunction;
    description.depthAttachmentPixelFormat = description.stencilAttachmentPixelFormat = (MTLPixelFormat)key.depth;
    // NV2A emits point size for triangle programs as well. The draw specifies
    // topology; declaring triangles here would reject that original output.
    description.inputPrimitiveTopology = MTLPrimitiveTopologyClassUnspecified;
    if (!draw.compactVertices) {
        MTLVertexDescriptor *layout = [MTLVertexDescriptor vertexDescriptor];
        for (unsigned reg = 0; reg < 16; reg++) {
            layout.attributes[reg].format = (draw.packedMask & (1u << reg)) ? MTLVertexFormatUInt : MTLVertexFormatFloat4;
            layout.attributes[reg].offset = reg * 16; layout.attributes[reg].bufferIndex = 1;
        }
        layout.layouts[1].stride = HaloMetalVertexStride; description.vertexDescriptor = layout;
    }
    MTLRenderPipelineColorAttachmentDescriptor *color = description.colorAttachments[0];
    color.pixelFormat = (MTLPixelFormat)key.color; color.writeMask = writeMask(s.color_write_mask);
    color.blendingEnabled = s.blend_enabled;
    color.sourceRGBBlendFactor = color.sourceAlphaBlendFactor = blend(s.blend_source);
    color.destinationRGBBlendFactor = color.destinationAlphaBlendFactor = blend(s.blend_destination);
    color.rgbBlendOperation = color.alphaBlendOperation = blendOperation(s.blend_operation);
    MTLRenderPipelineReflection *reflection = nil;
    NSError *underlying = nil;
    const BOOL diagnostics = _diagnosticsEnabled;
    const auto started = diagnostics ? std::chrono::steady_clock::now() : std::chrono::steady_clock::time_point{};
    id<MTLRenderPipelineState> pipeline = [_device newRenderPipelineStateWithDescriptor:description
        options:MTLPipelineOptionBindingInfo reflection:&reflection error:&underlying];
    if (diagnostics) {
        const auto ended = std::chrono::steady_clock::now();
        _lastPipelineCreationInterval = {
            (uint64_t)std::chrono::duration_cast<std::chrono::nanoseconds>(started.time_since_epoch()).count(),
            (uint64_t)std::chrono::duration_cast<std::chrono::nanoseconds>(ended.time_since_epoch()).count(),
            pipeline != nil && reflection != nil};
        _pipelineCreationNanoseconds += _lastPipelineCreationInterval.ended - _lastPipelineCreationInterval.started;
        _pipelineCreationCount++;
    }
    if (!pipeline || !reflection) {
        fail(error, HaloMetalDrawPipelineFailure, underlying.localizedDescription ?: @"Original draw pipeline/reflection creation failed");
        return nil;
    }
    entry = [HaloMetalPipelineEntry new]; entry.pipeline = pipeline;
    // Reflection is immutable for this pipeline. Preserve its validation order
    // as compact requirements instead of messaging every MTLBinding per draw.
    // Static errors remain requirements so draw-specific border/resource errors
    // retain the same precedence as the original reflection walk.
    for (unsigned stage = 0; stage < 2; stage++) {
        NSArray<id<MTLBinding>> *bindings = stage ? reflection.fragmentBindings : reflection.vertexBindings;
        for (id<MTLBinding> binding in bindings) {
            if (!binding.used) continue;
            const NSUInteger index = binding.index;
            if (binding.type == MTLBindingTypeBuffer) {
                if (index > (stage ? 0u : 1u))
                    entry->requirements.push_back({BindingRequirementKind::UnsupportedBuffer});
                else {
                    const NSUInteger available = index == 1 ?
                        (draw.compactVertices ? sizeof(halo_metal_compact_vertex_input) : HaloMetalVertexStride) :
                        (stage ? HaloMetalPixelUniformSize : HaloMetalVertexUniformSize);
                    if (((id<MTLBufferBinding>)binding).bufferDataSize > available)
                        entry->requirements.push_back({BindingRequirementKind::OversizedBuffer});
                }
            } else if (binding.type == MTLBindingTypeTexture) {
                if (!stage || index >= 4)
                    entry->requirements.push_back({BindingRequirementKind::UnsupportedTexture});
                else {
                    entry->requirements.push_back({BindingRequirementKind::Texture, index,
                        ((id<MTLTextureBinding>)binding).textureType});
                    entry->usedTextureMask |= 1u << index;
                }
            } else if (binding.type == MTLBindingTypeSampler) {
                if (!stage || index >= 8)
                    entry->requirements.push_back({BindingRequirementKind::InvalidSampler});
                else {
                    entry->requirements.push_back({BindingRequirementKind::Sampler, index});
                    if (index >= 4) entry->usedAuxiliarySamplerMask |= 1u << (index - 4);
                }
            } else entry->requirements.push_back({BindingRequirementKind::UnsupportedResource});
        }
    }
    entry.vertex = draw.vertexFunction; entry.fragment = draw.fragmentFunction; _pipelines[bytes] = entry;
    if (_warmupLearningEnabled && _createdPipelines.size() < 1024) {
        try { _createdPipelines.push_back({draw.vertexFunction,draw.fragmentFunction,key.color,key.depth,key.packed,key.mask,
                                         key.blendEnabled,key.source,key.destination,key.operation,key.compact}); }
        catch (const std::bad_alloc &) { /* Optional learning never rejects an otherwise valid draw. */ }
    }
    return entry;
}
- (id<MTLDepthStencilState>)depthForDraw:(const HaloMetalDraw &)draw error:(NSError **)error {
    const halo_metal_draw_state &s = draw.state;
    DepthKey key = {s.depth_enabled, s.depth_write, s.depth_compare, s.stencil_enabled,
        s.stencil_compare, s.stencil_read_mask, s.stencil_write_mask, s.stencil_fail, s.stencil_depth_fail, s.stencil_pass};
    NSData *bytes = [NSData dataWithBytes:&key length:sizeof(key)];
    id<MTLDepthStencilState> result = _depthStates[bytes]; if (result) return result;
    MTLDepthStencilDescriptor *description = [MTLDepthStencilDescriptor new];
    description.depthCompareFunction = s.depth_enabled ? compare(s.depth_compare) : MTLCompareFunctionAlways;
    description.depthWriteEnabled = s.depth_enabled && s.depth_write;
    if (s.stencil_enabled) {
        MTLStencilDescriptor *face = [MTLStencilDescriptor new];
        face.stencilCompareFunction = compare(s.stencil_compare);
        face.readMask = s.stencil_read_mask; face.writeMask = s.stencil_write_mask;
        face.stencilFailureOperation = stencil(s.stencil_fail);
        face.depthFailureOperation = stencil(s.stencil_depth_fail); face.depthStencilPassOperation = stencil(s.stencil_pass);
        description.frontFaceStencil = face; description.backFaceStencil = face;
    }
    result = [_device newDepthStencilStateWithDescriptor:description];
    if (!result) fail(error, HaloMetalDrawPipelineFailure, @"Original depth/stencil state creation failed");
    else _depthStates[bytes] = result;
    return result;
}
- (BOOL)validateBindings:(HaloMetalPipelineEntry *)entry draw:(const HaloMetalDraw &)draw error:(NSError **)error {
    if (draw.alphaBorderMask > 15 || draw.volumeBorderMask > 15 ||
        (draw.alphaBorderMask & draw.volumeBorderMask))
        return fail(error, HaloMetalDrawInvalid, @"Unknown or conflicting border stage masks");
    const uint32_t auxiliaryMask = draw.alphaBorderMask | draw.volumeBorderMask;
    for (unsigned i = 0; i < 4; i++) {
        if (!!draw.samplers[4+i] != !!(auxiliaryMask & (1u << i)))
            return fail(error, HaloMetalDrawInvalid, @"Border companion does not match stage mask");
        if (auxiliaryMask & (1u << i)) {
            const MTLTextureType type = (draw.volumeBorderMask & (1u << i)) ? MTLTextureType3D : MTLTextureType2D;
            if (!draw.textures[i] || draw.textures[i].textureType != type || draw.textures[i].mipmapLevelCount <= 1)
                return fail(error, HaloMetalDrawInvalid, @"Border companion texture does not match typed stage contract");
        }
    }
    for (const BindingRequirement &requirement : entry->requirements) {
        switch (requirement.kind) {
            case BindingRequirementKind::UnsupportedBuffer:
                return fail(error, HaloMetalDrawUnsupported, @"Shader requires an unsupported original buffer binding");
            case BindingRequirementKind::OversizedBuffer:
                return fail(error, HaloMetalDrawInvalid, @"Shader uniform/input structure exceeds the captured original buffer");
            case BindingRequirementKind::UnsupportedTexture:
                return fail(error, HaloMetalDrawUnsupported, @"Shader requires an unsupported original texture binding");
            case BindingRequirementKind::InvalidSampler:
                return fail(error, HaloMetalDrawInvalid, @"Used original sampler is absent or mismatched");
            case BindingRequirementKind::UnsupportedResource:
                return fail(error, HaloMetalDrawUnsupported, @"Shader requires an unsupported original resource binding");
            case BindingRequirementKind::Texture: {
                id<MTLTexture> texture = draw.textures[requirement.index];
                MTLTextureType type = requirement.textureType;
                if (!texture || texture.device != _device || texture.textureType != type ||
                    (type != MTLTextureType2D && type != MTLTextureTypeCube && type != MTLTextureType3D) ||
                    texture.sampleCount != 1 || !(texture.usage & MTLTextureUsageShaderRead) ||
                    texture == draw.color || texture == draw.depthStencil)
                    return fail(error, HaloMetalDrawInvalid, @"Used original texture is absent, mismatched or aliases a draw attachment");
                break;
            }
            case BindingRequirementKind::Sampler:
                if (!draw.samplers[requirement.index] || draw.samplers[requirement.index].device != _device)
                    return fail(error, HaloMetalDrawInvalid, @"Used original sampler is absent or mismatched");
                break;
        }
    }
    if (entry->usedAuxiliarySamplerMask != auxiliaryMask)
        return fail(error, HaloMetalDrawInvalid, @"Shader border companions do not match draw contract");
    return YES;
}
- (HaloMetalPipelineEntry *)prepareDraw:(const HaloMetalDraw &)draw
                             depthState:(id<MTLDepthStencilState> __strong *)depthState error:(NSError **)error {
    if (error) *error = nil;
    if (![self validateDraw:draw error:error]) return nil;
    HaloMetalPipelineEntry *entry = [self pipelineForDraw:draw error:error];
    if (!entry || ![self validateBindings:entry draw:draw error:error]) return nil;
    id<MTLDepthStencilState> depth = [self depthForDraw:draw error:error];
    if (!depth) return nil;
    if (depthState) *depthState = depth;
    return entry;
}
- (BOOL)prepareDraw:(const HaloMetalDraw &)draw error:(NSError **)error {
    @synchronized(self) { return [self prepareDraw:draw depthState:nullptr error:error] != nil; }
}
- (BOOL)usedTextureMaskForDraw:(const HaloMetalDraw &)draw mask:(uint32_t *)mask error:(NSError **)error {
    @synchronized(self) {
        if (!mask) return NO;
        HaloMetalPipelineEntry *entry = [self prepareDraw:draw depthState:nullptr error:error];
        if (!entry) return NO;
        *mask = entry->usedTextureMask;
        return YES;
    }
}
- (BOOL)encodeDraw:(const HaloMetalDraw &)draw commandBuffer:(id<MTLCommandBuffer>)command error:(NSError **)error {
    return [self encodeDraw:draw commandBuffer:command reusePass:NO error:error];
}
- (BOOL)encodeDraw:(const HaloMetalDraw &)draw commandBuffer:(id<MTLCommandBuffer>)command reusePass:(BOOL)reusePass error:(NSError **)error {
    @synchronized(self) {
        if (error) *error = nil;
        if (!command || command.commandQueue.device != _device || command.status != MTLCommandBufferStatusNotEnqueued) {
            [self endEncoding];
            return fail(error, HaloMetalDrawInvalid, @"Draw requires an unsubmitted command buffer on the encoder device");
        }
        id<MTLDepthStencilState> depth = nil;
        HaloMetalPipelineEntry *entry = [self prepareDraw:draw depthState:&depth error:error];
        if (!entry) { [self endEncoding]; return NO; }
        // Each occlusion query needs its own result buffer. A draw that reads
        // the image it is also writing needs that image stored first. Other
        // draws, including blended particles and shields, stay in one pass so
        // the full frame is not loaded and stored for every triangle.
        BOOL feedback = NO;
        for (unsigned i = 0; i < 4; i++) {
            id<MTLTexture> texture = draw.textures[i];
            if (texture && (texture == draw.color || texture == draw.depthStencil)) feedback = YES;
        }
        const BOOL reusable = reusePass && !draw.visibilityBuffer && !feedback;
        id<MTLRenderCommandEncoder> encoder = _activeEncoder;
        if (!reusable || !encoder || _activeCommandBuffer != command ||
            _activeColor != draw.color || _activeDepthStencil != draw.depthStencil) {
            [self endEncoding];
            MTLRenderPassDescriptor *pass = [MTLRenderPassDescriptor renderPassDescriptor];
            id<MTLTexture> target = draw.color ?: draw.depthStencil;
            pass.renderTargetWidth = target.width; pass.renderTargetHeight = target.height;
            if (draw.color) {
                pass.colorAttachments[0].texture = draw.color;
                pass.colorAttachments[0].loadAction = MTLLoadActionLoad; pass.colorAttachments[0].storeAction = MTLStoreActionStore;
            }
            if (draw.depthStencil) {
                pass.depthAttachment.texture = pass.stencilAttachment.texture = draw.depthStencil;
                pass.depthAttachment.loadAction = pass.stencilAttachment.loadAction = MTLLoadActionLoad;
                pass.depthAttachment.storeAction = pass.stencilAttachment.storeAction = MTLStoreActionStore;
            }
            if (draw.visibilityBuffer) pass.visibilityResultBuffer = draw.visibilityBuffer;
            encoder = [command renderCommandEncoderWithDescriptor:pass];
            if (!encoder) return fail(error, HaloMetalDrawEncoderFailure, @"Original draw render encoder creation failed");
            _renderPassCount++;
            if (reusable) {
                _activeEncoder = encoder; _activeCommandBuffer = command;
                _activeColor = draw.color; _activeDepthStencil = draw.depthStencil;
            }
        }
        const halo_metal_draw_state &s = draw.state;
        [encoder setRenderPipelineState:entry.pipeline]; [encoder setDepthStencilState:depth];
        [encoder setViewport:MTLViewport{s.viewport[0], s.viewport[1], s.viewport[2], s.viewport[3], s.viewport[4], s.viewport[5]}];
        [encoder setScissorRect:MTLScissorRect{s.scissor[0], s.scissor[1], s.scissor[2], s.scissor[3]}];
        [encoder setFrontFacingWinding:s.front_winding ? MTLWindingCounterClockwise : MTLWindingClockwise];
        [encoder setCullMode:(MTLCullMode)s.cull_mode];
        [encoder setDepthClipMode:s.depth_clip_mode ? MTLDepthClipModeClamp : MTLDepthClipModeClip];
        [encoder setTriangleFillMode:s.fill_mode ? MTLTriangleFillModeLines : MTLTriangleFillModeFill];
        [encoder setDepthBias:s.depth_bias slopeScale:s.slope_depth_bias clamp:s.depth_bias_clamp];
        [encoder setStencilReferenceValue:s.stencil_reference];
        [encoder setBlendColorRed:s.blend_color[0] green:s.blend_color[1] blue:s.blend_color[2] alpha:s.blend_color[3]];
        [encoder setVertexBuffer:draw.vertices offset:draw.vertexOffset atIndex:1];
        [encoder setVertexBuffer:draw.vertexUniforms offset:draw.vertexUniformOffset atIndex:0];
        [encoder setFragmentBuffer:draw.pixelUniforms offset:draw.pixelUniformOffset atIndex:0];
        for (unsigned i = 0; i < 4; i++) {
            [encoder setFragmentTexture:draw.textures[i] atIndex:i];
            [encoder setFragmentSamplerState:draw.samplers[i] atIndex:i];
            [encoder setFragmentSamplerState:draw.samplers[4+i] atIndex:4+i];
        }
        if (draw.visibilityBuffer)
            [encoder setVisibilityResultMode:draw.visibilityMode offset:draw.visibilityOffset];
        [encoder drawIndexedPrimitives:draw.primitive indexCount:draw.indexCount indexType:MTLIndexTypeUInt32
            indexBuffer:draw.indices indexBufferOffset:draw.indexOffset];
        if (!reusable) [encoder endEncoding];
        return YES;
    }
}
@end
#endif
