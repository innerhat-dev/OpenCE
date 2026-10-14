#include <SDL3/SDL.h>
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <EGL/eglext_angle.h>
#include <GLES3/gl32.h>
#include <GLES2/gl2ext.h>
#include "host_graphics.h"
#include "host_debug.h"
#include "host_shader_cache.h"
static EGLDisplay display;
static EGLConfig config;
static EGLSurface sharedSurface;
static GLuint sharedTexture;
static int sharedBound;
static int metal = 1;
extern int halo_debug_renderer_preference(void);
extern void halo_debug_set_renderer_preference(int);
int halo_graphics_metal(void) { return metal; }
int halo_graphics_prefer_metal(void) { return halo_debug_renderer_preference(); }
void halo_graphics_set_preference(int value) { halo_debug_set_renderer_preference(value); }
void halo_graphics_initialize(void) {
#ifdef HALO_IOS
    metal = halo_graphics_prefer_metal();
#endif
}
void *halo_graphics_proc(const char *name) {
#ifdef HALO_IOS
    if (!metal) return (void *)SDL_GL_GetProcAddress(name);
#endif
    return (void *)eglGetProcAddress(name);
}
void halo_graphics_attach(EGLDisplay current, EGLConfig configuration) {
    display=current; config=configuration;
    halo_debug_initialize();
    halo_shader_cache_install(display, eglGetProcAddress);
}
unsigned int halo_graphics_shared_create(void *surface,unsigned int w,unsigned int h) {
    halo_graphics_shared_destroy();
    EGLint attrs[]={EGL_WIDTH,(EGLint)w,EGL_HEIGHT,(EGLint)h,EGL_IOSURFACE_PLANE_ANGLE,0,EGL_TEXTURE_TARGET,EGL_TEXTURE_2D,EGL_TEXTURE_FORMAT,EGL_TEXTURE_RGBA,EGL_TEXTURE_TYPE_ANGLE,GL_UNSIGNED_BYTE,EGL_TEXTURE_INTERNAL_FORMAT_ANGLE,GL_BGRA_EXT,EGL_NONE};
    sharedSurface=eglCreatePbufferFromClientBuffer(display,EGL_IOSURFACE_ANGLE,surface,config,attrs);
    if(!sharedSurface)return 0;
    void (*genTextures)(GLsizei,GLuint *)=halo_graphics_proc("glGenTextures");genTextures(1,&sharedTexture);
    return halo_graphics_shared_begin()?sharedTexture:0;
}
int halo_graphics_shared_begin(void) {
    if(sharedBound)return 1;
    if(!sharedSurface)return 0;
    void (*bindTexture)(GLenum,GLuint)=halo_graphics_proc("glBindTexture");bindTexture(GL_TEXTURE_2D,sharedTexture);
    sharedBound=eglBindTexImage(display,sharedSurface,EGL_BACK_BUFFER);return sharedBound;
}
int halo_graphics_shared_end(void) {
    if(!sharedBound)return 1;
    EGLBoolean released=eglReleaseTexImage(display,sharedSurface,EGL_BACK_BUFFER);
    /* Complete both the rendering and any release-time work before another
       Metal command queue reads the IOSurface. */
    void (*finish)(void)=halo_graphics_proc("glFinish");finish();
    if(released)sharedBound=0;
    return released;
}
void halo_graphics_shared_destroy(void) {
    halo_graphics_shared_end();
    if(sharedTexture){void (*deleteTextures)(GLsizei,const GLuint *)=halo_graphics_proc("glDeleteTextures");deleteTextures(1,&sharedTexture);sharedTexture=0;}
    if(sharedSurface){eglDestroySurface(display,sharedSurface);sharedSurface=EGL_NO_SURFACE;}
    sharedBound=0;
}
