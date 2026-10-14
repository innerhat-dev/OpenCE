"""Exercise the real browser ranking, including a truncated caller buffer."""
import subprocess
from pathlib import Path
from harness import function

ROOT = Path(__file__).resolve().parents[1]


def test_joinable_busy_games_survive_truncation(tmp_path):
    source = (ROOT / 'port/linux/src/p2p_lobby.c').read_text()
    code = '''
#include <assert.h>
#include <pthread.h>
#include <stdlib.h>
#include <string.h>
#include "p2p.h"
#define MAXIMUM_GAMES 12
static pthread_mutex_t p2p_lock = PTHREAD_MUTEX_INITIALIZER;
static struct {struct {int used; struct p2p_listing listing;} games[MAXIMUM_GAMES];} lobby;
static int identifier_failed(const unsigned char *id) {return id[0] == 7;}
'''
    code += function(source, 'listing_order') + '\n' + function(source, 'p2p_lobby_games')
    code += '''
int main(void) {
    struct p2p_listing result[2];
    assert(p2p_lobby_games(result, 2) == 0);
    for (int i=0;i<12;i++) {
        lobby.games[i].used=1;
        struct p2p_listing *g=&lobby.games[i].listing;
        g->identifier[0]=i;g->open=1;g->maximum_player_count=128;g->player_count=i;
    }
    lobby.games[0].listing.player_count=128; // full despite open flag
    lobby.games[1].listing.player_count=100;lobby.games[1].listing.open=0;
    lobby.games[7].listing.player_count=90; // previously unreachable
    assert(p2p_lobby_games(result,2)==2);
    assert(result[0].identifier[0]==11 && result[1].identifier[0]==10);
    assert(p2p_lobby_games(result,0)==0);
    assert(p2p_lobby_games(result,-1)==0);
    assert(result[0].identifier[0]==11); // no write for zero capacity
    return 0;
}
'''
    c = tmp_path / 'ranking.c'; c.write_text(code)
    exe = tmp_path / 'ranking'
    subprocess.run(['clang', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                    '-I', str(ROOT / 'port/linux/src'), str(c), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
