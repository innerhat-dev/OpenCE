/*
HOST_GL.C

OpenGL ES for the guest. Its generated entry points (guest_gl.c) import
hostgl_<function>, resolved here to the driver's function; the arguments
already have host types by then. Only strings need copying back.
*/

#include "host.h"

#include <EGL/egl.h>
#include <GLES3/gl32.h>
#include <dlfcn.h>
#include <string.h>

void *host_gl_bridge(const char *name);
void *host_gl_resolve(const char *name) {
    void *profile = host_perf_resolve(name);
    if (profile) return profile;
    void *bridge = host_gl_bridge(name);
    return bridge ? bridge : (void *)eglGetProcAddress(name);
}

void host_gl_get_string(uint32_t name, int index, char *buffer, uint32_t size) {
    const GLubyte *text = index >= 0 ? glGetStringi(name, (GLuint)index) : glGetString(name);

    if (!size)
        return;
    buffer[0] = 0;
    if (text) {
        strncpy(buffer, (const char *)text, size - 1);
        buffer[size - 1] = 0;
    }
}

int host_gl_has_extension(const char *name) {
    GLint count = 0, index;

    glGetIntegerv(GL_NUM_EXTENSIONS, &count);
    for (index = 0; index < count; index++) {
        const char *extension = (const char *)glGetStringi(GL_EXTENSIONS, (GLuint)index);

        if (extension && !strcmp(extension, name))
            return 1;
    }
    return 0;
}

/* copies size bytes of a buffer object (the snapshots of the visibility
tests' counters, d3d8_gl.c); ES has no glGetBufferSubData, and the mapping
it offers instead is a host pointer. Binds GL_COPY_READ_BUFFER, which the
renderer uses only for its copies, and leaves it unbound. */
void host_gl_read_buffer(uint32_t buffer, uint32_t offset, uint32_t size, void *data) {
    const void *mapping;

    glBindBuffer(GL_COPY_READ_BUFFER, buffer);
    mapping = glMapBufferRange(GL_COPY_READ_BUFFER, offset, size, GL_MAP_READ_BIT);
    if (mapping) {
        memcpy(data, mapping, size);
        glUnmapBuffer(GL_COPY_READ_BUFFER);
    } else {
        memset(data, 0, size);
    }
    glBindBuffer(GL_COPY_READ_BUFFER, 0);
}

/* The renderer streams each frame's vertices and indices into the next of
a ring of buffers (d3d8_gl.c). A fence marks the end of each frame's work,
and a buffer is written again only once the GPU has passed the fence of the
frame that last used it: drivers queue several frames, and a draw still
waiting to run would otherwise read a later frame's vertices. */
#define FRAME_FENCE_SLOTS 8

static GLsync frame_fences[FRAME_FENCE_SLOTS];

void host_gl_fence_frame(uint32_t slot) {
    if (slot >= FRAME_FENCE_SLOTS)
        return;
    if (frame_fences[slot])
        glDeleteSync(frame_fences[slot]);
    frame_fences[slot] = glFenceSync(GL_SYNC_GPU_COMMANDS_COMPLETE, 0);
}

void host_gl_wait_frame(uint32_t slot) {
    if (slot >= FRAME_FENCE_SLOTS || !frame_fences[slot])
        return;
    /* at most a second: a lost context must not hang the game */
    glClientWaitSync(frame_fences[slot], GL_SYNC_FLUSH_COMMANDS_BIT, 1000000000ull);
    glDeleteSync(frame_fences[slot]);
    frame_fences[slot] = NULL;
}

/* writes data into the buffer bound to target without waiting for the
GPU: the renderer only streams into ranges no queued draw uses. (Mali
copies the whole buffer for a glBufferSubData into a buffer that queued
draws still reference; with hundreds of small uploads per frame that
exhausts memory within seconds.) */
void host_gl_buffer_write(uint32_t target, uint32_t offset, uint32_t size, const void *data) {
    host_perf_upload(size);
    void *mapping = glMapBufferRange(target, offset, size,
                                     GL_MAP_WRITE_BIT | GL_MAP_UNSYNCHRONIZED_BIT |
                                         GL_MAP_INVALIDATE_RANGE_BIT);

    if (!mapping) {
        glBufferSubData(target, offset, size, data);
        return;
    }
    memcpy(mapping, data, size);
    glUnmapBuffer(target);
}
