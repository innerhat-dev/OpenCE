"""Check timer layout and the production stock-glyph scaling path.

Fixtures compile the renderer and rasterizer functions with only engine state,
font-cache lookup and the hardware submission replaced. These check geometry
and draw state, not a live framebuffer or subjective font readability.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.test_performance_variants import block

ROOT = Path(__file__).resolve().parents[1]


def function(source, signature):
    return block(source[source.rindex(signature):], signature)


def compile_run(source):
    with tempfile.TemporaryDirectory(prefix="halo-timer-render-") as temporary:
        directory = Path(temporary)
        (directory / "test.c").write_text(source)
        subprocess.run(["clang", "-std=c11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                        "-Wno-unused-function", "-Wno-unused-parameter", "-Wno-unused-variable",
                        "-fsanitize=address,undefined", str(directory / "test.c"),
                        "-o", str(directory / "test")], check=True)
        subprocess.run([str(directory / "test")], check=True)


PREFIX = r'''
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef float real;
typedef int boolean;
typedef uint32_t pixel32;
typedef struct { short x,y; } point2d;
typedef struct { short y0,x0,y1,x1; } rectangle2d;
typedef struct { real alpha,red,green,blue; } real_argb_color;
#define HALO_PORT_MAXIMUM_NETWORK_PLAYERS 16
#define TRUE 1
#define FALSE 0
#define NONE (-1)
#define TICKS_PER_SECOND 30
#define NUMBER_OF_VERTICES_PER_QUADRILATERAL 4
#define MAX(a,b) ((a)>(b)?(a):(b))
#define MIN(a,b) ((a)<(b)?(a):(b))
#define FLOOR(a,b) MAX(a,b)
#define match_assert(file,line,condition) assert(condition)
static struct { struct { rectangle2d window_bounds,viewport_bounds; } camera; } render;
'''


class PerformanceTimerRenderTests(unittest.TestCase):
    def test_timer_placement_and_stock_default_draw(self):
        renderer = (ROOT / "port/linux/game/performance_timer_render.c").read_text()
        renderer = "\n".join(line for line in renderer.splitlines() if not line.startswith("#include"))
        source = PREFIX + r'''
static long position,font=77;
static double configured_scale=1;
static unsigned original_draws,scaled_draws,mode_changes;
static rectangle2d drawn;
static real drawn_scale,anchor_x,anchor_y;
static short justification;
static char drawn_text[32];
static real_argb_color hud_color={0.9f,0.2f,0.5f,0.8f};
static long hud_get_font_index(void) { return font; }
static void hud_get_text_color(real_argb_color *color) { *color=hud_color; }
static long config_integer(char const *key) { assert(!strcmp(key,"display.timer_position"));return position; }
static double config_real(char const *key) { assert(!strcmp(key,"display.timer_scale"));return configured_scale; }
static void draw_string_set_draw_mode(long f,short style,short align,short flags,real_argb_color *color) {
 assert(f==77 && style==NONE && flags==0 && !memcmp(color,&hud_color,sizeof(hud_color)));
 justification=align;++mode_changes;
}
static void rasterizer_draw_string(rectangle2d const *bounds,rectangle2d const *clip,point2d *cursor,short height,char const *text) {
 assert(!clip && !cursor && !height);drawn=*bounds;strcpy(drawn_text,text);++original_draws;
}
static void rasterizer_draw_string_scaled(rectangle2d const *bounds,rectangle2d const *clip,char const *text,float scale,float x,float y) {
 assert(!clip);drawn=*bounds;strcpy(drawn_text,text);drawn_scale=scale;anchor_x=x;anchor_y=y;++scaled_draws;
}
''' + renderer + r'''
static void bounds_equal(short x0,short y0,short x1,short y1) {
 assert(drawn.x0==x0 && drawn.y0==y0 && drawn.x1==x1 && drawn.y1==y1);
}
int main(void) {
 render.camera.window_bounds=render.camera.viewport_bounds=(rectangle2d){0,0,480,640};
 performance_timer_render(29);bounds_equal(0,12,640,44);assert(!strcmp(drawn_text,"00:00"));
 performance_timer_render(30);assert(!strcmp(drawn_text,"00:01"));
 performance_timer_render(1800);assert(!strcmp(drawn_text,"01:00"));
 performance_timer_render(30*60*123+30*59);assert(!strcmp(drawn_text,"123:59"));
 assert(original_draws==4 && !scaled_draws && justification==2);
 position=1;performance_timer_render(0);bounds_equal(0,436,640,468);assert(justification==2);
 position=2;performance_timer_render(0);bounds_equal(0,436,628,468);assert(justification==1);
 /* Nonzero origin in two- and four-player windows must stay viewport-local. */
 render.camera.window_bounds=render.camera.viewport_bounds=(rectangle2d){240,0,480,640};
 position=0;performance_timer_render(0);bounds_equal(0,12,640,44);
 position=1;performance_timer_render(0);bounds_equal(0,196,640,228);
 render.camera.window_bounds=render.camera.viewport_bounds=(rectangle2d){240,320,480,640};
 position=0;performance_timer_render(0);bounds_equal(0,12,320,44);
 position=2;performance_timer_render(0);bounds_equal(0,196,308,228);
 /* Letterboxing/safe-window offsets survive conversion to viewport-local. */
 render.camera.window_bounds=(rectangle2d){248,328,472,632};
 position=0;performance_timer_render(0);bounds_equal(8,20,312,52);
 unsigned unscaled=original_draws;
 for(unsigned step=0;step<=10;step++) {
  configured_scale=0.5+0.05*step;
  for(position=0;position<3;position++) {
   performance_timer_render(0);
   if(step<10) {
    assert(fabsf(drawn_scale-(float)configured_scale)<0.00001f);
    assert(anchor_x==(position==2?300:160));assert(anchor_y==(position==0?20:220));
   }
  }
 }
 assert(scaled_draws==30 && original_draws==unscaled+3);
 double invalid[]={0.49,1.01,NAN,INFINITY,-INFINITY};
 for(unsigned i=0;i<sizeof(invalid)/sizeof(invalid[0]);i++) {configured_scale=invalid[i];performance_timer_render(0);}
 assert(scaled_draws==30 && original_draws==unscaled+8);
 position=99;performance_timer_render(0);bounds_equal(8,20,312,52);assert(justification==2);
 unsigned before=mode_changes;performance_timer_render(-1);assert(mode_changes==before);
 font=NONE;performance_timer_render(0);assert(mode_changes==before);font=77;
 render.camera.window_bounds=(rectangle2d){240,320,240,320};performance_timer_render(0);assert(mode_changes==before);
 return 0;
}
'''
        compile_run(source)

    def test_glyph_scale_preserves_uv_color_shadow_and_restores_scope(self):
        text = (ROOT / "source/rasterizer/rasterizer_text.c").read_text()
        source = PREFIX + r'''
typedef struct { real x,y; } real_point2d;
struct dynamic_screen_vertex { real_point2d position,texture_coordinates; pixel32 color; };
struct parse_string_state { int unused; };
struct font_header { int unused; };
struct font_character { short hardware_character_index; };
static pixel32 global_shadow_color;
static struct dynamic_screen_vertex captured[32][4];
static unsigned captures;
static void rasterizer_text_draw_character(struct dynamic_screen_vertex const *vertices) {
 assert(captures<32);memcpy(captured[captures++],vertices,sizeof(captured[0]));
}
static void cache_hardware_format_character(struct font_header *font,struct font_character *character) { (void)font;(void)character; }
static void hardware_character_cache_get_origin(short index,short *x,short *y) { assert(index==7);*x=31;*y=47; }
''' + block(text, "static struct rasterizer_text_transform\n{") + " rasterizer_text_transform = {1,0,0};\n"
        source += function(text, "static void rasterizer_text_submit_character(") + "\n"
        source += function(text, "static void\nrasterizer_draw_character(") + "\n"
        source += function(text, "static void\nrasterizer_draw_character_with_dropshadow(") + "\n"
        source += r'''
static void rasterizer_draw_string_scaled(rectangle2d const *,rectangle2d const *,char const *,float,float,float);
static void glyph(void) {
 struct font_character character={7};
 rasterizer_draw_character_with_dropshadow(NULL,NULL,&character,0xCC55AADD,300,20,2,3,12,18);
}
/* The normal text path may return early, or reenter a nested scaled draw. */
static void rasterizer_draw_string(rectangle2d const *bounds,rectangle2d const *clip,point2d *cursor,short height,char const *string) {
 assert(!cursor && !height);
 if(!string[0])return;
 glyph();
 if(!strcmp(string,"nested")) {rasterizer_draw_string_scaled(bounds,clip,"inner",0.75f,100,200);glyph();}
}
''' + function(text, "void rasterizer_draw_string_scaled(") + r'''
static int near(real a,real b) { return fabsf(a-b)<0.0001f; }
int main(void) {
 struct dynamic_screen_vertex original[2][4];
 glyph();assert(captures==2);memcpy(original,captured,sizeof(original));
 assert(original[0][0].position.x==301 && original[0][0].position.y==21);
 assert(original[1][0].position.x==300 && original[1][0].position.y==20);
 assert(original[0][0].color==0xCC000000 && original[1][0].color==0xCC55AADD);
 assert(original[1][0].texture_coordinates.x==33 && original[1][0].texture_coordinates.y==50);
 for(unsigned step=0;step<=10;step++) {
  float scale=0.5f+0.05f*step;
  captures=0;rasterizer_draw_string_scaled(NULL,NULL,"timer",scale,320,12);assert(captures==2);
  for(unsigned pass=0;pass<2;pass++)for(unsigned vertex=0;vertex<4;vertex++) {
   struct dynamic_screen_vertex *v=&captured[pass][vertex],*o=&original[pass][vertex];
   assert(near(v->position.x,320+(o->position.x-320)*scale));
   assert(near(v->position.y,12+(o->position.y-12)*scale));
   assert(v->color==o->color && !memcmp(&v->texture_coordinates,&o->texture_coordinates,sizeof(v->texture_coordinates)));
  }
  assert(near(captured[0][0].position.x-captured[1][0].position.x,scale));
  assert(near(captured[0][0].position.y-captured[1][0].position.y,scale));
  captures=0;glyph();assert(!memcmp(captured,original,sizeof(original)));
 }
 captures=0;rasterizer_draw_string_scaled(NULL,NULL,"nested",0.5f,320,12);assert(captures==6);
 assert(near(captured[1][0].position.x,310));assert(near(captured[3][0].position.x,250));
 assert(!memcmp(captured[0],captured[4],sizeof(captured[0])));
 assert(!memcmp(captured[1],captured[5],sizeof(captured[1])));
 captures=0;rasterizer_draw_string_scaled(NULL,NULL,"",0.5f,320,12);assert(!captures);
 glyph();assert(!memcmp(captured,original,sizeof(original)));
 float invalid[]={NAN,0.49f,1.01f,INFINITY};
 for(unsigned i=0;i<sizeof(invalid)/sizeof(invalid[0]);i++) {
  captures=0;rasterizer_draw_string_scaled(NULL,NULL,"timer",invalid[i],320,12);
  assert(!memcmp(captured,original,sizeof(original)));
 }
 /* The no-shadow callback uses the same scoped transform. */
 captures=0;struct font_character character={7};
 rasterizer_text_transform=(struct rasterizer_text_transform){0.5f,320,12};
 rasterizer_draw_character(NULL,NULL,&character,0xCC55AADD,300,20,2,3,12,18);
 assert(captures==1 && captured[0][0].position.x==310 && captured[0][0].position.y==16);
 assert(captured[0][0].texture_coordinates.x==33 && captured[0][0].texture_coordinates.y==50);
 return 0;
}
'''
        compile_run(source)


if __name__ == "__main__":
    unittest.main()
