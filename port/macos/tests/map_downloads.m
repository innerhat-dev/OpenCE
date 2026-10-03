/* Synthetic Xbox headers and an NSURLProtocol HTTPS fixture; no game assets,
   credentials or external network are used. */
#import <Foundation/Foundation.h>
#import "HaloMapDownloads.h"
#include <CommonCrypto/CommonDigest.h>
#include <assert.h>

static NSMutableDictionary<NSString *, NSData *> *responses;
static unsigned requests;
@interface FixtureHTTPS : NSURLProtocol
@property(nonatomic) BOOL stopped;
@end
@implementation FixtureHTTPS
+ (BOOL)canInitWithRequest:(NSURLRequest *)request { return [request.URL.host isEqual:@"maps.test"]; }
+ (NSURLRequest *)canonicalRequestForRequest:(NSURLRequest *)request { return request; }
- (void)startLoading {
    NSData *bytes;
    @synchronized(FixtureHTTPS.class) { bytes = responses[self.request.URL.path]; requests++; }
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 20 * NSEC_PER_MSEC), dispatch_get_global_queue(QOS_CLASS_DEFAULT, 0), ^{
        @synchronized(self) {
            if (self.stopped) return;
            NSDictionary *headers = @{@"Content-Length":@(bytes.length).stringValue};
            NSHTTPURLResponse *response = [[NSHTTPURLResponse alloc] initWithURL:self.request.URL statusCode:bytes ? 200 : 404 HTTPVersion:@"HTTP/1.1" headerFields:headers];
            [self.client URLProtocol:self didReceiveResponse:response cacheStoragePolicy:NSURLCacheStorageNotAllowed];
            if (bytes) [self.client URLProtocol:self didLoadData:bytes];
            [self.client URLProtocolDidFinishLoading:self];
        }
    });
}
- (void)stopLoading { @synchronized(self) { self.stopped = YES; } }
@end

static NSData *fixtureMap(NSString *name, NSString *build) {
    NSMutableData *bytes = [NSMutableData dataWithLength:4096];
    unsigned char *p = bytes.mutableBytes;
    memcpy(p, "daeh", 4);
    uint32_t version = 5, declared = 4096, offset = 2048, size = 128;
    memcpy(p + 4, &version, 4); memcpy(p + 8, &declared, 4);
    memcpy(p + 16, &offset, 4); memcpy(p + 20, &size, 4);
    memcpy(p + 32, name.UTF8String, name.length); memcpy(p + 64, build.UTF8String, build.length);
    p[96] = 1; memcpy(p + 2044, "toof", 4);
    for (NSUInteger i = 2048; i < bytes.length; i++) p[i] = (unsigned char)i;
    return bytes;
}
static NSString *hash(NSData *bytes) {
    unsigned char digest[CC_SHA256_DIGEST_LENGTH];
    CC_SHA256(bytes.bytes, (CC_LONG)bytes.length, digest);
    NSMutableString *result = [NSMutableString string];
    for (unsigned i = 0; i < sizeof(digest); i++) [result appendFormat:@"%02x", digest[i]];
    return result;
}
static NSDictionary *entry(NSString *name, NSData *bytes) {
    NSString *sha = hash(bytes);
    return @{@"id":name, @"sha256":sha, @"file_bytes":@(bytes.length), @"cache_version":@5,
        @"cache_build":@"01.10.12.2276", @"scenario_type":@1,
        @"object_key":[NSString stringWithFormat:@"maps/sha256/%@/%@.map", sha, name]};
}
static NSData *catalog(NSArray *maps) {
    return [NSJSONSerialization dataWithJSONObject:@{@"schema_version":@1, @"profile":@"stock-xbox-ntsc", @"maps":maps} options:0 error:nil];
}
static void waitFor(BOOL (^predicate)(void)) {
    NSDate *until = [NSDate dateWithTimeIntervalSinceNow:5];
    while (!predicate() && until.timeIntervalSinceNow > 0)
        [NSRunLoop.currentRunLoop runMode:NSDefaultRunLoopMode beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.01]];
    assert(predicate());
}
static NSURL *folder(NSURL *root, NSString *name) {
    NSURL *result = [root URLByAppendingPathComponent:name isDirectory:YES];
    assert([NSFileManager.defaultManager createDirectoryAtURL:result withIntermediateDirectories:YES attributes:nil error:nil]);
    return result;
}
static HaloMapDownloads *manager(NSURL *support, NSURL *data, NSDictionary *config) {
    NSURLSessionConfiguration *session = NSURLSessionConfiguration.ephemeralSessionConfiguration;
    session.protocolClasses = @[FixtureHTTPS.class];
    HaloMapDownloads *downloads = [[HaloMapDownloads alloc] initWithSupportDirectory:support configuration:config sessionConfiguration:session];
    [downloads setGameDataRoot:data];
    return downloads;
}

