#ifndef HALO_MAP_DOWNLOADS_H
#define HALO_MAP_DOWNLOADS_H
#include <stddef.h>
enum halo_map_download_status {
    HALO_MAP_DOWNLOAD_FAILED = -1,
    HALO_MAP_DOWNLOAD_UNAVAILABLE = 0,
    HALO_MAP_DOWNLOAD_READY = 1,
    HALO_MAP_DOWNLOAD_PENDING = 2
};
/* These guest-facing hooks consult cached state/schedule work, never read files
   or wait for HTTP. The directory already includes the maps component. */
int halo_map_download_directory(char *out, size_t capacity);
int halo_map_download_request(const char *map_name);

#ifdef __OBJC__
#import <Foundation/Foundation.h>
@interface HaloMapDownloads : NSObject <NSURLSessionDataDelegate>
@property(nonatomic, readonly) NSURL *mapsDirectory;
@property(nonatomic, readonly) BOOL configured;
@property(nonatomic, readonly) BOOL enabled;
@property(nonatomic, readonly) BOOL compatibleData;
@property(nonatomic, readonly) NSString *statusText;
@property(nonatomic, copy) void (^statusChanged)(void);
- (instancetype)initWithSupportDirectory:(NSURL *)support configuration:(NSDictionary *)configuration
                    sessionConfiguration:(NSURLSessionConfiguration *)sessionConfiguration;
- (void)startEnabled:(BOOL)enabled;
- (void)setGameDataRoot:(NSURL *)root;
- (void)setDownloadsEnabled:(BOOL)enabled;
- (void)checkForMaps;
- (void)cancelDownloads;
- (int)requestMap:(NSString *)name;
- (void)activateForHost;
/* Local reconstruction is usable offline, independently of HTTP consent. */
- (void)registerAssembledMap:(NSURL *)file manifest:(NSDictionary *)manifest
                 completion:(void (^)(NSError *error))completion;
@end
BOOL HaloDownloadConfigurationIsValid(NSDictionary *configuration);
NSDictionary *HaloValidateMapCatalog(NSData *data, NSDictionary *configuration, NSError **error);
BOOL HaloVerifyDownloadedMap(NSURL *file, NSDictionary *entry, NSDictionary *configuration, NSError **error);
#endif
#endif
