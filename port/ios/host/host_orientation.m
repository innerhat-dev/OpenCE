#import "host_orientation.h"
#include "host.h"
#include "../../apple/host_debug.h"

/* SDL 3.4.16 owns these controllers. These categories add only orientation
   preferences inherited from UIKit, never replace SDL's own methods. Recheck
   the selectors when upgrading SDL; no runtime class mutation is needed. */
@interface SDL_uikitviewcontroller : UIViewController
@end
@interface SDLLaunchScreenController : UIViewController
@end
@interface SDLUIKitSceneDelegate : NSObject <UIWindowSceneDelegate>
@end

/* Restrict the allowed orientations without locking the scene to whichever
   landscape side happened to win at launch. A scene lock also prevents the
   other supported landscape orientation from following the user's rotation. */
#define HALO_LANDSCAPE_PREFERENCES \
- (UIInterfaceOrientation)preferredInterfaceOrientationForPresentation { return UIInterfaceOrientationLandscapeRight; } \
- (BOOL)prefersInterfaceOrientationLocked { return NO; }

@implementation HaloLandscapeController
- (UIInterfaceOrientationMask)supportedInterfaceOrientations { return UIInterfaceOrientationMaskLandscape; }
HALO_LANDSCAPE_PREFERENCES
- (void)viewDidAppear:(BOOL)animated {
    [super viewDidAppear:animated];
    host_ios_require_landscape(self.view.window);
}
@end

@implementation HaloLandscapeDocumentPicker
- (UIInterfaceOrientationMask)supportedInterfaceOrientations { return UIInterfaceOrientationMaskLandscape; }
HALO_LANDSCAPE_PREFERENCES
@end

@implementation SDL_uikitviewcontroller (HaloLandscape)
- (void)motionEnded:(UIEventSubtype)motion withEvent:(UIEvent *)event {
    if (motion == UIEventSubtypeMotionShake) halo_debug_present();
    else [super motionEnded:motion withEvent:event];
}
HALO_LANDSCAPE_PREFERENCES
@end

@implementation SDLLaunchScreenController (HaloLandscape)
HALO_LANDSCAPE_PREFERENCES
@end

@implementation SDLUIKitSceneDelegate (HaloLandscape)
/* iPadOS 27 consults the scene delegate in preference to Info.plist. */
- (UIInterfaceOrientationMask)supportedInterfaceOrientationsForWindowScene:(UIWindowScene *)scene {
    (void)scene;
    return UIInterfaceOrientationMaskLandscape;
}
#if __IPHONE_OS_VERSION_MAX_ALLOWED >= 260000
- (void)windowScene:(UIWindowScene *)scene didUpdateEffectiveGeometry:(UIWindowSceneGeometry *)previousGeometry API_AVAILABLE(ios(26.0)) {
    CGSize size=scene.effectiveGeometry.coordinateSpace.bounds.size;
    host_logf(HOST_LOG_INFO,"scene geometry %.0fx%.0f orientation=%ld locked=%d",
        size.width,size.height,(long)scene.effectiveGeometry.interfaceOrientation,
        scene.effectiveGeometry.isInterfaceOrientationLocked);
}
#endif
@end

void host_ios_require_landscape(UIWindow *window) {
    if (!window) return;
    [window.rootViewController setNeedsUpdateOfSupportedInterfaceOrientations];
#if __IPHONE_OS_VERSION_MAX_ALLOWED >= 260000
    if (@available(iOS 26.0,*)) [window.rootViewController setNeedsUpdateOfPrefersInterfaceOrientationLocked];
#endif
    UIWindowSceneGeometryPreferencesIOS *geometry=[[UIWindowSceneGeometryPreferencesIOS alloc]
        initWithInterfaceOrientations:UIInterfaceOrientationMaskLandscape];
    [window.windowScene requestGeometryUpdateWithPreferences:geometry errorHandler:^(NSError *error) {
        host_logf(HOST_LOG_WARN,"landscape request: %s",error.localizedDescription.UTF8String);
    }];
}
