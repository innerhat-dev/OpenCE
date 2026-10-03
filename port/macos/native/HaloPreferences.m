#import "HaloPreferences.h"
#include "xiso.h"
#include <string.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#include <CommonCrypto/CommonDigest.h>

static NSError *failure(NSString *message) {
    return [NSError errorWithDomain:@"HaloGameData" code:1
                          userInfo:@{NSLocalizedDescriptionKey: message}];
}

@implementation HaloPreferences {
    NSMutableDictionary *_settings;
}
- (instancetype)initWithSupportDirectory:(NSURL *)directory {
    if ((self = [super init])) {
        _supportDirectory = directory;
        NSData *data = [NSData dataWithContentsOfURL:[directory URLByAppendingPathComponent:@"macos-settings.json"]];
        id decoded = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
        _settings = [decoded isKindOfClass:NSDictionary.class] ? [decoded mutableCopy] : [NSMutableDictionary dictionary];
    }
    return self;
}
- (NSString *)dataPath { return [_settings[@"data_path"] isKindOfClass:NSString.class] ? _settings[@"data_path"] : nil; }
- (NSString *)isoPath { return [_settings[@"iso_path"] isKindOfClass:NSString.class] ? _settings[@"iso_path"] : nil; }
- (BOOL)windowed { return [_settings[@"windowed"] isKindOfClass:NSNumber.class] && [_settings[@"windowed"] boolValue]; }
- (BOOL)communityDownloadsEnabled {
    return [_settings[@"community_downloads"] isKindOfClass:NSNumber.class] && [_settings[@"community_downloads"] boolValue];
}
- (BOOL)save:(NSMutableDictionary *)settings error:(NSError **)error {
    NSData *data = [NSJSONSerialization dataWithJSONObject:settings options:NSJSONWritingPrettyPrinted error:error];
    if (!data || ![NSFileManager.defaultManager createDirectoryAtURL:_supportDirectory
                                       withIntermediateDirectories:YES attributes:nil error:error]) return NO;
    if (![data writeToURL:[_supportDirectory URLByAppendingPathComponent:@"macos-settings.json"]
                 options:NSDataWritingAtomic error:error]) return NO;
    _settings = settings;
    return YES;
}
- (BOOL)selectDataRoot:(NSURL *)root iso:(NSURL *)iso error:(NSError **)error {
    NSURL *validated = HaloValidateGameData(root, error);
    if (!validated) return NO;
    NSMutableDictionary *settings = [_settings mutableCopy];
    settings[@"data_path"] = validated.path;
    if (iso) settings[@"iso_path"] = iso.path;
    else [settings removeObjectForKey:@"iso_path"];
    return [self save:settings error:error];
}
- (BOOL)setWindowed:(BOOL)windowed error:(NSError **)error {
    NSMutableDictionary *settings = [_settings mutableCopy];
    settings[@"windowed"] = @(windowed);
    return [self save:settings error:error];
}
- (BOOL)setCommunityDownloadsEnabled:(BOOL)enabled error:(NSError **)error {
    NSMutableDictionary *settings = [_settings mutableCopy];
    settings[@"community_downloads"] = @(enabled);
    return [self save:settings error:error];
}
@end

static NSDictionary<NSString *, NSURL *> *entries(NSURL *directory, NSError **error) {
    NSArray<NSURL *> *files = [NSFileManager.defaultManager contentsOfDirectoryAtURL:directory
                          includingPropertiesForKeys:@[NSURLIsRegularFileKey] options:0 error:error];
    if (!files) return nil;
    NSMutableDictionary *result = [NSMutableDictionary dictionary];
    for (NSURL *file in files) {
        NSString *name = file.lastPathComponent.lowercaseString;
        if (result[name]) {
            if (error) *error = failure(@"This folder contains duplicate names with different capitalization.");
            return nil;
        }
        result[name] = file;
    }
    return result;
}

