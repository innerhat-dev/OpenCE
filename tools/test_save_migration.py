"""Exercise production desktop save migration using isolated synthetic files only."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def function(source, signature):
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 1
    end = brace + 1
    while depth:
        if source[end] == "{":
            depth += 1
        elif source[end] == "}":
            depth -= 1
        end += 1
    return source[start:end]


HARNESS = r'''
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifndef _WIN32
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#include <pthread.h>
#else
#include <direct.h>
#include <windows.h>
typedef SRWLOCK pthread_mutex_t;
#define PTHREAD_MUTEX_INITIALIZER SRWLOCK_INIT
static int pthread_mutex_lock(pthread_mutex_t *lock) { AcquireSRWLockExclusive(lock); return 0; }
static int pthread_mutex_unlock(pthread_mutex_t *lock) { ReleaseSRWLockExclusive(lock); return 0; }
#endif
#include "posix.h"
typedef int BOOL;
#define MAX_PATH 260
static int migration_calls;
static const char *config_string(const char *name) {
    const char *value = getenv("HALO_SAVE_ROOT");
    (void)name;
    return value ? value : (getenv("TEST_SAVE_CONFIG") ? getenv("TEST_SAVE_CONFIG") : "");
}
static const char *platform_data_root(void) { return "."; }
static void platform_log(const char *format, ...) {
    va_list arguments; va_start(arguments, format); vfprintf(stderr, format, arguments); va_end(arguments);
    fputc('\n', stderr);
}
#if !defined(HALO_MACOS) && !defined(HALO_ANDROID)
static const char *SDL_GetBasePath(void) { return getenv("TEST_CONFIG_BASE"); }
#endif
#ifndef _WIN32
#undef write
ssize_t migration_test_write(int descriptor, const void *buffer, size_t size) {
    if (getenv("TEST_SAVE_FAIL_WRITE")) { errno = ENOSPC; return -1; }
    return write(descriptor, buffer, size);
}
#undef linkat
int migration_test_linkat(int old_directory, const char *old_name, int directory, const char *name, int flags) {
    if (getenv("TEST_SAVE_RACE") && !strcmp(name, "profile.bin")) {
        int competitor = openat(directory, name, O_WRONLY | O_CREAT | O_EXCL, 0600);
        if (competitor >= 0) { write(competitor, "competing", 9); close(competitor); }
    }
    return linkat(old_directory, old_name, directory, name, flags);
}
#endif
#if !defined(HALO_MACOS) && !defined(HALO_ANDROID)
int real_migrate_save_directory(const char *legacy, const char *destination);
static int counted_migration(const char *legacy, const char *destination) {
    migration_calls++;
    return real_migrate_save_directory(legacy, destination);
}
#undef posix_migrate_save_directory
#define posix_migrate_save_directory counted_migration
#endif
/* ROOT_FUNCTIONS */
int main(int count, char **arguments) {
#if !defined(HALO_MACOS) && !defined(HALO_ANDROID)
    if (count == 4 && !strcmp(arguments[1], "migrate")) {
        printf("%d\n", real_migrate_save_directory(arguments[2], arguments[3])); return 0;
    }
    if (count == 3 && !strcmp(arguments[1], "translate")) {
        char path[1024]; platform_translate_path(arguments[2], path, sizeof(path)); puts(path); return 0;
    }
#endif
    if (count > 1 && !strcmp(arguments[1], "config")) {
        char path[1024]; config_path(path, sizeof(path)); puts(path); return 0;
    }
    puts(platform_save_root());
    fprintf(stderr, "migration_calls=%d\n", migration_calls);
    return 0;
}
'''


@unittest.skipUnless(shutil.which("clang"), "clang is required for the production C fixture")
class SaveMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.build.cleanup)
        cls.build_root = Path(cls.build.name).resolve()
        source = (ROOT / "port/linux/src/xbox_files.c").read_text()
        config = (ROOT / "port/linux/src/port_config.c").read_text()
        pieces = [function(source, signature) for signature in (
            "static BOOL directory_exists(", "static void trim_separators(",
            "static void make_directories(", "const char *platform_save_root(")]
        pieces.append(function(config, "static void config_path("))
        pieces.append("#if !defined(HALO_MACOS) && !defined(HALO_ANDROID)\n" +
                      function(source, "void platform_translate_path(") + "\n#endif")
        harness = cls.build_root / "fixture.c"
        harness.write_text(HARNESS.replace("/* ROOT_FUNCTIONS */", "\n".join(pieces)))
        base = ["clang", "-std=gnu11", "-Wall", "-Wextra", "-I", str(ROOT / "port/linux/src")]
        cls.executables = {}
        if sys.platform == "win32":
            # The Windows runner has LLVM, Visual Studio and its SDK, just as
            # tools/windows_build.py requires. Run the actual native Win APIs.
            binary = cls.build_root / "windows.exe"
            subprocess.run(base + ["-D_CRT_SECURE_NO_WARNINGS", "-DWIN32_LEAN_AND_MEAN",
                           "-Dposix_migrate_save_directory=real_migrate_save_directory",
                           str(harness), str(ROOT / "port/windows/src/win32_files.c"), "-o", str(binary)], check=True)
            cls.executables["windows"] = binary
            return
        flags = ["-D_GNU_SOURCE", "-D_FILE_OFFSET_BITS=64", "-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
        if sys.platform == "darwin":
            # Darwin spells the native timestamp fields differently; the ABI
            # helper and copy algorithm are otherwise compiled in full.
            flags += ["-Dst_mtim=st_mtimespec", "-Dst_atim=st_atimespec", "-Dst_ctim=st_ctimespec"]
        host = cls.build_root / "posix_files.o"
        subprocess.run(base + flags + ["-Dposix_migrate_save_directory=real_migrate_save_directory",
                       "-Dwrite=migration_test_write", "-Dlinkat=migration_test_linkat", "-c",
                       str(ROOT / "port/linux/src/posix_files.c"), "-o", str(host)], check=True)
        for flavor in ("linux", "windows-selection"):
            binary = cls.build_root / flavor
            # _WIN32 affects only the extracted selection function here, after
            # host headers: the separate host object keeps its actual POSIX ABI.
            text = harness.read_text()
            if flavor == "windows-selection":
                variant = cls.build_root / "windows-selection.c"
                variant.write_text(text.replace("/* ROOT_FUNCTIONS */", ""))
                marker = "static BOOL directory_exists("
                variant.write_text(text[:text.index(marker)] + "#define _WIN32 1\n" + text[text.index(marker):])
            else:
                variant = harness
            subprocess.run(base + flags + [str(variant), str(host), "-o", str(binary)], check=True)
            cls.executables[flavor] = binary
        # Mobile/Apple guests must keep using their host-selected roots and
        # compile without a declaration or import of the desktop migrator.
        stubs = cls.build_root / "mobile-stubs.c"
        stubs.write_text('''
#include <string.h>
#include <sys/stat.h>
#include "posix.h"
int posix_stat(const char *path, struct posix_file_information *information) {
    struct stat value; if (stat(path, &value)) return -1;
    memset(information,0,sizeof(*information)); return 0;
}
int posix_make_directory(const char *path) { return mkdir(path,0700); }
''')
        for flavor, define in (("apple-guest", "HALO_MACOS"), ("android-guest", "HALO_ANDROID")):
            binary = cls.build_root / flavor
            subprocess.run(base + flags + ["-D" + define, str(harness), str(stubs), "-o", str(binary)], check=True)
            cls.executables[flavor] = binary

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name).resolve()
        self.environ = os.environ.copy()
        for key in ("HALO_SAVE_ROOT", "TEST_SAVE_CONFIG", "TEST_SAVE_FAIL_WRITE", "TEST_SAVE_RACE", "XDG_DATA_HOME", "APPDATA"):
            self.environ.pop(key, None)
        self.environ["HOME"] = str(self.folder / "home")

    def run_root(self, flavor=None, **environment):
        flavor = flavor or ("windows" if sys.platform == "win32" else "linux")
        result = subprocess.run([str(self.executables[flavor])], env={**self.environ, **environment},
                                capture_output=True, text=True, check=True, timeout=15)
        return Path(result.stdout.strip()), result.stderr

    def roots(self):
        if sys.platform == "win32":
            base = self.folder / "appdata"
            self.environ["APPDATA"] = str(base)
            return base / "halo", base / "Halo OG"
        base = self.folder / "xdg"
        self.environ["XDG_DATA_HOME"] = str(base)
        return base / "halo-linux", base / "halo-og"

    def test_nested_files_are_copied_old_and_existing_new_bytes_preserved(self):
        legacy, destination = self.roots()
        (legacy / "u/profiles").mkdir(parents=True)
        (legacy / "z/campaign").mkdir(parents=True)
        (legacy / "u/profiles/profile.bin").write_bytes(b"original profile")
        (legacy / "z/campaign/save.bin").write_bytes(b"saved progress" * 17000)
        (legacy / "zero.bin").touch()
        (destination / "u/profiles").mkdir(parents=True)
        (destination / "u/profiles/profile.bin").write_bytes(b"newer profile")
        root, log = self.run_root()
        self.assertEqual(root, destination)
        self.assertIn("migration_calls=1", log)
        self.assertEqual((legacy / "u/profiles/profile.bin").read_bytes(), b"original profile")
        self.assertEqual((destination / "u/profiles/profile.bin").read_bytes(), b"newer profile")
        self.assertEqual((destination / "z/campaign/save.bin").read_bytes(), (legacy / "z/campaign/save.bin").read_bytes())
        self.assertEqual((destination / "zero.bin").read_bytes(), b"")
        self.assertEqual(list(destination.rglob("*.partial")), [])
        again, _ = self.run_root()
        self.assertEqual(again, destination)

    def test_absent_legacy_uses_new_default_and_home_or_windows_selection(self):
        legacy, destination = self.roots()
        root, _ = self.run_root()
        self.assertEqual(root, destination)
        self.assertFalse(legacy.exists())
        self.assertTrue(destination.is_dir())
        if sys.platform != "win32":
            self.environ.pop("XDG_DATA_HOME")
            root, _ = self.run_root()
            self.assertEqual(root, Path(self.environ["HOME"]) / ".local/share/halo-og")
            base = self.folder / "windows appdata"
            (base / "halo/u").mkdir(parents=True)
            (base / "halo/u/profile.bin").write_bytes(b"old")
            root, _ = self.run_root("windows-selection", APPDATA=str(base))
            self.assertEqual(root, base / "Halo OG")
            self.assertEqual((root / "u/profile.bin").read_bytes(), b"old")

    def test_explicit_config_and_environment_roots_bypass_migration(self):
        self.roots()
        configured, override = self.folder / "chosen", self.folder / "override"
        root, log = self.run_root(TEST_SAVE_CONFIG=str(configured))
        self.assertEqual(root, configured)
        self.assertIn("migration_calls=0", log)
        root, log = self.run_root(TEST_SAVE_CONFIG=str(configured), HALO_SAVE_ROOT=str(override))
        self.assertEqual(root, override)
        self.assertIn("migration_calls=0", log)

    def test_case_insensitive_existing_destination_wins_without_duplicate_spelling(self):
        legacy, destination = self.roots()
        (legacy / "u/profiles").mkdir(parents=True)
        (legacy / "u/profiles/profile.bin").write_bytes(b"old")
        (destination / "U/Profiles").mkdir(parents=True)
        (destination / "U/Profiles/Profile.bin").write_bytes(b"new")
        root, _ = self.run_root()
        self.assertEqual(root, destination)
        self.assertEqual((destination / "U/Profiles/Profile.bin").read_bytes(), b"new")
        self.assertEqual(sorted(path.name for path in destination.iterdir()), ["U"])
        self.assertEqual(sorted(path.name for path in (destination / "U/Profiles").iterdir()), ["Profile.bin"])
        flavor = "windows" if sys.platform == "win32" else "linux"
        result = subprocess.run([str(self.executables[flavor]), "translate", r"u:\profiles\profile.bin"],
                                env=self.environ, capture_output=True, text=True, check=True)
        translated = Path(result.stdout.strip())
        self.assertTrue(translated.samefile(destination / "U/Profiles/Profile.bin"))
        self.assertEqual(translated.read_bytes(), b"new")

    def test_directory_file_conflict_keeps_legacy_and_logs_failure(self):
        legacy, destination = self.roots()
        (legacy / "u").mkdir(parents=True)
        (legacy / "u/profile.bin").write_bytes(b"old")
        destination.mkdir(parents=True)
        (destination / "u").write_bytes(b"existing new file")
        root, log = self.run_root()
        self.assertEqual(root, legacy)
        self.assertIn("keeping legacy saves", log)
        self.assertEqual((destination / "u").read_bytes(), b"existing new file")
        self.assertEqual((legacy / "u/profile.bin").read_bytes(), b"old")

    def test_missing_legacy_with_blocked_destination_reports_fallback(self):
        legacy, destination = self.roots()
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"existing file blocking canonical folder")
        root, log = self.run_root()
        self.assertEqual(root, legacy)
        self.assertIn("keeping legacy saves", log)
        self.assertEqual(destination.read_bytes(), b"existing file blocking canonical folder")

    def test_links_are_not_followed_and_source_bytes_survive(self):
        legacy, destination = self.roots()
        legacy.mkdir(parents=True)
        outside = self.folder / "outside"
        outside.mkdir()
        (outside / "private.bin").write_bytes(b"not a save")
        try:
            (legacy / "linked").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Windows runner does not allow creating test symlinks")
        root, log = self.run_root()
        self.assertEqual(root, legacy)
        self.assertIn("keeping legacy saves", log)
        self.assertFalse((destination / "linked").exists())
        self.assertEqual((outside / "private.bin").read_bytes(), b"not a save")
        (legacy / "linked").unlink()
        (legacy / "profile.bin").write_bytes(b"old")
        destination.mkdir(exist_ok=True)
        (destination / "profile.bin").symlink_to(outside / "private.bin")
        root, log = self.run_root()
        self.assertEqual(root, legacy)
        self.assertIn("keeping legacy saves", log)
        self.assertEqual((outside / "private.bin").read_bytes(), b"not a save")

    @unittest.skipIf(sys.platform == "win32", "POSIX special file and write-race fixture")
    def test_failed_write_cleans_owned_temp_and_racing_destination_wins(self):
        legacy, destination = self.roots()
        legacy.mkdir(parents=True)
        (legacy / "profile.bin").write_bytes(b"original profile")
        root, log = self.run_root(TEST_SAVE_FAIL_WRITE="1")
        self.assertEqual(root, legacy)
        self.assertIn("keeping legacy saves", log)
        self.assertFalse((destination / "profile.bin").exists())
        self.assertEqual(list(destination.glob("*.partial")), [])
        root, _ = self.run_root(TEST_SAVE_RACE="1")
        self.assertEqual(root, destination)
        self.assertEqual((destination / "profile.bin").read_bytes(), b"competing")
        self.assertEqual((legacy / "profile.bin").read_bytes(), b"original profile")
        self.assertEqual(list(destination.glob("*.partial")), [])

    @unittest.skipIf(sys.platform == "win32", "POSIX FIFO test")
    def test_special_file_refuses_migration_without_hanging(self):
        legacy, _ = self.roots()
        legacy.mkdir(parents=True)
        os.mkfifo(legacy / "pipe")
        root, log = self.run_root()
        self.assertEqual(root, legacy)
        self.assertIn("keeping legacy saves", log)

    def test_configuration_still_reads_beside_executable(self):
        base = str(self.folder / "portable") + os.sep
        (self.folder / "portable").mkdir()
        (self.folder / "portable/config.toml").write_text("[paths]\nsaves = 'chosen'\n")
        flavor = "windows" if sys.platform == "win32" else "linux"
        result = subprocess.run([str(self.executables[flavor]), "config"],
                                env={**self.environ, "TEST_CONFIG_BASE": base, "HALO_SAVE_ROOT": str(self.folder / "custom")},
                                capture_output=True, text=True, check=True)
        self.assertEqual(Path(result.stdout.strip()), self.folder / "portable/config.toml")

    @unittest.skipIf(sys.platform == "win32", "Apple/Android guest preprocessor probe")
    def test_mobile_host_selected_roots_have_no_desktop_migration_import(self):
        for flavor in ("apple-guest", "android-guest"):
            with self.subTest(flavor=flavor):
                expected = self.folder / flavor
                root, log = self.run_root(flavor, HALO_SAVE_ROOT=str(expected))
                self.assertEqual(root, expected)
                self.assertIn("migration_calls=0", log)

    def test_direct_overlapping_tree_is_refused_without_creating_new_folders(self):
        legacy, _ = self.roots()
        legacy.mkdir(parents=True)
        flavor = "windows" if sys.platform == "win32" else "linux"
        result = subprocess.run([str(self.executables[flavor]), "migrate", str(legacy), str(legacy / "nested")],
                                capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), "-1")
        self.assertEqual(list(legacy.iterdir()), [])


class GuestImportMigrationTests(unittest.TestCase):
    def test_desktop_migrator_never_enters_android_apple_guest_abi_or_host_table(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            header = (ROOT / "port/linux/src/posix.h").read_text()
            baseline_header = folder / "without-desktop.h"
            baseline_header.write_text(header.replace("int posix_migrate_save_directory(const char *legacy, const char *destination);", ""))
            results = []
            for selected in (ROOT / "port/linux/src/posix.h", baseline_header):
                wrappers, imports = folder / (selected.stem + ".c"), folder / (selected.stem + ".list")
                subprocess.run([sys.executable, str(ROOT / "tools/android_posix_stubs.py"),
                                str(selected), str(wrappers), str(imports)], check=True)
                text, names = wrappers.read_text(), imports.read_text()
                self.assertNotIn("migrate_save_directory", text)
                self.assertNotIn("migrate_save_directory", names)
                self.assertIn("hostposix_stat", names)
                self.assertIn("hostposix_make_directory", names)
                results.append((text, names))
            self.assertEqual(results[0], results[1])
            # Exercise the next actual build stage, which previously emitted an
            # unavailable _posix_migrate_save_directory into Apple's host table.
            for ios in (False, True):
                table, assembly = folder / ("ios-table.c" if ios else "host-table.c"), folder / "imports.s"
                command = [sys.executable, str(ROOT / "tools/android_imports.py")]
                if ios:
                    command.append("--ios")
                subprocess.run(command + ["--host-table", str(table), str(assembly),
                                str(folder / "posix.list")], check=True)
                self.assertNotIn("migrate_save_directory", table.read_text())
                self.assertNotIn("migrate_save_directory", assembly.read_text())
                self.assertIn("posix_stat", table.read_text())


if __name__ == "__main__":
    unittest.main()
