#import <Foundation/Foundation.h>
#import "HaloPreferences.h"
#include <assert.h>
#include <sys/stat.h>

static unsigned progressCalls;
static void progress(void *context, const char *name, unsigned long long done, unsigned long long total) {
    (void)context;
    assert(name && done <= total);
    progressCalls++;
}

static void writeFixture(NSData *bytes, NSURL *file) {
    assert([NSFileManager.defaultManager createDirectoryAtURL:file.URLByDeletingLastPathComponent
        withIntermediateDirectories:YES attributes:nil error:nil]);
    assert([bytes writeToURL:file atomically:YES]);
}
static NSDictionary *snapshot(NSURL *root) {
    NSMutableDictionary *result = [NSMutableDictionary dictionary];
    NSDirectoryEnumerator<NSURL *> *walk = [NSFileManager.defaultManager enumeratorAtURL:root
        includingPropertiesForKeys:nil options:0 errorHandler:nil];
    for (NSURL *file in walk) {
        struct stat info;
        assert(!lstat(file.fileSystemRepresentation, &info));
        NSString *relative = [file.path substringFromIndex:root.path.length + 1];
        if (S_ISREG(info.st_mode)) result[relative] = [NSData dataWithContentsOfURL:file];
        else if (S_ISLNK(info.st_mode)) {
            result[relative] = [@"link:" stringByAppendingString:[NSFileManager.defaultManager destinationOfSymbolicLinkAtPath:file.path error:nil]];
            [walk skipDescendants];
        }
    }
    return result;
}
static void migrationFixtures(NSURL *test, NSURL *valid, NSURL *image) {
    NSURL *legacy = [test URLByAppendingPathComponent:@"migration/legacy"], *destination = [test URLByAppendingPathComponent:@"migration/Halo OG"];
    NSURL *oldImport = [legacy URLByAppendingPathComponent:@"Game Data/import-a"];
    assert([NSFileManager.defaultManager createDirectoryAtURL:oldImport.URLByDeletingLastPathComponent withIntermediateDirectories:YES attributes:nil error:nil]);
    assert([NSFileManager.defaultManager copyItemAtURL:valid toURL:oldImport error:nil]);
    NSURL *oldImage = [legacy URLByAppendingPathComponent:@"Images/local.iso"];
    writeFixture([NSData dataWithContentsOfURL:image], oldImage);
    NSData *controls = [@"legacy controls" dataUsingEncoding:NSUTF8StringEncoding];
    writeFixture(controls, [legacy URLByAppendingPathComponent:@"config.toml"]);
    writeFixture([@"save bytes" dataUsingEncoding:NSUTF8StringEncoding], [legacy URLByAppendingPathComponent:@"profiles/player/save.bin"]);
    writeFixture([NSData dataWithContentsOfURL:[valid URLByAppendingPathComponent:@"maps/ui.map"]], [legacy URLByAppendingPathComponent:@"Community Maps/maps/fixture.map"]);
    NSURL *externalLink = [legacy URLByAppendingPathComponent:@"external-maps"];
    assert([NSFileManager.defaultManager createSymbolicLinkAtURL:externalLink withDestinationURL:valid error:nil]);
    NSURL *relativeLink = [legacy URLByAppendingPathComponent:@"relative-import"];
    assert([NSFileManager.defaultManager createSymbolicLinkAtPath:relativeLink.path withDestinationPath:@"Game Data/import-a" error:nil]);
    NSDictionary *oldSettings = @{@"data_path":oldImport.path, @"iso_path":oldImage.path, @"windowed":@YES, @"community_downloads":@YES, @"future_key":@"kept"};
    writeFixture([NSJSONSerialization dataWithJSONObject:oldSettings options:0 error:nil], [legacy URLByAppendingPathComponent:@"macos-settings.json"]);
    NSDictionary *original = snapshot(legacy);
    NSError *error = nil;
    unsigned beforeProgress = progressCalls;
    assert(HaloMigrateLegacySupportDirectory(legacy, destination, progress, NULL, &error));
    assert(!error && progressCalls > beforeProgress);
    assert([snapshot(legacy) isEqual:original]);
    HaloPreferences *migrated = [[HaloPreferences alloc] initWithSupportDirectory:destination];
    assert([migrated.dataPath isEqual:[destination URLByAppendingPathComponent:@"Game Data/import-a"].path]);
    assert([migrated.isoPath isEqual:[destination URLByAppendingPathComponent:@"Images/local.iso"].path]);
    assert(migrated.windowed && migrated.communityDownloadsEnabled);
    assert([[NSData dataWithContentsOfURL:[destination URLByAppendingPathComponent:@"config.toml"]] isEqual:controls]);
    assert([[NSFileManager.defaultManager destinationOfSymbolicLinkAtPath:[destination URLByAppendingPathComponent:@"external-maps"].path error:nil] isEqual:valid.path]);
    assert([[NSFileManager.defaultManager destinationOfSymbolicLinkAtPath:[destination URLByAppendingPathComponent:@"relative-import"].path error:nil] isEqual:@"Game Data/import-a"]);
    NSDictionary *record = [NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfURL:[destination URLByAppendingPathComponent:@"legacy-migration.json"]] options:0 error:nil];
    assert([record[@"completed"] boolValue] && [record[@"legacy_preserved"] boolValue]);
    assert([record[@"settings_rewrites"] count] == 2);
    NSDictionary *newSnapshot = snapshot(destination);
    assert(HaloMigrateLegacySupportDirectory(legacy, destination, NULL, NULL, &error));
    assert([snapshot(destination) isEqual:newSnapshot] && [snapshot(legacy) isEqual:original]);

    /* A conflicting map cannot redirect the copied selection to mixed bytes. */
    NSURL *conflicting = [test URLByAppendingPathComponent:@"migration/conflicts"];
    NSData *newMap = [@"existing user map" dataUsingEncoding:NSUTF8StringEncoding];
    NSURL *collision = [conflicting URLByAppendingPathComponent:@"Game Data/import-a/maps/ui.map"];
    writeFixture(newMap, collision);
    assert(HaloMigrateLegacySupportDirectory(legacy, conflicting, NULL, NULL, &error));
    assert([[NSData dataWithContentsOfURL:collision] isEqual:newMap]);
    assert([[[HaloPreferences alloc] initWithSupportDirectory:conflicting].dataPath isEqual:oldImport.path]);
    assert([snapshot(legacy) isEqual:original]);

    /* Newer destination preferences/controls win; external selections remain. */
    NSURL *existing = [test URLByAppendingPathComponent:@"migration/existing"];
    NSData *newSettings = [NSJSONSerialization dataWithJSONObject:@{@"data_path":valid.path, @"windowed":@NO} options:0 error:nil];
    writeFixture(newSettings, [existing URLByAppendingPathComponent:@"macos-settings.json"]);
    NSData *newControls = [@"new controls" dataUsingEncoding:NSUTF8StringEncoding];
    writeFixture(newControls, [existing URLByAppendingPathComponent:@"config.toml"]);
    assert(HaloMigrateLegacySupportDirectory(legacy, existing, NULL, NULL, &error));
    assert([[NSData dataWithContentsOfURL:[existing URLByAppendingPathComponent:@"macos-settings.json"]] isEqual:newSettings]);
    assert([[NSData dataWithContentsOfURL:[existing URLByAppendingPathComponent:@"config.toml"]] isEqual:newControls]);
    assert([[[HaloPreferences alloc] initWithSupportDirectory:existing].dataPath isEqual:valid.path]);

    NSURL *externalLegacy = [test URLByAppendingPathComponent:@"migration/external-legacy"];
    NSData *externalSettings = [NSJSONSerialization dataWithJSONObject:@{@"data_path":valid.path, @"iso_path":image.path} options:0 error:nil];
    writeFixture(externalSettings, [externalLegacy URLByAppendingPathComponent:@"macos-settings.json"]);
    NSURL *externalDestination = [test URLByAppendingPathComponent:@"migration/external-new"];
    assert(HaloMigrateLegacySupportDirectory(externalLegacy, externalDestination, NULL, NULL, &error));
    HaloPreferences *externalPreferences = [[HaloPreferences alloc] initWithSupportDirectory:externalDestination];
    assert([externalPreferences.dataPath isEqual:valid.path] && [externalPreferences.isoPath isEqual:image.path]);

    /* Never traverse a destination link to overwrite external files. */
    NSURL *linkedDestination = [test URLByAppendingPathComponent:@"migration/linked-new"];
    assert([NSFileManager.defaultManager createDirectoryAtURL:linkedDestination withIntermediateDirectories:YES attributes:nil error:nil]);
    assert([NSFileManager.defaultManager createSymbolicLinkAtURL:[linkedDestination URLByAppendingPathComponent:@"Game Data"] withDestinationURL:valid error:nil]);
    NSDictionary *externalBefore = snapshot(valid);
    assert(HaloMigrateLegacySupportDirectory(legacy, linkedDestination, NULL, NULL, &error));
    assert([snapshot(valid) isEqual:externalBefore]);
    assert([[[HaloPreferences alloc] initWithSupportDirectory:linkedDestination].dataPath isEqual:oldImport.path]);

    /* Failure leaves settings unpublished; a corrected source retries safely. */
    NSURL *brokenLegacy = [test URLByAppendingPathComponent:@"migration/invalid-legacy"], *retry = [test URLByAppendingPathComponent:@"migration/retry"];
    writeFixture([@"{broken json" dataUsingEncoding:NSUTF8StringEncoding], [brokenLegacy URLByAppendingPathComponent:@"macos-settings.json"]);
    writeFixture(controls, [brokenLegacy URLByAppendingPathComponent:@"config.toml"]);
    assert(!HaloMigrateLegacySupportDirectory(brokenLegacy, retry, NULL, NULL, &error));
    assert(error.localizedDescription.length);
    assert(![NSFileManager.defaultManager fileExistsAtPath:[retry URLByAppendingPathComponent:@"macos-settings.json"].path]);
    assert(![NSFileManager.defaultManager fileExistsAtPath:[retry URLByAppendingPathComponent:@"legacy-migration.json"].path]);
    assert([[NSData dataWithContentsOfURL:[retry URLByAppendingPathComponent:@"config.toml"]] isEqual:controls]);
    writeFixture(externalSettings, [brokenLegacy URLByAppendingPathComponent:@"macos-settings.json"]);
    assert(HaloMigrateLegacySupportDirectory(brokenLegacy, retry, NULL, NULL, &error));
    for (NSURL *file in [NSFileManager.defaultManager contentsOfDirectoryAtURL:retry includingPropertiesForKeys:nil options:0 error:nil])
        assert(![file.lastPathComponent hasPrefix:@".migration-"]);
    NSURL *invalidExisting = [test URLByAppendingPathComponent:@"migration/invalid-existing"];
    NSData *invalidSettings = [@"{invalid existing" dataUsingEncoding:NSUTF8StringEncoding];
    writeFixture(invalidSettings, [invalidExisting URLByAppendingPathComponent:@"macos-settings.json"]);
    assert(!HaloMigrateLegacySupportDirectory(legacy, invalidExisting, NULL, NULL, &error));
    assert([[NSData dataWithContentsOfURL:[invalidExisting URLByAppendingPathComponent:@"macos-settings.json"]] isEqual:invalidSettings]);
    assert(![NSFileManager.defaultManager fileExistsAtPath:[invalidExisting URLByAppendingPathComponent:@"legacy-migration.json"].path]);
    assert(!HaloSupportDirectoryNeedsMigration(test));
    const char *previousOverride = getenv("HALO_SAVE_ROOT");
    NSString *savedOverride = previousOverride ? @(previousOverride) : nil;
    setenv("HALO_SAVE_ROOT", test.fileSystemRepresentation, 1);
    NSURL *canonical = [NSURL fileURLWithPath:[NSHomeDirectory() stringByAppendingPathComponent:@"Library/Application Support/Halo OG"] isDirectory:YES];
    assert(!HaloSupportDirectoryNeedsMigration(canonical));
    if (savedOverride) setenv("HALO_SAVE_ROOT", savedOverride.UTF8String, 1);
    else unsetenv("HALO_SAVE_ROOT");
    puts("Legacy support migration: hashes/bytes, managed path rewrites, links, conflicts, external selections, existing settings, failure/retry and original preservation passed");
}

