"""Compile the ping code retained by v11 against a deterministic, source-only game fixture.

The getter, sender, stale filter, receive validation/batch/role preamble and ping
receive case come from production source. Other message handlers are omitted;
their entry-size types are inert fixtures because these tests send only pings.
The guest uses 32-bit C long; extracted code substitutes int32_t on LP64 hosts.
This does not exercise socket transport, tick scheduling or the full game reset.
"""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def block(source, signature):
    """Return a C declaration/function through its matching closing brace."""
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 0
    tokens = r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[{}]'
    for match in re.finditer(tokens, source[opening:], re.S):
        if match[0] == "{":
            depth += 1
        elif match[0] == "}":
            depth -= 1
            if not depth:
                return source[start:opening + match.end()]
    raise ValueError(f"Unclosed C block: {signature}")


def constant(source, name):
    return re.search(rf"\b{re.escape(name)}\s*=\s*([^,\n]+)", source)[0] + ","


PREFIX = r'''
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "halo_port_limits.h"
typedef unsigned char byte;
typedef uint16_t word, message_header;
typedef int boolean;
typedef float real;
#define TRUE 1
#define FALSE 0
#define NONE (-1)
#define MIN(a,b) ((a) < (b) ? (a) : (b))
#define csmemcpy memcpy
/* DECLARATIONS */
enum { _game_connection_local, _game_connection_network_client, _game_connection_network_server };
static int connection, in_game = 1;
static int game_connection(void) { return connection; }
static int game_in_progress(void) { return in_game; }
static byte players[MAXIMUM_TRACKED_PLAYERS];
static void *distributed_player(short index) {
    assert(index >= 0 && index < MAXIMUM_TRACKED_PLAYERS);
    return players[index] ? &players[index] : NULL;
}
static int32_t distributed_player_machines[MAXIMUM_TRACKED_PLAYERS];
static struct { boolean valid; real average, deviation; }
    distributed_round_trips[HALO_PORT_MAXIMUM_NETWORK_MACHINES];
static word distributed_player_pings[MAXIMUM_TRACKED_PLAYERS];
static int32_t distributed_received_times[MAXIMUM_SENDERS][NUMBER_OF_DISTRIBUTED_MESSAGES];
static int32_t distributed_host_time = NONE;
static struct { unsigned received; } distributed_statistics;

/* Non-ping entry sizes are only needed to compile the original validation switch. */
struct distributed_player_statistics { byte unused; };
struct distributed_pickup { byte unused; };
struct distributed_player_input { byte unused; };
struct distributed_client_identity { byte unused; };
static word network_damage_entry_size(byte type) { (void)type; return 0; }
static word network_objects_entry_size(byte type) { (void)type; return 0; }
static void distributed_note_client_clock(int32_t machine, int32_t time) {
    (void)machine; (void)time; assert(0); /* Tests receive only from the host. */
}
static boolean distributed_machine_clock_fast(int32_t machine) { (void)machine; return FALSE; }

static unsigned sends;
static short sent_count;
static word sent_size;
static struct distributed_pings_message sent;
static void distributed_send(void *message, byte type, short count, word size, short destination) {
    assert(type == _distributed_message_pings && destination == _distributed_to_clients);
    assert(count > 0 && count <= MAXIMUM_PINGS_PER_MESSAGE);
    assert(size == sizeof(sent.header) + count * sizeof(sent.players[0]));
    assert(size <= sizeof(sent));
    memcpy(&sent, message, size);
    sent_count = count; sent_size = size; sends++;
}
/* FUNCTIONS */
'''

