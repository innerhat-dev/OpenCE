/*
GUEST_MACOS.LD

Layout of the Mac guest image. It is linked at 0xA0000000, just above the
512 MB Xbox window (HALO_GUEST_IMAGE_BASE in halo_android_abi.h). The host
copies the loadable segments to these addresses.
*/

ENTRY(__guest_header)

SECTIONS
{
	. = 0xA0000000;
	.guest_header : { KEEP(*(.guest_header)) }
	.text : { *(.text .text.*) }
	.rodata : { *(.rodata .rodata.*) }
	. = ALIGN(0x10000);
	.data : { *(.data .data.*) }
	.guest_init : {
		__guest_init_start = .;
		KEEP(*(.guest_init))
		__guest_init_end = .;
	}
	.bss : { *(.bss .bss.*) *(COMMON) }
	. = ALIGN(0x1000);
	__guest_image_end = .;
	/DISCARD/ : { *(.comment) *(.note.*) *(.guest_fini) *(.eh_frame) }
}
