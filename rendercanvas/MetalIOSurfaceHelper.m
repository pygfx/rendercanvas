/*

clang -dynamiclib -fobjc-arc \
  -framework Foundation -framework Metal -framework IOSurface \
  -arch x86_64 -arch arm64 \
  -mmacosx-version-min=10.13 \
  -o libMetalIOSurfaceHelper.dylib MetalIOSurfaceHelper.m

*/
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#import <IOSurface/IOSurface.h>

@interface MetalIOSurfaceHelper : NSObject
@property (nonatomic, readonly) id<MTLDevice> device;
@property (nonatomic, readonly) id<MTLTexture> texture;

- (instancetype)initWithWidth:(NSUInteger)width
                       height:(NSUInteger)height;

- (void *)baseAddress;
- (NSUInteger)bytesPerRow;
@end


@implementation MetalIOSurfaceHelper {
    IOSurfaceRef _surf;
}

- (instancetype)initWithWidth:(NSUInteger)width
                       height:(NSUInteger)height
{
    if ((self = [super init])) {
        // Create Metal device
        _device = MTLCreateSystemDefaultDevice();
        if (!_device) {
            NSLog(@"❌ Failed to create Metal device");
            return nil;
        }

        // Create IOSurface properties
        NSDictionary *props = @{
            (id)kIOSurfaceWidth: @(width),
            (id)kIOSurfaceHeight: @(height),
            (id)kIOSurfaceBytesPerElement: @(4),
            (id)kIOSurfacePixelFormat: @(0x42475241) // 'BGRA'
        };

        _surf = IOSurfaceCreate((__bridge CFDictionaryRef)props);
        if (!_surf) {
            NSLog(@"❌ Failed to create IOSurface");
            return nil;
        }

        // Create texture from IOSurface
        MTLTextureDescriptor *desc =
            [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatBGRA8Unorm
                                                                width:width
                                                               height:height
                                                            mipmapped:NO];
        desc.storageMode = MTLStorageModeShared;

        _texture = [_device newTextureWithDescriptor:desc iosurface:_surf plane:0];
        if (!_texture) {
            NSLog(@"❌ Failed to create MTLTexture from IOSurface");
            CFRelease(_surf);
            return nil;
        }
    }
    return self;
}

- (void *)baseAddress {
    return IOSurfaceGetBaseAddress(_surf);
}

- (NSUInteger)bytesPerRow {
    return IOSurfaceGetBytesPerRow(_surf);
}

- (void)dealloc {
    if (_surf) {
        CFRelease(_surf);
        _surf = NULL;
    }
}

@end