HARNESS = r'''
static void reset(void) {
    memset(players, 0, sizeof(players));
    memset(distributed_player_machines, 0xff, sizeof(distributed_player_machines));
    memset(distributed_round_trips, 0, sizeof(distributed_round_trips));
    memset(distributed_player_pings, 0xff, sizeof(distributed_player_pings));
    memset(distributed_received_times, 0xff, sizeof(distributed_received_times));
    distributed_host_time = NONE; sends = 0; in_game = 1;
}
static void wire_layout(void) {
    struct distributed_player_ping ping = {7, 0, 0x1234};
    const byte expected[] = {7, 0, 0x34, 0x12};
    assert(HALO_PORT_NETWORK_VERSION == 11);
    assert(_distributed_message_client_identity == 18 && _distributed_message_pings == 19);
    assert(NUMBER_OF_DISTRIBUTED_MESSAGES == 20);
    assert(sizeof(struct distributed_message_header) == 8);
    assert(offsetof(struct distributed_message_header, game_time) == 4);
    assert(sizeof(ping) == 4 && offsetof(struct distributed_player_ping, milliseconds) == 2);
    assert(sizeof(struct distributed_pings_message) == 520);
    assert(PING_INTERVAL_TICKS == 60 && MAXIMUM_PINGS_PER_MESSAGE == 128);
    assert(!memcmp(&ping, expected, sizeof(expected)));
}
static void mapping(void) {
    reset(); connection = _game_connection_network_server;
    assert(distributed_player_ping(-1) == NONE);
    assert(distributed_player_ping(MAXIMUM_TRACKED_PLAYERS) == NONE);
    assert(distributed_player_ping(0) == NONE);
    players[0] = 1; assert(distributed_player_ping(0) == 0);
    players[1] = 1; distributed_player_machines[1] = 3;
    assert(distributed_player_ping(1) == NONE);
    distributed_round_trips[3].valid = TRUE;
    distributed_round_trips[3].average = 3.0f;
    assert(distributed_player_ping(1) == 100);
    distributed_round_trips[3].average = 1.0f;
    assert(distributed_player_ping(1) == 33);
    distributed_round_trips[3].average = 1.5f;
    assert(distributed_player_ping(1) == 50);
    distributed_player_machines[1] = -2; assert(distributed_player_ping(1) == NONE);
    distributed_player_machines[1] = HALO_PORT_MAXIMUM_NETWORK_MACHINES;
    assert(distributed_player_ping(1) == NONE);
    connection = _game_connection_network_client;
    assert(distributed_player_ping(0) == NONE);
    distributed_player_pings[0] = 0; assert(distributed_player_ping(0) == 0);
    distributed_player_pings[0] = 65534; assert(distributed_player_ping(0) == 65534);
    connection = _game_connection_local; assert(distributed_player_ping(0) == NONE);
}
static void sending(void) {
    reset(); connection = _game_connection_network_server;
    distributed_send_pings(); assert(sends == 0);
    players[0] = players[7] = players[127] = 1;
    distributed_player_machines[7] = 2;
    distributed_player_machines[127] = 3;
    distributed_round_trips[3].valid = TRUE;
    distributed_round_trips[3].average = 2000.0f;
    distributed_send_pings(); assert(sends == 1 && sent_count == 3 && sent_size == 20);
    assert(sent.players[0].player_index == 0 && sent.players[0].milliseconds == 0);
    assert(sent.players[1].player_index == 7 && sent.players[1].milliseconds == UNKNOWN_PING);
    assert(sent.players[2].player_index == 127 && sent.players[2].milliseconds == 65534);
    for (int i = 0; i < sent_count; i++) assert(sent.players[i].pad == 0);
    memset(players, 1, sizeof(players)); sends = 0;
    distributed_send_pings(); assert(sends == 1 && sent_count == 128 && sent_size == 520);
    for (int i = 0; i < sent_count; i++) assert(sent.players[i].player_index == i);
}
static void receive(struct distributed_pings_message *message, word size) {
    network_distributed_handle_message(NONE, (word const *)message, size);
}
static void receiving(void) {
    struct distributed_pings_message message = {0};
    reset(); connection = _game_connection_network_client; players[0] = players[127] = 1;
    message.header.type = _distributed_message_pings;
    message.header.count = 2; message.header.game_time = 10;
    message.players[0] = (struct distributed_player_ping){0, 0, 42};
    message.players[1] = (struct distributed_player_ping){127, 0, 99};
    receive(&message, 7); receive(&message, 15); /* Header and entry truncation. */
    assert(distributed_player_ping(0) == NONE && distributed_host_time == NONE);
    in_game = 0; receive(&message, 16); assert(distributed_player_ping(0) == NONE);
    in_game = 1;
    connection = _game_connection_network_server;
    receive(&message, 16); assert(distributed_player_pings[0] == UNKNOWN_PING);
    connection = _game_connection_local;
    receive(&message, 16); assert(distributed_player_pings[0] == UNKNOWN_PING);
    connection = _game_connection_network_client;
    receive(&message, 16); assert(distributed_player_ping(0) == 42);
    assert(distributed_player_ping(127) == 99 && distributed_host_time == 10);
    message.header.game_time = 9; message.players[0].milliseconds = 300;
    receive(&message, 16); assert(distributed_player_ping(0) == 42);
    message.header.game_time = 10; message.players[0].milliseconds = 43;
    receive(&message, 16); assert(distributed_player_ping(0) == 43); /* Same-tick chunks allowed. */
    message.header.game_time = 11; message.players[0].milliseconds = UNKNOWN_PING;
    message.players[1].player_index = 255;
    receive(&message, 16); assert(distributed_player_ping(0) == NONE);
    assert(distributed_player_ping(127) == 99);
    message.header.game_time = 12; message.header.count = 255;
    receive(&message, sizeof(message)); assert(distributed_host_time == 11);
    message.header.count = 1; message.header.type = NUMBER_OF_DISTRIBUTED_MESSAGES;
    receive(&message, 12); assert(distributed_host_time == 11);
    message.header.type = 0; receive(&message, 12); assert(distributed_host_time == 11);
}
static void batching(void) {
    struct distributed_pings_message message = {0};
    word buffer[32] = {0}, length;
    struct distributed_message_header batch = {0};
    reset(); connection = _game_connection_network_client; players[7] = 1;
    message.header.type = _distributed_message_pings;
    message.header.count = 1; message.header.game_time = 20;
    message.players[0] = (struct distributed_player_ping){7, 0, 85};
    batch.type = _distributed_message_batch;
    memcpy(buffer, &batch, sizeof(batch));
    length = 12 - sizeof(message_header);
    memcpy((byte *)buffer + sizeof(batch), &length, sizeof(length));
    memcpy((byte *)buffer + sizeof(batch) + sizeof(length),
        (byte *)&message + sizeof(message_header), length);
    network_distributed_handle_message(NONE, buffer, 19);
    assert(distributed_player_ping(7) == NONE); /* Truncated contained message. */
    network_distributed_handle_message(NONE, buffer, 20);
    assert(distributed_player_ping(7) == 85);
}
int main(int argc, char **argv) {
    assert(argc == 2);
    if (!strcmp(argv[1], "wire")) wire_layout();
    else if (!strcmp(argv[1], "mapping")) mapping();
    else if (!strcmp(argv[1], "sending")) sending();
    else if (!strcmp(argv[1], "receiving")) receiving();
    else if (!strcmp(argv[1], "batching")) batching();
    else assert(0);
    return 0;
}
'''


