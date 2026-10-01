/* Executes guest instructions from a signed __TEXT section, with RW-only data. */
#include "image.h"
#include <mach/mach.h>
#include <mach/mach_vm.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#ifdef HALO_IOS_MAC_CHECK
#define BIAS UINT64_C(0x10000000000)
#else
#define BIAS UINT64_C(0x400000000)
#endif
static void *run(void *unused) {
    (void)unused;
    uint32_t (*entry)(uint32_t) = (void *)(halo_ios_image + HALO_IOS_IMAGE_ENTRY - HALO_IOS_IMAGE_BASE);
    uint32_t result = entry(42);
    printf("Signed image probe: result=%u expected=93; code=%p data=%p\n", result,
           (void *)entry, (void *)(BIAS + HALO_IOS_IMAGE_BASE));
    return (void *)(uintptr_t)(result != 93);
}
int main(void) {
    mach_vm_address_t address = BIAS;
    kern_return_t reserved = mach_vm_allocate(mach_task_self(), &address, UINT64_C(0x100000000), VM_FLAGS_FIXED);
    if (reserved) {
        fprintf(stderr, "Cannot reserve signed-image test arena: %s\n", mach_error_string(reserved));
        mach_vm_address_t occupied = BIAS;
        mach_vm_size_t length;
        vm_region_basic_info_data_64_t info;
        mach_msg_type_number_t count = VM_REGION_BASIC_INFO_COUNT_64;
        mach_port_t object;
        if (mach_vm_region(mach_task_self(), &occupied, &length, VM_REGION_BASIC_INFO_64,
                           (vm_region_info_t)&info, &count, &object) == KERN_SUCCESS) {
            fprintf(stderr, "Occupied range: %llx-%llx\n", occupied, occupied + length);
            if (object != MACH_PORT_NULL) mach_port_deallocate(mach_task_self(), object);
        }
        return 1;
    }
    mprotect((void *)BIAS, UINT64_C(0x100000000), PROT_NONE);
    mprotect((void *)(BIAS + HALO_IOS_IMAGE_BASE), HALO_IOS_IMAGE_SIZE, PROT_READ | PROT_WRITE);
    memcpy((void *)(BIAS + HALO_IOS_IMAGE_BASE), halo_ios_image, HALO_IOS_IMAGE_SIZE);
    mprotect((void *)(BIAS + 0xff0000), 16384, PROT_READ | PROT_WRITE);
    *(uint64_t *)(BIAS + 0xff0000) = (uintptr_t)halo_ios_image - HALO_IOS_IMAGE_BASE;
    mprotect((void *)(BIAS + 0xff0000), 16384, PROT_READ);
    mprotect((void *)(BIAS + 0x80000000), 16384, PROT_READ | PROT_WRITE);
    void *stack = (void *)(BIAS + 0x90000000);
    mprotect(stack, 0x400000, PROT_READ | PROT_WRITE);
    pthread_attr_t attributes;
    pthread_attr_init(&attributes);
    pthread_attr_setstack(&attributes, stack, 0x400000);
    pthread_t thread;
    if (pthread_create(&thread, &attributes, run, NULL)) return 2;
    void *result;
    pthread_join(thread, &result);
    return (int)(uintptr_t)result;
}
