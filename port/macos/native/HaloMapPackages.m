#import "HaloMapPackages.h"
#import "HaloMapDownloads.h"
#include <CommonCrypto/CommonDigest.h>
#include <CoreFoundation/CoreFoundation.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <sys/stat.h>
#include <unistd.h>

static const uint64_t packageLimit = 256ULL * 1024 * 1024;
static const uint64_t manifestLimit = 4ULL * 1024 * 1024;
static const uint64_t assetLimit = 128ULL * 1024 * 1024;
static const uint64_t treeLimit = 1024ULL * 1024 * 1024;
static NSString *const invaderCommit = @"7d25a855f5ef9e4ab8407abf490b21f8780abf27";
static NSString *const cacheBuild = @"01.10.12.2276";

static BOOL failure(NSError **error, NSString *message) {
    if (error) *error = [NSError errorWithDomain:@"HaloMapPackages" code:1
        userInfo:@{NSLocalizedDescriptionKey:message}];
    return NO;
}
static BOOL dictionary(id value, NSArray *keys) {
    return [value isKindOfClass:NSDictionary.class] &&
        [[NSSet setWithArray:[value allKeys]] isEqual:[NSSet setWithArray:keys]];
}
static BOOL integer(id value, uint64_t minimum, uint64_t maximum) {
    if (![value isKindOfClass:NSNumber.class] ||
        CFGetTypeID((__bridge CFTypeRef)value) == CFBooleanGetTypeID()) return NO;
    const char *type = [value objCType];
    return type[0] && !type[1] && strchr("cCsSiIlLqQ", type[0]) &&
        [value doubleValue] >= minimum && [value doubleValue] <= maximum &&
        [value doubleValue] == [value unsignedLongLongValue];
}
static BOOL checksum(id value) {
    return [value isKindOfClass:NSString.class] && [value length] == 64 &&
        [value rangeOfCharacterFromSet:
            [NSCharacterSet characterSetWithCharactersInString:@"0123456789abcdef"].invertedSet].location == NSNotFound;
}
static BOOL relativePath(id value) {
    if (![value isKindOfClass:NSString.class] || ![value length] ||
        [value lengthOfBytesUsingEncoding:NSUTF8StringEncoding] > 512) return NO;
    for (NSUInteger i = 0; i < [value length]; i++) {
        unichar c = [value characterAtIndex:i];
        if (c < 32 || c > 126 || c == '\\' || c == ':') return NO;
    }
    for (NSString *part in [value componentsSeparatedByString:@"/"]) {
        if (!part.length || [part hasPrefix:@"."]) return NO;
    }
    return YES;
}
static BOOL mapID(id value) {
    if (![value isKindOfClass:NSString.class] || [value length] < 1 || [value length] > 31) return NO;
    NSCharacterSet *first = [NSCharacterSet characterSetWithCharactersInString:@"abcdefghijklmnopqrstuvwxyz0123456789"];
    NSCharacterSet *rest = [NSCharacterSet characterSetWithCharactersInString:@"abcdefghijklmnopqrstuvwxyz0123456789_-"];
    if (![first characterIsMember:[value characterAtIndex:0]] ||
        [value rangeOfCharacterFromSet:rest.invertedSet].location != NSNotFound) return NO;
    static NSSet *reserved;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        reserved = [NSSet setWithArray:@[@"ui",@"a10",@"a30",@"a50",@"b30",@"b40",@"c10",@"c20",@"c40",@"d20",@"d40",
            @"beavercreek",@"bloodgulch",@"boardingaction",@"carousel",@"chillout",@"damnation",@"hangemhigh",
            @"longest",@"prisoner",@"putput",@"ratrace",@"sidewinder",@"wizard"]];
    });
    return ![reserved containsObject:value];
}
static uint32_t little32(const unsigned char *p) {
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}
static uint64_t little64(const unsigned char *p) {
    return little32(p) | (uint64_t)little32(p + 4) << 32;
}
static BOOL readRange(int fd, void *buffer, size_t length, uint64_t offset) {
    unsigned char *p = buffer;
    while (length) {
        ssize_t count = pread(fd, p, length, (off_t)offset);
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) return NO;
        length -= (size_t)count; p += count; offset += (size_t)count;
    }
    return YES;
}
static NSString *hashRange(int fd, uint64_t offset, uint64_t length, NSError **error) {
    CC_SHA256_CTX context;
    CC_SHA256_Init(&context);
    unsigned char bytes[65536], hash[CC_SHA256_DIGEST_LENGTH];
    while (length) {
        size_t count = (size_t)MIN(length, sizeof(bytes));
        if (!readRange(fd, bytes, count, offset)) {
            failure(error, @"A source file changed or could not be read.");
            return nil;
        }
        CC_SHA256_Update(&context, bytes, (CC_LONG)count);
        length -= count; offset += count;
    }
    CC_SHA256_Final(hash, &context);
    NSMutableString *result = [NSMutableString string];
    for (NSUInteger i = 0; i < sizeof(hash); i++) [result appendFormat:@"%02x", hash[i]];
    return result;
}
static int regularFile(NSURL *url, uint64_t maximum, uint64_t *size, NSError **error) {
    if (!url.isFileURL) { failure(error, @"Expected a local regular file."); return -1; }
    int fd = open(url.fileSystemRepresentation, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    struct stat info;
    if (fd < 0 || fstat(fd, &info) || !S_ISREG(info.st_mode) ||
        info.st_size < 0 || (uint64_t)info.st_size > maximum) {
        if (fd >= 0) close(fd);
        failure(error, @"A source is missing, linked, special, or exceeds the allowed size.");
        return -1;
    }
    if (size) *size = (uint64_t)info.st_size;
    return fd;
}

/* Foundation JSON does not reject duplicate keys. Scan the bounded document
   first; decoded keys also catch aliases such as "path" and "\u0070ath". */
typedef struct { const unsigned char *p; size_t size, cursor, nodes; } JSONCursor;
static void white(JSONCursor *s) {
    while (s->cursor < s->size && strchr(" \t\r\n", s->p[s->cursor])) s->cursor++;
}
static BOOL jsonValue(JSONCursor *s, unsigned depth);
static BOOL jsonString(JSONCursor *s, NSString **decoded) {
    size_t start = s->cursor;
    if (s->cursor >= s->size || s->p[s->cursor++] != '"') return NO;
    BOOL ended = NO;
    while (s->cursor < s->size) {
        unsigned char c = s->p[s->cursor++];
        if (c == '"') { ended = YES; break; }
        if (c < 32) return NO;
        if (c == '\\') {
            if (s->cursor >= s->size) return NO;
            s->cursor++;
        }
    }
    if (!ended) return NO;
    if (decoded) {
        NSMutableData *wrapper = [NSMutableData dataWithBytes:"[" length:1];
        [wrapper appendBytes:s->p + start length:s->cursor - start];
        [wrapper appendBytes:"]" length:1];
        id strings = [NSJSONSerialization JSONObjectWithData:wrapper options:0 error:nil];
        if (![strings isKindOfClass:NSArray.class] || [strings count] != 1 ||
            ![strings[0] isKindOfClass:NSString.class]) return NO;
        *decoded = strings[0];
    }
    return YES;
}
static BOOL jsonValue(JSONCursor *s, unsigned depth) {
    if (depth > 64 || ++s->nodes > 300000) return NO;
    white(s);
    if (s->cursor >= s->size) return NO;
    unsigned char c = s->p[s->cursor];
    if (c == '"') return jsonString(s, NULL);
    if (c == '{' || c == '[') {
        BOOL object = c == '{';
        unsigned char end = object ? '}' : ']';
        NSMutableSet *keys = object ? [NSMutableSet set] : nil;
        s->cursor++; white(s);
        if (s->cursor < s->size && s->p[s->cursor] == end) { s->cursor++; return YES; }
        for (;;) {
            if (object) {
                NSString *key;
                if (!jsonString(s, &key) || [keys containsObject:key]) return NO;
                [keys addObject:key]; white(s);
                if (s->cursor >= s->size || s->p[s->cursor++] != ':') return NO;
            }
            if (!jsonValue(s, depth + 1)) return NO;
            white(s);
            if (s->cursor >= s->size) return NO;
            c = s->p[s->cursor++];
            if (c == end) return YES;
            if (c != ',') return NO;
            white(s);
        }
    }
    size_t start = s->cursor;
    while (s->cursor < s->size && !strchr(" \t\r\n,}]", s->p[s->cursor])) s->cursor++;
    return s->cursor != start;
}

/* Register the spelling of every component, not just complete file paths.
   This prevents Foo/a and foo/b from aliasing on the standard Mac filesystem. */
static BOOL registerPath(NSString *tree, NSString *path, NSMutableDictionary *spellings,
                         NSMutableSet *files, NSMutableSet *directories) {
    NSArray *parts = [path componentsSeparatedByString:@"/"];
    NSMutableArray *prefix = [NSMutableArray array];
    for (NSUInteger i = 0; i < parts.count; i++) {
        [prefix addObject:parts[i]];
        NSString *actual = [prefix componentsJoinedByString:@"/"];
        NSString *key = [NSString stringWithFormat:@"%@/%@", tree, actual.lowercaseString];
        NSString *previous = spellings[key];
        if (previous && ![previous isEqual:actual]) return NO;
        spellings[key] = actual;
        if (i + 1 < parts.count) {
            if ([files containsObject:key]) return NO;
            [directories addObject:key];
        } else {
            if ([files containsObject:key] || [directories containsObject:key]) return NO;
            [files addObject:key];
        }
    }
    return YES;
}
static BOOL manifestIsValid(NSDictionary *m, NSError **error) {
    if (!dictionary(m, @[@"format",@"version",@"id",@"profile",@"cache_build",@"scenario",@"invader_commit",
        @"tool_sha256",@"stock_inputs",@"output",@"payload_bytes",@"files"]) ||
        ![m[@"format"] isEqual:@"halo-og-community-package"] || !integer(m[@"version"], 1, 1) ||
        ![m[@"profile"] isEqual:@"stock-xbox-ntsc"] || ![m[@"cache_build"] isEqual:cacheBuild] ||
        ![m[@"invader_commit"] isEqual:invaderCommit] || !mapID(m[@"id"]) || !relativePath(m[@"scenario"]))
        return failure(error, @"The package format, profile, or map identity is unsupported.");
    NSString *scenario = m[@"scenario"];
    NSCharacterSet *scenarioCharacters = [NSCharacterSet characterSetWithCharactersInString:
        @"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_ /-"];
    if ([scenario rangeOfCharacterFromSet:scenarioCharacters.invertedSet].location != NSNotFound ||
        ![scenario.lastPathComponent isEqual:m[@"id"]] ||
        !dictionary(m[@"tool_sha256"], @[@"extract",@"build"]) ||
        !checksum(m[@"tool_sha256"][@"extract"]) || !checksum(m[@"tool_sha256"][@"build"]))
        return failure(error, @"The scenario or source toolchain identity is invalid.");
    NSArray *stock = m[@"stock_inputs"];
    NSArray *names = @[@"bloodgulch",@"a10",@"ui"], *types = @[@1,@0,@2];
    if (![stock isKindOfClass:NSArray.class] || stock.count != 3)
        return failure(error, @"Exact original stock inputs are required.");
    for (NSUInteger i = 0; i < stock.count; i++) {
        NSDictionary *entry = stock[i];
        if (!dictionary(entry, @[@"name",@"size",@"sha256",@"type"]) || ![entry[@"name"] isEqual:names[i]] ||
            !integer(entry[@"type"], [types[i] unsignedLongLongValue], [types[i] unsignedLongLongValue]) ||
            !integer(entry[@"size"], 2048, 512ULL * 1024 * 1024) || !checksum(entry[@"sha256"]))
            return failure(error, @"The original stock input records are invalid.");
    }
    NSDictionary *output = m[@"output"];
    if (!dictionary(output, @[@"size",@"sha256",@"declared_bytes",@"tag_bytes"]) ||
        !integer(output[@"size"], 2048, assetLimit) || !checksum(output[@"sha256"]) ||
        !integer(output[@"declared_bytes"], 2048, assetLimit) ||
        !integer(output[@"tag_bytes"], 0, 22ULL * 1024 * 1024) ||
        !integer(m[@"payload_bytes"], 0, packageLimit - 16))
        return failure(error, @"The package cache or payload exceeds this build's limits.");
    NSArray *entries = m[@"files"];
    if (![entries isKindOfClass:NSArray.class] || !entries.count || entries.count > 20000)
        return failure(error, @"The package asset count is invalid.");
    NSMutableDictionary *spellings = [NSMutableDictionary dictionary];
    NSMutableSet *files = [NSMutableSet set], *directories = [NSMutableSet set];
    NSSet *classes = [NSSet setWithArray:@[@"unchanged-stock",@"modified-or-different-stock",
        @"unknown-or-community",@"compatibility-modified-stock",@"generated-data"]];
    uint64_t offset = 0, expanded = 0;
    BOOL hasScenario = NO;
    for (id value in entries) {
        if (![value isKindOfClass:NSDictionary.class])
            return failure(error, @"A package asset record is invalid.");
        NSDictionary *entry = value;
        NSString *tree = entry[@"tree"], *kind = entry[@"kind"], *classification = entry[@"classification"];
        if (![tree isKindOfClass:NSString.class] || ![kind isKindOfClass:NSString.class] ||
            ![classification isKindOfClass:NSString.class] ||
            ![@[@"tags",@"data",@"stock-overrides"] containsObject:tree] ||
            ![@[@"literal",@"stock-reference"] containsObject:kind] || ![classes containsObject:classification])
            return failure(error, @"A package asset storage type is unsupported.");
        BOOL literal = [kind isEqual:@"literal"], repair = [tree isEqual:@"stock-overrides"];
        NSMutableArray *keys = [@[@"tree",@"path",@"kind",@"classification",@"size",@"sha256"] mutableCopy];
        [keys addObject:literal ? @"offset" : @"stock_path"];
        if (repair) [keys addObject:@"original_sha256"];
        NSString *path = entry[@"path"];
        if (!dictionary(entry, keys) || !relativePath(path) || !integer(entry[@"size"], 0, assetLimit) ||
            !checksum(entry[@"sha256"]) || !registerPath(tree, path, spellings, files, directories))
            return failure(error, @"An asset path, hash, size, or collision is unsafe.");
        expanded += [entry[@"size"] unsignedLongLongValue];
        if (expanded > treeLimit) return failure(error, @"Expanded package assets exceed the allowed size.");
        if (literal) {
            if (!integer(entry[@"offset"], 0, packageLimit - 16) ||
                [entry[@"offset"] unsignedLongLongValue] != offset || [classification isEqual:@"unchanged-stock"])
                return failure(error, @"Literal payload ranges must be complete, contiguous assets.");
            offset += [entry[@"size"] unsignedLongLongValue];
        } else if (![tree isEqual:@"tags"] || ![classification isEqual:@"unchanged-stock"] ||
                   !relativePath(entry[@"stock_path"])) {
            return failure(error, @"Only whole unchanged original tags may be referenced.");
        }
        if (repair && (!literal || ![classification isEqual:@"compatibility-modified-stock"] ||
            !checksum(entry[@"original_sha256"]) || [entry[@"original_sha256"] isEqual:entry[@"sha256"]]))
            return failure(error, @"Stock repairs must retain entire modified assets with exact original hashes.");
        if ([tree isEqual:@"data"] && (!literal || ![classification isEqual:@"generated-data"] ||
                                     ![path hasSuffix:@".hsc"]))
            return failure(error, @"Only prepared script data is supported.");
        if ([tree isEqual:@"tags"] && [path isEqual:[scenario stringByAppendingString:@".scenario"]])
            hasScenario = literal;
        if (repair && [path isEqual:[scenario stringByAppendingString:@".scenario"]])
            return failure(error, @"Stock repairs cannot replace the community scenario.");
    }
    if (!hasScenario || offset != [m[@"payload_bytes"] unsignedLongLongValue])
        return failure(error, @"The package is missing its authored scenario or complete payload.");
    return YES;
}
static NSDictionary *openPackage(NSURL *url, int *descriptor, uint64_t *payloadStart, NSError **error) {
    uint64_t size;
    int fd = regularFile(url, packageLimit, &size, error);
    if (fd < 0) return nil;
    unsigned char header[16];
    NSDictionary *manifest = nil;
    uint64_t length = 0;
    if (size < 18 || !readRange(fd, header, sizeof(header), 0) || memcmp(header, "HOGPKG1\n", 8) ||
        (length = little64(header + 8)) < 2 || length > manifestLimit || 16 + length > size) {
        failure(error, @"The community package header or manifest size is invalid.");
    } else {
        NSMutableData *data = [NSMutableData dataWithLength:(NSUInteger)length];
        if (!readRange(fd, data.mutableBytes, data.length, 16)) {
            failure(error, @"The package manifest could not be read.");
        } else {
            JSONCursor cursor = {data.bytes, data.length, 0, 0};
            BOOL jsonOK = jsonValue(&cursor, 0);
            white(&cursor);
            if (!jsonOK || cursor.cursor != cursor.size) {
                failure(error, @"The package JSON is malformed, too deep, or contains duplicate keys.");
            } else {
                id value = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
                if (manifestIsValid(value, error)) manifest = value;
            }
        }
    }
    if (manifest && 16 + length + [manifest[@"payload_bytes"] unsignedLongLongValue] != size) {
        failure(error, @"The package payload is truncated or contains trailing bytes.");
        manifest = nil;
    }
    for (NSDictionary *entry in manifest[@"files"]) {
        if ([entry[@"kind"] isEqual:@"literal"]) {
            NSString *hash = hashRange(fd, 16 + length + [entry[@"offset"] unsignedLongLongValue],
                                       [entry[@"size"] unsignedLongLongValue], error);
            if (![hash isEqual:entry[@"sha256"]]) {
                failure(error, @"A complete literal asset failed its SHA-256 check.");
                manifest = nil;
                break;
            }
        }
    }
    if (!manifest) { close(fd); return nil; }
    if (descriptor) *descriptor = fd; else close(fd);
    if (payloadStart) *payloadStart = 16 + length;
    return manifest;
}
NSDictionary *HaloInspectCommunityPackage(NSURL *file, NSError **error) {
    return openPackage(file, NULL, NULL, error);
}

static BOOL realDirectory(NSURL *url, NSError **error) {
    struct stat info;
    if (!url.isFileURL || lstat(url.fileSystemRepresentation, &info) || !S_ISDIR(info.st_mode))
        return failure(error, @"A required directory is missing or is a symbolic link.");
    return YES;
}
static NSURL *existingChild(NSURL *root, NSString *name, BOOL directory, NSError **error) {
    if (!realDirectory(root, error)) return nil;
    NSArray *children = [NSFileManager.defaultManager contentsOfDirectoryAtURL:root
        includingPropertiesForKeys:nil options:0 error:nil];
    NSURL *selected = nil;
    if (!children) {
        failure(error, @"The selected original data directory could not be read.");
        return nil;
    }
    for (NSURL *child in children) {
        if ([child.lastPathComponent caseInsensitiveCompare:name] != NSOrderedSame) continue;
        if (selected) {
            failure(error, @"The original data has ambiguous filenames that differ only in case.");
            return nil;
        }
        selected = child;
    }
    struct stat info;
    if (!selected || lstat(selected.fileSystemRepresentation, &info) ||
        (directory ? !S_ISDIR(info.st_mode) : !S_ISREG(info.st_mode))) {
        failure(error, @"An original cache or directory is missing, linked, or not a regular source.");
        return nil;
    }
    return selected;
}
static NSURL *directoryUnder(NSURL *root, NSString *relative, NSError **error) {
    if (!relativePath(relative) || !realDirectory(root, error)) return nil;
    NSURL *current = root;
    for (NSString *part in [relative componentsSeparatedByString:@"/"]) {
        current = [current URLByAppendingPathComponent:part isDirectory:YES];
        if (mkdir(current.fileSystemRepresentation, 0700) && errno != EEXIST) {
            failure(error, @"A private community content directory could not be created.");
            return nil;
        }
        if (!realDirectory(current, error)) return nil;
    }
    return current;
}
static NSURL *assetTarget(NSURL *root, NSString *relative, NSError **error) {
    NSString *parent = [relative stringByDeletingLastPathComponent];
    NSURL *folder = parent.length ? directoryUnder(root, parent, error) : root;
    return folder ? [folder URLByAppendingPathComponent:relative.lastPathComponent] : nil;
}
static BOOL writeRange(int source, uint64_t offset, uint64_t size, NSURL *target, NSError **error) {
    int output = open(target.fileSystemRepresentation, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (output < 0) return failure(error, @"A new private asset could not be created exclusively.");
    BOOL success = YES;
    unsigned char bytes[65536];
    while (size && success) {
        size_t count = (size_t)MIN(size, sizeof(bytes));
        if (!readRange(source, bytes, count, offset)) { success = NO; break; }
        size_t written = 0;
        while (written < count) {
            ssize_t amount = write(output, bytes + written, count - written);
            if (amount < 0 && errno == EINTR) continue;
            if (amount <= 0) { success = NO; break; }
            written += (size_t)amount;
        }
        size -= count; offset += count;
    }
    if (success && fsync(output)) success = NO;
    if (close(output)) success = NO;
    if (!success) {
        unlink(target.fileSystemRepresentation);
        return failure(error, @"A private asset could not be fully written.");
    }
    return YES;
}
static NSString *hashFile(NSURL *url, uint64_t maximum, uint64_t *size, NSError **error) {
    uint64_t count;
    int fd = regularFile(url, maximum, &count, error);
    if (fd < 0) return nil;
    NSString *result = hashRange(fd, 0, count, error);
    close(fd);
    if (size) *size = count;
    return result;
}
static NSDictionary *originalTree(NSURL *root, NSError **error) {
    if (!realDirectory(root, error)) return nil;
    __block BOOL enumerationFailed = NO;
    NSDirectoryEnumerator *enumerator = [NSFileManager.defaultManager enumeratorAtURL:root
        includingPropertiesForKeys:nil options:0 errorHandler:^BOOL(NSURL *url, NSError *problem) {
            (void)url; (void)problem; enumerationFailed = YES; return NO;
        }];
    NSMutableDictionary *result = [NSMutableDictionary dictionary], *spellings = [NSMutableDictionary dictionary];
    NSMutableSet *files = [NSMutableSet set], *directories = [NSMutableSet set];
    uint64_t total = 0;
    for (NSURL *url in enumerator) {
        NSString *relative = [url.path substringFromIndex:root.path.length + 1];
        struct stat info;
        if (!relativePath(relative) || lstat(url.fileSystemRepresentation, &info) ||
            (!S_ISREG(info.st_mode) && !S_ISDIR(info.st_mode))) {
            failure(error, @"Extracted stock content contains unsafe paths, links, or special files.");
            return nil;
        }
        if (S_ISDIR(info.st_mode)) continue;
        if (result.count >= 20000 || !registerPath(@"stock", relative, spellings, files, directories)) {
            failure(error, @"Extracted stock paths collide or exceed the asset count limit.");
            return nil;
        }
        uint64_t size = 0;
        NSString *hash = hashFile(url, assetLimit, &size, error);
        if (!hash || (total += size) > treeLimit) {
            if (hash) failure(error, @"Extracted original assets exceed the allowed size.");
            return nil;
        }
        result[relative] = @{@"url":url, @"size":@(size), @"sha256":hash};
    }
    if (enumerationFailed || !enumerator) {
        failure(error, @"The complete original stock asset tree could not be enumerated.");
        return nil;
    }
    return result;
}
static BOOL stockCacheMatches(NSURL *file, NSDictionary *entry, NSError **error) {
    uint64_t size;
    int fd = regularFile(file, 512ULL * 1024 * 1024, &size, error);
    if (fd < 0) return NO;
    unsigned char header[2048];
    BOOL valid = size == [entry[@"size"] unsignedLongLongValue] && size >= 2048 &&
        readRange(fd, header, sizeof(header), 0) && !memcmp(header, "daeh", 4) &&
        !memcmp(header + 2044, "toof", 4) && little32(header + 4) == 5;
    if (valid) {
        const unsigned char *nameEnd = memchr(header + 32, 0, 32), *buildEnd = memchr(header + 64, 0, 32);
        NSString *name = nameEnd ? [[NSString alloc] initWithBytes:header + 32
            length:(NSUInteger)(nameEnd - header - 32) encoding:NSASCIIStringEncoding] : nil;
        NSString *build = buildEnd ? [[NSString alloc] initWithBytes:header + 64
            length:(NSUInteger)(buildEnd - header - 64) encoding:NSASCIIStringEncoding] : nil;
        valid = [name.lowercaseString isEqual:entry[@"name"]] && [build isEqual:cacheBuild] &&
            ((unsigned)header[96] | (unsigned)header[97] << 8) == [entry[@"type"] unsignedIntValue] &&
            [hashRange(fd, 0, size, error) isEqual:entry[@"sha256"]];
    }
    close(fd);
    return valid || failure(error, @"The selected data does not contain this package's exact original Xbox NTSC stock caches.");
}
static BOOL runTool(NSURL *tool, NSArray *arguments, NSURL *workspace, NSURL *log, NSError **error) {
    int fd = open(log.fileSystemRepresentation, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (fd < 0) return failure(error, @"A private reconstruction log could not be created.");
    NSFileHandle *handle = [[NSFileHandle alloc] initWithFileDescriptor:fd closeOnDealloc:YES];
    NSTask *task = [[NSTask alloc] init];
    task.executableURL = tool;
    task.arguments = arguments;
    task.currentDirectoryURL = workspace;
    task.environment = @{@"PATH":@"/usr/bin:/bin", @"LC_ALL":@"C"};
    task.standardOutput = handle; task.standardError = handle;
    NSError *launchError;
    if (![task launchAndReturnError:&launchError])
        return failure(error, @"The verified bundled content helper could not start.");
    NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:180];
    BOOL exceeded = NO;
    while (task.running) {
        struct stat info;
        if ([deadline timeIntervalSinceNow] <= 0 || fstat(fd, &info) ||
            info.st_size > 8 * 1024 * 1024) {
            exceeded = YES;
            /* This is only the helper process launched above. A hard stop
               prevents an ignored SIGTERM from bypassing the fixed deadline. */
            kill(task.processIdentifier, SIGKILL);
            break;
        }
        usleep(100000);
    }
    [task waitUntilExit];
    [handle closeFile];
    if (exceeded || task.terminationReason != NSTaskTerminationReasonExit || task.terminationStatus != 0)
        return failure(error, exceeded ? @"The content helper exceeded its time or log limit." :
            @"The content helper could not reconstruct this package; the original files were preserved.");
    return YES;
}
static NSDictionary *mapConfiguration(void) {
    return @{@"schema_version":@1, @"profile":@"stock-xbox-ntsc", @"cache_build":cacheBuild,
        @"allowed_origins":@[], @"catalog_url":NSNull.null, @"objects_base_url":NSNull.null,
        @"max_catalog_bytes":@1048576, @"max_map_bytes":@(assetLimit), @"max_cache_bytes":@(assetLimit),
        @"max_tag_bytes":@(22ULL * 1024 * 1024), @"max_maps":@115};
}
static BOOL verifyOutput(NSURL *file, NSDictionary *manifest, NSError **error) {
    NSDictionary *expected = manifest[@"output"];
    NSDictionary *entry = @{@"id":manifest[@"id"], @"sha256":expected[@"sha256"],
        @"file_bytes":expected[@"size"], @"cache_version":@5, @"cache_build":cacheBuild, @"scenario_type":@1};
    if (!HaloVerifyDownloadedMap(file, entry, mapConfiguration(), error)) return NO;
    unsigned char header[24];
    int fd = regularFile(file, assetLimit, NULL, error);
    BOOL valid = fd >= 0 && readRange(fd, header, sizeof(header), 0) &&
        little32(header + 8) == [expected[@"declared_bytes"] unsignedIntValue] &&
        little32(header + 20) == [expected[@"tag_bytes"] unsignedIntValue];
    if (fd >= 0) close(fd);
    return valid || failure(error, @"The Xbox cache header differs from the package's approved output.");
}

NSURL *HaloAssembleCommunityPackage(NSURL *package, NSURL *gameDataRoot, NSURL *supportDirectory,
    NSURL *toolsDirectory, NSDictionary *toolsRecord, void (^progress)(NSString *), NSError **error) {
    int packageFD = -1;
    uint64_t payloadStart = 0;
    NSDictionary *m = openPackage(package, &packageFD, &payloadStart, error);
    if (!m) return nil;
    NSURL *work = nil, *published = nil;
    @try {
        if (![toolsRecord isKindOfClass:NSDictionary.class] || !integer(toolsRecord[@"schema"], 1, 1) ||
            ![toolsRecord[@"architecture"] isEqual:@"arm64"] ||
            ![toolsRecord[@"invader_commit"] isEqual:invaderCommit] ||
            ![toolsRecord[@"binaries"] isKindOfClass:NSDictionary.class] ||
            !realDirectory(toolsDirectory, error) || !realDirectory(gameDataRoot, error) ||
            !realDirectory(supportDirectory, error)) {
            failure(error, @"This build lacks the reviewed native content helpers or valid data directories.");
            return nil;
        }
        NSMutableDictionary *helpers = [NSMutableDictionary dictionary];
        for (NSString *name in @[@"extract",@"build"]) {
            NSDictionary *record = toolsRecord[@"binaries"][name];
            NSURL *helper = [toolsDirectory URLByAppendingPathComponent:[@"invader-" stringByAppendingString:name]];
            if (![record isKindOfClass:NSDictionary.class] || !checksum(record[@"source_sha256"]) ||
                !checksum(record[@"bundled_sha256"]) || ![record[@"architecture"] isEqual:@"arm64"] ||
                ![record[@"source_sha256"] isEqual:m[@"tool_sha256"][name]] ||
                ![hashFile(helper, assetLimit, NULL, error) isEqual:record[@"bundled_sha256"]]) {
                failure(error, @"The package toolchain or bundled helper bytes differ from this build's trusted provenance.");
                return nil;
            }
            helpers[name] = helper;
        }
        NSURL *stockMaps = existingChild(gameDataRoot, @"maps", YES, error);
        if (!stockMaps) return nil;
        NSMutableDictionary *stockFiles = [NSMutableDictionary dictionary];
        for (NSDictionary *entry in m[@"stock_inputs"]) {
            NSURL *source = existingChild(stockMaps, [entry[@"name"] stringByAppendingString:@".map"], NO, error);
            if (!source || !stockCacheMatches(source, entry, error)) return nil;
            stockFiles[entry[@"name"]] = source;
        }
        NSURL *maps = directoryUnder(supportDirectory, @"Community Maps/maps", error);
        if (!maps) return nil;
        NSURL *destination = [maps URLByAppendingPathComponent:[m[@"id"] stringByAppendingString:@".map"]];
        struct stat existing;
        if (!lstat(destination.fileSystemRepresentation, &existing)) {
            if (verifyOutput(destination, m, error)) return destination;
            failure(error, @"A different or unsafe map already exists; it was preserved.");
            return nil;
        } else if (errno != ENOENT) {
            failure(error, @"The destination map could not be checked.");
            return nil;
        }
        NSURL *workRoot = directoryUnder(supportDirectory, @"Community Content/Work", error);
        if (!workRoot) return nil;
        work = [workRoot URLByAppendingPathComponent:NSUUID.UUID.UUIDString isDirectory:YES];
        if (mkdir(work.fileSystemRepresentation, 0700)) {
            work = nil;
            failure(error, @"An exclusive private reconstruction workspace could not be created.");
            return nil;
        }
        NSURL *original = directoryUnder(work, @"original-stock", error);
        NSURL *stock = directoryUnder(work, @"stock", error);
        NSURL *tags = directoryUnder(work, @"tags", error);
        NSURL *data = directoryUnder(work, @"data", error);
        NSURL *outputMaps = directoryUnder(work, @"maps", error);
        NSURL *logs = directoryUnder(work, @"logs", error);
        if (!original || !stock || !tags || !data || !outputMaps || !logs) return nil;
        if (progress) progress(@"Extracting your exact original Xbox stock assets…");
        for (NSDictionary *entry in m[@"stock_inputs"]) {
            NSURL *source = stockFiles[entry[@"name"]];
            if (!runTool(helpers[@"extract"], @[@"-t",original.path,source.path], work,
                         [logs URLByAppendingPathComponent:[entry[@"name"] stringByAppendingString:@".log"]], error)) return nil;
        }
        NSDictionary *originals = originalTree(original, error);
        if (!originals) return nil;
        NSString *scenarioFile = [m[@"scenario"] stringByAppendingString:@".scenario"];
        NSString *level = [[m[@"scenario"] stringByDeletingLastPathComponent] stringByAppendingString:@"/"];
        if (originals[scenarioFile]) {
            failure(error, @"Original stock lookup would replace the community scenario.");
            return nil;
        }
        /* Authenticate all references and guarded repair bases before writing
           any materialized package assets. */
        for (NSDictionary *entry in m[@"files"]) {
            NSDictionary *base = originals[entry[@"stock_path"] ?: entry[@"path"]];
            if ([entry[@"kind"] isEqual:@"stock-reference"] &&
                (!base || ![base[@"sha256"] isEqual:entry[@"sha256"]] || ![base[@"size"] isEqual:entry[@"size"]])) {
                failure(error, @"An unchanged original asset is absent or differs from this package's exact base.");
                return nil;
            }
            if ([entry[@"tree"] isEqual:@"stock-overrides"] &&
                (!base || ![base[@"sha256"] isEqual:entry[@"original_sha256"]])) {
                failure(error, @"A compatibility repair does not match the whole original stock asset.");
                return nil;
            }
            if ([entry[@"tree"] isEqual:@"tags"] && originals[entry[@"path"]] &&
                ([entry[@"path"] hasPrefix:level] || [entry[@"path"] hasSuffix:@".scenario_structure_bsp"])) {
                failure(error, @"Original stock lookup would replace authored community level content.");
                return nil;
            }
        }
        if (progress) progress(@"Restoring whole assets into a private workspace…");
        for (NSString *relative in originals) {
            NSDictionary *item = originals[relative];
            NSURL *target = assetTarget(stock, relative, error);
            int fd = regularFile(item[@"url"], assetLimit, NULL, error);
            if (!target || fd < 0) { if (fd >= 0) close(fd); return nil; }
            BOOL copied = writeRange(fd, 0, [item[@"size"] unsignedLongLongValue], target, error);
            close(fd);
            if (!copied || ![hashFile(target, assetLimit, NULL, error) isEqual:item[@"sha256"]]) {
                failure(error, @"An original stock asset changed while copying into the private workspace.");
                return nil;
            }
        }
        for (NSDictionary *entry in m[@"files"]) {
            BOOL repair = [entry[@"tree"] isEqual:@"stock-overrides"];
            NSURL *tree = repair ? stock : ([entry[@"tree"] isEqual:@"tags"] ? tags : data);
            NSURL *target = assetTarget(tree, entry[@"path"], error);
            if (!target) return nil;
            NSURL *written = repair ? [target.URLByDeletingLastPathComponent
                URLByAppendingPathComponent:[@"repair-" stringByAppendingString:NSUUID.UUID.UUIDString]] : target;
            if ([entry[@"kind"] isEqual:@"stock-reference"]) {
                NSDictionary *item = originals[entry[@"stock_path"]];
                int fd = regularFile(item[@"url"], assetLimit, NULL, error);
                if (fd < 0) return nil;
                BOOL copied = writeRange(fd, 0, [entry[@"size"] unsignedLongLongValue], written, error);
                close(fd);
                if (!copied) return nil;
            } else if (!writeRange(packageFD, payloadStart + [entry[@"offset"] unsignedLongLongValue],
                                   [entry[@"size"] unsignedLongLongValue], written, error)) return nil;
            if (![hashFile(written, assetLimit, NULL, error) isEqual:entry[@"sha256"]]) {
                failure(error, @"A materialized whole asset differs from its authenticated bytes.");
                return nil;
            }
            if (repair && (![hashFile(target, assetLimit, NULL, error) isEqual:entry[@"original_sha256"]] ||
                rename(written.fileSystemRepresentation, target.fileSystemRepresentation))) {
                failure(error, @"A private stock repair target changed; the original data was preserved.");
                return nil;
            }
        }
        if (progress) progress(@"Rebuilding the community map with the verified native helper…");
        if (!runTool(helpers[@"build"], @[@"-g",@"xbox-ntsc",@"-t",stock.path,@"-t",tags.path,
            @"-m",outputMaps.path,@"-d",data.path,@"-S",@"data",@"-E",m[@"scenario"]], work,
            [logs URLByAppendingPathComponent:@"build.log"], error)) return nil;
        NSURL *rebuilt = [outputMaps URLByAppendingPathComponent:[m[@"id"] stringByAppendingString:@".map"]];
        if (!verifyOutput(rebuilt, m, error)) return nil;
        int rebuiltFD = regularFile(rebuilt, assetLimit, NULL, error);
        BOOL outputValid = rebuiltFD >= 0 && !fsync(rebuiltFD);
        if (rebuiltFD >= 0) close(rebuiltFD);
        if (!outputValid) { failure(error, @"The rebuilt Xbox cache header differs from its approved output."); return nil; }
        for (NSDictionary *entry in m[@"stock_inputs"])
            if (!stockCacheMatches(stockFiles[entry[@"name"]], entry, error)) return nil;
        if (link(rebuilt.fileSystemRepresentation, destination.fileSystemRepresentation)) {
            if (errno != EEXIST || !verifyOutput(destination, m, error)) {
                failure(error, @"A different destination map appeared; it was preserved without replacement.");
                return nil;
            }
        }
        int mapsFD = open(maps.fileSystemRepresentation, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
        if (mapsFD >= 0) { fsync(mapsFD); close(mapsFD); }
        published = destination;
        if (progress) progress(@"The exact verified community map is ready.");
    } @catch (NSException *exception) {
        failure(error, @"The community package could not be safely assembled.");
    } @finally {
        close(packageFD);
        if (work) [NSFileManager.defaultManager removeItemAtURL:work error:nil];
    }
    return published;
}
