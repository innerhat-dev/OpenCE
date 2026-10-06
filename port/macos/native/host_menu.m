#import <Cocoa/Cocoa.h>
#import <Sparkle/Sparkle.h>
#import "HaloPreferences.h"
#import "HaloMapDownloads.h"
#import "HaloMapPackages.h"
#include <SDL3/SDL.h>
#include "host_menu.h"
#include <stdlib.h>
#include <string.h>

@interface HaloMenu : NSObject <NSApplicationDelegate, NSMenuDelegate, NSMenuItemValidation,
                               SPUUpdaterDelegate, SPUStandardUserDriverDelegate>
@property(nonatomic, strong) HaloPreferences *preferences;
@property(nonatomic, strong) NSStatusItem *status;
@property(nonatomic, strong) NSWindow *settingsWindow;
@property(nonatomic, strong) NSTextField *dataLabel;
@property(nonatomic, strong) NSTextField *sourceLabel;
@property(nonatomic, strong) NSButton *fullscreenButton;
@property(nonatomic, strong) NSButton *automaticUpdatesButton;
@property(nonatomic, strong) NSButton *communityDownloadsButton;
@property(nonatomic, strong) NSTextField *downloadsLabel;
@property(nonatomic, strong) HaloMapDownloads *mapDownloads;
@property(nonatomic, strong) NSButton *packageImportButton;
@property(nonatomic, copy) NSString *packageStatus;
@property(nonatomic, strong) SPUStandardUpdaterController *updater;
@property(nonatomic, strong) id previousDelegate;
@property(nonatomic) BOOL gameRunning;
@property(nonatomic) BOOL waitingForUpdate;
@property(nonatomic) BOOL importing;
@property(nonatomic) BOOL settingsVisible;
@property(nonatomic) BOOL quitting;
@property(nonatomic, copy) void (^pendingInstall)(void);
@property(nonatomic, copy) NSString *availableVersion;
@property(nonatomic, copy) NSString *launchDataPath;
- (void)refreshSettings;
- (void)refreshFullscreen;
- (void)updateSystemChrome;
- (BOOL)chooseFolder;
- (BOOL)chooseImage;
- (void)showSettings:(id)sender;
- (void)closeSettings:(id)sender;
- (void)importImage:(NSURL *)image completion:(void (^)(BOOL))completion;
- (void)acceptFolder:(NSURL *)folder completion:(void (^)(BOOL))completion;
- (void)copyFolder:(NSURL *)folder completion:(void (^)(BOOL))completion;
- (BOOL)migrateSupportIfNeeded:(NSURL *)support;
@end

static HaloMenu *menu;

static void showError(NSError *error) {
    NSAlert *alert = [[NSAlert alloc] init];
    alert.messageText = @"Halo OG could not use that setting";
    alert.informativeText = error.localizedDescription ?: @"Please try again.";
    if (menu.gameRunning) {
        [menu showSettings:nil];
        [alert beginSheetModalForWindow:menu.settingsWindow completionHandler:nil];
    } else {
        [alert runModal];
    }
}

static NSMenuItem *item(NSMenu *parent, NSString *title, SEL action, NSString *key) {
    NSMenuItem *result = [[NSMenuItem alloc] initWithTitle:title action:action keyEquivalent:key ?: @""];
    result.target = menu;
    [parent addItem:result];
    return result;
}

static NSTextField *label(NSView *view, NSString *text, NSRect frame, BOOL secondary) {
    NSTextField *result = [NSTextField labelWithString:text];
    result.frame = frame;
    result.lineBreakMode = NSLineBreakByTruncatingMiddle;
    if (secondary) result.textColor = NSColor.secondaryLabelColor;
    [view addSubview:result];
    return result;
}

static NSButton *button(NSView *view, NSString *title, SEL action, NSRect frame) {
    NSButton *result = [NSButton buttonWithTitle:title target:menu action:action];
    result.frame = frame;
    [view addSubview:result];
    return result;
}

struct import_progress {
    __unsafe_unretained NSTextField *label;
    __unsafe_unretained NSProgressIndicator *bar;
};

static void importProgress(void *context, const char *file, unsigned long long done, unsigned long long total) {
    struct import_progress *progress = context;
    NSTextField *progressLabel = progress->label;
    NSProgressIndicator *bar = progress->bar;
    NSString *name = [NSString stringWithUTF8String:file] ?: @"Maps";
    dispatch_async(dispatch_get_main_queue(), ^{
        progressLabel.stringValue = [NSString stringWithFormat:@"%@ — %llu of %llu MB", name, done >> 20, total >> 20];
        bar.doubleValue = total ? (100.0 * done / total) : 0;
    });
}

static void migrationProgress(void *context, const char *file, unsigned long long done, unsigned long long total) {
    struct import_progress *progress = context;
    NSTextField *progressLabel = progress->label;
    NSProgressIndicator *bar = progress->bar;
    NSString *name = [NSString stringWithUTF8String:file] ?: @"Saved data";
    dispatch_async(dispatch_get_main_queue(), ^{
        progressLabel.stringValue = total ? [NSString stringWithFormat:@"%@ — %llu of %llu MB", name, done >> 20, total >> 20] : name;
        bar.indeterminate = !total;
        if (total) { [bar stopAnimation:nil]; bar.doubleValue = 100.0 * done / total; }
        else [bar startAnimation:nil];
    });
}

