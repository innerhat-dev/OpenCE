#import <Foundation/Foundation.h>

/* User data stays outside the signed app and survives an application update. */
@interface HaloPreferences : NSObject
@property(nonatomic, readonly) NSURL *supportDirectory;
@property(nonatomic, readonly) NSString *dataPath;
@property(nonatomic, readonly) NSString *isoPath;
@property(nonatomic, readonly) BOOL windowed;
@property(nonatomic, readonly) BOOL communityDownloadsEnabled;
- (instancetype)initWithSupportDirectory:(NSURL *)directory;
- (BOOL)selectDataRoot:(NSURL *)root iso:(NSURL *)iso error:(NSError **)error;
- (BOOL)setWindowed:(BOOL)windowed error:(NSError **)error;
- (BOOL)setCommunityDownloadsEnabled:(BOOL)enabled error:(NSError **)error;
@end

/* Accept the extracted game directory or its maps subdirectory. Header checks
   establish the supported format, not a claim of complete gameplay parity. */
NSURL *HaloValidateGameData(NSURL *selection, NSError **error);
NSURL *HaloImportDiscImage(NSURL *image, NSURL *supportDirectory,
                          void (*progress)(void *, const char *, unsigned long long, unsigned long long),
                          void *context, NSError **error);
unsigned long long HaloGameDataCopySize(NSURL *root, NSError **error);
NSURL *HaloCopyGameData(NSURL *root, NSURL *supportDirectory,
                       void (*progress)(void *, const char *, unsigned long long, unsigned long long),
                       void *context, NSError **error);
BOOL HaloUpdateConfigurationIsValid(NSDictionary *info);

/* Launch migration is eligible only for the canonical default support folder,
   never a HALO_SAVE_ROOT override. The copy helper is separately fixtureable.
   Existing destination files/settings and the complete legacy tree survive. */
BOOL HaloSupportDirectoryNeedsMigration(NSURL *directory);
BOOL HaloMigrateLegacySupportDirectory(NSURL *legacy, NSURL *destination,
    void (*progress)(void *, const char *, unsigned long long, unsigned long long),
    void *context, NSError **error);
