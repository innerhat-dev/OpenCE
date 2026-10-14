/* Shader-source diagnostics are exportable data, never game maps or saves. */
#if !defined(HALO_IOS)
#import <AppKit/AppKit.h>
#else
#import <UIKit/UIKit.h>
#endif
#import <QuartzCore/QuartzCore.h>
#include <GLES3/gl32.h>
#import <CommonCrypto/CommonDigest.h>
#include <stdatomic.h>
#include <string.h>
#include <sys/utsname.h>
#include "host_debug.h"
#ifdef HALO_IOS
void host_ios_touch_focus(void);
void host_ios_touch_reset(void);
#endif
#include "host.h"
#include "host_gl_dispatch.h"

static atomic_bool recording;
static NSMutableDictionary *shaderKeys,*sources,*attachments;
static NSMutableArray *events;
static NSMutableSet *drawnPrograms;
static uint32_t currentProgram;
static NSString *glRenderer;
#ifndef HALO_BUILD_REVISION
#define HALO_BUILD_REVISION "unknown"
#endif
static NSUInteger sourceBytes,dropped;
static int frameLimit = 60;
static BOOL showFPS;
static NSMutableArray *frameSamples;
static double frameTotal,frameWorst;
static NSUInteger frameCount;
static double lastSample;
#ifdef HALO_IOS
static UILabel *fpsLabel;
static void exportReport(UIViewController *presenter);
#endif
int halo_debug_renderer_preference(void) {
#ifdef HALO_IOS
    NSString *forced=NSProcessInfo.processInfo.environment[@"HALO_IOS_TEST_RENDERER"];
    NSString *setting=forced?:[NSUserDefaults.standardUserDefaults stringForKey:@"HaloRenderer"];
    return ![setting isEqualToString:@"opengl"];
#else
    return 1;
#endif
}
void halo_debug_set_renderer_preference(int metal) {
    [NSUserDefaults.standardUserDefaults setObject:metal?@"metal":@"opengl" forKey:@"HaloRenderer"];
}
int halo_debug_frame_limit(void) {return frameLimit;}
void halo_debug_configure_launch(void) {
#ifdef HALO_IOS
    NSUserDefaults *settings=NSUserDefaults.standardUserDefaults;
    [settings registerDefaults:@{@"HaloRenderHeight":@720,@"HaloFrameLimit":@60,@"HaloFPSOverlay":@NO,@"HaloInterpolation":@YES}];
    int height=(int)[settings integerForKey:@"HaloRenderHeight"];
    if (!height) {
        CGSize pixels=UIScreen.mainScreen.nativeBounds.size;
        height=(int)MIN(pixels.width,pixels.height);
    }
    char value[32];snprintf(value,sizeof(value),"%d",height);
    setenv("HALO_IOS_RENDER_HEIGHT",value,0);
    setenv("HALO_CONSOLE_LOG","none",0);
    setenv("HALO_INTERPOLATION",[settings boolForKey:@"HaloInterpolation"]?"1":"0",0);
    setenv("HALO_IOS_REFRESH_RATE","60",0);
    frameLimit=(int)[settings integerForKey:@"HaloFrameLimit"];
    if(frameLimit!=30 && frameLimit!=60 && frameLimit!=120)frameLimit=60;
    if(frameLimit==120)setenv("HALO_IOS_REFRESH_RATE","120",1);
    showFPS=[settings boolForKey:@"HaloFPSOverlay"];
#endif
}
void halo_debug_frame(double milliseconds) {
#ifdef HALO_IOS
    if(milliseconds<=0)return;
    frameCount++;frameTotal+=milliseconds;frameWorst=MAX(frameWorst,milliseconds);
    double now=CACurrentMediaTime();
    if(now-lastSample<0.5)return;
    if(!frameSamples)frameSamples=[NSMutableArray new];
    double mean=frameTotal/MAX((NSUInteger)1,frameCount);
    [frameSamples addObject:@{@"time":@(NSDate.date.timeIntervalSince1970),@"frames":@(frameCount),@"mean_ms":@(mean),@"worst_ms":@(frameWorst),@"thermal_state":@(NSProcessInfo.processInfo.thermalState)}];
    if(frameSamples.count>1200)[frameSamples removeObjectAtIndex:0];
    if(showFPS && !fpsLabel) {
        UIWindow *window=nil;
        for(UIWindowScene *scene in UIApplication.sharedApplication.connectedScenes)
            if([scene isKindOfClass:UIWindowScene.class])for(UIWindow *w in scene.windows)if(w.isKeyWindow)window=w;
        if(window) {
            fpsLabel=[[UILabel alloc]initWithFrame:CGRectMake(window.safeAreaInsets.left+12,window.safeAreaInsets.top+8,160,26)];
            fpsLabel.font=[UIFont monospacedDigitSystemFontOfSize:13 weight:UIFontWeightSemibold];
            fpsLabel.textColor=UIColor.whiteColor;fpsLabel.backgroundColor=[UIColor colorWithWhite:0 alpha:.6];
            fpsLabel.userInteractionEnabled=NO;fpsLabel.accessibilityLabel=@"Frame rate";
            [window.rootViewController.view addSubview:fpsLabel];
        }
    }
    if(fpsLabel.superview) {
        UIEdgeInsets insets=fpsLabel.superview.safeAreaInsets;
        fpsLabel.frame=CGRectMake(insets.left+12,insets.top+8,160,26);
    }
    fpsLabel.hidden=!showFPS;
    fpsLabel.text=[NSString stringWithFormat:@" %.0f FPS · %.1f ms",1000.0/mean,mean];
    frameCount=0;frameTotal=frameWorst=0;lastSample=now;
    static BOOL testExported;
    if(!testExported && frameSamples.count>=10 && [NSProcessInfo.processInfo.environment[@"HALO_IOS_TEST_REPORT_EXPORT"] boolValue]) {
        testExported=YES;exportReport(nil);
    }
#else
    (void)milliseconds;
#endif
}