int main(int argc, const char **argv) {
    @autoreleasepool {
        assert(argc == 3);
        NSURL *root = [NSURL fileURLWithPath:@(argv[1]) isDirectory:YES];
        NSDictionary *unconfigured = [NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:@(argv[2])] options:0 error:nil];
        assert(HaloDownloadConfigurationIsValid(unconfigured));
        NSMutableDictionary *config = [unconfigured mutableCopy];
        config[@"catalog_url"] = @"https://maps.test/catalog.json";
        config[@"objects_base_url"] = @"https://maps.test/";
        config[@"allowed_origins"] = @[@"https://maps.test"];
        assert(HaloDownloadConfigurationIsValid(config));
        NSMutableDictionary *badConfig = [config mutableCopy];
        badConfig[@"catalog_url"] = @"http://maps.test/catalog.json";
        assert(!HaloDownloadConfigurationIsValid(badConfig));
        badConfig[@"catalog_url"] = @"https://evil.test/catalog.json";
        assert(!HaloDownloadConfigurationIsValid(badConfig));
        badConfig[@"catalog_url"] = @"https://person:password@maps.test/catalog.json";
        assert(!HaloDownloadConfigurationIsValid(badConfig));
        NSData *map = fixtureMap(@"downrush", @"01.10.12.2276");
        NSDictionary *approved = entry(@"downrush", map);
        NSError *error = nil;
        assert(HaloValidateMapCatalog(catalog(@[approved]), config, &error).count == 1);
        for (NSString *name in @[@"ui", @"a10", @"bloodgulch", @"../unsafe", @"bad/name", @"bad\\name"]) {
            assert(!HaloValidateMapCatalog(catalog(@[entry(name, map)]), config, &error));
        }
        assert(!HaloValidateMapCatalog(catalog(@[approved, approved]), config, &error));
        assert(!HaloValidateMapCatalog(catalog(@[entry(@"DownRush", map)]), config, &error));
        assert(!HaloValidateMapCatalog(catalog(@[@3]), config, &error));
        for (NSDictionary *replacement in @[@{@"cache_version":@7}, @{@"cache_build":@"01.01.14.2342"},
            @{@"file_bytes":@134217729}, @{@"object_key":@"../downrush.map"}, @{@"sha256":@"wrong"}]) {
            NSMutableDictionary *bad = [approved mutableCopy]; [bad addEntriesFromDictionary:replacement];
            assert(!HaloValidateMapCatalog(catalog(@[bad]), config, &error));
        }
        NSURL *file = [root URLByAppendingPathComponent:@"map.map"];
        assert([map writeToURL:file atomically:YES]);
        assert(HaloVerifyDownloadedMap(file, approved, config, &error));
        NSMutableDictionary *lowerLimits = [config mutableCopy];
        lowerLimits[@"max_cache_bytes"] = @2048;
        assert(!HaloVerifyDownloadedMap(file, approved, lowerLimits, &error));
        lowerLimits[@"max_cache_bytes"] = @4096; lowerLimits[@"max_tag_bytes"] = @64;
        assert(!HaloVerifyDownloadedMap(file, approved, lowerLimits, &error));
        NSMutableData *tampered = [map mutableCopy]; ((unsigned char *)tampered.mutableBytes)[2500] ^= 1;
        assert([tampered writeToURL:file atomically:YES]); assert(!HaloVerifyDownloadedMap(file, approved, config, &error));
        NSData *wrongHeader = fixtureMap(@"atlas", @"01.10.12.2276");
        assert([wrongHeader writeToURL:file atomically:YES]);
        NSMutableDictionary *correctHashWrongName = [approved mutableCopy]; correctHashWrongName[@"sha256"] = hash(wrongHeader);
        assert(!HaloVerifyDownloadedMap(file, correctHashWrongName, config, &error));
        assert([[map subdataWithRange:NSMakeRange(0, 1000)] writeToURL:file atomically:YES]);
        assert(!HaloVerifyDownloadedMap(file, approved, config, &error));
        NSURL *linked = [root URLByAppendingPathComponent:@"link.map"];
        assert([NSFileManager.defaultManager createSymbolicLinkAtURL:linked withDestinationURL:file error:nil]);
        assert(!HaloVerifyDownloadedMap(linked, approved, config, &error));

        NSURL *game = folder(root, @"game"), *maps = folder(game, @"maps");
        assert([fixtureMap(@"ui", @"01.10.12.2276") writeToURL:[maps URLByAppendingPathComponent:@"ui.map"] atomically:YES]);
        responses = [@{@"/catalog.json":catalog(@[approved]),
            [@"/" stringByAppendingString:approved[@"object_key"]]:map} mutableCopy];
        HaloMapDownloads *disabled = manager(folder(root, @"disabled"), game, config);
        [disabled startEnabled:NO];
        waitFor(^BOOL{ return [disabled requestMap:@"downrush"] == HALO_MAP_DOWNLOAD_UNAVAILABLE; });
        assert(requests == 0);

        HaloMapDownloads *downloads = manager(folder(root, @"support"), game, config);
        [downloads activateForHost];
        [downloads startEnabled:YES];
        assert(halo_map_download_request("downrush") == HALO_MAP_DOWNLOAD_PENDING);
        waitFor(^BOOL{ return [downloads.statusText containsString:@"approved maps available"]; });
        assert([downloads requestMap:@"unknown"] == HALO_MAP_DOWNLOAD_UNAVAILABLE);
        assert([downloads requestMap:@"ui"] == HALO_MAP_DOWNLOAD_UNAVAILABLE);
        assert([downloads requestMap:@"downrush"] == HALO_MAP_DOWNLOAD_PENDING);
        waitFor(^BOOL{ return [downloads requestMap:@"downrush"] == HALO_MAP_DOWNLOAD_READY; });
        NSURL *installed = [downloads.mapsDirectory URLByAppendingPathComponent:@"downrush.map"];
        assert([[NSData dataWithContentsOfURL:installed] isEqual:map]);
        char path[4096]; assert(halo_map_download_directory(path, sizeof(path)));
        assert([@(path) isEqual:downloads.mapsDirectory.path]);
        [downloads setDownloadsEnabled:NO];
        assert([downloads requestMap:@"downrush"] == HALO_MAP_DOWNLOAD_READY);
        unsigned afterDownload = requests;
        HaloMapDownloads *offline = manager(folder(root, @"support"), game, config);
        [offline startEnabled:NO];
        waitFor(^BOOL{ return [offline requestMap:@"downrush"] == HALO_MAP_DOWNLOAD_READY; });
        assert(requests == afterDownload);

        // Revalidation clears stale ready state when installed bytes disappear.
        assert([NSFileManager.defaultManager removeItemAtURL:installed error:nil]);
        [offline setDownloadsEnabled:YES];
        waitFor(^BOOL{ return [offline.statusText containsString:@"approved maps available"]; });
        assert([offline requestMap:@"downrush"] == HALO_MAP_DOWNLOAD_PENDING);
        waitFor(^BOOL{ return [offline requestMap:@"downrush"] == HALO_MAP_DOWNLOAD_READY; });
        [offline setDownloadsEnabled:NO];

        HaloMapDownloads *collision = manager(folder(root, @"collision"), game, config);
        folder(folder(root, @"collision/Community Maps"), @"maps");
        NSURL *existing = [collision.mapsDirectory URLByAppendingPathComponent:@"downrush.map"];
        NSData *personal = [@"user file" dataUsingEncoding:NSUTF8StringEncoding];
        assert([personal writeToURL:existing atomically:YES]);
        [collision startEnabled:YES];
        waitFor(^BOOL{ return [collision requestMap:@"downrush"] == HALO_MAP_DOWNLOAD_FAILED; });
        waitFor(^BOOL{ return [collision.statusText containsString:@"approved maps available"]; });
        assert([collision.statusText containsString:@"conflicts with an existing map"]);
        assert([[NSData dataWithContentsOfURL:existing] isEqual:personal]);
        [collision cancelDownloads];
        waitFor(^BOOL{ return [collision.statusText containsString:@"cancelled"]; });
        assert([collision requestMap:@"downrush"] == HALO_MAP_DOWNLOAD_UNAVAILABLE);
        [collision checkForMaps];
        waitFor(^BOOL{ return [collision requestMap:@"downrush"] == HALO_MAP_DOWNLOAD_FAILED; });
        [collision setDownloadsEnabled:NO];
        assert([collision requestMap:@"downrush"] == HALO_MAP_DOWNLOAD_UNAVAILABLE);

        // A catalog-authenticated hash does not bypass the Xbox header checks.
        NSMutableDictionary *wrongEntry = [approved mutableCopy]; wrongEntry[@"sha256"] = hash(wrongHeader);
        wrongEntry[@"object_key"] = [NSString stringWithFormat:@"maps/sha256/%@/downrush.map", hash(wrongHeader)];
        @synchronized(FixtureHTTPS.class) {
            responses[@"/catalog.json"] = catalog(@[wrongEntry]);
            responses[[@"/" stringByAppendingString:wrongEntry[@"object_key"]]] = wrongHeader;
        }
        HaloMapDownloads *invalid = manager(folder(root, @"invalid"), game, config);
        [invalid startEnabled:YES];
        waitFor(^BOOL{ return [invalid.statusText containsString:@"approved maps available"]; });
        assert([invalid requestMap:@"downrush"] == HALO_MAP_DOWNLOAD_PENDING);
        waitFor(^BOOL{ return [invalid requestMap:@"downrush"] == HALO_MAP_DOWNLOAD_FAILED; });
        assert(![NSFileManager.defaultManager fileExistsAtPath:[invalid.mapsDirectory URLByAppendingPathComponent:@"downrush.map"].path]);
        assert([NSFileManager.defaultManager contentsOfDirectoryAtPath:[invalid.mapsDirectory.URLByDeletingLastPathComponent.path stringByAppendingPathComponent:@"Downloads"] error:nil].count == 0);
        @synchronized(FixtureHTTPS.class) { responses[@"/catalog.json"] = catalog(@[approved]); }
        [invalid checkForMaps];
        waitFor(^BOOL{ return [invalid requestMap:@"downrush"] == HALO_MAP_DOWNLOAD_READY; });

        NSURL *pal = folder(root, @"pal"), *palMaps = folder(pal, @"maps");
        assert([fixtureMap(@"ui", @"01.01.14.2342") writeToURL:[palMaps URLByAppendingPathComponent:@"ui.map"] atomically:YES]);
        HaloMapDownloads *incompatible = manager(folder(root, @"pal-support"), pal, config);
        [incompatible activateForHost]; [incompatible startEnabled:YES];
        assert(!incompatible.compatibleData && [incompatible requestMap:@"downrush"] == HALO_MAP_DOWNLOAD_UNAVAILABLE);
        assert(!halo_map_download_directory(path, sizeof(path)));
        assert([incompatible.statusText containsString:@"NTSC 2276"]);
        NSURL *upper = folder(root, @"uppercase"), *upperMaps = folder(upper, @"MAPS");
        assert([fixtureMap(@"ui", @"01.10.12.2276") writeToURL:[upperMaps URLByAppendingPathComponent:@"UI.MAP"] atomically:YES]);
        HaloMapDownloads *uppercase = manager(folder(root, @"uppercase-support"), upper, config);
        assert(uppercase.compatibleData);

        HaloMapDownloads *cancelled = manager(folder(root, @"cancelled"), game, config);
        [cancelled startEnabled:YES];
        waitFor(^BOOL{ return [cancelled.statusText containsString:@"approved maps available"]; });
        assert([cancelled requestMap:@"downrush"] == HALO_MAP_DOWNLOAD_PENDING);
        [cancelled cancelDownloads];
        waitFor(^BOOL{ return [cancelled.statusText containsString:@"cancelled"]; });
        assert([cancelled requestMap:@"downrush"] == HALO_MAP_DOWNLOAD_UNAVAILABLE);
        assert(![NSFileManager.defaultManager fileExistsAtPath:[cancelled.mapsDirectory URLByAppendingPathComponent:@"downrush.map"].path]);
        [cancelled checkForMaps];
        waitFor(^BOOL{ return [cancelled.statusText containsString:@"approved maps available"]; });
        assert([cancelled requestMap:@"downrush"] == HALO_MAP_DOWNLOAD_PENDING);
        waitFor(^BOOL{ return [cancelled requestMap:@"downrush"] == HALO_MAP_DOWNLOAD_READY; });

        // Removing catalog authority also removes the exported READY state.
        @synchronized(FixtureHTTPS.class) { responses[@"/catalog.json"] = catalog(@[]); }
        [cancelled checkForMaps];
        waitFor(^BOOL{ return [cancelled.statusText containsString:@"0 approved maps available"]; });
        assert([cancelled requestMap:@"downrush"] == HALO_MAP_DOWNLOAD_UNAVAILABLE);
        assert([NSFileManager.defaultManager fileExistsAtPath:[cancelled.mapsDirectory URLByAppendingPathComponent:@"downrush.map"].path]);

        // An HTTP error leaves the missing-map hook in FAILED until a retry.
        @synchronized(FixtureHTTPS.class) { [responses removeObjectForKey:@"/catalog.json"]; }
        HaloMapDownloads *failedCatalog = manager(folder(root, @"catalog-failure"), game, config);
        [failedCatalog startEnabled:YES];
        assert([failedCatalog requestMap:@"downrush"] == HALO_MAP_DOWNLOAD_PENDING);
        waitFor(^BOOL{ return [failedCatalog requestMap:@"downrush"] == HALO_MAP_DOWNLOAD_FAILED; });
        assert([failedCatalog.statusText containsString:@"catalog unavailable"]);
        @synchronized(FixtureHTTPS.class) { responses[@"/catalog.json"] = catalog(@[approved]); }
        [failedCatalog checkForMaps];
        waitFor(^BOOL{ return [failedCatalog.statusText containsString:@"approved maps available"]; });
        assert(![failedCatalog.statusText containsString:@"catalog unavailable"]);
        assert([failedCatalog requestMap:@"unknown"] == HALO_MAP_DOWNLOAD_UNAVAILABLE);
        // Immediate cancel/retry while catalog completion is still queued must
        // schedule a fresh check rather than losing the retry to pending state.
        HaloMapDownloads *rapidRetry = manager(folder(root, @"rapid-retry"), game, config);
        [rapidRetry startEnabled:YES];
        [rapidRetry cancelDownloads];
        [rapidRetry checkForMaps];
        waitFor(^BOOL{ return [rapidRetry.statusText containsString:@"approved maps available"]; });
        assert([rapidRetry requestMap:@"downrush"] == HALO_MAP_DOWNLOAD_PENDING);
        waitFor(^BOOL{ return [rapidRetry requestMap:@"downrush"] == HALO_MAP_DOWNLOAD_READY; });
        puts("Native HTTPS fixtures: opt-in, async pending/ready, catalog bounds, SHA/header checks, atomic install, offline reuse, collision preservation, retry and PAL gating passed");
    }
    return 0;
}
