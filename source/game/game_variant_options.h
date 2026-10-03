/* Version 11's PC gametype-options wire record. Included after game_variant.
 * Keep its complete layout for interoperability while this fork continues to
 * play its existing Xbox rules. Unsupported active options are refused before
 * a received settings record can start precaching or change the client state.
 */
#ifndef __GAME_VARIANT_OPTIONS_H
#define __GAME_VARIANT_OPTIONS_H

struct game_variant_options
{
	short time_limit;
	short friendly_fire;
	short friendly_fire_penalty;
	short vehicle_respawn_time;
	boolean auto_team_balance;
	byte radar_players;
	byte vehicle_set[2];
	byte vehicle_counts[2][6];
	byte loadout;
	byte primary_weapon;
	byte secondary_weapon;
	byte pad;
};

typedef char verify_game_variant_options_size[sizeof(struct game_variant_options) == 0x1C ? 1 : -1];

/* Identical to upstream v11's Xbox-rule defaults: friendly fire on, category
 * loadout, no time/respawn/penalty/team-balancing overrides, the variant's radar
 * and vehicle set. The primary/secondary fields are inactive with this loadout.
 */
static inline void game_variant_options_default(
	struct game_variant const *variant,
	struct game_variant_options *options)
{
	csmemset(options, 0, sizeof(*options));
	options->primary_weapon = 2; /* assault rifle */
	options->secondary_weapon = 3; /* pistol */
	options->radar_players = variant &&
		!TEST_FLAG(variant->universal_variant.flags, _game_variant_draw_object_in_motion_sensor_bit) ? 2 : 0;
	options->vehicle_set[0] = options->vehicle_set[1] =
		variant ? (byte)variant->universal_variant.vehicle_set : 0;
}

static inline char const *game_variant_options_unsupported(
	struct game_variant const *variant,
	struct game_variant_options const *options)
{
	struct game_variant_options defaults;

	game_variant_options_default(variant, &defaults);
	if (options->time_limit) return "time limit";
	if (options->friendly_fire) return "friendly fire mode";
	if (options->friendly_fire_penalty) return "friendly fire penalty";
	if (options->vehicle_respawn_time) return "vehicle respawn time";
	if (options->auto_team_balance) return "automatic team balancing";
	if (options->radar_players != defaults.radar_players) return "radar players";
	if (options->vehicle_set[0] != defaults.vehicle_set[0] ||
		options->vehicle_set[1] != defaults.vehicle_set[1]) return "per-team vehicle sets";
	if (options->loadout) return "custom loadout";
	if (variant->universal_variant.weapon_set < 0 ||
		variant->universal_variant.weapon_set > 10) return "PC weapon set";
	/* Counts are inactive unless a vehicle set is custom (already rejected).
	 * Likewise primary/secondary weapons are inactive in category loadouts.
	 */
	return NULL;
}

#endif
