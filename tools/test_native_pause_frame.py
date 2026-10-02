"""Exercise production pause-frame slicing and bitmap submission geometry.

The renderer functions and frame-tag helper come directly from production.
Only tag lookup, bitmap loading and GPU submission are replaced. This checks
UVs, clipping, corner dimensions and stock draw behavior, not final pixels.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.test_performance_variants import block

ROOT = Path(__file__).resolve().parents[1]


def function(source, signature):
    return block(source[source.rindex(signature):], signature)


PREFIX = r'''
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef float real;
typedef unsigned char byte,boolean;
typedef uint32_t pixel32;
typedef struct {short x,y;} point2d;
typedef struct {short y0,x0,y1,x1;} rectangle2d;
typedef struct {real x,y;} real_point2d;
typedef struct {real i,j;} real_vector2d;
typedef struct {real red,green,blue;} real_rgb_color;
typedef struct {real alpha,red,green,blue;} real_argb_color;
#define TRUE 1
#define FALSE 0
#define NONE (-1)
#define HALO_PORT_MAXIMUM_NETWORK_PLAYERS 16
#define NUMBER_OF_POINTS_PER_RECTANGLE 4
#define MAX(a,b) ((a)>(b)?(a):(b))
#define MIN(a,b) ((a)<(b)?(a):(b))
#define csmemset memset
enum {UI_WIDGET_DEFINITION_TAG='DeLa',UNICODE_STRING_LIST_TAG='ustr',FONT_GROUP_TAG='font',
      _ui_widget_type_container=1000,_widget_controller_any=4,_interface_bitmap_iface_map3=3};
struct tag_reference {long group_tag,index;};
struct ui_widget_definition {
 short type,controller_index; rectangle2d bounds;
 struct tag_reference background_bitmap,text_label_string_list,text_font,list_header_bitmap,
  list_footer_bitmap,extended_description_widget;
};
struct widget_instance {long definition_tag_index;};
struct bitmap_data {short width,height;};
struct tag_block {long count;void *address;};
struct bitmap_group {struct tag_block bitmaps;};
#define TAG_BLOCK_GET_ELEMENT(b,i,t) (&((t *)(b)->address)[i])
/* RASTERIZER DECLARATIONS */
static struct bitmap_data bitmaps[4]={{16,256},{4,256},{16,256},{64,64}};
static struct bitmap_group plasma={{1,&bitmaps[3]}};
static struct {long tag;const char *name;void *definition;} registry[3];
static unsigned registry_count,generation,quad_count;
static short missing_bitmap=NONE;
static boolean missing_legend;
static struct {
 struct dynamic_screen_vertex vertices[4];
 struct bitmap_data *bitmap; boolean plasma; real alpha;
} quads[32];
static real_argb_color ui_plasma_effect_color={0.25f,0.05f,0.05f,0.05f};
static long tag_loaded(long group,const char *name) {
 static const char *const names[]={"ui\\shell\\bitmaps\\pausebox2_left",
  "ui\\shell\\bitmaps\\pausebox2_center","ui\\shell\\bitmaps\\pausebox2_right"};
 if(group=='bitm')for(short i=0;i<3;i++)if(!strcmp(name,names[i]))return missing_bitmap==i?NONE:10+i;
 if(group==UI_WIDGET_DEFINITION_TAG && !strcmp(name,"ui\\shell\\main_menu\\button_key_sm"))return missing_legend?NONE:42;
 if(group==UI_WIDGET_DEFINITION_TAG)for(unsigned i=0;i<registry_count;i++)
  if(!strcmp(name,registry[i].name))return registry[i].tag;
 return NONE;
}
static long cache_files_register_runtime_ui_tag(long group,const char *name,void *definition) {
 assert(group==UI_WIDGET_DEFINITION_TAG);
 for(unsigned i=0;i<registry_count;i++)if(!strcmp(name,registry[i].name)) {
  assert(definition==registry[i].definition);return registry[i].tag;
 }
 assert(registry_count<3);unsigned i=registry_count++;
 registry[i].tag=1000+generation*10+i;registry[i].name=name;registry[i].definition=definition;
 return registry[i].tag;
}
static struct ui_widget_definition *ui_widget_definition_get(long tag) {
 for(unsigned i=0;i<registry_count;i++)if(registry[i].tag==tag)return registry[i].definition;
 assert(!"unknown widget");return NULL;
}
static struct bitmap_data *bitmap_group_get_bitmap_from_sequence(long tag,short sequence,short frame) {
 assert(sequence==0 && frame==0 && tag>=10 && tag<=12);return &bitmaps[tag-10];
}
static long interface_get_tag_index(short index) {assert(index==3);return 3;}
static struct bitmap_group *bitmap_group_get(long tag) {assert(tag==3);return &plasma;}
static long system_milliseconds(void) {return 1000;}
static pixel32 modulate_pixel32_by_real_alpha(pixel32 color,real alpha) {
 return (color&0xFFFFFF)|((pixel32)(alpha*255)<<24);
}
static void rasterizer_psuedo_dynamic_screen_quad_draw(
 struct rasterizer_dynamic_screen_geometry_parameters *parameters,struct dynamic_screen_vertex *vertices) {
 assert(quad_count<32);unsigned q=quad_count++;
 memcpy(quads[q].vertices,vertices,sizeof(quads[q].vertices));
 quads[q].plasma=parameters->doing_plasma_effect;
 quads[q].bitmap=parameters->map[parameters->doing_plasma_effect?2:0];
 quads[q].alpha=parameters->plasma_fade.alpha;
 assert(!parameters->point_sampled && parameters->framebuffer_blend_function==0);
}
'''


HARNESS = r'''
static void near(real actual,real expected) {assert(fabsf(actual-expected)<0.00001f);}
static void vertex(unsigned quad,unsigned index,real x,real y,real u,real v) {
 struct dynamic_screen_vertex *p=&quads[quad].vertices[index];
 near(p->position.x,x);near(p->position.y,y);near(p->texture_coordinates.x,u);near(p->texture_coordinates.y,v);
}
static void tag_lifecycle(void) {
 assert(native_pause_frame_tag(160)==NONE && !registry_count);
 missing_bitmap=1;assert(native_pause_frame_tag(213)==NONE && !registry_count);
 missing_bitmap=NONE;missing_legend=TRUE;assert(native_pause_frame_tag(213)==NONE && !registry_count);
 missing_legend=FALSE;long first=native_pause_frame_tag(159);assert(first==1000 && registry_count==3);
 for(unsigned i=0;i<3;i++) {
  long tag=native_pause_frame_tag(native_pause_frame_heights[i]);
  assert(tag==1000+i && native_pause_frame_is_widget(tag));
  struct ui_widget_definition *definition=ui_widget_definition_get(tag);
  assert(definition->bounds.x0==-4 && definition->bounds.x1==222);
  assert(definition->bounds.y0==0 && definition->bounds.y1==native_pause_frame_heights[i]);
  assert(definition->background_bitmap.index==NONE && definition->text_font.index==NONE);
  assert(definition->type==_ui_widget_type_container && definition->controller_index==_widget_controller_any);
 }
 assert(registry_count==3 && !native_pause_frame_is_widget(42) && !native_pause_frame_is_widget(NONE));
 registry_count=0;generation++;long replacement=native_pause_frame_tag(213);
 assert(replacement==1011 && !native_pause_frame_is_widget(first));
}
static void authored_caps_and_viewports(void) {
 const rectangle2d clips[]={{0,0,480,640},{0,0,240,640},{0,0,240,320}};
 const point2d origins[]={{211,120},{211,0},{51,0}};
 for(unsigned layout=0;layout<3;layout++)for(unsigned size=0;size<3;size++) {
  short height=native_pause_frame_heights[size];
  struct widget_instance widget={native_pause_frame_tag(height)};
  rectangle2d clip=clips[layout];point2d origin=origins[layout];quad_count=0;
  native_pause_frame_render(&widget,&clip,origin,0.5f);assert(quad_count==9);
  for(unsigned piece=0;piece<3;piece++) {
   unsigned top=piece*3,middle=top+1,bottom=top+2;
   real x0=origin.x+(piece==0?-4:piece==1?12:206),width=piece==1?194:16;
   vertex(top,0,x0,origin.y,0,0);vertex(top,2,x0+width,origin.y+16,1,16.0f/256);
   vertex(middle,0,x0,origin.y+16,0,16.0f/256);
   vertex(middle,2,x0+width,origin.y+height-31,1,128.0f/256);
   vertex(bottom,0,x0,origin.y+height-31,0,128.0f/256);
   vertex(bottom,2,x0+width,origin.y+height,1,159.0f/256);
   assert(quads[top].bitmap==&bitmaps[piece] && quads[middle].bitmap==&bitmaps[piece] && quads[bottom].bitmap==&bitmaps[piece]);
   for(unsigned band=0;band<3;band++) {
    unsigned q=top+band;assert(quads[q].plasma && quads[q].alpha==0.25f);
    for(unsigned v=0;v<4;v++) {
     assert(quads[q].vertices[v].color==0x7FFFFFFF);
     assert(quads[q].vertices[v].position.x>=clip.x0 && quads[q].vertices[v].position.x<=clip.x1);
     assert(quads[q].vertices[v].position.y>=clip.y0 && quads[q].vertices[v].position.y<=clip.y1);
    }
   }
  }
 }
 /* A stock widget must not enter this rendering path. */
 struct widget_instance stock={42};quad_count=0;
 native_pause_frame_render(&stock,NULL,(point2d){0,0},1);assert(!quad_count);
}
static void clipped_source_alignment(void) {
 rectangle2d destination={50,10,150,210},source={128,3,159,15},clip={75,60,125,160};
 rectangle2d before_destination=destination,before_source=source,before_clip=clip;
 quad_count=0;draw_bitmap_region_in_rect(&bitmaps[0],&destination,&source,&clip,0xAACCDDFF,NULL,TRUE,&source);
 assert(quad_count==1 && !quads[0].plasma);
 vertex(0,0,60,75,6.0f/16,135.75f/256);vertex(0,2,160,125,12.0f/16,151.25f/256);
 assert(quads[0].vertices[0].color==0xAACCDDFF);
 assert(!memcmp(&before_destination,&destination,sizeof(destination)));
 assert(!memcmp(&before_source,&source,sizeof(source)) && !memcmp(&before_clip,&clip,sizeof(clip)));
 /* Fully outside, empty destination and a clip merely touching an edge draw nothing. */
 const rectangle2d outside[]={{0,0,40,300},{160,0,200,300},{0,220,200,300},{0,-30,200,0},
                             {0,0,50,300},{0,0,200,10},{50,10,50,210}};
 for(unsigned i=0;i<sizeof(outside)/sizeof(outside[0]);i++) {
  rectangle2d c=outside[i];quad_count=0;
  draw_bitmap_region_in_rect(&bitmaps[0],&destination,&source,&c,0,NULL,TRUE,&source);assert(!quad_count);
 }
 rectangle2d empty={50,10,50,210};quad_count=0;
 draw_bitmap_region_in_rect(&bitmaps[0],&empty,&source,NULL,0,NULL,TRUE,&source);assert(!quad_count);
 /* The full panel clips into a small viewport without moving/stretching caps. */
 struct widget_instance widget={native_pause_frame_tag(240)};
 clip=(rectangle2d){30,110,200,320};quad_count=0;
 native_pause_frame_render(&widget,&clip,(point2d){108,24},1);assert(quad_count==6);
 vertex(0,0,110,30,6.0f/16,6.0f/256);vertex(0,2,120,40,1,16.0f/256);
 vertex(5,0,314,40,0,16.0f/256);
 vertex(5,2,320,200,6.0f/16,(16.0f+160.0f*112.0f/193.0f)/256);
}
static void stock_bitmap_regression(void) {
 /* Authored widgets retain their previous UV behavior, including source
  * extents from bounds and clipping without source-coordinate adjustment. */
 rectangle2d destination={30,20,270,220},clip={90,60,210,200};quad_count=0;
 draw_bitmap_in_rect(&bitmaps[0],&destination,&destination,&clip,0xFFFFFFFF,NULL,TRUE);
 assert(quad_count==1 && !quads[0].plasma);
 vertex(0,0,60,90,0,0);vertex(0,2,200,210,1,240.0f/256);
 rectangle2d bitmap_rect={7,5,166,9};quad_count=0;
 draw_bitmap_in_rect(&bitmaps[0],&destination,&bitmap_rect,&clip,0xFFFFFFFF,NULL,FALSE);
 assert(quad_count==1 && quads[0].plasma && quads[0].bitmap==&bitmaps[0]);
 vertex(0,0,60,90,0,0);vertex(0,2,200,210,4.0f/16,159.0f/256);
 quad_count=0;draw_bitmap_in_rect(&bitmaps[0],&destination,NULL,NULL,0xFFFFFFFF,NULL,TRUE);
 vertex(0,0,20,30,0,0);vertex(0,2,220,270,1,1);
 quad_count=0;draw_bitmap_in_rect(NULL,&destination,NULL,NULL,0,NULL,TRUE);assert(!quad_count);
 draw_bitmap_in_rect(&bitmaps[0],NULL,NULL,NULL,0,NULL,TRUE);assert(!quad_count);
}
int main(void) {
 tag_lifecycle();authored_caps_and_viewports();clipped_source_alignment();stock_bitmap_regression();
 puts("Native pause-frame caps, explicit UV clipping, viewport bounds and stock bitmap behavior passed");
 return 0;
}
'''


class NativePauseFrameTests(unittest.TestCase):
    def test_production_frame_geometry_and_stock_bitmap_regression(self):
        widget = (ROOT / "source/interface/ui_widget.c").read_text()
        rasterizer = (ROOT / "source/rasterizer/rasterizer.h").read_text()
        declarations = "\n".join(block(rasterizer, signature) + ";" for signature in (
            "struct dynamic_screen_vertex\n{", "struct rasterizer_dynamic_screen_geometry_parameters\n{"))
        source = PREFIX.replace("/* RASTERIZER DECLARATIONS */", declarations)
        source += (ROOT / "source/interface/native_pause_frame.inc").read_text() + "\n"
        for signature in ("static __inline real compute_offset_coordinate(",
                          "static void draw_bitmap_region_in_rect(", "void draw_bitmap_in_rect(",
                          "static void native_pause_frame_render("):
            source += function(widget, signature) + "\n"
        source += HARNESS
        with tempfile.TemporaryDirectory(prefix="halo-pause-frame-") as temporary:
            directory = Path(temporary)
            (directory / "test.c").write_text(source)
            subprocess.run(["clang", "-std=c11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                            "-Wno-unused-parameter", "-fsanitize=address,undefined",
                            str(directory / "test.c"), "-o", str(directory / "test")], check=True)
            subprocess.run([str(directory / "test")], check=True)


if __name__ == "__main__":
    unittest.main()
