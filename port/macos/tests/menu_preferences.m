#import <Foundation/Foundation.h>
#import "HaloPreferences.h"
#include <assert.h>

static unsigned progressCalls;
static void progress(void *context, const char *name, unsigned long long done, unsigned long long total) {
    (void)context;
    assert(name && done <= total);
    progressCalls++;
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
        puts("Map validation, XISO import, failed-import rollback, persistent preferences and update configuration passed");
    }
    return 0;
}
