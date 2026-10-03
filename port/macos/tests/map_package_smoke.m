#import "HaloMapPackages.h"
#import "HaloMapDownloads.h"
#include <CommonCrypto/CommonDigest.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

static NSUInteger networkAttempts;
static NSUInteger mockCatalogRequests;
@interface HaloPackageOfflineGuard : NSURLProtocol
@end
@implementation HaloPackageOfflineGuard
+ (BOOL)canInitWithRequest:(NSURLRequest *)request { (void)request; return YES; }
+ (NSURLRequest *)canonicalRequestForRequest:(NSURLRequest *)request { return request; }
- (void)startLoading {
    if ([self.request.URL.absoluteString isEqual:@"https://package-smoke.invalid/catalog.json"]) {
        @synchronized(HaloPackageOfflineGuard.class) { mockCatalogRequests++; }
        NSData *bytes = [NSJSONSerialization dataWithJSONObject:@{@"schema_version":@1,
            @"profile":@"stock-xbox-ntsc", @"maps":@[]} options:0 error:nil];
        NSHTTPURLResponse *response = [[NSHTTPURLResponse alloc] initWithURL:self.request.URL
            statusCode:200 HTTPVersion:@"HTTP/1.1" headerFields:@{@"Content-Type":@"application/json"}];
        [self.client URLProtocol:self didReceiveResponse:response cacheStoragePolicy:NSURLCacheStorageNotAllowed];
        [self.client URLProtocol:self didLoadData:bytes];
        [self.client URLProtocolDidFinishLoading:self];
        return;
    }
    @synchronized(HaloPackageOfflineGuard.class) { networkAttempts++; }
    [self.client URLProtocol:self didFailWithError:[NSError errorWithDomain:@"HaloPackageSmoke" code:1
        userInfo:@{NSLocalizedDescriptionKey:@"Unexpected network attempt in local-only package smoke"}]];
}
- (void)stopLoading {}
@end

