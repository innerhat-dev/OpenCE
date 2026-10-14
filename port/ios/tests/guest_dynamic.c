/* Exercise the generated host-import bridge with stack and global pointers. */
extern unsigned guest_test(unsigned);
extern unsigned host_probe(unsigned *);
static unsigned value = 13;
unsigned dynamic_test(unsigned input) {
    unsigned stack = 29;
    if (host_probe(&stack) != 30 || host_probe(&value) != 14)
        return 106;
    return guest_test(input);
}