#if !defined(HALO_IOS)
static BOOL debugPresented;
#else
static __weak UIViewController *debugController;
#endif
void halo_debug_initialize(void) {
    NSUserDefaults *settings=NSUserDefaults.standardUserDefaults;
    atomic_store(&recording,[settings boolForKey:@"HaloRecordShaderStalls"] || [NSProcessInfo.processInfo.environment[@"HALO_IOS_TEST_SHADER_CAPTURE"] boolValue]);
    halo_metalfx_set_enabled([settings boolForKey:@"HaloMetalFX"] || [NSProcessInfo.processInfo.environment[@"HALO_IOS_TEST_METALFX"] boolValue]);
}
static void prepare(void) {
    if(!shaderKeys){shaderKeys=[NSMutableDictionary new];sources=[NSMutableDictionary new];attachments=[NSMutableDictionary new];events=[NSMutableArray new];drawnPrograms=[NSMutableSet new];}
}
void halo_debug_shader_source(uint32_t shader,int count,const char *const *strings,const int *lengths) {
    prepare();if(!glRenderer){const GLubyte *name=glGetString(GL_RENDERER);if(name)glRenderer=[NSString stringWithUTF8String:(const char *)name];}
    [shaderKeys removeObjectForKey:@(shader)];NSMutableData *data=[NSMutableData new];
    for(int i=0;i<count;i++) {
        NSUInteger length=lengths && lengths[i]>=0?(NSUInteger)lengths[i]:strlen(strings[i]);
        if(length>1024*1024 || data.length+length>1024*1024){dropped++;return;}
        [data appendBytes:strings[i] length:length];
    }
    unsigned char digest[CC_SHA256_DIGEST_LENGTH];CC_SHA256(data.bytes,(CC_LONG)data.length,digest);
    NSMutableString *key=[NSMutableString new];for(int i=0;i<CC_SHA256_DIGEST_LENGTH;i++)[key appendFormat:@"%02x",digest[i]];
    NSString *text=[[NSString alloc]initWithData:data encoding:NSUTF8StringEncoding];
    if(!text)return;
    if(!sources[key]) {
        if(sourceBytes+data.length>32*1024*1024){dropped++;return;}
        GLint type=0;glGetShaderiv(shader,GL_SHADER_TYPE,&type);
        sources[key]=@{@"source":text,@"type":type==GL_VERTEX_SHADER?@"vertex":@"fragment"};sourceBytes+=data.length;
    }
    shaderKeys[@(shader)]=key;
}
void halo_debug_attach(uint32_t program,uint32_t shader) {
    prepare();NSMutableArray *list=attachments[@(program)];
    if(!list){list=[NSMutableArray new];attachments[@(program)]=list;}
    NSString *key=shaderKeys[@(shader)];if(key && ![list containsObject:key])[list addObject:key];
}
double halo_debug_begin(void) {return CACurrentMediaTime();}
void halo_debug_end(uint32_t object,int program,double started) {
    if(!started)return;
    GLint ok=0;
    if(program)glGetProgramiv(object,GL_LINK_STATUS,&ok);else glGetShaderiv(object,GL_COMPILE_STATUS,&ok);
    double ms=(CACurrentMediaTime()-started)*1000;
    if(ms<2 && ok)return;
    prepare();if(events.count>=4096){dropped++;return;}
    NSArray *keys=program?(attachments[@(object)]?:@[]):(shaderKeys[@(object)]?@[shaderKeys[@(object)]]:@[]);
    [events addObject:@{@"stage":program?@"link":@"compile",@"milliseconds":@(ms),@"success":@(ok!=0),@"sources":keys,@"time":@([NSDate date].timeIntervalSince1970)}];
}
void halo_debug_use_program(uint32_t program) {currentProgram=program;}
double halo_debug_draw_begin(void) {
    if(!atomic_load(&recording) || !currentProgram)return 0;
    prepare();if([drawnPrograms containsObject:@(currentProgram)])return 0;
    [drawnPrograms addObject:@(currentProgram)];
    /* Drain older work outside the timed interval. This is deliberately
       intrusive diagnostics, never enabled during normal rendering. */
    glFinish();return CACurrentMediaTime();
}
void halo_debug_draw_end(double started) {
    if(!started)return;
    glFinish();double ms=(CACurrentMediaTime()-started)*1000;
    if(ms<2)return;
    if(events.count>=4096){dropped++;return;}
    [events addObject:@{@"stage":@"first_draw_wait",@"milliseconds":@(ms),@"sources":[attachments[@(currentProgram)] copy]?:@[],@"time":@([NSDate date].timeIntervalSince1970)}];
}
#if !defined(HALO_IOS)
int halo_debug_is_presented(void) {return debugPresented;}
#else
int halo_debug_is_presented(void) {return debugController!=nil;}
#endif
void halo_debug_forget(uint32_t object,int program) {
    if(program)[drawnPrograms removeObject:@(object)];
    if(program)[attachments removeObjectForKey:@(object)];else [shaderKeys removeObjectForKey:@(object)];
}
#if !defined(HALO_IOS)
static void exportReport(id presenter) {
#else
static void exportReport(UIViewController *presenter) {
#endif
    prepare();struct utsname device;uname(&device);
    NSMutableDictionary *programs=[NSMutableDictionary new];
    for(NSNumber *name in attachments)programs[name.stringValue]=[attachments[name] copy];
    NSMutableDictionary *report=[@{@"schema":@3,@"renderer":halo_graphics_metal()?@"Metal (ANGLE)":@"OpenGL ES (Apple)",@"gpu":glRenderer?:@"unknown",@"revision":@HALO_BUILD_REVISION,@"metalfx":@(halo_metalfx_enabled()!=0),@"device":[NSString stringWithUTF8String:device.machine],@"os":NSProcessInfo.processInfo.operatingSystemVersionString,
        @"build":[NSBundle.mainBundle objectForInfoDictionaryKey:@"CFBundleVersion"]?:@"unknown",@"threshold_ms":@2,
        @"note":@"CPU compile/link completion timings are always recorded. Synchronized first-use draw waits are opt-in. First-use waits include draw cost and may include deferred driver compilation; they are not isolated shader-compiler timings. Shader sources can guide warm-up updates.",
        @"first_use_gpu_recording":@(atomic_load(&recording)),@"programs":programs,
        @"requested_render_height":@([NSUserDefaults.standardUserDefaults integerForKey:@"HaloRenderHeight"]),@"frame_limit":@(frameLimit),@"fps_overlay":@(showFPS),@"frame_samples":[frameSamples copy]?:@[],@"dropped":@(dropped),@"events":[events copy],@"sources":[sources copy]} mutableCopy];
#ifdef HALO_IOS
    report[@"render_height"]=@(atoi(getenv("HALO_IOS_RENDER_HEIGHT")?:"720"));
    report[@"interpolation"]=@(!strcmp(getenv("HALO_INTERPOLATION")?:"0","1"));
#endif
    NSError *error=nil;NSData *data=[NSJSONSerialization dataWithJSONObject:report options:NSJSONWritingPrettyPrinted error:&error];
    NSURL *folder=[[NSFileManager.defaultManager URLsForDirectory:NSCachesDirectory inDomains:NSUserDomainMask].firstObject URLByAppendingPathComponent:@"ShaderReports" isDirectory:YES];
    [NSFileManager.defaultManager createDirectoryAtURL:folder withIntermediateDirectories:YES attributes:nil error:&error];
    NSArray<NSString *> *oldReports=[[NSFileManager.defaultManager contentsOfDirectoryAtPath:folder.path error:nil] filteredArrayUsingPredicate:[NSPredicate predicateWithBlock:^BOOL(NSString *name,NSDictionary *bindings){(void)bindings;return [name hasPrefix:@"halo-shaders-"] && [name hasSuffix:@".json"];}]];
    oldReports=[oldReports sortedArrayUsingSelector:@selector(compare:)];
    for(NSUInteger i=0;i+4<oldReports.count;i++)[NSFileManager.defaultManager removeItemAtURL:[folder URLByAppendingPathComponent:oldReports[i]] error:nil];
    NSURL *file=[folder URLByAppendingPathComponent:[NSString stringWithFormat:@"halo-shaders-%.0f.json",NSDate.date.timeIntervalSince1970]];
#if !defined(HALO_IOS)
    (void)presenter;
    NSString *testExport=NSProcessInfo.processInfo.environment[@"HALO_MAC_TEST_SHADER_EXPORT"];
    if(testExport.length) {
        if(!data || ![data writeToFile:testExport options:NSDataWritingAtomic error:&error])host_fatal("Shader report export failed: %s",error.localizedDescription.UTF8String);
        return;
    }
    if(!data || ![data writeToURL:file options:NSDataWritingAtomic error:&error]){NSAlert *alert=[NSAlert new];alert.messageText=@"Export failed";alert.informativeText=error.localizedDescription;[alert runModal];return;}
    NSSharingService *share=[NSSharingService sharingServiceNamed:NSSharingServiceNameSendViaAirDrop];
    [share performWithItems:@[file]];
}
#else
    if(!data || ![data writeToURL:file options:NSDataWritingAtomic error:&error]){UIAlertController *alert=[UIAlertController alertControllerWithTitle:@"Export failed" message:error.localizedDescription preferredStyle:UIAlertControllerStyleAlert];[alert addAction:[UIAlertAction actionWithTitle:@"OK" style:UIAlertActionStyleDefault handler:nil]];[presenter presentViewController:alert animated:YES completion:nil];return;}
    NSMutableArray *files=[NSMutableArray arrayWithObject:file];
    const char *roots[]={getenv("HALO_SAVE_ROOT"),getenv("HALO_DATA_ROOT")};
    const char *names[]={"halo.log","debug.txt"};
    for(int i=0;i<2;i++)if(roots[i]) {
        NSString *path=[[NSString stringWithUTF8String:roots[i]] stringByAppendingPathComponent:[NSString stringWithUTF8String:names[i]]];
        NSFileHandle *input=[NSFileHandle fileHandleForReadingAtPath:path];
        if(input) {
            unsigned long long length=[input seekToEndOfFile];
            [input seekToFileOffset:length>2*1024*1024?length-2*1024*1024:0];
            NSData *tail=[input readDataToEndOfFile];[input closeFile];
            NSURL *log=[folder URLByAppendingPathComponent:[NSString stringWithFormat:@"halo-session-%d.txt",i]];
            if([tail writeToURL:log atomically:YES])[files addObject:log];
        }
    }
    if([NSProcessInfo.processInfo.environment[@"HALO_IOS_TEST_REPORT_EXPORT"] boolValue])return;
    UIActivityViewController *share=[[UIActivityViewController alloc]initWithActivityItems:files applicationActivities:nil];
    share.popoverPresentationController.sourceView=presenter.view;share.popoverPresentationController.sourceRect=CGRectMake(CGRectGetMidX(presenter.view.bounds),40,1,1);
    [presenter presentViewController:share animated:YES completion:nil];
}
@interface HaloDebugController : UITableViewController <UIAdaptivePresentationControllerDelegate>
@end
@implementation HaloDebugController
- (void)viewDidLoad {
    [super viewDidLoad];self.title=@"Graphics & Diagnostics";
    self.navigationItem.rightBarButtonItem=[[UIBarButtonItem alloc]initWithBarButtonSystemItem:UIBarButtonSystemItemDone target:self action:@selector(done)];
}
- (void)done {[self dismissViewControllerAnimated:YES completion:^{debugController=nil;host_ios_touch_focus();}];}
- (void)presentationControllerDidDismiss:(UIPresentationController *)presentationController {
    (void)presentationController;debugController=nil;host_ios_touch_focus();
}
- (NSInteger)tableView:(UITableView *)table numberOfRowsInSection:(NSInteger)section {(void)table;(void)section;return 10;}
- (UITableViewCell *)tableView:(UITableView *)table cellForRowAtIndexPath:(NSIndexPath *)path {
    (void)table;UITableViewCell *cell=[[UITableViewCell alloc]initWithStyle:UITableViewCellStyleSubtitle reuseIdentifier:nil];
    cell.detailTextLabel.numberOfLines=0;
    NSUserDefaults *settings=NSUserDefaults.standardUserDefaults;
    switch(path.row) {
    case 0: {
        cell.textLabel.text=@"Renderer";
        cell.detailTextLabel.text=@"Metal (ANGLE) or native OpenGL ES. Relaunch to apply.";
        UISegmentedControl *control=[[UISegmentedControl alloc]initWithItems:@[@"OpenGL",@"Metal"]];
        control.selectedSegmentIndex=halo_graphics_prefer_metal()?1:0;
        [control addTarget:self action:@selector(rendererChanged:) forControlEvents:UIControlEventValueChanged];
        cell.accessoryView=control;break;
    }
    case 1: {
        NSInteger height=[settings integerForKey:@"HaloRenderHeight"];
        cell.textLabel.text=height?[NSString stringWithFormat:@"Render resolution: %ldp",(long)height]:@"Render resolution: Native";
        cell.detailTextLabel.text=@"720p balances detail and GPU load. Lower values trade detail for speed. Relaunch to apply.";
        cell.accessoryType=UITableViewCellAccessoryDisclosureIndicator;break;
    }
    case 2:
        cell.textLabel.text=[NSString stringWithFormat:@"Frame limit: %d FPS",frameLimit];
        cell.detailTextLabel.text=@"Limits rendering only; game simulation stays at 30 Hz. 120 FPS needs a compatible display and relaunch.";
        cell.accessoryType=UITableViewCellAccessoryDisclosureIndicator;break;
    case 3: case 4: case 5: {
        UISwitch *toggle=[UISwitch new];toggle.tag=path.row;
        if(path.row==3) {
            cell.textLabel.text=@"MetalFX spatial upscaling";
            cell.detailTextLabel.text=@"Upscale the render image to the display. Requires the active Metal renderer.";
            toggle.enabled=halo_graphics_metal() && halo_metalfx_supported();toggle.on=halo_metalfx_enabled();
        } else if(path.row==4) {
            cell.textLabel.text=@"FPS overlay";cell.detailTextLabel.text=@"Show measured game frames and frame time.";toggle.on=showFPS;
        } else {
            cell.textLabel.text=@"Record first-use GPU stalls";
            cell.detailTextLabel.text=@"Diagnostic only: synchronization can slow play. Normal session timing and shader compilation are recorded without it.";
            toggle.on=atomic_load(&recording);
        }
        [toggle addTarget:self action:@selector(changed:) forControlEvents:UIControlEventValueChanged];cell.accessoryView=toggle;break;
    }
    case 6:cell.textLabel.text=@"Share play-session report…";cell.detailTextLabel.text=@"AirDrop logs, graphics settings, frame timings and shader diagnostics to your Mac. No game image or saves.";break;
    case 8: {
        UISwitch *toggle=[UISwitch new];toggle.tag=8;toggle.on=[settings boolForKey:@"HaloInterpolation"];
        cell.textLabel.text=@"Smooth motion";cell.detailTextLabel.text=@"Interpolate rendered motion as in the earlier Apple build. Simulation stays at 30 Hz. Relaunch to apply.";
        [toggle addTarget:self action:@selector(changed:) forControlEvents:UIControlEventValueChanged];cell.accessoryView=toggle;break;
    }
    case 9: {
        UISwitch *toggle=[UISwitch new];toggle.tag=9;toggle.on=[settings boolForKey:@"HaloSeparateTouchPlayer"];
        cell.textLabel.text=@"Touch as a separate player";
        cell.detailTextLabel.text=@"Touch controls stay visible for player 1; controllers join as other players. Use Add Player in the lobby. Relaunch to apply.";
        [toggle addTarget:self action:@selector(changed:) forControlEvents:UIControlEventValueChanged];cell.accessoryView=toggle;break;
    }
    case 7:cell.textLabel.text=@"Clear recorded diagnostics";cell.detailTextLabel.text=@"Start a fresh measurement for your next play session.";break;
    }
    return cell;
}
- (void)rendererChanged:(UISegmentedControl *)sender {
    halo_graphics_set_preference(sender.selectedSegmentIndex==1);[self.tableView reloadData];
}
- (void)changed:(UISwitch *)sender {
    NSUserDefaults *settings=NSUserDefaults.standardUserDefaults;
    if(sender.tag==9)[settings setBool:sender.on forKey:@"HaloSeparateTouchPlayer"];
    if(sender.tag==8)[settings setBool:sender.on forKey:@"HaloInterpolation"];
    if(sender.tag==3){halo_metalfx_set_enabled(sender.on);[settings setBool:sender.on forKey:@"HaloMetalFX"];}
    if(sender.tag==4){showFPS=sender.on;fpsLabel.hidden=!showFPS;[settings setBool:sender.on forKey:@"HaloFPSOverlay"];}
    if(sender.tag==5){atomic_store(&recording,sender.on);[drawnPrograms removeAllObjects];[settings setBool:sender.on forKey:@"HaloRecordShaderStalls"];}
}
- (void)tableView:(UITableView *)table didSelectRowAtIndexPath:(NSIndexPath *)path {
    [table deselectRowAtIndexPath:path animated:YES];
    if(path.row==6){exportReport(self);return;}
    if(path.row==7){[events removeAllObjects];[drawnPrograms removeAllObjects];[frameSamples removeAllObjects];frameTotal=frameWorst=0;frameCount=0;dropped=0;[table reloadData];return;}
    if(path.row!=1 && path.row!=2)return;
    BOOL resolution=path.row==1;
    UIAlertController *choice=[UIAlertController alertControllerWithTitle:resolution?@"Render resolution":@"Frame limit" message:resolution?@"Resolution changes apply after relaunch.":@"Higher limits use more power and may increase heat." preferredStyle:UIAlertControllerStyleActionSheet];
    NSArray *values=resolution?@[@480,@720,@900,@1080,@0]:@[@30,@60,@120];
    for(NSNumber *value in values) {
        NSString *title=resolution?(value.intValue?[NSString stringWithFormat:@"%@p",value]:@"Native"):[NSString stringWithFormat:@"%@ FPS",value];
        [choice addAction:[UIAlertAction actionWithTitle:title style:UIAlertActionStyleDefault handler:^(UIAlertAction *action){
            (void)action;
            [NSUserDefaults.standardUserDefaults setInteger:value.integerValue forKey:resolution?@"HaloRenderHeight":@"HaloFrameLimit"];
            if(!resolution)frameLimit=value.intValue;
            [table reloadData];
        }]];
    }
    [choice addAction:[UIAlertAction actionWithTitle:@"Cancel" style:UIAlertActionStyleCancel handler:nil]];
    choice.popoverPresentationController.sourceView=[table cellForRowAtIndexPath:path];
    choice.popoverPresentationController.sourceRect=[table cellForRowAtIndexPath:path].bounds;
    [self presentViewController:choice animated:YES completion:nil];
}
@end
void halo_debug_present(void) {
    if(debugController)return;prepare();
    UIWindow *window=nil;for(UIScene *scene in UIApplication.sharedApplication.connectedScenes)if([scene isKindOfClass:UIWindowScene.class])for(UIWindow *w in ((UIWindowScene*)scene).windows)if(w.isKeyWindow)window=w;
    UIViewController *presenter=window.rootViewController;
    while(presenter.presentedViewController)presenter=presenter.presentedViewController;
    if(!presenter)return;
    host_ios_touch_reset();HaloDebugController *controller=[[HaloDebugController alloc]initWithStyle:UITableViewStyleInsetGrouped];
    UINavigationController *navigation=[[UINavigationController alloc]initWithRootViewController:controller];
    navigation.modalPresentationStyle=UIModalPresentationPageSheet;debugController=navigation;
    [presenter presentViewController:navigation animated:YES completion:nil];
    navigation.presentationController.delegate=controller;
}

