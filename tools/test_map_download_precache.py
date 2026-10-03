"""Run the production loader's async map-download boundary with cache stubs.

This checks client readiness and missing-media behavior without a game, network,
or map content. Download verification and path precedence have separate native
and custom-map tests.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.test_network_pings import block

ROOT = Path(__file__).resolve().parents[1]

FIXTURE = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#define HALO_MACOS 1
#define TRUE 1
#define FALSE 0
typedef unsigned char boolean;
typedef float real;
static int loaded, download_status, copy_active, copying_requested, copy_status, begin_success;
static unsigned loaded_checks, download_requests, begins, ends, media_errors, priorities, status_checks;
static boolean cache_files_precache_map_loaded(char const *map) {
    assert(map && map[0]); loaded_checks++; return loaded;
}
static int native_map_download_pending(char const *map) {
    assert(map && map[0]); download_requests++; return download_status;
}
static boolean cache_files_precache_in_progress(void) { return copy_active; }
static boolean cache_files_precache_is_copying_map(char const *map) {
    assert(map && map[0]); return copying_requested;
}
static void cache_files_precache_map_end(void) {
    assert(copy_active); ends++; copy_active=0;
    if(copying_requested && copy_status==1) loaded=1;
}
static short cache_files_precache_map_status(real *progress) {
    assert(copy_active); *progress=0.5f; status_checks++; return copy_status;
}
static void display_error_damaged_media(void) { media_errors++; }
static void cache_files_precache_set_priority(int priority) { assert(priority==0); priorities++; }
static boolean cache_files_precache_map_begin(char const *map,boolean copy) {
    assert(map && map[0] && !copy); begins++;
    if(begin_success) { copy_active=1; copying_requested=1; }
    return begin_success;
}
/* PRODUCTION */
static void reset(void) {
    loaded=download_status=copy_active=copying_requested=copy_status=begin_success=0;
    loaded_checks=download_requests=begins=ends=media_errors=priorities=status_checks=0;
}
static void downloads_wait(void) {
    for(int state=0;state<2;state++) {
        reset(); download_status=state ? -1 : 2;
        /* An unrelated copy stays untouched while its successor downloads. */
        copy_active=1; copying_requested=0; copy_status=2;
        assert(!cache_files_give_time_to_precache("downrush"));
        assert(loaded_checks==1 && download_requests==1);
        assert(!begins && !ends && !media_errors && !priorities && !status_checks);
        assert(copy_active);
        assert(!cache_files_give_time_to_precache("downrush"));
        assert(download_requests==2 && !begins && !media_errors);
    }
}
static void existing_map_ready(void) {
    reset(); loaded=1; download_status=2;
    assert(cache_files_give_time_to_precache("downrush"));
    assert(loaded_checks==1 && !download_requests && !begins && !media_errors);
    download_status=-1;
    assert(cache_files_give_time_to_precache("downrush"));
    assert(!download_requests);
    reset(); assert(!cache_files_give_time_to_precache(NULL));
    assert(!cache_files_give_time_to_precache(""));
    assert(!loaded_checks && !download_requests && !begins && !media_errors);
}
static void original_missing_media(void) {
    reset(); download_status=0; begin_success=0;
    assert(!cache_files_give_time_to_precache("unknown_map"));
    assert(download_requests==1 && begins==1 && priorities==1 && media_errors==1);
    /* Ordinary cache-copy failure remains an error after the download hook. */
    reset(); download_status=0; copy_active=copying_requested=1; copy_status=2;
    assert(!cache_files_give_time_to_precache("known_map"));
    assert(!begins && media_errors==1 && status_checks==1);
}
static void completion_precaches(void) {
    reset(); download_status=2; begin_success=1;
    assert(!cache_files_give_time_to_precache("downrush"));
    assert(!begins && !copy_active && !media_errors);
    /* Atomic install has completed: the pending hook now returns zero. */
    download_status=0;
    assert(!cache_files_give_time_to_precache("downrush"));
    assert(begins==1 && priorities==1 && copy_active && !media_errors);
    assert(!cache_files_give_time_to_precache("downrush"));
    assert(begins==1 && status_checks==1 && !loaded);
    copy_status=1;
    assert(!cache_files_give_time_to_precache("downrush"));
    assert(ends==1 && loaded && !copy_active && !media_errors);
    unsigned requests_before_ready=download_requests;
    assert(cache_files_give_time_to_precache("downrush"));
    assert(download_requests==requests_before_ready && begins==1);
    /* Once a file is available, replacing an old copy follows the old path. */
    reset(); download_status=0; begin_success=1; copy_active=1;
    assert(!cache_files_give_time_to_precache("downrush"));
    assert(ends==1 && begins==1 && copy_active && !media_errors);
}
int main(int argc,char **argv) {
    assert(argc==2);
    if(!strcmp(argv[1],"wait")) downloads_wait();
    else if(!strcmp(argv[1],"ready")) existing_map_ready();
    else if(!strcmp(argv[1],"missing")) original_missing_media();
    else if(!strcmp(argv[1],"complete")) completion_precaches();
    else assert(0);
    return 0;
}
'''


class MapDownloadPrecacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="halo-map-precache-")
        cls.addClassCleanup(cls.directory.cleanup)
        source = (ROOT / "source/cache/cache_files.c").read_text()
        function = block(source, "boolean cache_files_give_time_to_precache(\n")
        path = Path(cls.directory.name) / "precache.c"
        path.write_text(FIXTURE.replace("/* PRODUCTION */", function))
        cls.executable = path.with_suffix("")
        result = subprocess.run([
            "clang", "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-fsanitize=address,undefined", str(path), "-o", str(cls.executable),
        ], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stderr)

    def run_case(self, case):
        result = subprocess.run([str(self.executable), case], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_pending_and_failed_downloads_never_begin_cache_or_damage_media(self):
        self.run_case("wait")

    def test_loaded_maps_stay_ready_and_empty_names_remain_unready(self):
        self.run_case("ready")

    def test_unknown_or_disabled_download_preserves_missing_media_errors(self):
        self.run_case("missing")

    def test_verified_download_completion_resumes_normal_precache(self):
        self.run_case("complete")


if __name__ == "__main__":
    unittest.main()