int main(int argc, const char **argv) {
    @autoreleasepool {
        assert(argc >= 2);
        NSURL *test = [NSURL fileURLWithPath:@(argv[1]) isDirectory:YES];
        NSURL *valid = [test URLByAppendingPathComponent:@"valid"];
        NSURL *support = [test URLByAppendingPathComponent:@"support"];
        NSError *error = nil;
        assert([HaloValidateGameData(valid, &error).path isEqualToString:valid.path]);
        assert([HaloValidateGameData([valid URLByAppendingPathComponent:@"maps"], &error).path isEqualToString:valid.path]);
        for (NSString *name in @[@"pc", @"mixed", @"missing", @"truncated"]) {
            error = nil;
            assert(!HaloValidateGameData([test URLByAppendingPathComponent:name], &error));
            assert(error.localizedDescription.length);
        }
        error = nil;
        assert([HaloValidateGameData([test URLByAppendingPathComponent:@"withcustom"], &error).path
            isEqualToString:[test URLByAppendingPathComponent:@"withcustom"].path]);
        if (argc == 3) assert(HaloValidateGameData([NSURL fileURLWithPath:@(argv[2])], &error));
        HaloPreferences *preferences = [[HaloPreferences alloc] initWithSupportDirectory:support];
        assert([preferences selectDataRoot:valid iso:nil error:&error]);
        NSURL *settings = [support URLByAppendingPathComponent:@"macos-settings.json"];
        NSMutableDictionary *saved = [[NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfURL:settings]
            options:0 error:nil] mutableCopy];
        saved[@"future_setting"] = @"preserve me";
        assert([[NSJSONSerialization dataWithJSONObject:saved options:0 error:nil] writeToURL:settings atomically:YES]);
        NSURL *controls = [support URLByAppendingPathComponent:@"config.toml"];
        assert([@"[bindings]\nx = \"E\"\n" writeToURL:controls atomically:YES encoding:NSUTF8StringEncoding error:&error]);
        preferences = [[HaloPreferences alloc] initWithSupportDirectory:support];
        assert([preferences setWindowed:YES error:&error]);
        assert(!preferences.communityDownloadsEnabled);
        assert([preferences setCommunityDownloadsEnabled:YES error:&error]);
        assert([[HaloPreferences alloc] initWithSupportDirectory:support].communityDownloadsEnabled);
        assert([preferences setCommunityDownloadsEnabled:NO error:&error]);
        assert(![[HaloPreferences alloc] initWithSupportDirectory:support].communityDownloadsEnabled);
        NSData *before = [NSData dataWithContentsOfURL:settings];
        assert(![preferences selectDataRoot:[test URLByAppendingPathComponent:@"pc"] iso:nil error:&error]);
        assert([[NSData dataWithContentsOfURL:settings] isEqualToData:before]);
        assert([preferences.dataPath isEqualToString:valid.path]);
        assert(HaloGameDataCopySize(valid, &error) == 4096);
        NSURL *copied = HaloCopyGameData(valid, support, NULL, NULL, &error);
        assert(copied && ![copied.path isEqual:valid.path]);
        assert([[NSData dataWithContentsOfURL:[copied URLByAppendingPathComponent:@"maps/ui.map"]]
            isEqual:[NSData dataWithContentsOfURL:[valid URLByAppendingPathComponent:@"maps/ui.map"]]]);
        assert([preferences.dataPath isEqual:valid.path]);
        assert([NSFileManager.defaultManager fileExistsAtPath:[valid URLByAppendingPathComponent:@"maps/a10.map"].path]);
        NSData *unchanged = [NSData dataWithContentsOfURL:settings];
        assert(!HaloCopyGameData([test URLByAppendingPathComponent:@"pc"], support, NULL, NULL, &error));
        assert([[NSData dataWithContentsOfURL:settings] isEqual:unchanged]);
        NSURL *uppercase = [test URLByAppendingPathComponent:@"upper/MAPS"];
        assert([NSFileManager.defaultManager createDirectoryAtURL:uppercase withIntermediateDirectories:YES attributes:nil error:nil]);
        for (NSString *name in @[@"ui", @"a10"]) {
            NSData *bytes = [NSData dataWithContentsOfURL:[valid URLByAppendingPathComponent:[NSString stringWithFormat:@"maps/%@.map", name]]];
            assert([bytes writeToURL:[uppercase URLByAppendingPathComponent:[name.uppercaseString stringByAppendingString:@".MAP"]] atomically:YES]);
        }
        assert(HaloGameDataCopySize(uppercase, &error) == 4096);
        assert(HaloCopyGameData(uppercase, support, NULL, NULL, &error));
        NSURL *linkedRoot = [test URLByAppendingPathComponent:@"linked/maps"];
        assert([NSFileManager.defaultManager createDirectoryAtURL:linkedRoot withIntermediateDirectories:YES attributes:nil error:nil]);
        for (NSString *name in @[@"ui", @"a10"]) {
            assert(([NSFileManager.defaultManager createSymbolicLinkAtURL:[linkedRoot URLByAppendingPathComponent:[name stringByAppendingPathExtension:@"map"]]
                withDestinationURL:[valid URLByAppendingPathComponent:[NSString stringWithFormat:@"maps/%@.map", name]] error:nil]));
        }
        assert(HaloValidateGameData(linkedRoot, &error));
        assert(!HaloCopyGameData(linkedRoot, support, NULL, NULL, &error));
        assert([[NSData dataWithContentsOfURL:settings] isEqual:unchanged]);
        NSURL *image = [test URLByAppendingPathComponent:@"disc.iso"];
        NSURL *imported = HaloImportDiscImage(image, support, progress, NULL, &error);
        assert(imported && progressCalls == 2);
        assert([preferences.dataPath isEqualToString:valid.path]);
        assert([[NSData dataWithContentsOfURL:[imported URLByAppendingPathComponent:@"maps/ui.map"]]
            isEqualToData:[NSData dataWithContentsOfURL:[valid URLByAppendingPathComponent:@"maps/ui.map"]]]);
        assert([preferences selectDataRoot:imported iso:image error:&error]);
        before = [NSData dataWithContentsOfURL:settings];
        NSURL *imports = [support URLByAppendingPathComponent:@"Game Data"];
        NSUInteger count = [NSFileManager.defaultManager contentsOfDirectoryAtURL:imports
            includingPropertiesForKeys:nil options:0 error:nil].count;
        for (NSString *name in @[@"broken.iso", @"pc.iso"]) {
            assert(!HaloImportDiscImage([test URLByAppendingPathComponent:name], support, NULL, NULL, &error));
            assert([NSFileManager.defaultManager contentsOfDirectoryAtURL:imports
                includingPropertiesForKeys:nil options:0 error:nil].count == count);
            assert([[NSData dataWithContentsOfURL:settings] isEqualToData:before]);
        }
        preferences = [[HaloPreferences alloc] initWithSupportDirectory:support];
        assert(preferences.windowed && [preferences.isoPath isEqualToString:image.path]);
        assert([preferences.dataPath isEqualToString:imported.path]);
        saved = [NSJSONSerialization JSONObjectWithData:before options:0 error:nil];
        assert([saved[@"future_setting"] isEqualToString:@"preserve me"]);
        assert([[NSString stringWithContentsOfURL:controls encoding:NSUTF8StringEncoding error:nil]
            isEqualToString:@"[bindings]\nx = \"E\"\n"]);
        NSURL *blocked = [test URLByAppendingPathComponent:@"not-a-directory"];
        assert([@"file" writeToURL:blocked atomically:YES encoding:NSUTF8StringEncoding error:&error]);
        HaloPreferences *unwritable = [[HaloPreferences alloc] initWithSupportDirectory:blocked];
        assert(![unwritable selectDataRoot:valid iso:nil error:&error]);
        assert(!unwritable.dataPath);
        NSString *key = [[NSMutableData dataWithLength:32] base64EncodedStringWithOptions:0];
        assert(HaloUpdateConfigurationIsValid(@{@"SUFeedURL":@"https://example.com/appcast.xml", @"SUPublicEDKey":key}));
        for (NSString *url in @[@"http://example.com/feed.xml", @"https://user:pass@example.com/feed.xml", @"file:///feed.xml"])
            assert(!HaloUpdateConfigurationIsValid(@{@"SUFeedURL":url, @"SUPublicEDKey":key}));
        assert(!HaloUpdateConfigurationIsValid(@{}));
        assert(!HaloUpdateConfigurationIsValid(@{@"SUFeedURL":@"https://example.com/feed.xml", @"SUPublicEDKey":@"invalid"}));
        migrationFixtures(test, valid, image);
        puts("Map validation, XISO import, failed-import rollback, persistent preferences and update configuration passed");
    }
    return 0;
}