NSURL *HaloValidateGameData(NSURL *selection, NSError **error) {
    NSURL *root = selection.URLByStandardizingPath.URLByResolvingSymlinksInPath;
    NSURL *maps;
    if ([root.lastPathComponent.lowercaseString isEqualToString:@"maps"]) {
        maps = root;
        root = root.URLByDeletingLastPathComponent;
    } else {
        maps = entries(root, error)[@"maps"];
    }
    if (!maps) {
        if (error) *error = failure(@"Choose an extracted Xbox Halo game folder containing maps, or the maps folder itself.");
        return nil;
    }
    NSDictionary<NSString *, NSURL *> *files = entries(maps, error);
    if (!files) return nil;
    NSString *discBuild = nil;
    BOOL hasUI = NO, hasOpeningLevel = NO;
    for (NSString *name in files) {
        if (![name.pathExtension isEqualToString:@"map"]) continue;
        NSURL *file = files[name];
        NSFileHandle *handle = [NSFileHandle fileHandleForReadingFromURL:file error:error];
        if (!handle) return nil;
        NSData *header = [handle readDataUpToLength:2048 error:error];
        [handle closeFile];
        if (!header) return nil;
        const unsigned char *bytes = header.bytes;
        BOOL valid = header.length == 2048 && !memcmp(bytes, "daeh", 4) && !memcmp(bytes + 2044, "toof", 4);
        uint32_t version = 0, length = 0;
        NSString *cacheName = nil, *build = nil;
        if (valid) {
            memcpy(&version, bytes + 4, 4);
            memcpy(&length, bytes + 8, 4);
            const unsigned char *nameEnd = memchr(bytes + 32, 0, 32), *buildEnd = memchr(bytes + 64, 0, 32);
            if (nameEnd && buildEnd) {
                cacheName = [[NSString alloc] initWithBytes:bytes + 32 length:nameEnd - bytes - 32 encoding:NSASCIIStringEncoding];
                build = [[NSString alloc] initWithBytes:bytes + 64 length:buildEnd - bytes - 64 encoding:NSASCIIStringEncoding];
            }
            valid = version == 5 && length >= 2048 && length <= 0x11600000 &&
                [cacheName.lowercaseString isEqualToString:name.stringByDeletingPathExtension] &&
                ([@"01.01.14.2342" isEqualToString:build] || [@"01.10.12.2276" isEqualToString:build]);
        }
        if (!valid) {
            if (error) *error = failure([NSString stringWithFormat:@"%@ is not a supported original Xbox Halo map. PC, Custom Edition, Anniversary and MCC maps cannot be used.", file.lastPathComponent]);
            return nil;
        }
        if (discBuild && ![discBuild isEqualToString:build]) {
            if (error) *error = failure(@"The maps mix different Xbox releases. Choose one complete set from one disc.");
            return nil;
        }
        discBuild = build;
        hasUI |= [name isEqualToString:@"ui.map"];
        hasOpeningLevel |= [name isEqualToString:@"a10.map"];
    }
    if (!hasUI || !hasOpeningLevel) {
        if (error) *error = failure(@"This folder needs ui.map and a10.map from the same Xbox Halo disc. Use a complete maps folder.");
        return nil;
    }
    return root;
}

NSURL *HaloImportDiscImage(NSURL *image, NSURL *supportDirectory,
                          xiso_progress_proc progress, void *context, NSError **error) {
    /* A new directory for every import. Failed imports never replace working data. */
    NSURL *destination = [[supportDirectory URLByAppendingPathComponent:@"Game Data" isDirectory:YES]
                          URLByAppendingPathComponent:NSUUID.UUID.UUIDString isDirectory:YES];
    if (![NSFileManager.defaultManager createDirectoryAtURL:destination withIntermediateDirectories:YES
                                                attributes:nil error:error]) return nil;
    char detail[512] = {0};
    BOOL extracted = xiso_extract_maps(image.fileSystemRepresentation, destination.fileSystemRepresentation,
                                      progress, context, detail, sizeof(detail));
    NSURL *validated = extracted ? HaloValidateGameData(destination, error) : nil;
    if (!validated) {
        [NSFileManager.defaultManager removeItemAtURL:destination error:nil];
        if (!extracted && error) *error = failure([NSString stringWithUTF8String:detail] ?: @"The disc image could not be read.");
    }
    return validated;
}

