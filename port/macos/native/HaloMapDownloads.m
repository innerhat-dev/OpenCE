#import "HaloMapDownloads.h"
#include <CommonCrypto/CommonDigest.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

static HaloMapDownloads *hostDownloads;
static NSError *downloadError(NSString *message) {
    return [NSError errorWithDomain:@"HaloMapDownloads" code:1 userInfo:@{NSLocalizedDescriptionKey:message}];
}
static NSString *origin(NSURL *url) {
    if (![url.scheme.lowercaseString isEqualToString:@"https"] || !url.host.length || url.user || url.password) return nil;
    return [NSString stringWithFormat:@"https://%@%@", url.host.lowercaseString,
            url.port && url.port.integerValue != 443 ? [@":" stringByAppendingString:url.port.stringValue] : @""];
}
static BOOL allowedURL(NSURL *url, NSDictionary *config) {
    NSString *value = origin(url);
    if (!value || url.fragment) return NO;
    for (id allowed in config[@"allowed_origins"]) {
        if ([allowed isKindOfClass:NSString.class] && [value isEqualToString:allowed]) return YES;
    }
    return NO;
}
static BOOL numberInRange(id value, unsigned long long maximum) {
    return [value isKindOfClass:NSNumber.class] && strcmp([value objCType], @encode(BOOL)) &&
        [value doubleValue] >= 1 && [value doubleValue] <= maximum &&
        [value doubleValue] == [value unsignedLongLongValue];
}
static BOOL mapNameIsValid(NSString *name) {
    if (![name isKindOfClass:NSString.class] || name.length < 1 || name.length > 31) return NO;
    NSCharacterSet *letters = [NSCharacterSet characterSetWithCharactersInString:@"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_ -"];
    if ([name rangeOfCharacterFromSet:letters.invertedSet].location != NSNotFound) return NO;
    static NSSet *reserved;
    static dispatch_once_t once;
    dispatch_once(&once, ^{ reserved = [NSSet setWithArray:@[@"ui", @"a10", @"a30", @"a50", @"b30", @"b40", @"c10", @"c20", @"c40", @"d20", @"d40",
        @"beavercreek", @"sidewinder", @"damnation", @"ratrace", @"prisoner", @"hangemhigh", @"chillout", @"carousel", @"boardingaction", @"bloodgulch", @"wizard", @"putput", @"longest"]]; });
    return ![reserved containsObject:name.lowercaseString];
}
static BOOL hashIsValid(id hash) {
    return [hash isKindOfClass:NSString.class] && [hash length] == 64 &&
        [hash rangeOfCharacterFromSet:[NSCharacterSet characterSetWithCharactersInString:@"0123456789abcdef"].invertedSet].location == NSNotFound;
}
BOOL HaloDownloadConfigurationIsValid(NSDictionary *config) {
    if (![config isKindOfClass:NSDictionary.class] || ![config[@"schema_version"] isEqual:@1] ||
        ![config[@"profile"] isEqual:@"stock-xbox-ntsc"] || ![config[@"cache_build"] isEqual:@"01.10.12.2276"] ||
        ![config[@"allowed_origins"] isKindOfClass:NSArray.class] ||
        !numberInRange(config[@"max_catalog_bytes"], 1048576) || !numberInRange(config[@"max_map_bytes"], 134217728) ||
        !numberInRange(config[@"max_cache_bytes"], 134217728) || !numberInRange(config[@"max_tag_bytes"], 23068672) ||
        !numberInRange(config[@"max_maps"], 115)) return NO;
    id catalog = config[@"catalog_url"], base = config[@"objects_base_url"];
    if (!catalog || catalog == NSNull.null) return (!base || base == NSNull.null) && [config[@"allowed_origins"] count] == 0;
    if (![catalog isKindOfClass:NSString.class] || ![base isKindOfClass:NSString.class]) return NO;
    NSURL *catalogURL = [NSURL URLWithString:catalog], *baseURL = [NSURL URLWithString:base];
    return allowedURL(catalogURL, config) && allowedURL(baseURL, config) && !catalogURL.query && !baseURL.query;
}
NSDictionary *HaloValidateMapCatalog(NSData *data, NSDictionary *config, NSError **error) {
    if (!HaloDownloadConfigurationIsValid(config) || data.length > [config[@"max_catalog_bytes"] unsignedLongLongValue]) {
        if (error) *error = downloadError(@"The map catalog exceeds this build's limits.");
        return nil;
    }
    id catalog = [NSJSONSerialization JSONObjectWithData:data options:0 error:error];
    if (![catalog isKindOfClass:NSDictionary.class] || ![catalog[@"schema_version"] isEqual:@1] ||
        ![catalog[@"profile"] isEqual:config[@"profile"]] || ![catalog[@"maps"] isKindOfClass:NSArray.class] ||
        [catalog[@"maps"] count] > [config[@"max_maps"] unsignedIntegerValue]) {
        if (error) *error = downloadError(@"The map catalog is incompatible with this build.");
        return nil;
    }
    NSMutableDictionary *entries = [NSMutableDictionary dictionary];
    for (id entry in catalog[@"maps"]) {
        NSString *name = [entry isKindOfClass:NSDictionary.class] ? entry[@"id"] : nil;
        BOOL valid = mapNameIsValid(name) && [name isEqual:name.lowercaseString] && hashIsValid(entry[@"sha256"]) && !entries[name.lowercaseString] &&
            numberInRange(entry[@"file_bytes"], [config[@"max_map_bytes"] unsignedLongLongValue]) &&
            [entry[@"file_bytes"] unsignedLongLongValue] >= 2048 && [entry[@"cache_version"] isEqual:@5] &&
            [entry[@"cache_build"] isEqual:config[@"cache_build"]] && [entry[@"scenario_type"] isEqual:@1];
        NSString *key = valid ? [NSString stringWithFormat:@"maps/sha256/%@/%@.map", entry[@"sha256"], name] : nil;
        if (!valid || ![entry[@"object_key"] isEqual:key] ||
            (entry[@"prefetch"] && ![entry[@"prefetch"] isKindOfClass:NSNumber.class])) {
            if (error) *error = downloadError(@"The map catalog contains an unsafe, duplicate or unsupported map.");
            return nil;
        }
        entries[name.lowercaseString] = entry;
    }
    return entries;
}
static uint32_t little32(const unsigned char *p) {
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}
BOOL HaloVerifyDownloadedMap(NSURL *file, NSDictionary *entry, NSDictionary *config, NSError **error) {
    int descriptor = open(file.fileSystemRepresentation, O_RDONLY | O_NOFOLLOW);
    struct stat info;
    unsigned char header[2048];
    BOOL valid = HaloDownloadConfigurationIsValid(config) && descriptor >= 0 && !fstat(descriptor, &info) && S_ISREG(info.st_mode) &&
        [entry[@"file_bytes"] unsignedLongLongValue] <= [config[@"max_map_bytes"] unsignedLongLongValue] &&
        info.st_size >= 0 && (unsigned long long)info.st_size == [entry[@"file_bytes"] unsignedLongLongValue] && read(descriptor, header, sizeof(header)) == sizeof(header);
    if (valid) {
        const unsigned char *nameEnd = memchr(header + 32, 0, 32), *buildEnd = memchr(header + 64, 0, 32);
        NSString *name = nameEnd ? [[NSString alloc] initWithBytes:header + 32 length:nameEnd - header - 32 encoding:NSASCIIStringEncoding] : nil;
        NSString *build = buildEnd ? [[NSString alloc] initWithBytes:header + 64 length:buildEnd - header - 64 encoding:NSASCIIStringEncoding] : nil;
        uint32_t declared = little32(header + 8), tagOffset = little32(header + 16), tagSize = little32(header + 20);
        valid = !memcmp(header, "daeh", 4) && !memcmp(header + 2044, "toof", 4) && little32(header + 4) == 5 &&
            header[96] == 1 && header[97] == 0 && [name.lowercaseString isEqual:[entry[@"id"] lowercaseString]] &&
            [build isEqual:entry[@"cache_build"]] && declared >= 2048 && declared <= [config[@"max_cache_bytes"] unsignedLongLongValue] &&
            tagSize <= [config[@"max_tag_bytes"] unsignedLongLongValue] &&
            tagOffset >= 2048 && (uint64_t)tagOffset + tagSize <= declared;
        /* v5 caches can be compressed; declared bytes describe decompressed
           cache size. The catalog's transfer length and SHA authenticate the
           exact complete file; do not mistake transfer length for cache size. */
    }
    CC_SHA256_CTX context;
    CC_SHA256_Init(&context);
    if (valid) {
        CC_SHA256_Update(&context, header, sizeof(header));
        unsigned char bytes[65536];
        ssize_t count;
        while ((count = read(descriptor, bytes, sizeof(bytes))) > 0) CC_SHA256_Update(&context, bytes, (CC_LONG)count);
        valid = count == 0;
        unsigned char digest[CC_SHA256_DIGEST_LENGTH];
        CC_SHA256_Final(digest, &context);
        NSMutableString *hash = [NSMutableString string];
        for (unsigned i = 0; i < sizeof(digest); i++) [hash appendFormat:@"%02x", digest[i]];
        valid = valid && [hash isEqual:entry[@"sha256"]];
    }
    if (descriptor >= 0) close(descriptor);
    if (!valid && error) *error = downloadError(@"The downloaded map failed its size, SHA-256 or Xbox v5 compatibility check.");
    return valid;
}