#endif
#if !defined(HALO_IOS)
@interface HaloDebugActions : NSWindowController <NSWindowDelegate>
@property NSButton *upscaleButton;
@property NSButton *recordButton;
@property NSTextField *eventCount;
@end
@implementation HaloDebugActions
- (instancetype)init {
    NSWindow *window=[[NSWindow alloc]initWithContentRect:NSMakeRect(0,0,480,360)
        styleMask:NSWindowStyleMaskTitled|NSWindowStyleMaskClosable backing:NSBackingStoreBuffered defer:NO];
    self=[super initWithWindow:window];
    if(self) {
        window.title=@"Graphics Diagnostics";window.releasedWhenClosed=NO;window.delegate=self;
        NSStackView *stack=[NSStackView new];stack.orientation=NSUserInterfaceLayoutOrientationVertical;
        stack.alignment=NSLayoutAttributeLeading;stack.spacing=14;stack.translatesAutoresizingMaskIntoConstraints=NO;
        [window.contentView addSubview:stack];
        [NSLayoutConstraint activateConstraints:@[
            [stack.leadingAnchor constraintEqualToAnchor:window.contentView.leadingAnchor constant:24],
            [stack.trailingAnchor constraintEqualToAnchor:window.contentView.trailingAnchor constant:-24],
            [stack.topAnchor constraintEqualToAnchor:window.contentView.topAnchor constant:24],
            [stack.bottomAnchor constraintLessThanOrEqualToAnchor:window.contentView.bottomAnchor constant:-24]]];
        [stack addArrangedSubview:[NSTextField labelWithString:@"Renderer: Metal (ANGLE)"]];
        self.upscaleButton=[NSButton checkboxWithTitle:@"MetalFX spatial upscaling" target:self action:@selector(upscale:)];
        [stack addArrangedSubview:self.upscaleButton];
        self.recordButton=[NSButton checkboxWithTitle:@"Record first-use GPU stalls" target:self action:@selector(record:)];
        [stack addArrangedSubview:self.recordButton];
        NSTextField *note=[NSTextField wrappingLabelWithString:@"Compile/link stalls are recorded automatically. First-use GPU recording adds synchronization overhead; disable it for normal play."];
        [stack addArrangedSubview:note];[note.widthAnchor constraintEqualToAnchor:stack.widthAnchor].active=YES;
        [stack addArrangedSubview:[NSButton buttonWithTitle:@"AirDrop shader report…" target:self action:@selector(share:)]];
        [stack addArrangedSubview:[NSButton buttonWithTitle:@"Clear recorded events" target:self action:@selector(clear:)]];
        self.eventCount=[NSTextField labelWithString:@""];[stack addArrangedSubview:self.eventCount];
        [window center];
    }
    return self;
}
-(void)refresh {
    self.upscaleButton.enabled=halo_metalfx_supported();self.upscaleButton.state=halo_metalfx_enabled();
    self.recordButton.state=atomic_load(&recording);
    self.eventCount.stringValue=[NSString stringWithFormat:@"%lu events; %lu dropped",(unsigned long)events.count,(unsigned long)dropped];
}
-(void)openSettings:(id)sender {
    (void)sender;[self refresh];debugPresented=YES;[self showWindow:nil];[self.window makeKeyAndOrderFront:nil];
    NSString *capture=NSProcessInfo.processInfo.environment[@"HALO_MAC_TEST_SETTINGS_IMAGE"];
    if(capture.length) {
        NSView *view=self.window.contentView;[view layoutSubtreeIfNeeded];
        NSBitmapImageRep *bitmap=[view bitmapImageRepForCachingDisplayInRect:view.bounds];
        [view cacheDisplayInRect:view.bounds toBitmapImageRep:bitmap];
        [[bitmap representationUsingType:NSBitmapImageFileTypePNG properties:@{}]writeToFile:capture atomically:YES];
    }
}
-(void)windowWillClose:(NSNotification *)notification {(void)notification;debugPresented=NO;}
-(void)network:(NSButton *)item {[NSUserDefaults.standardUserDefaults setBool:item.state==NSControlStateValueOn forKey:@"HaloBrowserRooms"];}
-(void)upscale:(NSButton *)item {BOOL on=item.state==NSControlStateValueOn;halo_metalfx_set_enabled(on);[NSUserDefaults.standardUserDefaults setBool:on forKey:@"HaloMetalFX"];[self refresh];}
-(void)record:(NSButton *)item {BOOL on=item.state==NSControlStateValueOn;atomic_store(&recording,on);[drawnPrograms removeAllObjects];[NSUserDefaults.standardUserDefaults setBool:on forKey:@"HaloRecordShaderStalls"];[self refresh];}
-(void)share:(id)sender {(void)sender;exportReport(nil);}
-(void)clear:(id)sender {(void)sender;[events removeAllObjects];[drawnPrograms removeAllObjects];dropped=0;[self refresh];}
@end
static HaloDebugActions *actions;
void halo_debug_install_menu(void) {
    if(actions)return;prepare();actions=[HaloDebugActions new];
    NSMenu *menu=NSApp.mainMenu.itemArray.firstObject.submenu;
    if(!menu)return;
    NSMenuItem *item=[[NSMenuItem alloc] initWithTitle:@"Graphics Diagnostics…" action:@selector(openSettings:) keyEquivalent:@""];
    item.target=actions;[menu insertItem:item atIndex:MIN(2,menu.numberOfItems)];
}
void halo_debug_present(void) {halo_debug_install_menu();[actions openSettings:nil];}
#endif