/* Copy only regular map files in the known game-data directories. External
   folder mode remains available for deliberate symlink-based developer data. */
static NSArray<NSURL *> *copySources(NSURL *selection, NSError **error) {
    NSURL *root = HaloValidateGameData(selection, error);
    if (!root) return nil;
    NSMutableArray *sources = [NSMutableArray array];
    NSDictionary<NSString *, NSURL *> *directories = entries(root, error);
    if (!directories) return nil;
    for (NSString *name in @[@"maps", @"maps_de", @"maps_fr", @"maps_es", @"maps_it"]) {
        NSURL *directory = directories[name];
        if (!directory) continue;
        struct stat info;
        if (lstat(directory.fileSystemRepresentation, &info)) continue;
        if (!S_ISDIR(info.st_mode)) {
            if (error) *error = failure(@"Managed copying needs real maps directories. Use This Folder for linked developer data.");
            return nil;
        }
        NSDictionary *files = entries(directory, error);
        if (!files) return nil;
        for (NSString *fileName in [[files allKeys] sortedArrayUsingSelector:@selector(compare:)]) {
            if (![fileName.pathExtension isEqualToString:@"map"]) continue;
            NSURL *file = files[fileName];
            if (lstat(file.fileSystemRepresentation, &info) || !S_ISREG(info.st_mode)) {
                if (error) *error = failure(@"Managed copying needs regular map files. Use This Folder to keep your linked data in place.");
                return nil;
            }
            [sources addObject:file];
        }
    }
    return sources;
}

unsigned long long HaloGameDataCopySize(NSURL *root, NSError **error) {
    NSArray<NSURL *> *sources = copySources(root, error);
    unsigned long long size = 0;
    for (NSURL *source in sources) {
        struct stat info;
        if (lstat(source.fileSystemRepresentation, &info) || !S_ISREG(info.st_mode) || info.st_size < 0) {
            if (error) *error = failure(@"A source map changed. Choose the folder again.");
            return 0;
        }
        size += (unsigned long long)info.st_size;
    }
    return size;
}

static NSString *copyHash(CC_SHA256_CTX *context) {
    unsigned char digest[CC_SHA256_DIGEST_LENGTH];
    CC_SHA256_Final(digest, context);
    NSMutableString *result = [NSMutableString string];
    for (unsigned i = 0; i < sizeof(digest); i++) [result appendFormat:@"%02x", digest[i]];
    return result;
}
static NSString *copiedFileHash(NSURL *file) {
    int descriptor = open(file.fileSystemRepresentation, O_RDONLY | O_NOFOLLOW);
    if (descriptor < 0) return nil;
    CC_SHA256_CTX context; CC_SHA256_Init(&context);
    unsigned char bytes[65536]; ssize_t count;
    while ((count = read(descriptor, bytes, sizeof(bytes))) > 0) CC_SHA256_Update(&context, bytes, (CC_LONG)count);
    close(descriptor);
    return count == 0 ? copyHash(&context) : nil;
}

