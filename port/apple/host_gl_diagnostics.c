/* Host GL arguments have already been widened by the shared guest bridge. */
#include <GLES3/gl32.h>
#include "host_gl_dispatch.h"
#include <string.h>
#include "host_debug.h"
static void shader_source(GLuint shader, GLsizei count, const GLchar *const *text, const GLint *lengths) {
    halo_debug_shader_source(shader, count, text, lengths);
    glShaderSource(shader, count, text, lengths);
}
static void compile_shader(GLuint shader) { double t=halo_debug_begin(); glCompileShader(shader); halo_debug_end(shader,0,t); }
static void link_program(GLuint program) { double t=halo_debug_begin(); glLinkProgram(program); halo_debug_end(program,1,t); }
static void attach_shader(GLuint program, GLuint shader) { halo_debug_attach(program,shader); glAttachShader(program,shader); }
static void use_program(GLuint program) { halo_debug_use_program(program); glUseProgram(program); }
static void delete_shader(GLuint shader) { halo_debug_forget(shader,0); glDeleteShader(shader); }
static void delete_program(GLuint program) { halo_debug_forget(program,1); glDeleteProgram(program); }
static void draw_arrays(GLenum mode, GLint first, GLsizei count) { double t=halo_debug_draw_begin(); glDrawArrays(mode,first,count); halo_debug_draw_end(t); }
static void draw_elements(GLenum mode, GLsizei count, GLenum type, const void *indices) { double t=halo_debug_draw_begin(); glDrawElements(mode,count,type,indices); halo_debug_draw_end(t); }
void *halo_debug_gl_resolve(const char *name) {
#define WRAP(gl, fn) if (!strcmp(name, #gl)) return (void *)fn
    WRAP(glShaderSource,shader_source); WRAP(glCompileShader,compile_shader); WRAP(glLinkProgram,link_program);
    WRAP(glAttachShader,attach_shader); WRAP(glUseProgram,use_program);
    WRAP(glDeleteShader,delete_shader); WRAP(glDeleteProgram,delete_program);
    WRAP(glDrawArrays,draw_arrays); WRAP(glDrawElements,draw_elements);
#undef WRAP
    return 0;
}