static void pump(void) {
    [NSRunLoop.currentRunLoop runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.05]];
}
static NSDictionary *offlineConfiguration(void) {
    return @{@"schema_version":@1, @"catalog_url":NSNull.null, @"objects_base_url":NSNull.null,
        @"allowed_origins":@[], @"profile":@"stock-xbox-ntsc", @"cache_build":@"01.10.12.2276",
        @"max_catalog_bytes":@1048576, @"max_map_bytes":@134217728, @"max_cache_bytes":@134217728,
        @"max_tag_bytes":@23068672, @"max_maps":@115};
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
    return @{@"sha256":hash, @"file_bytes":@(length), @"inode":@(info.st_ino)};
}
static id readJSON(NSURL *file, NSError **error) {
    NSData *bytes = [NSData dataWithContentsOfURL:file options:0 error:error];
    return bytes ? [NSJSONSerialization JSONObjectWithData:bytes options:0 error:error] : nil;
}
static HaloMapDownloads *manager(NSURL *support, NSURL *dataRoot) {
    NSURLSessionConfiguration *session = NSURLSessionConfiguration.ephemeralSessionConfiguration;
    session.protocolClasses = @[HaloPackageOfflineGuard.class];
    HaloMapDownloads *result = [[HaloMapDownloads alloc] initWithSupportDirectory:support
        configuration:offlineConfiguration() sessionConfiguration:session];
    [result setGameDataRoot:dataRoot];
    [result startEnabled:NO];
    return result;
}
static BOOL registerMap(HaloMapDownloads *downloads, NSURL *map, NSDictionary *manifest, NSError **error) {
    __block BOOL complete = NO;
    __block NSError *failure = nil;
    [downloads registerAssembledMap:map manifest:manifest completion:^(NSError *result) {
        failure = result; complete = YES;
    }];
    NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:20];
    while (!complete && deadline.timeIntervalSinceNow > 0) pump();
    if (!complete) failure = [NSError errorWithDomain:@"HaloPackageSmoke" code:2
        userInfo:@{NSLocalizedDescriptionKey:@"Local receipt registration timed out"}];
    if (error) *error = failure;
    return complete && !failure;
}
static BOOL waitReady(HaloMapDownloads *downloads, NSString *name) {
    NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:20];
    while (deadline.timeIntervalSinceNow > 0) {
        if ([downloads requestMap:name] == HALO_MAP_DOWNLOAD_READY) return YES;
        pump();
    }
    return NO;
}
static NSURL *assemble(NSURL *package, NSURL *data, NSURL *support, NSURL *helpers,
                      NSDictionary *tools, NSMutableArray *timeline, NSError **error) {
    __block NSURL *result = nil;
    __block NSError *failure = nil;
    dispatch_semaphore_t done = dispatch_semaphore_create(0);
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        result = HaloAssembleCommunityPackage(package, data, support, helpers, tools, ^(NSString *text) {
            @synchronized(timeline) { [timeline addObject:text]; }
            fprintf(stderr, "%s\n", text.UTF8String);
            fflush(stderr);
        }, &failure);
        dispatch_semaphore_signal(done);
    });
    // Production helper calls each have their own bounded 180-second deadline.
    // Keep the worker alive until cleanup rather than abandoning a spawned tool.
    while (dispatch_semaphore_wait(done, DISPATCH_TIME_NOW)) pump();
    if (error) *error = failure;
    return result;
}
static int writeReport(NSMutableDictionary *report, NSURL *file, BOOL success) {
    report[@"success"] = @(success);
    NSError *error = nil;
    NSData *bytes = [NSJSONSerialization dataWithJSONObject:report
        options:NSJSONWritingPrettyPrinted | NSJSONWritingSortedKeys error:&error];
    if (!bytes || ![bytes writeToURL:file options:NSDataWritingWithoutOverwriting error:&error]) {
        fprintf(stderr, "Could not preserve native smoke report: %s\n", error.localizedDescription.UTF8String);
        return 2;
    }
    return success ? 0 : 1;
}
static BOOL mutateMap(NSURL *map) {
    int descriptor = open(map.fileSystemRepresentation, O_RDWR | O_NOFOLLOW);
    unsigned char byte;
    BOOL success = descriptor >= 0 && pread(descriptor, &byte, 1, 2048) == 1;
    if (success) { byte ^= 1; success = pwrite(descriptor, &byte, 1, 2048) == 1 && !fsync(descriptor); }
    if (descriptor >= 0) close(descriptor);
    return success;
}

