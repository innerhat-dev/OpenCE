"""Check first-frame and changed-target presentation using the real FBO adapter."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HARNESS = r'''
#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
#define HALO_ANDROID 1
#define TRUE 1
#define GL_FRAMEBUFFER 1
#define GL_READ_FRAMEBUFFER 2
#define GL_DRAW_FRAMEBUFFER 3
#define GL_COLOR_ATTACHMENT0 4
#define GL_DEPTH_STENCIL_ATTACHMENT 5
#define GL_TEXTURE_2D 6
#define GL_NONE 0
#define GL_FRAMEBUFFER_COMPLETE 7
#define GL_SCISSOR_TEST 8
#define GL_TRUE 1
#define GL_COLOR_BUFFER_BIT 9
#define GL_LINEAR 10
#define STREAM_BUFFER_RING 8
typedef unsigned GLuint, GLenum;
typedef int GLint, BOOL;
struct framebuffer_entry { GLuint color, depth, framebuffer; struct framebuffer_entry *next; };
static struct framebuffer_entry *framebuffers;
struct surface { unsigned Data; };
struct render_target_entry { struct { GLuint texture; unsigned long gl_width, gl_height; } target; };
static struct {
    BOOL gl_ready;
    struct surface back_buffer;
    unsigned long frame, buffer_ring, stream_offset, index_offset;
    GLuint stream_buffer, index_buffer, stream_buffers[8], index_buffers[8];
} device;
static GLuint read_target, draw_target, next_framebuffer, blits, swaps;
static void glGenFramebuffers(unsigned count, GLuint *output) {
    assert(count == 1); *output = ++next_framebuffer;
}
static void glBindFramebuffer(GLenum target, GLuint framebuffer) {
    if (target == GL_FRAMEBUFFER || target == GL_READ_FRAMEBUFFER) read_target = framebuffer;
    if (target == GL_FRAMEBUFFER || target == GL_DRAW_FRAMEBUFFER) draw_target = framebuffer;
}
static void glFramebufferTexture2D(GLenum target, GLenum attachment, GLenum texture, GLuint object, int level) {
    (void)attachment; (void)texture; (void)object; (void)level; assert(target == GL_FRAMEBUFFER);
}
static void glDrawBuffers(unsigned count, const GLenum *buffers) { (void)buffers; assert(count == 1); }
static GLenum glCheckFramebufferStatus(GLenum target) { assert(target == GL_FRAMEBUFFER); return GL_FRAMEBUFFER_COMPLETE; }
static void platform_log(const char *message, ...) { (void)message; assert(0); }
static void xgpu_gl_state_invalidate(void) {}
/* FRAMEBUFFERS */
static struct render_target_entry *render_target_get(struct surface *surface) {
    static struct render_target_entry target;
    target.target.texture = surface->Data;
    target.target.gl_width = 640; target.target.gl_height = 480;
    return &target;
}
static int trace_frame(void) { return 0; }
static void write_screenshot(struct render_target_entry *target) { (void)target; assert(0); }
static void platform_video_drawable_size(int *width, int *height) { *width = 640; *height = 480; }
static void glDisable(GLenum target) { (void)target; }
static void glColorMask(int r, int g, int b, int a) { (void)r; (void)g; (void)b; (void)a; }
static void glClearColor(float r, float g, float b, float a) { (void)r; (void)g; (void)b; (void)a; }
static void glClear(GLenum mask) { (void)mask; assert(draw_target == 0); }
static void glBlitFramebuffer(int a, int b, int c, int d, int e, int f, int g, int h, GLenum mask, GLenum filter) {
    (void)a; (void)b; (void)c; (void)d; (void)e; (void)f; (void)g; (void)h; (void)mask; (void)filter;
    assert(read_target && draw_target == 0 && read_target != draw_target); blits++;
}
static void platform_video_swap(void) { swaps++; }
static void gl_check_errors(const char *where) { (void)where; }
static void xgpu_texture_cache_begin_frame(void) {}
static void host_gl_fence_frame(unsigned slot) { assert(slot < STREAM_BUFFER_RING); }
static void host_gl_wait_frame(unsigned slot) { assert(slot < STREAM_BUFFER_RING); }
static void present(void) {
    long screenshot_every = 0;
    /* PRESENT */
    device.frame++;
}
int main(void) {
    present(); assert(!blits && !next_framebuffer);
    device.gl_ready = TRUE;
    device.back_buffer.Data = 17;
    present(); assert(blits == 1 && next_framebuffer == 1);
    present(); assert(blits == 2 && next_framebuffer == 1);
    device.back_buffer.Data = 29;
    present(); assert(blits == 3 && next_framebuffer == 2);
    device.back_buffer.Data = 17;
    present(); assert(blits == 4 && next_framebuffer == 2 && swaps == 4);
    puts("First-frame, cached and changed-target presentation has no framebuffer feedback loop");
}
'''


class Presentation(unittest.TestCase):
    def test_first_frame_and_target_reuse(self):
        source = (ROOT / 'port/linux/src/d3d8_gl.c').read_text()
        framebuffer = 'static GLuint framebuffer_get' + source.split('static GLuint framebuffer_get', 1)[1].split(
            '/* the pixels per unit of the bound targets', 1)[0]
        present = source.split('void WINAPI D3DDevice_Present', 1)[1]
        body = '\tif (device.gl_ready)' + present.split('\tif (device.gl_ready)', 1)[1].split('\tdevice.frame++;', 1)[0]
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            probe = directory / 'presentation.c'
            probe.write_text(HARNESS.replace('/* FRAMEBUFFERS */', framebuffer).replace('/* PRESENT */', body))
            executable = directory / 'presentation'
            compiled = subprocess.run(['clang', '-O2', '-Wall', probe, '-o', executable],
                                      capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            tested = subprocess.run([executable], capture_output=True, text=True, timeout=5)
            self.assertEqual(tested.returncode, 0, tested.stderr)


if __name__ == '__main__':
    unittest.main()