NSURL *HaloCopyGameData(NSURL *selection, NSURL *supportDirectory, xiso_progress_proc progress,
                       void *context, NSError **error) {
    NSURL *root = HaloValidateGameData(selection, error);
    NSArray<NSURL *> *sources = root ? copySources(root, error) : nil;
    if (!sources) return nil;
    unsigned long long total = HaloGameDataCopySize(root, error), done = 0;
    if (!total) return nil;
    NSURL *destination = [[supportDirectory URLByAppendingPathComponent:@"Game Data" isDirectory:YES]
                          URLByAppendingPathComponent:NSUUID.UUID.UUIDString isDirectory:YES];
    BOOL success = [NSFileManager.defaultManager createDirectoryAtURL:destination
        withIntermediateDirectories:YES attributes:nil error:error];
    NSMutableArray *records = [NSMutableArray array];
    for (NSURL *source in sources) {
        if (!success) break;
        NSURL *folder = [destination URLByAppendingPathComponent:source.URLByDeletingLastPathComponent.lastPathComponent isDirectory:YES];
        success = [NSFileManager.defaultManager createDirectoryAtURL:folder withIntermediateDirectories:YES attributes:nil error:error];
        NSURL *target = [folder URLByAppendingPathComponent:source.lastPathComponent];
        int input = success ? open(source.fileSystemRepresentation, O_RDONLY | O_NOFOLLOW) : -1;
        struct stat before, after;
        int output = -1;
        success = input >= 0 && !fstat(input, &before) && S_ISREG(before.st_mode);
        if (success) output = open(target.fileSystemRepresentation, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0600);
        success = success && output >= 0;
        char bytes[65536];
        ssize_t amount;
        unsigned long long copied = 0;
        CC_SHA256_CTX sourceHash; CC_SHA256_Init(&sourceHash);
        while (success && (amount = read(input, bytes, sizeof(bytes))) > 0) {
            if ((unsigned long long)amount > (unsigned long long)before.st_size - copied) { success = NO; break; }
            CC_SHA256_Update(&sourceHash, bytes, (CC_LONG)amount);
            ssize_t offset = 0;
            while (offset < amount) {
                ssize_t written = write(output, bytes + offset, (size_t)(amount - offset));
                if (written <= 0) { success = NO; break; }
                offset += written;
            }
            copied += (unsigned long long)amount;
            done += (unsigned long long)amount;
            if (progress) progress(context, source.lastPathComponent.UTF8String, MIN(done, total), total);
        }
        if (success) success = amount == 0 && !fstat(input, &after) &&
            before.st_size == after.st_size && before.st_mtimespec.tv_sec == after.st_mtimespec.tv_sec &&
            before.st_mtimespec.tv_nsec == after.st_mtimespec.tv_nsec && copied == (unsigned long long)before.st_size && !fsync(output);
        if (input >= 0) close(input);
        if (output >= 0) close(output);
        NSString *sourceDigest = copyHash(&sourceHash);
        if (success) success = [sourceDigest isEqual:copiedFileHash(target)];
        if (success) [records addObject:@{@"path": [NSString stringWithFormat:@"%@/%@", folder.lastPathComponent, target.lastPathComponent],
                                         @"bytes": @(copied), @"sha256": sourceDigest}];
    }
    NSURL *validated = success ? HaloValidateGameData(destination, error) : nil;
    if (validated) {
        NSDictionary *record = @{@"schema_version": @1, @"source_kind": @"copied-folder", @"source_path": root.path,
                                  @"files": records, @"completed": @YES};
        NSData *data = [NSJSONSerialization dataWithJSONObject:record options:NSJSONWritingPrettyPrinted error:error];
        if (!data || ![data writeToURL:[destination URLByAppendingPathComponent:@"import.json"] options:NSDataWritingAtomic error:error]) validated = nil;
    }
    if (!validated) {
        [NSFileManager.defaultManager removeItemAtURL:destination error:nil];
        if (error && !*error) *error = failure(@"The maps could not be copied. Your original files and previous selection are unchanged.");
    }
    return validated;
}

BOOL HaloUpdateConfigurationIsValid(NSDictionary *info) {
    NSString *feed = info[@"SUFeedURL"], *publicKey = info[@"SUPublicEDKey"];
    if (![feed isKindOfClass:NSString.class] || ![publicKey isKindOfClass:NSString.class]) return NO;
    NSURL *url = [NSURL URLWithString:feed];
    NSData *key = [[NSData alloc] initWithBase64EncodedString:publicKey options:0];
    return [url.scheme isEqualToString:@"https"] && url.host.length && !url.user && !url.password && key.length == 32;
}