@implementation HaloMenu
- (BOOL)migrateSupportIfNeeded:(NSURL *)support {
    if (!HaloSupportDirectoryNeedsMigration(support)) return YES;
    self.importing = YES;
    NSURL *parent = [NSURL fileURLWithPath:[NSHomeDirectory() stringByAppendingPathComponent:@"Library/Application Support"] isDirectory:YES];
    NSURL *legacy = [parent URLByAppendingPathComponent:@"Halo CE Universal" isDirectory:YES];
    NSWindow *window = [[NSWindow alloc] initWithContentRect:NSMakeRect(0, 0, 520, 150)
        styleMask:NSWindowStyleMaskTitled backing:NSBackingStoreBuffered defer:NO];
    window.title = @"Preparing Halo OG Data";
    window.releasedWhenClosed = NO;
    label(window.contentView, @"Copying your saved data into Halo OG’s Application Support folder.", NSMakeRect(24, 103, 472, 25), NO);
    NSTextField *status = label(window.contentView, @"Your original files and existing Halo OG files stay in place.", NSMakeRect(24, 73, 472, 22), YES);
    NSProgressIndicator *bar = [[NSProgressIndicator alloc] initWithFrame:NSMakeRect(24, 35, 472, 18)];
    bar.style = NSProgressIndicatorStyleBar;
    bar.indeterminate = YES;
    [window.contentView addSubview:bar];
    [window center]; [window makeKeyAndOrderFront:nil]; [bar startAnimation:nil];
    __block struct import_progress progress = {.label = status, .bar = bar};
    __block BOOL finished = NO, success = NO;
    __block NSError *migrationError = nil;
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        @autoreleasepool {
            BOOL copied = HaloMigrateLegacySupportDirectory(legacy, support, migrationProgress, &progress, &migrationError);
            dispatch_async(dispatch_get_main_queue(), ^{ success = copied; finished = YES; });
        }
    });
    /* This is before the game starts; keep the launch window responsive while
       copying large imports, with no simulation or network tick running yet. */
    while (!finished) [NSRunLoop.currentRunLoop runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.05]];
    [bar stopAnimation:nil]; [window close];
    self.importing = NO;
    if (!success) {
        NSAlert *alert = [[NSAlert alloc] init];
        alert.messageText = @"Halo OG could not finish copying your saved data";
        alert.informativeText = [NSString stringWithFormat:@"%@\n\nThe older Application Support folder and existing Halo OG files were preserved. The game will close so you can fix the issue and retry; it will not start with empty settings.", migrationError.localizedDescription ?: @"The copy could not finish."];
        [alert addButtonWithTitle:@"Quit and Retry Later"];
        [alert runModal];
    }
    return success;
}
- (BOOL)respondsToSelector:(SEL)selector {
    return [super respondsToSelector:selector] || [self.previousDelegate respondsToSelector:selector];
}
- (id)forwardingTargetForSelector:(SEL)selector {
    return [self.previousDelegate respondsToSelector:selector] ? self.previousDelegate : [super forwardingTargetForSelector:selector];
}
- (NSApplicationTerminateReply)applicationShouldTerminate:(NSApplication *)sender {
    (void)sender;
    if (self.importing) return NSTerminateCancel;
    if (self.gameRunning) {
        self.quitting = YES;
        if (NSApp.modalWindow) [NSApp stopModal];
        [self closeSettings:nil];
        host_sdl_request_quit();
        return NSTerminateCancel;
    }
    return NSTerminateNow;
}
- (void)buildMenus {
    self.status = [NSStatusBar.systemStatusBar statusItemWithLength:NSSquareStatusItemLength];
    NSURL *icon = [NSBundle.mainBundle URLForResource:@"Helmet" withExtension:@"pdf"];
    NSImage *image = [[NSImage alloc] initWithContentsOfURL:icon];
    image.size = NSMakeSize(18, 18);
    image.template = YES;
    self.status.button.image = image ?: [NSImage imageWithSystemSymbolName:@"gamecontroller" accessibilityDescription:@"Halo OG"];
    self.status.button.toolTip = @"Halo OG";
    self.status.button.accessibilityLabel = @"Halo OG";
    NSMenu *statusMenu = [[NSMenu alloc] initWithTitle:@"Halo OG"];
    statusMenu.delegate = self;
    NSMenuItem *title = [[NSMenuItem alloc] initWithTitle:@"Halo OG" action:nil keyEquivalent:@""];
    title.enabled = NO;
    [statusMenu addItem:title];
    [statusMenu addItem:NSMenuItem.separatorItem];
    item(statusMenu, @"Show Game", @selector(showGame:), @"");
    item(statusMenu, @"Enter Full Screen", @selector(toggleFullscreen:), @"");
    item(statusMenu, @"Settings…", @selector(showSettings:), @",");
    [statusMenu addItem:NSMenuItem.separatorItem];
    item(statusMenu, @"Choose Disc Image…", @selector(selectImage:), @"");
    item(statusMenu, @"Choose Maps Folder…", @selector(selectFolder:), @"");
    item(statusMenu, @"Open Saves Folder", @selector(openSaves:), @"");
    item(statusMenu, @"Edit Controls and Advanced Settings…", @selector(openConfig:), @"");
    [statusMenu addItem:NSMenuItem.separatorItem];
    item(statusMenu, @"Check for Updates…", @selector(checkUpdates:), @"");
    NSMenuItem *statusQuit = item(statusMenu, @"Quit Halo OG", @selector(terminate:), @"q");
    statusQuit.target = NSApp;
    self.status.menu = statusMenu;

    NSMenu *main = [[NSMenu alloc] initWithTitle:@"Main"];
    NSMenuItem *app = [[NSMenuItem alloc] initWithTitle:@"Halo OG" action:nil keyEquivalent:@""];
    NSMenu *appMenu = [[NSMenu alloc] initWithTitle:@"Halo OG"];
    item(appMenu, @"About Halo OG", @selector(about:), @"");
    item(appMenu, @"Settings…", @selector(showSettings:), @",");
    item(appMenu, @"Check for Updates…", @selector(checkUpdates:), @"");
    [appMenu addItem:NSMenuItem.separatorItem];
    NSMenuItem *appQuit = item(appMenu, @"Quit Halo OG", @selector(terminate:), @"q");
    appQuit.target = NSApp;
    app.submenu = appMenu;
    [main addItem:app];
    NSMenuItem *view = [[NSMenuItem alloc] initWithTitle:@"View" action:nil keyEquivalent:@""];
    NSMenu *viewMenu = [[NSMenu alloc] initWithTitle:@"View"];
    viewMenu.delegate = self;
    NSMenuItem *fullscreen = item(viewMenu, @"Enter Full Screen", @selector(toggleFullscreen:), @"f");
    fullscreen.keyEquivalentModifierMask = NSEventModifierFlagControl | NSEventModifierFlagCommand;
    item(viewMenu, @"Show Game", @selector(showGame:), @"");
    view.submenu = viewMenu;
    [main addItem:view];
    NSApp.mainMenu = main;
}
- (void)menuWillOpen:(NSMenu *)sender { (void)sender; host_sdl_release_mouse(); }
- (void)menuNeedsUpdate:(NSMenu *)sender {
    for (NSMenuItem *entry in sender.itemArray) {
        if (entry.action == @selector(toggleFullscreen:))
            entry.title = host_sdl_is_fullscreen() ? @"Exit Full Screen" : @"Enter Full Screen";
        if (entry.action == @selector(checkUpdates:))
            entry.title = self.pendingInstall ? @"Update Ready — Quit to Install" : self.availableVersion
                ? [NSString stringWithFormat:@"Update to Halo OG %@…", self.availableVersion] : @"Check for Updates…";
    }
}
- (BOOL)validateMenuItem:(NSMenuItem *)entry {
    if (self.importing) return NO;
    if (entry.action == @selector(showGame:)) return self.gameRunning;
    if (entry.action == @selector(toggleFullscreen:)) return self.gameRunning;
    if (entry.action == @selector(checkUpdates:)) return self.updater.updater.canCheckForUpdates && !self.pendingInstall;
    return YES;
}
- (void)updateSystemChrome {
    /* Borderless full screen stays on the normal desktop so settings and file
       panels can sit above the game. Hide the Dock and menu bar only for that
       full screen game, including when the pointer touches the screen edge.
       Settings and file panels, and a windowed game, use the normal desktop. */
    BOOL hide = self.gameRunning && !self.settingsVisible && !self.quitting && host_sdl_is_fullscreen();
    NSApplicationPresentationOptions options = hide
        ? (NSApplicationPresentationHideDock | NSApplicationPresentationHideMenuBar)
        : NSApplicationPresentationDefault;
    if (NSApp.presentationOptions != options) {
        @try {
            [NSApp setPresentationOptions:options];
        } @catch (NSException *exception) {
            (void)exception;
        }
    }
    if (!hide) return;
    int count = 0;
    SDL_Window **windows = SDL_GetWindows(&count);
    for (int index = 0; windows && index < count; index++) {
        NSWindow *native = (__bridge NSWindow *)SDL_GetPointerProperty(SDL_GetWindowProperties(windows[index]),
            SDL_PROP_WINDOW_COCOA_WINDOW_POINTER, NULL);
        NSScreen *screen = native.screen ?: NSScreen.mainScreen;
        if (native && screen && !NSEqualRects(native.frame, screen.frame))
            [native setFrame:screen.frame display:YES];
    }
    SDL_free(windows);
}
- (void)applicationDidBecomeActive:(NSNotification *)notification {
    (void)notification;
    [self updateSystemChrome];
}
- (void)refreshFullscreen {
    self.fullscreenButton.state = (self.gameRunning ? host_sdl_is_fullscreen() : !self.preferences.windowed)
        ? NSControlStateValueOn : NSControlStateValueOff;
    [self updateSystemChrome];
}
- (void)toggleFullscreen:(id)sender {
    (void)sender;
    BOOL fullscreen = self.gameRunning ? !host_sdl_is_fullscreen() : self.preferences.windowed;
    if (!host_menu_set_fullscreen(fullscreen)) {
        showError([NSError errorWithDomain:@"Halo" code:1 userInfo:@{NSLocalizedDescriptionKey:@"The display could not change modes."}]);
        [self refreshFullscreen];
        return;
    }
    [self refreshFullscreen];
    if (self.settingsVisible) {
        host_sdl_release_mouse();
        [self.settingsWindow makeKeyAndOrderFront:self];
    }
}
- (void)showGame:(id)sender { (void)sender; host_sdl_show_game(); }
- (void)about:(id)sender {
    (void)sender;
    host_sdl_release_mouse();
    [NSApp orderFrontStandardAboutPanelWithOptions:@{NSAboutPanelOptionApplicationName:@"Halo OG"}];
}
- (void)quit:(id)sender {
    (void)sender;
    if (self.importing) return;
    self.quitting = YES;
    [self closeSettings:nil];
    if (self.gameRunning) host_sdl_request_quit();
    else [NSApp terminate:self];
}
- (void)buildSettings {
    self.settingsWindow = [[NSWindow alloc] initWithContentRect:NSMakeRect(0, 0, 520, 542)
        styleMask:NSWindowStyleMaskTitled backing:NSBackingStoreBuffered defer:NO];
    self.settingsWindow.title = @"Halo OG Settings";
    self.settingsWindow.releasedWhenClosed = NO;
    self.settingsWindow.preventsApplicationTerminationWhenModal = NO;
    self.settingsWindow.level = NSFloatingWindowLevel;
    self.settingsWindow.collectionBehavior = NSWindowCollectionBehaviorCanJoinAllSpaces | NSWindowCollectionBehaviorFullScreenAuxiliary;
    NSView *content = self.settingsWindow.contentView;
    label(content, @"Display", NSMakeRect(24, 305, 472, 22), NO).font = [NSFont boldSystemFontOfSize:13];
    self.fullscreenButton = [NSButton checkboxWithTitle:@"Full Screen" target:self action:@selector(toggleFullscreen:)];
    self.fullscreenButton.frame = NSMakeRect(24, 275, 472, 24);
    [content addSubview:self.fullscreenButton];
    label(content, @"Game Data", NSMakeRect(24, 235, 472, 22), NO).font = [NSFont boldSystemFontOfSize:13];
    self.dataLabel = label(content, @"No maps selected", NSMakeRect(24, 206, 472, 20), YES);
    self.sourceLabel = label(content, @"", NSMakeRect(24, 182, 472, 20), YES);
    button(content, @"Choose Disc Image…", @selector(selectImage:), NSMakeRect(20, 143, 183, 32));
    button(content, @"Choose Maps Folder…", @selector(selectFolder:), NSMakeRect(211, 143, 193, 32));
    label(content, @"Changes to game data take effect when Halo OG next opens.", NSMakeRect(24, 116, 472, 19), YES).font = [NSFont systemFontOfSize:11];
    self.automaticUpdatesButton = [NSButton checkboxWithTitle:@"Automatically check for updates"
                                                                  target:self action:@selector(automaticUpdates:)];
    self.automaticUpdatesButton.frame = NSMakeRect(24, 78, 472, 24);
    self.automaticUpdatesButton.enabled = self.updater != nil;
    [content addSubview:self.automaticUpdatesButton];
    if (!self.updater) label(content, @"Updates aren’t available for this build.", NSMakeRect(24, 58, 472, 17), YES).font = [NSFont systemFontOfSize:11];
    button(content, @"Advanced Settings…", @selector(openConfig:), NSMakeRect(20, 14, 185, 32));
    NSButton *done = button(content, @"Done", @selector(closeSettings:), NSMakeRect(401, 14, 95, 32));
    done.keyEquivalent = @"\r";
    for (NSView *view in content.subviews) {
        if (view.frame.origin.y >= 116) {
            NSRect frame = view.frame; frame.origin.y += 150; view.frame = frame;
        }
    }
    label(content, @"Community Maps", NSMakeRect(24, 227, 472, 22), NO).font = [NSFont boldSystemFontOfSize:13];
    self.communityDownloadsButton = [NSButton checkboxWithTitle:@"Download approved community maps in the background"
        target:self action:@selector(communityDownloads:)];
    self.communityDownloadsButton.frame = NSMakeRect(24, 197, 472, 24);
    self.communityDownloadsButton.enabled = self.mapDownloads.configured && self.mapDownloads.compatibleData;
    [content addSubview:self.communityDownloadsButton];
    self.downloadsLabel = label(content, @"", NSMakeRect(24, 149, 472, 42), YES);
    self.downloadsLabel.lineBreakMode = NSLineBreakByWordWrapping;
    self.downloadsLabel.maximumNumberOfLines = 2;
    self.downloadsLabel.font = [NSFont systemFontOfSize:11];
    button(content, @"Check Maps / Retry", @selector(checkMaps:), NSMakeRect(20, 108, 164, 32));
    button(content, @"Cancel Downloads", @selector(cancelMaps:), NSMakeRect(190, 108, 151, 32));
    button(content, @"Open Library", @selector(openMapLibrary:), NSMakeRect(347, 108, 149, 32));
    for (NSView *view in content.subviews) {
        if (view.frame.origin.y >= 108) {
            NSRect frame = view.frame; frame.origin.y += 42; view.frame = frame;
        }
    }
    self.packageImportButton = button(content, @"Import Community Package…", @selector(importCommunityPackage:), NSMakeRect(20, 108, 250, 32));
    label(content, @"Uses your original disc data", NSMakeRect(278, 114, 218, 20), YES).font = [NSFont systemFontOfSize:11];
}
- (void)refreshSettings {
    self.dataLabel.stringValue = self.preferences.dataPath ?: self.launchDataPath ?: @"No maps selected";
    self.dataLabel.toolTip = self.dataLabel.stringValue;
    self.sourceLabel.stringValue = self.preferences.isoPath ? [@"Disc image: " stringByAppendingString:self.preferences.isoPath] : @"Using an extracted maps folder";
    self.sourceLabel.toolTip = self.preferences.isoPath;
    self.automaticUpdatesButton.state = self.updater.updater.automaticallyChecksForUpdates ? NSControlStateValueOn : NSControlStateValueOff;
    self.communityDownloadsButton.state = self.preferences.communityDownloadsEnabled ? NSControlStateValueOn : NSControlStateValueOff;
    self.downloadsLabel.stringValue = self.packageStatus ?: self.mapDownloads.statusText ?: @"Map hosting is not configured for this build.";
    self.downloadsLabel.toolTip = self.downloadsLabel.stringValue;
    BOOL packageTools = [NSBundle.mainBundle URLForResource:@"ContentTools" withExtension:@"json"] != nil;
    self.packageImportButton.enabled = packageTools && self.mapDownloads.compatibleData && !self.importing;
    self.packageImportButton.toolTip = packageTools ? @"Rebuild a community map using your original Xbox game data." : @"This build does not include community package import.";
    [self refreshFullscreen];
}
- (void)showSettings:(id)sender {
    (void)sender;
    host_sdl_release_mouse();
    if (!self.settingsWindow) [self buildSettings];
    [self refreshSettings];
    [self.settingsWindow center];
    [NSApp activateIgnoringOtherApps:YES];
    [self.settingsWindow makeKeyAndOrderFront:self];
    /* Return to SDL immediately: the guest must keep servicing its network
       connections while native settings are open. */
    self.settingsVisible = YES;
    [self updateSystemChrome];
}
- (void)closeSettings:(id)sender {
    (void)sender;
    if (self.settingsWindow.attachedSheet)
        [self.settingsWindow endSheet:self.settingsWindow.attachedSheet returnCode:NSModalResponseCancel];
    self.settingsVisible = NO;
    [self.settingsWindow orderOut:self];
    [self updateSystemChrome];
    if (self.gameRunning && !self.quitting) host_sdl_show_game();
}
- (void)automaticUpdates:(NSButton *)sender {
    self.updater.updater.automaticallyChecksForUpdates = sender.state == NSControlStateValueOn;
}
- (void)communityDownloads:(NSButton *)sender {
    BOOL enabled = sender.state == NSControlStateValueOn;
    if (!enabled) {
        NSError *error = nil;
        if (![self.preferences setCommunityDownloadsEnabled:NO error:&error]) showError(error);
        else [self.mapDownloads setDownloadsEnabled:NO];
        [self refreshSettings]; return;
    }
    NSAlert *alert = [[NSAlert alloc] init];
    alert.messageText = @"Allow community map downloads?";
    alert.informativeText = @"Halo OG will download approved maps from this build's configured HTTPS catalog into Application Support. Missing maps and the catalog's selected launch maps can download while you play. Your original maps and disc images stay in place.";
    [alert addButtonWithTitle:@"Allow Downloads"];
    [alert addButtonWithTitle:@"Cancel"];
    [alert beginSheetModalForWindow:self.settingsWindow completionHandler:^(NSModalResponse response) {
        NSError *error = nil;
        if (response == NSAlertFirstButtonReturn) {
            if (![self.preferences setCommunityDownloadsEnabled:YES error:&error]) showError(error);
            else [self.mapDownloads setDownloadsEnabled:YES];
        }
        [self refreshSettings];
    }];
}
- (void)checkMaps:(id)sender { (void)sender; [self.mapDownloads checkForMaps]; }
- (void)cancelMaps:(id)sender { (void)sender; [self.mapDownloads cancelDownloads]; }
- (void)importCommunityPackage:(id)sender {
    (void)sender;
    if (self.importing || !self.launchDataPath) return;
    NSURL *recordURL = [NSBundle.mainBundle URLForResource:@"ContentTools" withExtension:@"json"];
    NSData *recordBytes = recordURL ? [NSData dataWithContentsOfURL:recordURL] : nil;
    NSDictionary *record = recordBytes ? [NSJSONSerialization JSONObjectWithData:recordBytes options:0 error:nil] : nil;
    if (![record isKindOfClass:NSDictionary.class]) return;
    NSOpenPanel *panel = NSOpenPanel.openPanel;
    panel.canChooseDirectories = NO; panel.canChooseFiles = YES; panel.allowsMultipleSelection = NO;
    panel.allowedFileTypes = @[@"hogpkg"]; panel.allowsOtherFileTypes = NO; panel.resolvesAliases = NO;
    panel.message = @"Choose a Halo OG community package. Halo OG will build its playable map from this package and your original Xbox disc data, then keep it in your map library.";
    [panel beginSheetModalForWindow:self.settingsWindow completionHandler:^(NSModalResponse response) {
        if (response != NSModalResponseOK || self.importing) return;
        self.importing = YES; self.packageStatus = @"Checking community package…"; [self refreshSettings];
        NSURL *package = panel.URL;
        NSURL *dataRoot = [NSURL fileURLWithPath:self.launchDataPath isDirectory:YES];
        NSURL *support = self.preferences.supportDirectory;
        NSURL *helpers = [NSBundle.mainBundle.bundleURL URLByAppendingPathComponent:@"Contents/Helpers" isDirectory:YES];
        dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{
            NSError *error = nil;
            NSDictionary *manifest = HaloInspectCommunityPackage(package, &error);
            NSURL *map = manifest ? HaloAssembleCommunityPackage(package, dataRoot, support, helpers, record, ^(NSString *progress) {
                dispatch_async(dispatch_get_main_queue(), ^{ self.packageStatus = progress; [self refreshSettings]; });
            }, &error) : nil;
            if (map) {
                [self.mapDownloads registerAssembledMap:map manifest:manifest completion:^(NSError *registrationError) {
                    self.importing = NO; self.packageStatus = nil; [self refreshSettings];
                    if (registrationError) showError(registrationError);
                }];
            } else {
                dispatch_async(dispatch_get_main_queue(), ^{
                    self.importing = NO; self.packageStatus = error.localizedDescription ?: @"The community map could not be prepared.";
                    [self refreshSettings]; if (error) showError(error);
                });
            }
        });
    }];
}
- (void)openMapLibrary:(id)sender {
    (void)sender;
    NSURL *library = [self.preferences.supportDirectory URLByAppendingPathComponent:@"Community Maps" isDirectory:YES];
    NSError *error = nil;
    if (![NSFileManager.defaultManager createDirectoryAtURL:library withIntermediateDirectories:YES attributes:nil error:&error]) showError(error);
    else [NSWorkspace.sharedWorkspace openURL:library];
}
- (void)openSaves:(id)sender {
    (void)sender;
    [NSWorkspace.sharedWorkspace openURL:self.preferences.supportDirectory];
}
- (void)openConfig:(id)sender {
    (void)sender;
    NSURL *config = [self.preferences.supportDirectory URLByAppendingPathComponent:@"config.toml"];
    if ([NSFileManager.defaultManager fileExistsAtPath:config.path]) {
        NSURL *editor = [NSWorkspace.sharedWorkspace URLForApplicationWithBundleIdentifier:@"com.apple.TextEdit"];
        if (editor) [NSWorkspace.sharedWorkspace openURLs:@[config] withApplicationAtURL:editor
            configuration:NSWorkspaceOpenConfiguration.configuration completionHandler:nil];
        else [NSWorkspace.sharedWorkspace openURL:config];
    } else {
        NSAlert *alert = [[NSAlert alloc] init];
        alert.messageText = @"Advanced settings appear after the first game launch";
        alert.informativeText = @"Start Halo OG once to create its controls and advanced settings file.";
        if (self.gameRunning) {
            [self showSettings:nil];
            [alert beginSheetModalForWindow:self.settingsWindow completionHandler:nil];
        } else {
            [alert runModal];
        }
    }
}
- (BOOL)chooseFolder {
    host_sdl_release_mouse();
    NSOpenPanel *panel = NSOpenPanel.openPanel;
    panel.title = @"Choose Your Xbox Halo Maps";
    panel.message = @"Choose an extracted game folder or its maps folder.";
    panel.canChooseDirectories = YES;
    panel.canChooseFiles = NO;
    panel.allowsMultipleSelection = NO;
    NSModalResponse result = [panel runModal];
    if (result != NSModalResponseOK) return NO;
    __block BOOL finished = NO, success = NO;
    [self acceptFolder:panel.URL completion:^(BOOL accepted) { success = accepted; finished = YES; }];
    while (!finished) [NSRunLoop.currentRunLoop runMode:NSDefaultRunLoopMode beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.05]];
    return success;
}
- (void)acceptFolder:(NSURL *)folder completion:(void (^)(BOOL))completion {
    NSError *error = nil;
    NSURL *valid = HaloValidateGameData(folder, &error);
    if (!valid) { showError(error); completion(NO); return; }
    NSError *copyError = nil;
    unsigned long long bytes = HaloGameDataCopySize(valid, &copyError);
    NSAlert *alert = [[NSAlert alloc] init];
    alert.messageText = @"Let Halo OG manage a copy of these maps?";
    alert.informativeText = copyError ? @"This folder uses linked map data. Use it in place to preserve your developer setup."
        : [NSString stringWithFormat:@"Halo OG can copy about %.1f GB into its Application Support folder and organize community maps there. Your original files stay in place.", bytes / 1073741824.0];
    [alert addButtonWithTitle:@"Copy and Manage"];
    [alert addButtonWithTitle:@"Use This Folder"];
    [alert addButtonWithTitle:@"Cancel"];
    alert.buttons.firstObject.enabled = !copyError;
    void (^apply)(NSModalResponse) = ^(NSModalResponse response) {
        if (response == NSAlertFirstButtonReturn && !copyError) [self copyFolder:valid completion:completion];
        else if (response == NSAlertSecondButtonReturn) {
            NSError *selectionError = nil;
            BOOL success = [self.preferences selectDataRoot:valid iso:nil error:&selectionError];
            if (!success) showError(selectionError);
            else [self refreshSettings];
            completion(success);
        } else completion(NO);
    };
    if (self.gameRunning) [alert beginSheetModalForWindow:self.settingsWindow completionHandler:apply];
    else apply([alert runModal]);
}
- (void)copyFolder:(NSURL *)folder completion:(void (^)(BOOL))completion {
    NSWindow *window = [[NSWindow alloc] initWithContentRect:NSMakeRect(0, 0, 470, 130)
        styleMask:NSWindowStyleMaskTitled backing:NSBackingStoreBuffered defer:NO];
    window.title = @"Copying Halo OG Maps";
    window.level = NSFloatingWindowLevel;
    NSTextField *progressLabel = label(window.contentView, @"Preparing a managed copy…", NSMakeRect(24, 78, 422, 22), NO);
    NSProgressIndicator *bar = [[NSProgressIndicator alloc] initWithFrame:NSMakeRect(24, 48, 422, 18)];
    bar.indeterminate = NO; bar.minValue = 0; bar.maxValue = 100;
    [window.contentView addSubview:bar];
    label(window.contentView, @"Your original maps and existing saves stay in place.", NSMakeRect(24, 16, 422, 19), YES);
    [window center]; [window makeKeyAndOrderFront:self];
    self.importing = YES;
    __block struct import_progress progress = {progressLabel, bar};
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        NSError *error = nil;
        NSURL *imported = HaloCopyGameData(folder, self.preferences.supportDirectory, importProgress, &progress, &error);
        dispatch_async(dispatch_get_main_queue(), ^{
            self.importing = NO; [window orderOut:self];
            NSError *selectionError = error;
            BOOL success = imported && [self.preferences selectDataRoot:imported iso:nil error:&selectionError];
            if (!success) {
                if (imported) [NSFileManager.defaultManager removeItemAtURL:imported error:nil];
                showError(selectionError);
            } else [self refreshSettings];
            completion(success);
        });
    });
}
- (BOOL)chooseImage {
    host_sdl_release_mouse();
    NSOpenPanel *panel = NSOpenPanel.openPanel;
    panel.title = @"Choose Your Xbox Halo Disc Image";
    panel.message = @"The app imports only the maps from your local disc image.";
    panel.canChooseDirectories = NO;
    panel.canChooseFiles = YES;
    panel.allowsMultipleSelection = NO;
    NSModalResponse result = [panel runModal];
    if (result != NSModalResponseOK) return NO;
    __block BOOL finished = NO, succeeded = NO;
    [self importImage:panel.URL completion:^(BOOL success) { succeeded = success; finished = YES; }];
    /* The first-launch chooser runs before the engine starts. Runtime imports
       use the asynchronous completion directly and never enter this loop. */
    while (!finished)
        [NSRunLoop.currentRunLoop runMode:NSDefaultRunLoopMode beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.05]];
    return succeeded;
}
- (void)importImage:(NSURL *)image completion:(void (^)(BOOL))completion {
    NSWindow *window = [[NSWindow alloc] initWithContentRect:NSMakeRect(0, 0, 470, 130)
        styleMask:NSWindowStyleMaskTitled backing:NSBackingStoreBuffered defer:NO];
    window.title = @"Importing Halo OG Maps";
    window.level = NSFloatingWindowLevel;
    NSTextField *progressLabel = label(window.contentView, @"Reading disc image…", NSMakeRect(24, 78, 422, 22), NO);
    NSProgressIndicator *bar = [[NSProgressIndicator alloc] initWithFrame:NSMakeRect(24, 48, 422, 18)];
    bar.indeterminate = NO;
    bar.minValue = 0;
    bar.maxValue = 100;
    [window.contentView addSubview:bar];
    label(window.contentView, @"Your existing maps and saves stay in place.", NSMakeRect(24, 16, 422, 19), YES);
    [window center];
    [window makeKeyAndOrderFront:self];
    self.importing = YES;
    __block struct import_progress progress = {progressLabel, bar};
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        NSError *error = nil;
        NSURL *imported = HaloImportDiscImage(image, self.preferences.supportDirectory, importProgress, &progress, &error);
        dispatch_async(dispatch_get_main_queue(), ^{
            self.importing = NO;
            [window orderOut:self];
            NSError *selectionError = error;
            BOOL succeeded = imported && [self.preferences selectDataRoot:imported iso:image error:&selectionError];
            if (!succeeded) {
                if (imported) [NSFileManager.defaultManager removeItemAtURL:imported error:nil];
                showError(selectionError);
            } else {
                [self refreshSettings];
            }
            completion(succeeded);
        });
    });
}
- (void)changedDataNotice {
    if (!self.gameRunning) return;
    NSAlert *alert = [[NSAlert alloc] init];
    alert.messageText = @"Game data updated";
    alert.informativeText = @"Halo OG will use your selection the next time it opens. Your current game can continue.";
    [self showSettings:nil];
    [alert beginSheetModalForWindow:self.settingsWindow completionHandler:nil];
}
- (void)selectFolder:(id)sender {
    (void)sender;
    if (self.importing || self.settingsWindow.attachedSheet) return;
    if (!self.gameRunning) { [self chooseFolder]; return; }
    [self showSettings:nil];
    NSOpenPanel *panel = NSOpenPanel.openPanel;
    panel.title = @"Choose Your Xbox Halo Maps";
    panel.message = @"Choose an extracted game folder or its maps folder.";
    panel.canChooseDirectories = YES;
    panel.canChooseFiles = NO;
    panel.allowsMultipleSelection = NO;
    [panel beginSheetModalForWindow:self.settingsWindow completionHandler:^(NSModalResponse response) {
        if (self.quitting || response != NSModalResponseOK) return;
        [self acceptFolder:panel.URL completion:^(BOOL success) { if (success) [self changedDataNotice]; }];
    }];
}
- (void)selectImage:(id)sender {
    (void)sender;
    if (self.importing || self.settingsWindow.attachedSheet) return;
    if (!self.gameRunning) { [self chooseImage]; return; }
    [self showSettings:nil];
    NSOpenPanel *panel = NSOpenPanel.openPanel;
    panel.title = @"Choose Your Xbox Halo Disc Image";
    panel.message = @"The app imports only the maps from your local disc image.";
    panel.canChooseDirectories = NO;
    panel.canChooseFiles = YES;
    panel.allowsMultipleSelection = NO;
    [panel beginSheetModalForWindow:self.settingsWindow completionHandler:^(NSModalResponse response) {
        if (self.quitting || response != NSModalResponseOK) return;
        [self importImage:panel.URL completion:^(BOOL success) { if (success) [self changedDataNotice]; }];
    }];
}
- (void)checkUpdates:(id)sender {
    (void)sender;
    host_sdl_release_mouse();
    [self.updater checkForUpdates:self];
}
- (BOOL)supportsGentleScheduledUpdateReminders { return YES; }
- (BOOL)standardUserDriverShouldHandleShowingScheduledUpdate:(SUAppcastItem *)update andInImmediateFocus:(BOOL)focus {
    (void)update; (void)focus;
    return !self.gameRunning;
}
- (void)standardUserDriverWillHandleShowingUpdate:(BOOL)handle forUpdate:(SUAppcastItem *)update state:(SPUUserUpdateState *)state {
    (void)handle; (void)state;
    self.availableVersion = update.displayVersionString;
    self.status.button.toolTip = [NSString stringWithFormat:@"Halo OG %@ is available", self.availableVersion];
}
- (BOOL)updater:(SPUUpdater *)updater shouldPostponeRelaunchForUpdate:(SUAppcastItem *)update untilInvokingBlock:(void (^)(void))install {
    (void)updater; (void)update;
    if (!self.gameRunning) return NO;
    self.pendingInstall = install;
    self.status.button.toolTip = @"Halo OG update ready — quit the game to install";
    return YES;
}
- (BOOL)updater:(SPUUpdater *)updater willInstallUpdateOnQuit:(SUAppcastItem *)update immediateInstallationBlock:(void (^)(void))install {
    (void)updater; (void)update;
    self.pendingInstall = install;
    return YES;
}
- (void)updater:(SPUUpdater *)updater didAbortWithError:(NSError *)error {
    (void)updater; (void)error;
    self.pendingInstall = nil;
    self.waitingForUpdate = NO;
}
@end

