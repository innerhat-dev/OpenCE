#ifndef HALO_MAP_PACKAGES_H
#define HALO_MAP_PACKAGES_H
#import <Foundation/Foundation.h>

/* Inspection authenticates all literal assets and does not create files. */
NSDictionary *HaloInspectCommunityPackage(NSURL *file, NSError **error);

/* Call on a worker queue. Only private work files and a verified, new map are
   written; original caches and existing installed maps are never replaced. */
NSURL *HaloAssembleCommunityPackage(NSURL *package, NSURL *gameDataRoot,
    NSURL *supportDirectory, NSURL *toolsDirectory, NSDictionary *toolsRecord,
    void (^progress)(NSString *), NSError **error);
#endif