def production_code():
    source = (ROOT / "port/linux/game/network_distributed.c").read_text()
    header = (ROOT / "port/linux/game/network_distributed.h").read_text()
    declarations = header.split("/* ---------- constants */", 1)[1].split(
        "/* ---------- prototypes/NETWORK_DISTRIBUTED.C */", 1)[0]
    values = [(source, name) for name in (
        "PING_INTERVAL_TICKS", "MAXIMUM_PINGS_PER_MESSAGE", "UNKNOWN_PING",
        "MAXIMUM_SENDERS", "HOST_SENDER", "DISTRIBUTED_UNIT_STATE_MINIMUM_SIZE",
        "DISTRIBUTED_RELAYED_ACTION_MINIMUM_SIZE")]
    for path, name in (
        ("source/cseries/cseries.h", "TICKS_PER_SECOND"),
        ("source/networking/network_connection.h", "DATAGRAM_MAXIMUM_SIZE"),
        ("source/bungie_net/common/message_header.h", "MAXIMUM_MESSAGE_SIZE"),
    ):
        values.insert(0, ((ROOT / path).read_text(), name))
    declarations = "enum {\n" + "\n".join(constant(text, name) for text, name in values) + "\n};\n" + declarations
    for name in ("distributed_player_ping", "distributed_pings_message"):
        declarations += block(source, f"struct {name}\n") + ";\n"
    functions = "\n".join(block(source, signature) for signature in (
        "long distributed_player_ping(", "static void distributed_send_pings(",
        "static boolean distributed_message_stale("))
    dispatcher = block(source, "void network_distributed_handle_message(")
    # Keep all production pre-dispatch checks, including unpacking batch messages.
    preamble, cases = dispatcher.rsplit("\n\tswitch (header.type)", 1)
    ping_case = cases.split("case _distributed_message_pings:", 1)[1].split(
        "case _distributed_message_inventories:", 1)[0]
    ping_case = "case _distributed_message_pings:" + ping_case
    functions += preamble + "\nswitch (header.type) {\n" + ping_case + "\ndefault: assert(0);\n}\n}\n"
    # The real game uses ILP32; preserve its wire layout in the native LP64 probe.
    return tuple(re.sub(r"\blong\b", "int32_t", part) for part in (declarations, functions))


class NetworkPings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        directory = Path(cls.directory.name)
        declarations, functions = production_code()
        probe = directory / "network_pings.c"
        probe.write_text(PREFIX.replace("/* DECLARATIONS */", declarations).replace(
            "/* FUNCTIONS */", functions) + HARNESS)
        cls.executable = directory / "network_pings"
        compiled = subprocess.run([
            "clang", "-std=c11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
            "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
            "-iquote", str(ROOT / "port/linux/include"), str(probe), "-o", str(cls.executable),
        ], capture_output=True, text=True, timeout=30)
        if compiled.returncode:
            raise AssertionError(compiled.stderr)

    def run_case(self, case):
        tested = subprocess.run([str(self.executable), case], capture_output=True, text=True, timeout=10)
        self.assertEqual(tested.returncode, 0, tested.stdout + tested.stderr)

    def test_wire_layout_and_protocol_version(self):
        self.run_case("wire")

    def test_host_client_ping_mapping(self):
        self.run_case("mapping")

    def test_sparse_full_and_clamped_outgoing_pings(self):
        self.run_case("sending")

    def test_receive_validation_roles_staleness_and_invalid_players(self):
        self.run_case("receiving")

    def test_batched_and_truncated_pings(self):
        self.run_case("batching")


if __name__ == "__main__":
    unittest.main()