void host_menu_style_window(void *window) {
    SDL_Window *sdlWindow = window;
    NSWindow *native = (__bridge NSWindow *)SDL_GetPointerProperty(SDL_GetWindowProperties(sdlWindow),
        SDL_PROP_WINDOW_COCOA_WINDOW_POINTER, NULL);
    if (!native) return;
    native.titleVisibility = NSWindowTitleHidden;
    native.titlebarAppearsTransparent = YES;
    native.styleMask |= NSWindowStyleMaskFullSizeContentView;
    native.movableByWindowBackground = NO;
    [native standardWindowButton:NSWindowCloseButton].hidden = YES;
    [native standardWindowButton:NSWindowMiniaturizeButton].hidden = YES;
    [native standardWindowButton:NSWindowZoomButton].hidden = YES;
}

int host_menu_set_fullscreen(int enabled) {
    /* Before first launch the settings panel edits the next launch's mode. */
    if (menu.preferences && !menu.gameRunning)
        return [menu.preferences setWindowed:!enabled error:nil];
    BOOL wasFullscreen = host_sdl_is_fullscreen();
    if (!host_sdl_set_fullscreen(enabled)) return 0;
    if (menu.preferences) {
        NSError *error = nil;
        if (![menu.preferences setWindowed:!enabled error:&error]) {
            host_sdl_set_fullscreen(wasFullscreen);
            return 0;
        }
    }
    return 1;
}

