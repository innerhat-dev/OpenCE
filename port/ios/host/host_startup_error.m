/* A startup failure must remain usable without an SDL game window. */
#import "host_orientation.h"
#include "host.h"
#include <stdlib.h>

@interface HaloStartupErrorController : HaloLandscapeController
@property(nonatomic, copy) NSString *message;
@end
@implementation HaloStartupErrorController
- (void)loadView {
    self.view=[UIView new];self.view.backgroundColor=UIColor.systemBackgroundColor;
    UILabel *title=[UILabel new];title.text=@"Halo could not start";
    title.font=[UIFont preferredFontForTextStyle:UIFontTextStyleHeadline];
    title.numberOfLines=0;
    UITextView *details=[UITextView new];details.text=self.message;details.editable=NO;
    details.font=[UIFont preferredFontForTextStyle:UIFontTextStyleBody];
    details.accessibilityIdentifier=@"startup-error-details";
    UIButton *copy=[UIButton buttonWithType:UIButtonTypeSystem];
    [copy setTitle:@"Copy details" forState:UIControlStateNormal];
    [copy addTarget:self action:@selector(copyDetails:) forControlEvents:UIControlEventTouchUpInside];
    UIButton *close=[UIButton buttonWithType:UIButtonTypeSystem];
    [close setTitle:@"Close" forState:UIControlStateNormal];
    [close addTarget:self action:@selector(close:) forControlEvents:UIControlEventTouchUpInside];
    UIStackView *buttons=[[UIStackView alloc]initWithArrangedSubviews:@[copy,close]];
    buttons.distribution=UIStackViewDistributionFillEqually;buttons.spacing=16;
    UIStackView *stack=[[UIStackView alloc]initWithArrangedSubviews:@[title,details,buttons]];
    stack.axis=UILayoutConstraintAxisVertical;stack.spacing=12;stack.translatesAutoresizingMaskIntoConstraints=NO;
    [self.view addSubview:stack];
    UILayoutGuide *safe=self.view.safeAreaLayoutGuide;
    [NSLayoutConstraint activateConstraints:@[
        [stack.topAnchor constraintEqualToAnchor:safe.topAnchor constant:16],
        [stack.bottomAnchor constraintEqualToAnchor:safe.bottomAnchor constant:-16],
        [stack.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor constant:20],
        [stack.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor constant:-20],
        [buttons.heightAnchor constraintEqualToConstant:48]]];
}
- (void)copyDetails:(UIButton *)sender {
    UIPasteboard.generalPasteboard.string=[NSString stringWithFormat:@"%@\n%@",self.message,
        NSProcessInfo.processInfo.operatingSystemVersionString];
    [sender setTitle:@"Copied" forState:UIControlStateNormal];
}
- (void)close:(id)sender {(void)sender;exit(1);}
@end

static UIWindow *errorWindow;
static void show_error(NSString *message) {
    if(errorWindow)return;
    UIWindowScene *chosen=nil;
    for(UIScene *scene in UIApplication.sharedApplication.connectedScenes) {
        if(![scene isKindOfClass:UIWindowScene.class])continue;
        if(!chosen || scene.activationState==UISceneActivationStateForegroundActive)chosen=(UIWindowScene *)scene;
        if(scene.activationState==UISceneActivationStateForegroundActive)break;
    }
    if(!chosen) {host_logf(HOST_LOG_ERROR,"No UIKit scene available for startup error");exit(1);}
    HaloStartupErrorController *controller=[HaloStartupErrorController new];controller.message=message;
    errorWindow=[[UIWindow alloc]initWithWindowScene:chosen];
    errorWindow.frame=chosen.coordinateSpace.bounds;
    errorWindow.windowLevel=UIWindowLevelAlert+1;
    errorWindow.rootViewController=controller;[errorWindow makeKeyAndVisible];
    /* Hide SDL's fading launch window, which otherwise competes for focus. */
    for(UIWindow *window in chosen.windows)
        if(window!=errorWindow)window.hidden=YES;
}

void host_ios_show_fatal(const char *text) __attribute__((noreturn));
void host_ios_show_fatal(const char *text) {
    NSString *message=[NSString stringWithUTF8String:text] ?: @"Unknown startup error.";
    if(!NSThread.isMainThread) {
        dispatch_async(dispatch_get_main_queue(),^{show_error(message);});
        dispatch_semaphore_wait(dispatch_semaphore_create(0),DISPATCH_TIME_FOREVER);
        abort();
    }
    show_error(message);
    for(;;) {@autoreleasepool {
        CFRunLoopRunInMode(kCFRunLoopDefaultMode,0.01,true);
        CFRunLoopRunInMode((__bridge CFStringRef)UITrackingRunLoopMode,0.01,true);
    }}
}
