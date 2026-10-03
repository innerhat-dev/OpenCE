#import "HaloMapDownloads.h"
#include <CommonCrypto/CommonDigest.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

/* The live phase uses the production NSURLSession transport. The second
   manager explicitly disables downloads and this guard rejects/counts any
   unexpected network attempt, proving disk-only reuse rather than HTTP cache. */
static NSUInteger offlineRequests;
@interface HaloOfflineGuard : NSURLProtocol
@end
@implementation HaloOfflineGuard
+ (BOOL)canInitWithRequest:(NSURLRequest *)request { return YES; }
+ (NSURLRequest *)canonicalRequestForRequest:(NSURLRequest *)request { return request; }
- (void)startLoading {
    @synchronized(HaloOfflineGuard.class) { offlineRequests++; }
    [self.client URLProtocol:self didFailWithError:[NSError errorWithDomain:@"HaloDownloadSmoke"
        code:1 userInfo:@{NSLocalizedDescriptionKey:@"Unexpected offline network request"}]];
}
- (void)stopLoading {}
@end

static NSString *stateName(int state) {
    switch (state) {
        case HALO_MAP_DOWNLOAD_FAILED: return @"FAILED";
        case HALO_MAP_DOWNLOAD_UNAVAILABLE: return @"UNAVAILABLE";
        case HALO_MAP_DOWNLOAD_READY: return @"READY";
        case HALO_MAP_DOWNLOAD_PENDING: return @"PENDING";
        default: return @"UNKNOWN";
    }
}
static void pump(void) {
    [NSRunLoop.currentRunLoop runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.05]];
}
static BOOL waitForReady(HaloMapDownloads *manager, NSString *name, NSTimeInterval timeout,
                         BOOL offline, NSMutableArray *timeline, NSString **failure) {
    NSTimeInterval started = NSProcessInfo.processInfo.systemUptime;
    int previous = INT_MIN;
    NSString *previousText = nil;
    NSTimeInterval unavailableSince = -1;
    while (NSProcessInfo.processInfo.systemUptime - started < timeout) {
        int state = [manager requestMap:name];
        NSString *text = manager.statusText ?: @"";
        if (state != previous || ![text isEqual:previousText]) {
            [timeline addObject:@{@"elapsed_seconds":@(NSProcessInfo.processInfo.systemUptime - started),
                @"state":stateName(state), @"status":text}];
            fprintf(stderr, "%s: %s\n", stateName(state).UTF8String, text.UTF8String);
            previous = state; previousText = text;
        }
        if (state == HALO_MAP_DOWNLOAD_READY) return YES;
        NSTimeInterval elapsed = NSProcessInfo.processInfo.systemUptime - started;
        if (state == HALO_MAP_DOWNLOAD_UNAVAILABLE) {
            if (unavailableSince < 0) unavailableSince = elapsed;
        } else unavailableSince = -1;
        /* Catalog completion clears its pending flag just before accepting
           entries on the worker queue. Do not mistake that short transition
           for a definitive unknown map. */
        if (!offline && (state == HALO_MAP_DOWNLOAD_FAILED ||
            (state == HALO_MAP_DOWNLOAD_UNAVAILABLE && elapsed - unavailableSince >= 0.5))) {
            if (failure) *failure = state == HALO_MAP_DOWNLOAD_UNAVAILABLE
                ? [@"The requested map is not in the approved catalog. " stringByAppendingString:text] : text;
            return NO;
        }
        pump();
    }
    if (failure) *failure = [NSString stringWithFormat:@"Timed out waiting for %@ READY. %@", name, manager.statusText];
    return NO;
}
static NSDictionary *fileDigest(NSURL *file, NSError **error) {
    int descriptor = open(file.fileSystemRepresentation, O_RDONLY | O_NOFOLLOW);
    struct stat info;
    if (descriptor < 0 || fstat(descriptor, &info) || !S_ISREG(info.st_mode)) {
        if (descriptor >= 0) close(descriptor);
        if (error) *error = [NSError errorWithDomain:NSPOSIXErrorDomain code:errno userInfo:nil];
        return nil;
    }
    CC_SHA256_CTX context;
    CC_SHA256_Init(&context);
    unsigned char bytes[65536], digest[CC_SHA256_DIGEST_LENGTH];
    unsigned long long length = 0;
    ssize_t count;
    while ((count = read(descriptor, bytes, sizeof(bytes))) > 0) {
        length += count;
        CC_SHA256_Update(&context, bytes, (CC_LONG)count);
    }
    int readError = errno;
    close(descriptor);
    if (count < 0) {
        if (error) *error = [NSError errorWithDomain:NSPOSIXErrorDomain code:readError userInfo:nil];
        return nil;
    }
    CC_SHA256_Final(digest, &context);
    NSMutableString *hash = [NSMutableString string];
    for (unsigned i = 0; i < sizeof(digest); i++) [hash appendFormat:@"%02x", digest[i]];
    return @{@"sha256":hash, @"file_bytes":@(length)};
}
static int writeReport(NSMutableDictionary *report, NSURL *destination, BOOL success) {
    report[@"success"] = @(success);
    NSError *error = nil;
    NSData *data = [NSJSONSerialization dataWithJSONObject:report
        options:NSJSONWritingPrettyPrinted | NSJSONWritingSortedKeys error:&error];
    if (!data || ![data writeToURL:destination options:NSDataWritingWithoutOverwriting error:&error]) {
        fprintf(stderr, "Cannot preserve smoke report: %s\n", error.localizedDescription.UTF8String);
        return 2;
    }
    return success ? 0 : 1;
}

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc != 7) {
            fprintf(stderr, "Usage: probe config.json data-root fresh-support map-id report.json timeout-seconds\n");
            return 2;
        }
        NSURL *configURL = [NSURL fileURLWithPath:@(argv[1])], *dataRoot = [NSURL fileURLWithPath:@(argv[2]) isDirectory:YES];
        NSURL *support = [NSURL fileURLWithPath:@(argv[3]) isDirectory:YES], *reportURL = [NSURL fileURLWithPath:@(argv[5])];
        NSString *name = @(argv[4]);
        NSTimeInterval timeout = atof(argv[6]);
        NSMutableDictionary *report = [@{@"schema_version":@1, @"map_id":name, @"data_root":dataRoot.path,
            @"support_directory":support.path, @"transport":@"production NSURLSession HTTPS",
            @"gameplay_verified":@NO, @"profile_gate":@"ui.map build header; not a full original-data or gameplay validation"} mutableCopy];
        NSError *error = nil;
        NSData *configBytes = [NSData dataWithContentsOfURL:configURL options:0 error:&error];
        id config = configBytes ? [NSJSONSerialization JSONObjectWithData:configBytes options:0 error:&error] : nil;
        if (!HaloDownloadConfigurationIsValid(config) || timeout < 1 || timeout > 600) {
            report[@"error"] = error.localizedDescription ?: @"Invalid downloader configuration or timeout.";
            return writeReport(report, reportURL, NO);
        }
        report[@"catalog_url"] = config[@"catalog_url"];
        report[@"profile"] = config[@"profile"];
        report[@"cache_build"] = config[@"cache_build"];
        HaloMapDownloads *live = [[HaloMapDownloads alloc] initWithSupportDirectory:support configuration:config sessionConfiguration:nil];
        [live setGameDataRoot:dataRoot];
        report[@"configured"] = @(live.configured);
        report[@"compatible_data"] = @(live.compatibleData);
        if (!live.configured || !live.compatibleData) {
            report[@"error"] = live.statusText;
            return writeReport(report, reportURL, NO);
        }
        [live activateForHost];
        [live startEnabled:YES];
        NSMutableArray *timeline = [NSMutableArray array];
        report[@"live_timeline"] = timeline;
        NSString *failure = nil;
        if (!waitForReady(live, name, timeout, NO, timeline, &failure)) {
            [live cancelDownloads];
            report[@"error"] = failure ?: @"Live download did not reach READY.";
            return writeReport(report, reportURL, NO);
        }
        NSURL *file = [live.mapsDirectory URLByAppendingPathComponent:[name stringByAppendingPathExtension:@"map"]];
        NSURL *catalogURL = [[support URLByAppendingPathComponent:@"Community Maps" isDirectory:YES] URLByAppendingPathComponent:@"catalog.json"];
        NSData *cached = [NSData dataWithContentsOfURL:catalogURL options:0 error:&error];
        id record = cached ? [NSJSONSerialization JSONObjectWithData:cached options:0 error:&error] : nil;
        NSData *catalogBytes = [record isKindOfClass:NSDictionary.class] && record[@"catalog"]
            ? [NSJSONSerialization dataWithJSONObject:record[@"catalog"] options:0 error:&error] : nil;
        NSDictionary *entries = catalogBytes ? HaloValidateMapCatalog(catalogBytes, config, &error) : nil;
        NSDictionary *entry = entries[name];
        NSDictionary *digest = entry ? fileDigest(file, &error) : nil;
        char hostDirectory[4096] = {0};
        BOOL hostReady = halo_map_download_directory(hostDirectory, sizeof(hostDirectory)) &&
            !strcmp(hostDirectory, live.mapsDirectory.fileSystemRepresentation) && halo_map_download_request(name.UTF8String) == HALO_MAP_DOWNLOAD_READY;
        if (!entry || !digest || ![record[@"catalog_url"] isEqual:config[@"catalog_url"]] ||
            !HaloVerifyDownloadedMap(file, entry, config, &error) || !hostReady) {
            report[@"error"] = error.localizedDescription ?: @"READY map/catalog or guest-facing host hooks did not validate.";
            [live cancelDownloads];
            return writeReport(report, reportURL, NO);
        }
        report[@"map_path"] = file.path;
        report[@"catalog_entry"] = entry;
        report[@"actual_file"] = digest;
        report[@"native_full_file_verified"] = @YES;
        report[@"guest_hooks_ready"] = @(hostReady);
        [live setDownloadsEnabled:NO];
        /* Stop proactive transfers before constructing the offline manager. */
        for (int i = 0; i < 5; i++) pump();
        NSURLSessionConfiguration *offlineConfig = NSURLSessionConfiguration.ephemeralSessionConfiguration;
        offlineConfig.protocolClasses = @[HaloOfflineGuard.class];
        HaloMapDownloads *offline = [[HaloMapDownloads alloc] initWithSupportDirectory:support
            configuration:config sessionConfiguration:offlineConfig];
        [offline setGameDataRoot:dataRoot];
        [offline activateForHost];
        [offline startEnabled:NO];
        NSMutableArray *offlineTimeline = [NSMutableArray array];
        report[@"offline_timeline"] = offlineTimeline;
        BOOL offlineReady = waitForReady(offline, name, MIN(timeout, 15), YES, offlineTimeline, &failure);
        NSUInteger attemptedRequests;
        @synchronized(HaloOfflineGuard.class) { attemptedRequests = offlineRequests; }
        NSDictionary *offlineDigest = offlineReady ? fileDigest(file, &error) : nil;
        BOOL unchanged = offlineDigest && [offlineDigest isEqual:digest];
        report[@"offline_ready"] = @(offlineReady);
        report[@"offline_downloads_enabled"] = @(offline.enabled);
        report[@"offline_network_attempts"] = @(attemptedRequests);
        report[@"offline_file_unchanged"] = @(unchanged);
        BOOL success = offlineReady && !offline.enabled && !attemptedRequests && unchanged &&
            HaloVerifyDownloadedMap(file, entry, config, &error) && halo_map_download_request(name.UTF8String) == HALO_MAP_DOWNLOAD_READY;
        if (!success) report[@"error"] = failure ?: error.localizedDescription ?: @"Offline reuse did not validate.";
        report[@"final_status"] = offline.statusText;
        return writeReport(report, reportURL, success);
    }
}
