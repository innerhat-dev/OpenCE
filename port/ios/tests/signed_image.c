/* Executes guest instructions from a signed __TEXT section, with RW-only data. */
#include "image.h"
#include <mach/mach.h>
#include <mach/mach_vm.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
static uintptr_t BIAS;
static unsigned host_probe(unsigned *p) {
    if ((uintptr_t)p < BIAS || (uintptr_t)p >= BIAS + UINT64_C(0x100000000)) abort();
    return ++*p;
}
static void *run(void *unused) {
    (void)unused;
    uint32_t (*entry)(uint32_t) = (void *)(halo_ios_image + HALO_IOS_IMAGE_ENTRY - HALO_IOS_IMAGE_BASE);
    uint32_t result = entry(42);
    printf("Signed image probe: result=%u expected=93; code=%p data=%p\n", result,
           (void *)entry, (void *)(BIAS + HALO_IOS_IMAGE_BASE));
    return (void *)(uintptr_t)(result != 93);
}
int main(int argc, char **argv) {
    // Optional fixed addresses exercise the exact same code at different bases.
    vm_address_t address = argc > 1 ? strtoull(argv[1], NULL, 0) : 0;
    kern_return_t reserved = vm_map(mach_task_self(), &address, UINT64_C(0x100000000),
        UINT64_C(0xffffffff), address ? VM_FLAGS_FIXED : VM_FLAGS_ANYWHERE,
        MACH_PORT_NULL, 0, FALSE, VM_PROT_NONE, VM_PROT_READ | VM_PROT_WRITE, VM_INHERIT_NONE);
    if (reserved || !address || (address & UINT64_C(0xffffffff))) {
        fprintf(stderr, "Cannot reserve aligned test arena: %s\n", mach_error_string(reserved));
        return 1;
    }
    BIAS = address;
    mprotect((void *)BIAS, UINT64_C(0x100000000), PROT_NONE);
    mprotect((void *)(BIAS + HALO_IOS_IMAGE_BASE), HALO_IOS_IMAGE_SIZE, PROT_READ | PROT_WRITE);
    memcpy((void *)(BIAS + HALO_IOS_IMAGE_BASE), halo_ios_image, HALO_IOS_IMAGE_SIZE);
    *(uintptr_t *)(BIAS + TEST_IMPORT_TABLE) = (uintptr_t)host_probe;
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