void host_menu_initialize_application(void) {
    @autoreleasepool {
        /* SDL's NSApplication subclass intercepts terminate: without consulting
           delegates. Use Cocoa's normal lifecycle so settings can close and
           Sparkle can terminate after the guest saves and exits. SDL supports
           an existing NSApplication and still pumps its native input/events. */
        [NSApplication sharedApplication];
        [NSApp setActivationPolicy:NSApplicationActivationPolicyRegular];
    }
}

int host_menu_prepare(const char *support, const char *fallback, char *data, size_t capacity) {
    @autoreleasepool {
        menu = [[HaloMenu alloc] init];
        menu.previousDelegate = NSApp.delegate;
        NSApp.delegate = menu;
        if (HaloUpdateConfigurationIsValid(NSBundle.mainBundle.infoDictionary))
            menu.updater = [[SPUStandardUpdaterController alloc] initWithStartingUpdater:YES updaterDelegate:menu userDriverDelegate:menu];
        [menu buildMenus];
        [NSApp finishLaunching];
        NSURL *supportDirectory = [NSURL fileURLWithPath:@(support) isDirectory:YES];
        if (![menu migrateSupportIfNeeded:supportDirectory]) return 0;
        menu.preferences = [[HaloPreferences alloc] initWithSupportDirectory:supportDirectory];
        NSString *selected = menu.preferences.dataPath;
        const char *override = getenv("HALO_DATA_ROOT");
        if (override && *override) selected = @(override);
        NSURL *valid = selected ? HaloValidateGameData([NSURL fileURLWithPath:selected], nil) : nil;
        if (!selected && fallback && *fallback) valid = HaloValidateGameData([NSURL fileURLWithPath:@(fallback)], nil);
        if (valid && !selected) {
            NSError *error = nil;
            if (![menu.preferences selectDataRoot:valid iso:nil error:&error]) { showError(error); return 0; }
        }
        while (!valid) {
            NSAlert *alert = [[NSAlert alloc] init];
            alert.messageText = @"Choose your Halo OG game data";
            alert.informativeText = @"Use your own original Xbox Halo disc image or extracted maps folder. The app does not include game data.";
            [alert addButtonWithTitle:@"Choose Disc Image…"];
            [alert addButtonWithTitle:@"Choose Maps Folder…"];
            [alert addButtonWithTitle:@"Quit"];
            NSModalResponse answer = [alert runModal];
            if (answer == NSAlertThirdButtonReturn) return 0;
            BOOL chosen = answer == NSAlertFirstButtonReturn ? [menu chooseImage] : [menu chooseFolder];
            if (chosen) valid = [NSURL fileURLWithPath:menu.preferences.dataPath];
        }
        /* Development overrides apply to this launch; chooser actions save the
           next launch's selection without changing the current game's files. */
        menu.launchDataPath = valid.path;
        NSURL *downloadConfiguration = [NSBundle.mainBundle URLForResource:@"map-downloads" withExtension:@"json"];
        NSData *downloadSettings = downloadConfiguration ? [NSData dataWithContentsOfURL:downloadConfiguration] : nil;
        NSDictionary *downloadConfig = downloadSettings ? [NSJSONSerialization JSONObjectWithData:downloadSettings options:0 error:nil] : nil;
        menu.mapDownloads = [[HaloMapDownloads alloc] initWithSupportDirectory:menu.preferences.supportDirectory
            configuration:downloadConfig sessionConfiguration:nil];
        [menu.mapDownloads setGameDataRoot:valid];
        [menu.mapDownloads activateForHost];
        __weak HaloMenu *weakMenu = menu;
        menu.mapDownloads.statusChanged = ^{ [weakMenu refreshSettings]; };
        [menu.mapDownloads startEnabled:menu.preferences.communityDownloadsEnabled];
        if (!getenv("HALO_WINDOWED")) SDL_setenv_unsafe("HALO_WINDOWED", menu.preferences.windowed ? "1" : "0", 1);
        return [valid.path getCString:data maxLength:capacity encoding:NSUTF8StringEncoding] ? 1 : 0;
    }
}
void host_menu_begin_game(void) { menu.gameRunning = YES; [menu refreshFullscreen]; }
void host_menu_window_changed(void) { [menu refreshFullscreen]; }
void host_menu_finish_game(int exit_code) {
    @autoreleasepool {
        menu.quitting = YES;
        [menu.mapDownloads cancelDownloads];
        [menu closeSettings:nil];
        menu.gameRunning = NO;
        [menu updateSystemChrome];
        if (!exit_code && menu.pendingInstall) {
            menu.waitingForUpdate = YES;
            menu.pendingInstall();
            menu.pendingInstall = nil;
            /* Sparkle gets a normal Cocoa termination after the guest has saved
               and exited. SDL's delegate must not cancel that termination. */
            while (menu.waitingForUpdate)
                [NSRunLoop.currentRunLoop runMode:NSDefaultRunLoopMode beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.05]];
        }
        if (menu.status) [NSStatusBar.systemStatusBar removeStatusItem:menu.status];
    }
}
