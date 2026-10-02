"""Compile production cache-tag lookup and exercise native UI tag lifetimes.

The fixture supplies a loaded cache and unload dependencies. It verifies the
registration boundary, native lookup routes, capacity, unload invalidation and
unchanged retail metadata; it does not validate rendered widgets.
"""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def c_block(source, signature):
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 0
    tokens = r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[{}]'
    for token in re.finditer(tokens, source[opening:], re.S):
        if token[0] == "{":
            depth += 1
        elif token[0] == "}":
            depth -= 1
            if not depth:
                return source[start:opening + token.end()]
    raise ValueError(signature)


PREFIX = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#define TRUE 1
#define FALSE 0
#define NONE (-1)
#define HALO_PORT_MAXIMUM_NETWORK_PLAYERS 128
#define csmemset memset
#define csstrcmp strcmp
#define _stricmp strcasecmp
#define match_assert(file,line,condition) assert(condition)
#define match_vassert(file,line,condition,message) do { if (!(condition)) { (void)(message); assert(condition); } } while (0)
#define csprintf(buffer,...) (snprintf(buffer,sizeof(temporary),__VA_ARGS__),buffer)
typedef int boolean;
static char temporary[256];
static char *tag_to_string(int32_t group,char *out) { snprintf(out,16,"%08x",(uint32_t)group); return out; }
/* INSTANCE */
struct cache_file_tag_header { int32_t tag_count; uint32_t checksum; };
static struct {
    boolean tags_loaded;
    struct { uint32_t checksum; } header;
    struct cache_file_tag_header *tag_header;
} cache_file_globals;
static struct cache_file_tag_instance *global_tag_instances;
static unsigned unload_calls;
void hud_hires_tags_unloaded(void) { unload_calls++; }
static void sound_cache_close(void) { unload_calls++; }
static void texture_cache_close(void) { unload_calls++; }
static void cache_file_close(void) { unload_calls++; }
static void tags_header_deregister_vertex_and_index_buffers(struct cache_file_tag_header *header) {
    assert(header == cache_file_globals.tag_header); unload_calls++;
}
/* PRODUCTION */
'''

HARNESS = r'''
static int definitions[MAXIMUM_RUNTIME_UI_TAGS + 1];
static char names[MAXIMUM_RUNTIME_UI_TAGS + 1][32];
static int retail_definition[2];
static struct cache_file_tag_instance retail_tags[2] = {
    {'DeLa', {NONE,NONE}, 0x12340000, "ui\\stock_widget", &retail_definition[0], {0,0}},
    {'ustr', {NONE,NONE}, 0x12340001, "ui\\stock_strings", &retail_definition[1], {0,0}}
};
static struct cache_file_tag_header header = {2,0x18273465};
static void load_fixture(void) {
    cache_file_globals.tags_loaded = TRUE;
    cache_file_globals.header.checksum = 0x77665544;
    cache_file_globals.tag_header = &header;
    global_tag_instances = retail_tags;
}
static void assert_stock(void) {
    assert(tag_loaded('DeLa', "UI\\STOCK_WIDGET") == 0x12340000);
    assert(tag_get('DeLa',0x12340000) == &retail_definition[0]);
    assert(tag_get('ustr',0x12340001) == &retail_definition[1]);
    assert(tag_get('DeLa',0) == &retail_definition[0]);
    assert(!strcmp(tag_get_name(0x12340000),"ui\\stock_widget"));
    assert(tag_get_group_tag(0x12340001) == 'ustr');
    assert(tag_index_is_group(0x12340000,'DeLa'));
    assert(!tag_index_is_group(0x12340000,'ustr'));
    assert(tag_groups_checksum() == 0x18273465);
    assert(cache_files_get_checksum() == 0x77665544);
}
static void invalid_and_idempotent(void) {
    int32_t widget, strings;
    assert(cache_files_register_runtime_ui_tag('DeLa',"ui\\runtime",&definitions[0]) == NONE);
    load_fixture(); assert_stock();
    assert(cache_files_register_runtime_ui_tag('scnr',"ui\\runtime",&definitions[0]) == NONE);
    assert(cache_files_register_runtime_ui_tag('DeLa',NULL,&definitions[0]) == NONE);
    assert(cache_files_register_runtime_ui_tag('DeLa',"",&definitions[0]) == NONE);
    assert(cache_files_register_runtime_ui_tag('DeLa',"ui\\runtime",NULL) == NONE);
    assert(cache_files_register_runtime_ui_tag('DeLa',"UI\\STOCK_WIDGET",&definitions[0]) == NONE);
    assert(cache_files_register_runtime_ui_tag('ustr',"ui\\stock_strings",&definitions[0]) == NONE);
    widget = cache_files_register_runtime_ui_tag('DeLa',"ui\\runtime",&definitions[0]);
    strings = cache_files_register_runtime_ui_tag('ustr',"ui\\runtime_strings",&definitions[1]);
    assert(widget != NONE && strings != NONE && widget != strings);
    assert((int16_t)widget < 0 && (int16_t)strings < 0);
    assert(cache_files_register_runtime_ui_tag('DeLa',"ui\\runtime",&definitions[0]) == widget);
    assert(cache_files_register_runtime_ui_tag('DeLa',"ui\\runtime",&definitions[2]) == NONE);
    assert(cache_files_register_runtime_ui_tag('DeLa',"UI\\RUNTIME",&definitions[0]) == NONE);
    assert(cache_files_register_runtime_ui_tag('DeLa',"ui\\alias",&definitions[0]) == NONE);
    assert(cache_files_register_runtime_ui_tag('ustr',"ui\\alias",&definitions[0]) == NONE);
    assert(tag_loaded('DeLa',"ui\\runtime") == widget);
    assert(tag_loaded('DeLa',"UI\\RUNTIME") == NONE);
    assert(tag_loaded('ustr',"ui\\runtime_strings") == strings);
    assert(tag_get('DeLa',widget) == &definitions[0]);
    assert(tag_get('ustr',strings) == &definitions[1]);
    assert(!strcmp(tag_get_name(widget),"ui\\runtime"));
    assert(tag_get_group_tag(strings) == 'ustr');
    assert(tag_index_is_group(widget,'DeLa') && !tag_index_is_group(widget,'ustr'));
    assert(!tag_index_is_group(widget ^ 0x10000,'DeLa'));
    assert(!tag_index_is_group(NONE,'DeLa'));
    assert(!tag_index_is_group(widget | 63,'DeLa'));
    definitions[0] = 7; assert(*(int *)tag_get('DeLa',widget) == 7); /* Borrowed. */
    assert_stock();
    scenario_tags_unload();
    assert(unload_calls == 5 && !global_tag_instances);
    assert(!tag_index_is_group(widget,'DeLa'));
    assert(tag_loaded('DeLa',"ui\\runtime") == NONE);
    assert(cache_files_register_runtime_ui_tag('DeLa',"ui\\runtime",&definitions[0]) == NONE);
    load_fixture();
    assert(!tag_index_is_group(widget,'DeLa'));
    int32_t replacement = cache_files_register_runtime_ui_tag('DeLa',"ui\\runtime",&definitions[0]);
    assert(replacement != NONE && replacement != widget);
    assert(!tag_index_is_group(widget,'DeLa') && tag_index_is_group(replacement,'DeLa'));
    assert(tag_get('DeLa',replacement) == &definitions[0]);
    scenario_tags_unload();
}
static void bounded_capacity_and_metadata(void) {
    struct cache_file_tag_instance original_tags[2];
    struct cache_file_tag_header original_header = header;
    int32_t ids[MAXIMUM_RUNTIME_UI_TAGS];
    memcpy(original_tags,retail_tags,sizeof(retail_tags)); load_fixture();
    for (unsigned i=0;i<=MAXIMUM_RUNTIME_UI_TAGS;i++) snprintf(names[i],sizeof(names[i]),"ui\\generated_%u",i);
    for (unsigned i=0;i<MAXIMUM_RUNTIME_UI_TAGS;i++) {
        ids[i] = cache_files_register_runtime_ui_tag(i%2 ? 'ustr' : 'DeLa',names[i],&definitions[i]);
        assert(ids[i] != NONE);
        assert(tag_loaded(i%2 ? 'ustr' : 'DeLa',names[i]) == ids[i]);
        assert(tag_get(i%2 ? 'ustr' : 'DeLa',ids[i]) == &definitions[i]);
        for (unsigned j=0;j<i;j++) assert(ids[j] != ids[i]);
    }
    assert(cache_files_register_runtime_ui_tag('DeLa',names[MAXIMUM_RUNTIME_UI_TAGS],&definitions[MAXIMUM_RUNTIME_UI_TAGS]) == NONE);
    assert(cache_files_register_runtime_ui_tag('DeLa',names[0],&definitions[0]) == ids[0]);
    assert(!memcmp(original_tags,retail_tags,sizeof(retail_tags)));
    assert(!memcmp(&original_header,&header,sizeof(header))); assert_stock();
    scenario_tags_unload(); load_fixture();
    for (unsigned i=0;i<MAXIMUM_RUNTIME_UI_TAGS;i++) assert(!tag_index_is_group(ids[i],i%2 ? 'ustr' : 'DeLa'));
    assert(cache_files_register_runtime_ui_tag('DeLa',names[MAXIMUM_RUNTIME_UI_TAGS],&definitions[MAXIMUM_RUNTIME_UI_TAGS]) != NONE);
}
int main(void) {
    invalid_and_idempotent(); bounded_capacity_and_metadata();
    puts("runtime UI tag registry passed"); return 0;
}
'''


class RuntimeUITagTests(unittest.TestCase):
    def test_production_registry_and_cache_lookup(self):
        source = (ROOT / "source/cache/cache_files.c").read_text()
        declarations_start = source.index("#ifdef HALO_PORT_MAXIMUM_NETWORK_PLAYERS\nenum\n{\n\tRUNTIME_UI_TAG_INDEX_BITS")
        declarations_end = source.index("#endif", declarations_start) + len("#endif")
        chunks = [source[declarations_start:declarations_end]]
        signatures = [
            "static struct cache_file_tag_instance *cache_runtime_ui_tag_instance(\n",
            "static void cache_runtime_ui_tags_clear(\n",
            "static struct cache_file_tag_instance *cache_get_tag_instance(\n\tlong tag_index)\n{",
            "long cache_files_register_runtime_ui_tag(\n",
            "void scenario_tags_unload(\n",
            "unsigned long cache_files_get_checksum(\n",
            "unsigned long tag_groups_checksum(\n",
            "long tag_loaded(\n",
            "void *tag_get(\n",
            "boolean tag_index_is_group(\n",
            "char *tag_get_name(\n",
            "unsigned long tag_get_group_tag(\n",
        ]
        chunks.extend(c_block(source, signature) for signature in signatures)
        instance = c_block(source, "struct cache_file_tag_instance\n{") + ";"
        fixture = PREFIX.replace("/* INSTANCE */", instance).replace("/* PRODUCTION */", "\n".join(chunks)) + HARNESS
        # Match guest arithmetic even when the host compiler uses 64-bit long.
        fixture = re.sub(r"\bunsigned long\b", "uint32_t", fixture)
        fixture = re.sub(r"\blong\b", "int32_t", fixture)
        with tempfile.TemporaryDirectory(prefix="halo-runtime-ui-tags-") as temporary:
            folder = Path(temporary)
            (folder / "fixture.c").write_text(fixture)
            subprocess.run(["clang", "-std=c99", "-Wall", "-Wextra", "-Werror", "-Wno-multichar",
                            str(folder / "fixture.c"), "-o", str(folder / "fixture")], check=True)
            result = subprocess.run([str(folder / "fixture")], check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout.strip(), "runtime UI tag registry passed")


if __name__ == "__main__":
    unittest.main()