@interface HaloMapTransfer : NSObject
@property(nonatomic) BOOL catalog;
@property(nonatomic) BOOL accepted;
@property(nonatomic, strong) NSDictionary *entry;
@property(nonatomic, strong) NSMutableData *data;
@property(nonatomic, strong) NSURL *partial;
@property(nonatomic) int descriptor;
@property(nonatomic) unsigned long long received;
@property(nonatomic, strong) NSError *failure;
@property(nonatomic, strong) NSURLSessionTask *task;
@property(nonatomic) BOOL cancelled;
@end
@implementation HaloMapTransfer
@end

@implementation HaloMapDownloads {
    NSURL *_support, *_library, *_partials;
    NSDictionary *_configuration;
    NSURLSession *_session;
    dispatch_queue_t _work;
    NSMutableDictionary<NSNumber *, HaloMapTransfer *> *_transfers;
    NSDictionary<NSString *, NSDictionary *> *_entries;
    NSMutableDictionary<NSString *, NSNumber *> *_states;
    NSMutableDictionary<NSString *, NSString *> *_failures;
    NSMutableOrderedSet<NSString *> *_requests;
    BOOL _catalogPending, _catalogFailed, _refreshRequested, _initializing, _mapPending, _enabled, _configured, _cancelled, _compatibleData;
    NSString *_statusText;
}
- (instancetype)initWithSupportDirectory:(NSURL *)support configuration:(NSDictionary *)config
                    sessionConfiguration:(NSURLSessionConfiguration *)sessionConfiguration {
    if ((self = [super init])) {
        _support = support.URLByStandardizingPath.URLByResolvingSymlinksInPath;
        _library = [_support URLByAppendingPathComponent:@"Community Maps" isDirectory:YES];
        _mapsDirectory = [_library URLByAppendingPathComponent:@"maps" isDirectory:YES];
        _partials = [_library URLByAppendingPathComponent:@"Downloads" isDirectory:YES];
        _configuration = [config copy];
        _configured = HaloDownloadConfigurationIsValid(config) && [config[@"catalog_url"] isKindOfClass:NSString.class];
        _statusText = _configured ? @"Community downloads are off." : @"Map hosting is not configured for this build.";
        _work = dispatch_queue_create("com.pfista.halo.maps", DISPATCH_QUEUE_SERIAL);
        _states = [NSMutableDictionary dictionary];
        _failures = [NSMutableDictionary dictionary];
        _transfers = [NSMutableDictionary dictionary];
        _requests = [NSMutableOrderedSet orderedSet];
        _entries = @{};
        NSOperationQueue *delegates = [[NSOperationQueue alloc] init];
        delegates.maxConcurrentOperationCount = 1;
        NSURLSessionConfiguration *session = sessionConfiguration ?: NSURLSessionConfiguration.ephemeralSessionConfiguration;
        session.timeoutIntervalForRequest = 30;
        session.timeoutIntervalForResource = 600;
        session.URLCache = nil;
        _session = [NSURLSession sessionWithConfiguration:session delegate:self delegateQueue:delegates];
    }
    return self;
}
- (BOOL)configured { return _configured; }
- (BOOL)enabled { @synchronized(self) { return _enabled; } }
- (BOOL)compatibleData { @synchronized(self) { return _compatibleData; } }
- (NSString *)statusText {
    @synchronized(self) {
        NSString *key = [[_failures.allKeys sortedArrayUsingSelector:@selector(compare:)] firstObject];
        NSString *failure = key ? _failures[key] : nil;
        return failure && ![_statusText containsString:failure]
            ? [NSString stringWithFormat:@"%@\n%@", failure, _statusText] : _statusText;
    }
}
- (void)status:(NSString *)text {
    @synchronized(self) { _statusText = [text copy]; }
    dispatch_async(dispatch_get_main_queue(), ^{ if (self.statusChanged) self.statusChanged(); });
}
- (void)activateForHost { hostDownloads = self; }
- (void)setGameDataRoot:(NSURL *)root {
    /* Called before the engine starts. Changing the next-launch preference
       never switches the current session's content profile. */
    NSURL *maps = nil, *ui = nil;
    for (NSURL *file in [NSFileManager.defaultManager contentsOfDirectoryAtURL:root includingPropertiesForKeys:nil options:0 error:nil])
        if ([file.lastPathComponent.lowercaseString isEqual:@"maps"]) maps = file;
    for (NSURL *file in maps ? [NSFileManager.defaultManager contentsOfDirectoryAtURL:maps includingPropertiesForKeys:nil options:0 error:nil] : @[])
        if ([file.lastPathComponent.lowercaseString isEqual:@"ui.map"]) ui = file;
    NSFileHandle *file = [NSFileHandle fileHandleForReadingFromURL:ui error:nil];
    NSData *header = [file readDataUpToLength:2048 error:nil];
    [file closeFile];
    NSString *build = nil;
    if (header.length == 2048) {
        const unsigned char *bytes = header.bytes, *end = memchr(bytes + 64, 0, 32);
        if (end) build = [[NSString alloc] initWithBytes:bytes + 64 length:end - bytes - 64 encoding:NSASCIIStringEncoding];
    }
    @synchronized(self) { _compatibleData = [build isEqual:_configuration[@"cache_build"]]; }
    if (!self.compatibleData && _configured) [self status:@"This map collection needs original Xbox NTSC 2276 game data. Your current maps stay unchanged."];
}
- (BOOL)prepareDirectories:(NSError **)error {
    for (NSURL *directory in @[_library, _mapsDirectory, _partials]) {
        struct stat info;
        if (!lstat(directory.fileSystemRepresentation, &info) && !S_ISDIR(info.st_mode)) {
            if (error) *error = downloadError(@"The managed map folder contains a link or file where a directory is required.");
            return NO;
        }
        if (![NSFileManager.defaultManager createDirectoryAtURL:directory withIntermediateDirectories:YES attributes:nil error:error]) return NO;
    }
    return YES;
}
- (void)startEnabled:(BOOL)enabled {
    @synchronized(self) { _enabled = enabled; _initializing = _configured; }
    dispatch_async(_work, ^{
        if (!self->_configured || !self.compatibleData) { @synchronized(self) { self->_initializing = NO; } return; }
        NSError *error = nil;
        if (![self prepareDirectories:&error]) {
            @synchronized(self) { self->_initializing = NO; self->_catalogFailed = YES; }
            [self status:error.localizedDescription]; return;
        }
        NSURL *cached = [self->_library URLByAppendingPathComponent:@"catalog.json"];
        NSData *bytes = [NSData dataWithContentsOfURL:cached options:NSDataReadingMappedIfSafe error:nil];
        if (bytes) {
            NSDictionary *record = [NSJSONSerialization JSONObjectWithData:bytes options:0 error:nil];
            if ([record isKindOfClass:NSDictionary.class] && [record[@"catalog_url"] isEqual:self->_configuration[@"catalog_url"]]) {
                NSData *catalog = [NSJSONSerialization dataWithJSONObject:record[@"catalog"] ?: @{} options:0 error:nil];
                NSDictionary *entries = HaloValidateMapCatalog(catalog, self->_configuration, nil);
                if (entries) [self acceptCatalog:entries];
            }
        }
        if (self.enabled) [self fetchCatalog];
        @synchronized(self) { self->_initializing = NO; }
    });
}
- (void)setDownloadsEnabled:(BOOL)enabled {
    @synchronized(self) { _enabled = enabled; }
    if (enabled) [self checkForMaps];
    else [self cancelDownloads];
}
- (void)checkForMaps {
    dispatch_async(_work, ^{
        @synchronized(self) {
            self->_cancelled = NO; self->_catalogFailed = NO;
            [self->_failures removeObjectForKey:@"_catalog"];
        }
        if (!self->_configured) { [self status:@"Map hosting is not configured for this build."]; return; }
        if (!self.compatibleData) { [self status:@"This map collection requires Xbox NTSC 2276 game data."]; return; }
        if (!self.enabled) { [self status:@"Enable community downloads to check for maps."]; return; }
        @synchronized(self) {
            for (NSString *name in self->_states.allKeys) if (self->_states[name].intValue == HALO_MAP_DOWNLOAD_FAILED) {
                [self->_states removeObjectForKey:name];
                [self->_failures removeObjectForKey:name];
                [self->_requests addObject:name];
            }
        }
        if (self->_catalogPending) self->_refreshRequested = YES;
        else [self fetchCatalog];
    });
}
- (void)cancelDownloads {
    dispatch_async(_work, ^{
        @synchronized(self) {
            self->_cancelled = YES; self->_catalogFailed = NO;
            [self->_failures removeAllObjects];
        }
        self->_refreshRequested = NO;
        for (HaloMapTransfer *transfer in self->_transfers.allValues) { transfer.cancelled = YES; [transfer.task cancel]; }
        [self->_requests removeAllObjects];
        @synchronized(self) {
            for (NSString *name in self->_states.allKeys) if (self->_states[name].intValue != HALO_MAP_DOWNLOAD_READY)
                [self->_states removeObjectForKey:name];
        }
        [self status:@"Map downloads cancelled. Use Check Maps to retry."];
    });
}
- (int)requestMap:(NSString *)name {
    if (!mapNameIsValid(name) || !self.compatibleData) return HALO_MAP_DOWNLOAD_UNAVAILABLE;
    NSString *key = name.lowercaseString;
    @synchronized(self) {
        NSNumber *state = _states[key];
        if (state.intValue == HALO_MAP_DOWNLOAD_READY) return HALO_MAP_DOWNLOAD_READY;
        if (!_enabled || !_configured || _cancelled) return HALO_MAP_DOWNLOAD_UNAVAILABLE;
        if (state) return state.intValue;
        if (!_entries[key]) return _catalogPending || _initializing ? HALO_MAP_DOWNLOAD_PENDING :
            _catalogFailed ? HALO_MAP_DOWNLOAD_FAILED : HALO_MAP_DOWNLOAD_UNAVAILABLE;
        _states[key] = @(HALO_MAP_DOWNLOAD_PENDING);
    }
    dispatch_async(_work, ^{ [self->_requests addObject:key]; [self nextMap]; });
    return HALO_MAP_DOWNLOAD_PENDING;
}
- (void)acceptCatalog:(NSDictionary *)entries {
    @synchronized(self) {
        _entries = entries;
        for (NSString *name in _states.allKeys) {
            if (!entries[name] || _states[name].intValue == HALO_MAP_DOWNLOAD_READY) {
                [_states removeObjectForKey:name]; [_failures removeObjectForKey:name];
            }
        }
    }
    for (NSString *name in entries) {
        NSDictionary *entry = entries[name];
        NSURL *file = [_mapsDirectory URLByAppendingPathComponent:[entry[@"id"] stringByAppendingPathExtension:@"map"]];
        struct stat info;
        if (!lstat(file.fileSystemRepresentation, &info)) {
            NSError *error = nil;
            BOOL valid = HaloVerifyDownloadedMap(file, entry, _configuration, &error);
            NSString *message = [NSString stringWithFormat:@"%@ conflicts with an existing map. Keep that file or move it manually before retrying.", entry[@"id"]];
            @synchronized(self) {
                _states[name] = @(valid ? HALO_MAP_DOWNLOAD_READY : HALO_MAP_DOWNLOAD_FAILED);
                if (valid) [_failures removeObjectForKey:name]; else _failures[name] = message;
            }
            if (!valid) [self status:message];
        }
        if (self.enabled && [entry[@"prefetch"] boolValue]) [self requestMap:name];
    }
}
- (void)fetchCatalog {
    if (_catalogPending || _cancelled || !self.enabled) return;
    NSError *error = nil;
    if (![self prepareDirectories:&error]) {
        @synchronized(self) { _catalogFailed = YES; }
        [self status:error.localizedDescription]; return;
    }
    @synchronized(self) { _catalogPending = YES; }
    [self status:@"Checking approved community maps…"];
    HaloMapTransfer *transfer = [[HaloMapTransfer alloc] init];
    transfer.catalog = YES;
    transfer.descriptor = -1;
    transfer.data = [NSMutableData data];
    NSURLSessionDataTask *task = [_session dataTaskWithURL:[NSURL URLWithString:_configuration[@"catalog_url"]]];
    transfer.task = task;
    _transfers[@(task.taskIdentifier)] = transfer;
    [task resume];
}
- (void)nextMap {
    if (_mapPending || _catalogPending || _cancelled || !self.enabled) return;
    NSString *name = _requests.firstObject;
    if (!name) return;
    [_requests removeObject:name];
    NSDictionary *entry = _entries[name];
    if (!entry) {
        @synchronized(self) { [_states removeObjectForKey:name]; }
        [self nextMap]; return;
    }
    @synchronized(self) { if (_states[name].intValue == HALO_MAP_DOWNLOAD_READY) { [self nextMap]; return; } }
    NSError *error = nil;
    if (![self prepareDirectories:&error]) { [self failMap:name message:error.localizedDescription]; return; }
    NSURL *destination = [_mapsDirectory URLByAppendingPathComponent:[entry[@"id"] stringByAppendingPathExtension:@"map"]];
    struct stat info;
    if (!lstat(destination.fileSystemRepresentation, &info)) {
        if (HaloVerifyDownloadedMap(destination, entry, _configuration, &error)) {
            @synchronized(self) { _states[name] = @(HALO_MAP_DOWNLOAD_READY); }
            [self nextMap]; return;
        }
        [self failMap:name message:@"An existing map has different bytes. It was left unchanged; move it manually before retrying."]; return;
    }
    NSNumber *free = nil;
    [_library getResourceValue:&free forKey:NSURLVolumeAvailableCapacityKey error:nil];
    if (free && free.unsignedLongLongValue < [entry[@"file_bytes"] unsignedLongLongValue] + 1048576) {
        [self failMap:name message:@"There is not enough free space to download this map."]; return;
    }
    HaloMapTransfer *transfer = [[HaloMapTransfer alloc] init];
    transfer.entry = entry;
    transfer.partial = [_partials URLByAppendingPathComponent:[NSString stringWithFormat:@"%@-%@.partial", entry[@"sha256"], NSUUID.UUID.UUIDString]];
    transfer.descriptor = open(transfer.partial.fileSystemRepresentation, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0600);
    if (transfer.descriptor < 0) { [self failMap:name message:@"The download staging file could not be created."]; return; }
    NSURL *url = [[NSURL URLWithString:_configuration[@"objects_base_url"]] URLByAppendingPathComponent:entry[@"object_key"]];
    if (!allowedURL(url, _configuration)) { close(transfer.descriptor); unlink(transfer.partial.fileSystemRepresentation); [self failMap:name message:@"The map URL is not an approved HTTPS origin."]; return; }
    _mapPending = YES;
    @synchronized(self) { _states[name] = @(HALO_MAP_DOWNLOAD_PENDING); }
    [self status:[NSString stringWithFormat:@"Downloading %@…", entry[@"id"]]];
    NSURLSessionDataTask *task = [_session dataTaskWithURL:url];
    transfer.task = task;
    _transfers[@(task.taskIdentifier)] = transfer;
    [task resume];
}
- (void)failMap:(NSString *)name message:(NSString *)message {
    NSString *failure = [NSString stringWithFormat:@"%@: %@ Use Check Maps to retry.", name, message];
    @synchronized(self) { _states[name] = @(HALO_MAP_DOWNLOAD_FAILED); _failures[name] = failure; }
    [self status:failure];
    [self nextMap];
}
- (void)URLSession:(NSURLSession *)session task:(NSURLSessionTask *)task
 willPerformHTTPRedirection:(NSHTTPURLResponse *)response newRequest:(NSURLRequest *)request
 completionHandler:(void (^)(NSURLRequest *))completion {
    (void)session; (void)task; (void)response;
    completion(allowedURL(request.URL, _configuration) ? request : nil);
}
- (void)URLSession:(NSURLSession *)session dataTask:(NSURLSessionDataTask *)task didReceiveResponse:(NSURLResponse *)response
 completionHandler:(void (^)(NSURLSessionResponseDisposition))completion {
    (void)session;
    dispatch_async(_work, ^{
        HaloMapTransfer *transfer = self->_transfers[@(task.taskIdentifier)];
        unsigned long long limit = transfer.catalog ? [self->_configuration[@"max_catalog_bytes"] unsignedLongLongValue] : [transfer.entry[@"file_bytes"] unsignedLongLongValue];
        transfer.accepted = [response isKindOfClass:NSHTTPURLResponse.class] && ((NSHTTPURLResponse *)response).statusCode == 200 &&
            allowedURL(response.URL, self->_configuration) && (response.expectedContentLength < 0 || (unsigned long long)response.expectedContentLength <= limit);
        if (!transfer.accepted) transfer.failure = downloadError(@"The server returned an unexpected response or file size.");
        completion(transfer.accepted ? NSURLSessionResponseAllow : NSURLSessionResponseCancel);
    });
}
- (void)URLSession:(NSURLSession *)session dataTask:(NSURLSessionDataTask *)task didReceiveData:(NSData *)data {
    (void)session;
    dispatch_async(_work, ^{
        HaloMapTransfer *transfer = self->_transfers[@(task.taskIdentifier)];
        if (!transfer || transfer.failure) return;
        unsigned long long limit = transfer.catalog ? [self->_configuration[@"max_catalog_bytes"] unsignedLongLongValue] : [transfer.entry[@"file_bytes"] unsignedLongLongValue];
        if (data.length > limit - transfer.received) { transfer.failure = downloadError(@"The server sent more bytes than the approved file size."); [task cancel]; return; }
        if (transfer.catalog) [transfer.data appendData:data];
        else {
            const char *bytes = data.bytes;
            NSUInteger offset = 0;
            while (offset < data.length) {
                ssize_t written = write(transfer.descriptor, bytes + offset, data.length - offset);
                if (written <= 0) { transfer.failure = downloadError(@"The map could not be written. Check free space."); [task cancel]; return; }
                offset += (NSUInteger)written;
            }
        }
        transfer.received += data.length;
        if (!transfer.catalog) [self status:[NSString stringWithFormat:@"%@ — %llu of %llu MB", transfer.entry[@"id"], transfer.received >> 20, limit >> 20]];
    });
}
- (void)URLSession:(NSURLSession *)session task:(NSURLSessionTask *)task didCompleteWithError:(NSError *)networkError {
    (void)session;
    dispatch_async(_work, ^{
        HaloMapTransfer *transfer = self->_transfers[@(task.taskIdentifier)];
        if (!transfer) return;
        [self->_transfers removeObjectForKey:@(task.taskIdentifier)];
        NSError *error = transfer.cancelled ? downloadError(@"Download cancelled.") : transfer.failure ?: networkError;
        if (transfer.catalog) {
            @synchronized(self) { self->_catalogPending = NO; }
            NSDictionary *entries = !error && transfer.accepted ? HaloValidateMapCatalog(transfer.data, self->_configuration, &error) : nil;
            if (entries) {
                NSDictionary *catalog = [NSJSONSerialization JSONObjectWithData:transfer.data options:0 error:nil];
                NSData *cached = [NSJSONSerialization dataWithJSONObject:@{@"catalog_url":self->_configuration[@"catalog_url"], @"catalog":catalog} options:0 error:&error];
                if (cached && [cached writeToURL:[self->_library URLByAppendingPathComponent:@"catalog.json"] options:NSDataWritingAtomic error:&error]) {
                    @synchronized(self) { self->_catalogFailed = NO; [self->_failures removeObjectForKey:@"_catalog"]; }
                    [self acceptCatalog:entries];
                    [self status:[NSString stringWithFormat:@"%lu approved maps available. Missing maps download when needed.", (unsigned long)entries.count]];
                }
            }
            if (error && !transfer.cancelled) {
                NSString *failure = [@"Map catalog unavailable: " stringByAppendingString:error.localizedDescription];
                @synchronized(self) { self->_catalogFailed = YES; self->_failures[@"_catalog"] = failure; }
                [self status:failure];
            }
        } else {
            self->_mapPending = NO;
            if (transfer.descriptor >= 0) {
                if (fsync(transfer.descriptor) && !error) error = downloadError(@"The map could not be saved to disk.");
                close(transfer.descriptor);
            }
            NSString *name = [transfer.entry[@"id"] lowercaseString];
            if (!error && ![self->_entries[name][@"sha256"] isEqual:transfer.entry[@"sha256"]])
                error = downloadError(@"The approved map revision changed during download. Retry with the current catalog.");
            if (!error && transfer.accepted && HaloVerifyDownloadedMap(transfer.partial, transfer.entry, self->_configuration, &error)) {
                NSURL *destination = [self->_mapsDirectory URLByAppendingPathComponent:[transfer.entry[@"id"] stringByAppendingPathExtension:@"map"]];
                /* link is atomic and exclusive; unlike rename it cannot replace
                   a file that appeared while the HTTP task was running. */
                if (!link(transfer.partial.fileSystemRepresentation, destination.fileSystemRepresentation) ||
                    HaloVerifyDownloadedMap(destination, transfer.entry, self->_configuration, nil)) {
                    @synchronized(self) { self->_states[name] = @(HALO_MAP_DOWNLOAD_READY); [self->_failures removeObjectForKey:name]; }
                    [self status:[NSString stringWithFormat:@"%@ is ready.", transfer.entry[@"id"]]];
                } else error = downloadError(@"The destination already exists or could not be created. Existing files were preserved.");
            }
            if (transfer.partial) unlink(transfer.partial.fileSystemRepresentation);
            if (error && !transfer.cancelled) [self failMap:name message:error.localizedDescription];
        }
        if (transfer.catalog && self->_refreshRequested && self.enabled && !self->_cancelled) {
            self->_refreshRequested = NO;
            [self fetchCatalog];
        }
        [self nextMap];
    });
}
@end

int halo_map_download_directory(char *out, size_t capacity) {
    if (!out || !capacity || !hostDownloads || !hostDownloads.compatibleData) return 0;
    return [hostDownloads.mapsDirectory.path getCString:out maxLength:capacity encoding:NSUTF8StringEncoding] ? 1 : 0;
}
int halo_map_download_request(const char *map_name) {
    if (!hostDownloads || !map_name) return HALO_MAP_DOWNLOAD_UNAVAILABLE;
    NSString *name = [[NSString alloc] initWithBytes:map_name length:strnlen(map_name, 32) encoding:NSASCIIStringEncoding];
    return [hostDownloads requestMap:name];
}