int main(int argc, const char **argv) {
    @autoreleasepool {
        if (argc != 7) { fprintf(stderr, "Invalid native package probe arguments\n"); return 2; }
        BOOL inspect = !strcmp(argv[1], "--inspect"), rejectTools = !strcmp(argv[1], "--reject-tools");
        BOOL rejectReuse = !strcmp(argv[1], "--reject-reuse");
        NSUInteger shift = inspect || rejectTools || rejectReuse ? 1 : 0;
        NSURL *package = [NSURL fileURLWithPath:@(argv[1 + shift])];
        NSURL *dataRoot = [NSURL fileURLWithPath:@(argv[2 + shift]) isDirectory:YES];
        NSURL *toolsApp = [NSURL fileURLWithPath:@(argv[3 + shift]) isDirectory:YES];
        NSURL *support = [NSURL fileURLWithPath:@(argv[4 + shift]) isDirectory:YES];
        NSURL *reportURL = [NSURL fileURLWithPath:@(argv[5 + shift])];
        NSMutableDictionary *report = [@{@"schema_version":@1,
            @"scope":@"Native local package/receipt storage only; no game or user preferences",
            @"user_preferences_modified":@NO, @"application_installed":@NO} mutableCopy];
        NSError *error = nil;
        NSDictionary *manifest = HaloInspectCommunityPackage(package, &error);
        NSURL *helpers = [toolsApp URLByAppendingPathComponent:@"Contents/Helpers" isDirectory:YES];
        NSDictionary *tools = readJSON([toolsApp URLByAppendingPathComponent:@"Contents/Resources/ContentTools.json"], nil);
        if (inspect || rejectTools || rejectReuse) {
            if ((rejectTools || rejectReuse) && manifest) {
                [NSFileManager.defaultManager createDirectoryAtURL:support withIntermediateDirectories:YES attributes:nil error:&error];
                NSMutableArray *timeline = [NSMutableArray array];
                NSURL *assembled = error ? nil : assemble(package, dataRoot, support, helpers, tools, timeline, &error);
                report[@"accepted"] = assembled ? @YES : @NO;
                report[@"progress"] = timeline;
                report[@"rejected_before_helpers"] = !assembled && !timeline.count && error != nil ? @YES : @NO;
            } else report[@"accepted"] = manifest ? @YES : @NO;
            if (error) report[@"error"] = error.localizedDescription;
            BOOL accepted = [report[@"accepted"] boolValue];
            return writeReport(report, reportURL, accepted);
        }
        if (!manifest || !tools) {
            report[@"error"] = error.localizedDescription ?: @"Package or helper provenance did not validate";
            return writeReport(report, reportURL, NO);
        }
        report[@"manifest"] = manifest;
        NSDictionary *packageBefore = fileDigest(package, &error);
        if (!packageBefore) {
            report[@"error"] = error.localizedDescription;
            return writeReport(report, reportURL, NO);
        }
        report[@"package_before"] = packageBefore;
        NSMutableArray *progress = [NSMutableArray array];
        report[@"assembly_progress"] = progress;
        NSDate *start = NSDate.date;
        NSURL *map = assemble(package, dataRoot, support, helpers, tools, progress, &error);
        report[@"assembly_seconds"] = @(-start.timeIntervalSinceNow);
        if (!map) {
            report[@"error"] = error.localizedDescription ?: @"Native assembly failed";
            return writeReport(report, reportURL, NO);
        }
        NSString *name = manifest[@"id"];
        NSDictionary *digest = fileDigest(map, &error);
        NSDictionary *expected = manifest[@"output"];
        BOOL exact = [digest[@"sha256"] isEqual:expected[@"sha256"]] && [digest[@"file_bytes"] isEqual:expected[@"size"]];
        report[@"map_path"] = map.path; report[@"assembled_file"] = digest ?: @{};
        report[@"exact_expected_bytes"] = @(exact);
        if (!exact) {
            report[@"error"] = error.localizedDescription ?: @"Native assembled map differs from expected bytes";
            return writeReport(report, reportURL, NO);
        }
        HaloMapDownloads *registered = manager(support, dataRoot);
        BOOL localRegistered = registerMap(registered, map, manifest, &error);
        [registered activateForHost];
        char directory[4096] = {0};
        BOOL hostReady = halo_map_download_directory(directory, sizeof(directory)) &&
            !strcmp(directory, registered.mapsDirectory.fileSystemRepresentation) &&
            halo_map_download_request(name.UTF8String) == HALO_MAP_DOWNLOAD_READY;
        report[@"local_registered"] = @(localRegistered);
        report[@"local_ready_downloads_disabled"] = @((BOOL)(!registered.enabled && [registered requestMap:name] == HALO_MAP_DOWNLOAD_READY));
        report[@"guest_hooks_ready"] = @(hostReady);
        if (!localRegistered || !hostReady) {
            report[@"error"] = error.localizedDescription ?: @"Local registration or guest hooks failed";
            return writeReport(report, reportURL, NO);
        }
        NSURL *receiptURL = [support URLByAppendingPathComponent:@"Community Maps/local-maps.json"];
        NSDictionary *receipt = readJSON(receiptURL, &error);
        report[@"local_receipt"] = receipt ?: @{};
        BOOL receiptValid = [receipt[@"version"] isEqual:@1] && [receipt[@"maps"] count] == 1 &&
            [receipt[@"maps"][0][@"id"] isEqual:name] &&
            [receipt[@"maps"][0][@"output"][@"sha256"] isEqual:expected[@"sha256"]];
        HaloMapDownloads *offline = manager(support, dataRoot);
        int startupState = [offline requestMap:name];
        BOOL offlineReady = waitReady(offline, name);
        [offline activateForHost];
        report[@"offline_unconfigured"] = @((BOOL)!offline.configured);
        report[@"offline_ready"] = @(offlineReady);
        report[@"offline_downloads_disabled"] = @((BOOL)!offline.enabled);
        report[@"receipt_valid"] = @(receiptValid);
        report[@"offline_startup_state"] = @(startupState);
        report[@"offline_startup_pending"] = @((BOOL)(startupState == HALO_MAP_DOWNLOAD_PENDING));
        NSMutableArray *replayProgress = [NSMutableArray array];
        NSError *replayError = nil;
        NSURL *replayed = assemble(package, dataRoot, support, helpers, tools, replayProgress, &replayError);
        BOOL reused = replayed && [replayed.path isEqual:map.path] &&
            [fileDigest(replayed, nil) isEqual:digest] && !replayProgress.count;
        report[@"exact_replay_reused"] = @(reused);
        report[@"replay_progress"] = replayProgress;
        NSURL *parent = support.URLByDeletingLastPathComponent;
        NSURL *tamperSupport = [parent URLByAppendingPathComponent:@"tamper-support" isDirectory:YES];
        [NSFileManager.defaultManager createDirectoryAtURL:tamperSupport withIntermediateDirectories:NO attributes:nil error:&error];
        NSURL *library = [support URLByAppendingPathComponent:@"Community Maps" isDirectory:YES];
        NSURL *tamperLibrary = [tamperSupport URLByAppendingPathComponent:@"Community Maps" isDirectory:YES];
        BOOL copied = !error && [NSFileManager.defaultManager copyItemAtURL:library toURL:tamperLibrary error:&error];
        NSURL *tampered = [tamperLibrary URLByAppendingPathComponent:[@"maps/" stringByAppendingString:[name stringByAppendingString:@".map"]]];
        BOOL mutated = copied && mutateMap(tampered);
        HaloMapDownloads *tamper = mutated ? manager(tamperSupport, dataRoot) : nil;
        NSError *tamperError = nil;
        // The rejected registration callback also acts as a barrier after startup
        // receipt validation, so UNAVAILABLE is not a premature async observation.
        BOOL invalidRegistration = tamper && !registerMap(tamper, tampered, manifest, &tamperError) && tamperError;
        BOOL tamperRefused = invalidRegistration && [tamper requestMap:name] != HALO_MAP_DOWNLOAD_READY;
        report[@"tampered_copy_not_ready"] = @(tamperRefused);
        report[@"tampered_copy_registration_refused"] = @(invalidRegistration);
        report[@"tampered_copy_file"] = mutated ? fileDigest(tampered, nil) : @{};
        NSURL *conflictSupport = [parent URLByAppendingPathComponent:@"conflict-support" isDirectory:YES];
        NSURL *conflictMaps = [conflictSupport URLByAppendingPathComponent:@"Community Maps/maps" isDirectory:YES];
        NSError *conflictError = nil;
        BOOL created = [NSFileManager.defaultManager createDirectoryAtURL:conflictMaps withIntermediateDirectories:YES attributes:nil error:&conflictError];
        NSURL *conflict = [conflictMaps URLByAppendingPathComponent:[name stringByAppendingString:@".map"]];
        NSData *authoredConflict = [@"Authored conflicting map bytes; never original game assets.\n" dataUsingEncoding:NSUTF8StringEncoding];
        created = created && [authoredConflict writeToURL:conflict options:NSDataWritingWithoutOverwriting error:&conflictError];
        NSDictionary *conflictBefore = created ? fileDigest(conflict, nil) : nil;
        NSMutableArray *conflictProgress = [NSMutableArray array];
        NSURL *conflictResult = created ? assemble(package, dataRoot, conflictSupport, helpers, tools, conflictProgress, &conflictError) : nil;
        BOOL conflictPreserved = created && !conflictResult && conflictError &&
            [fileDigest(conflict, nil) isEqual:conflictBefore] && !conflictProgress.count;
        report[@"conflicting_map_preserved"] = @(conflictPreserved);
        report[@"conflict_error"] = conflictError.localizedDescription ?: @"";
        NSURL *removedSupport = [parent URLByAppendingPathComponent:@"removed-support" isDirectory:YES];
        NSError *removedError = nil;
        BOOL removedCopied = [NSFileManager.defaultManager createDirectoryAtURL:removedSupport withIntermediateDirectories:NO attributes:nil error:&removedError] &&
            [NSFileManager.defaultManager copyItemAtURL:library
                toURL:[removedSupport URLByAppendingPathComponent:@"Community Maps" isDirectory:YES] error:&removedError];
        NSMutableDictionary *mockConfiguration = [offlineConfiguration() mutableCopy];
        mockConfiguration[@"catalog_url"] = @"https://package-smoke.invalid/catalog.json";
        mockConfiguration[@"objects_base_url"] = @"https://package-smoke.invalid/";
        mockConfiguration[@"allowed_origins"] = @[@"https://package-smoke.invalid"];
        NSURLSessionConfiguration *mockSession = NSURLSessionConfiguration.ephemeralSessionConfiguration;
        mockSession.protocolClasses = @[HaloPackageOfflineGuard.class];
        HaloMapDownloads *removed = removedCopied ? [[HaloMapDownloads alloc] initWithSupportDirectory:removedSupport
            configuration:mockConfiguration sessionConfiguration:mockSession] : nil;
        [removed setGameDataRoot:dataRoot]; [removed startEnabled:NO];
        BOOL removalStartedReady = removed && waitReady(removed, name);
        NSURL *removedFile = [removed.mapsDirectory URLByAppendingPathComponent:[name stringByAppendingString:@".map"]];
        BOOL deleted = removalStartedReady && [NSFileManager.defaultManager removeItemAtURL:removedFile error:&removedError];
        if (deleted) [removed setDownloadsEnabled:YES];
        NSDate *removedDeadline = [NSDate dateWithTimeIntervalSinceNow:20];
        while (deleted && [removed requestMap:name] != HALO_MAP_DOWNLOAD_FAILED && removedDeadline.timeIntervalSinceNow > 0) pump();
        BOOL removedFailedSafely = deleted && [removed requestMap:name] == HALO_MAP_DOWNLOAD_FAILED;
        report[@"removed_local_map_failed_with_http_enabled"] = @(removedFailedSafely);
        NSString *missingHelp = removed.statusText ?: @"";
        BOOL reimportHelp = [missingHelp rangeOfString:@"re-import" options:NSCaseInsensitiveSearch].location != NSNotFound;
        report[@"missing_local_map_status"] = missingHelp;
        report[@"missing_local_map_reimport_help"] = @(reimportHelp);
        [removed cancelDownloads];
        NSDate *cancelDeadline = [NSDate dateWithTimeIntervalSinceNow:20];
        while (deleted && [removed requestMap:name] != HALO_MAP_DOWNLOAD_UNAVAILABLE && cancelDeadline.timeIntervalSinceNow > 0) pump();
        BOOL localMissingCancelled = deleted && [removed requestMap:name] == HALO_MAP_DOWNLOAD_UNAVAILABLE;
        report[@"missing_local_map_cancelled_to_unavailable"] = @(localMissingCancelled);
        [removed setDownloadsEnabled:NO];
        // Uppercase source names are tested with private byte copies. No source
        // hardlinks/symlinks are made and original map metadata stays untouched.
        NSURL *uppercaseData = [parent URLByAppendingPathComponent:@"uppercase-data" isDirectory:YES];
        NSURL *uppercaseMaps = [uppercaseData URLByAppendingPathComponent:@"MAPS" isDirectory:YES];
        NSError *caseError = nil;
        BOOL uppercaseCopied = [NSFileManager.defaultManager createDirectoryAtURL:uppercaseMaps withIntermediateDirectories:YES attributes:nil error:&caseError];
        NSURL *sourceMaps = [dataRoot URLByAppendingPathComponent:@"maps" isDirectory:YES];
        for (NSDictionary *entry in manifest[@"stock_inputs"]) {
            NSURL *source = [sourceMaps URLByAppendingPathComponent:[entry[@"name"] stringByAppendingString:@".map"]];
            NSURL *target = [uppercaseMaps URLByAppendingPathComponent:[[entry[@"name"] stringByAppendingString:@".map"] uppercaseString]];
            uppercaseCopied = uppercaseCopied && [NSFileManager.defaultManager copyItemAtURL:source toURL:target error:&caseError];
        }
        NSMutableArray *uppercaseProgress = [NSMutableArray array];
        NSURL *uppercaseReplay = uppercaseCopied ? assemble(package, uppercaseData, support, helpers, tools, uppercaseProgress, &caseError) : nil;
        BOOL uppercaseAccepted = uppercaseReplay && [uppercaseReplay.path isEqual:map.path] && !uppercaseProgress.count;
        report[@"uppercase_stock_paths_accepted"] = @(uppercaseAccepted);
        NSURL *duplicate = [uppercaseMaps URLByAppendingPathComponent:@"ui.map"];
        int duplicateFD = open(duplicate.fileSystemRepresentation, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0600);
        BOOL caseCollisionPassed = duplicateFD < 0 && errno == EEXIST;
        if (duplicateFD >= 0) {
            const char authored[] = "authored duplicate-name fixture";
            BOOL duplicateWritten = write(duplicateFD, authored, sizeof(authored)) == sizeof(authored);
            close(duplicateFD);
            NSError *duplicateError = nil;
            NSMutableArray *duplicateProgress = [NSMutableArray array];
            NSURL *duplicateResult = duplicateWritten ? assemble(package, uppercaseData, support, helpers, tools, duplicateProgress, &duplicateError) : nil;
            caseCollisionPassed = duplicateWritten && !duplicateResult && duplicateError && !duplicateProgress.count;
            report[@"case_collision_test"] = @"ambiguous source names rejected";
            report[@"case_collision_rejected"] = @(caseCollisionPassed);
        } else {
            report[@"case_collision_test"] = @"case-insensitive volume cannot create duplicate names; existing uppercase copy preserved";
            report[@"case_collision_tested"] = @NO;
        }
        report[@"package_unchanged"] = @([fileDigest(package, nil) isEqual:packageBefore]);
        report[@"assembled_file_unchanged"] = @([fileDigest(map, nil) isEqual:digest]);
        NSUInteger attempts;
        @synchronized(HaloPackageOfflineGuard.class) { attempts = networkAttempts; }
        report[@"network_attempts"] = @(attempts);
        @synchronized(HaloPackageOfflineGuard.class) { report[@"mock_catalog_requests"] = @(mockCatalogRequests); }
        BOOL success = exact && receiptValid && offlineReady && !offline.configured && !offline.enabled &&
            halo_map_download_request(name.UTF8String) == HALO_MAP_DOWNLOAD_READY && reused &&
            startupState == HALO_MAP_DOWNLOAD_PENDING && tamperRefused && conflictPreserved && removedFailedSafely &&
            reimportHelp && localMissingCancelled && uppercaseAccepted && caseCollisionPassed && !attempts && [report[@"package_unchanged"] boolValue] &&
            [report[@"assembled_file_unchanged"] boolValue];
        if (!success) report[@"error"] = error.localizedDescription ?: replayError.localizedDescription ?: @"A local receipt/replay/tamper/conflict check failed";
        return writeReport(report, reportURL, success);
    }
}