/* Developer regression: compile every source in a received report using the
   actual bundled driver. No game state, textures or buffers are changed. */
void halo_debug_replay_shader_report(void) {
#if !defined(HALO_IOS)
    NSString *path=NSProcessInfo.processInfo.environment[@"HALO_MAC_TEST_SHADER_REPORT"];
    if(!path.length)return;
    NSData *data=[NSData dataWithContentsOfFile:path];
    NSDictionary *report=data?[NSJSONSerialization JSONObjectWithData:data options:0 error:nil]:nil;
    NSDictionary *entries=[report isKindOfClass:NSDictionary.class]?report[@"sources"]:nil;
    if(![entries isKindOfClass:NSDictionary.class] || entries.count>4096)host_fatal("Invalid shader replay report");
    PFNGLCREATESHADERPROC create=halo_graphics_proc("glCreateShader");
    PFNGLSHADERSOURCEPROC source=halo_graphics_proc("glShaderSource");
    PFNGLCOMPILESHADERPROC compile=halo_graphics_proc("glCompileShader");
    PFNGLDELETESHADERPROC destroy=halo_graphics_proc("glDeleteShader");
    PFNGLGETSHADERINFOLOGPROC getLog=halo_graphics_proc("glGetShaderInfoLog");
    unsigned passed=0,failed=0;
    for(NSString *key in entries) {
        NSDictionary *entry=entries[key];
        if(![entry isKindOfClass:NSDictionary.class])host_fatal("Invalid shader replay entry");
        NSString *text=entry[@"source"],*kind=entry[@"type"];
        if(![text isKindOfClass:NSString.class] || text.length>1024*1024 ||
            (![kind isEqualToString:@"vertex"] && ![kind isEqualToString:@"fragment"]))host_fatal("Invalid shader replay entry");
        GLuint shader=create([kind isEqualToString:@"vertex"]?GL_VERTEX_SHADER:GL_FRAGMENT_SHADER);
        const char *utf8=text.UTF8String;source(shader,1,&utf8,NULL);compile(shader);
        GLint ok=0;glGetShaderiv(shader,GL_COMPILE_STATUS,&ok);
        if(ok)passed++;else {char log[4096];getLog(shader,sizeof(log),NULL,log);host_logf(HOST_LOG_ERROR,"Shader replay %s failed: %s",key.UTF8String,log);failed++;}
        destroy(shader);
    }
    host_logf(HOST_LOG_INFO,"Shader replay: %u compiled, %u failed",passed,failed);
#endif
}

void halo_debug_test_export(void) {
#if !defined(HALO_IOS)
    if(NSProcessInfo.processInfo.environment[@"HALO_MAC_TEST_SHADER_EXPORT"].length)exportReport(nil);
#endif
}
