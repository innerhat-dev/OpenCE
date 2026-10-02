"""Compare owned Xbox-cache samples through the production event/mixer fixture.

This produces fixture WAVs, never recordings of a live session. Inputs and tag
data remain untouched. Run as python3 -m tools.verify_performance_sound_samples.
"""
import argparse
import array
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import wave
import zlib

from tools.import_performance_audio import decode_xbox_adpcm
from tools.test_performance_sound import ROOT, GAME, channel_fixture


class Cache:
    def __init__(self, path):
        self.path = path.resolve()
        raw = path.read_bytes()
        version, size = struct.unpack_from("<II", raw, 4)
        if version != 5 or not 2048 <= size <= 128 * 1024 * 1024:
            raise ValueError("Expected a bounded Xbox v5 cache")
        self.file = raw if len(raw) == size else raw[:2048] + zlib.decompress(raw[2048:])
        if len(self.file) != size:
            raise ValueError("Cache decompressed length mismatch")
        offset, length = struct.unpack_from("<II", self.file, 16)
        self.data = self.file[offset:offset + length]
        self.base = 0x803A6000
        table = self.unpack("<I", self.base)[0]
        count = self.unpack("<I", self.base + 12)[0]
        self.tags = {}
        for i in range(count):
            group, _, _, index, name, address, _, _ = self.unpack("<8I", table + 32 * i)
            self.tags[index] = {"index": index, "group": group.to_bytes(4, "big").decode(),
                                "path": self.string(name), "address": address}
        self.by_path = {t["path"]: t for t in self.tags.values()}
        self.sha256 = hashlib.sha256(raw).hexdigest()

    def unpack(self, format, address):
        offset = address - self.base
        if not 0 <= offset <= len(self.data) - struct.calcsize(format):
            raise ValueError("Tag address outside cache")
        return struct.unpack_from(format, self.data, offset)

    def string(self, address):
        offset = address - self.base
        if not 0 <= offset < len(self.data):
            raise ValueError("Tag string outside cache")
        return self.data[offset:self.data.index(b"\0", offset)].decode("ascii")

    def movement_tag(self, event):
        material = self.by_path[r"globals\cyborg"]
        count, address, _ = self.unpack("<3I", material["address"])
        if event >= count:
            raise ValueError("Missing movement event")
        count, address, _ = self.unpack("<3I", address + event * 0x1C)
        for material_index in range(count):
            tag = self.tags.get(self.unpack("<I", address + material_index * 0x30 + 0x1C)[0])
            if tag:
                return tag["path"], material_index
        raise ValueError("Missing movement event sound")

    def sample(self, path):
        tag = self.by_path[path]
        if tag["group"] != "snd!":
            raise ValueError("Expected sound tag")
        address = tag["address"]
        sound_class, rate = self.unpack("<hh", address + 4)
        encoding, compression = self.unpack("<hh", address + 108)
        if rate not in (0, 1) or encoding not in (0, 1) or compression != 1:
            raise ValueError("Expected mono/stereo 22/44kHz Xbox ADPCM")
        pitch_count, pitch, _ = self.unpack("<3I", address + 152)
        if not 1 <= pitch_count <= 8:
            raise ValueError("Invalid sound pitch count")
        count, permutation, _ = self.unpack("<3I", pitch + 60)
        if not 1 <= count <= 256 or self.unpack("<hh", permutation + 40) != (1, -1):
            raise ValueError("Unsupported first permutation or linked audio")
        size, _, offset, _, _ = self.unpack("<5I", permutation + 64)
        if not 0 < size <= 1024 * 1024 or offset < 2048 or offset + size > len(self.file):
            raise ValueError("Sample data outside cache")
        compressed = self.file[offset:offset + size]
        pcm = decode_xbox_adpcm(compressed, encoding + 1)
        return pcm, {"tag": path, "tag_index": tag["index"], "class_index": sound_class,
                     "permutation": self.string(permutation), "pitch_range": self.string(pitch),
                     "sample_offset": offset, "compressed_bytes": size,
                     "compressed_sha256": hashlib.sha256(compressed).hexdigest(),
                     "pcm_sha256": hashlib.sha256(pcm).hexdigest(),
                     "rate": (22050, 44100)[rate], "channels": encoding + 1,
                     "source_frames": len(pcm) // (2 * (encoding + 1)),
                     "permutation_gain": self.unpack("<f", permutation + 36)[0],
                     "definition_gain": self.unpack("<f", address + 40)[0],
                     "zero_gain_modifier": self.unpack("<f", address + 64)[0],
                     "one_gain_modifier": self.unpack("<f", address + 88)[0]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock-map", type=Path, required=True)
    parser.add_argument("--converted-map", type=Path, action="append", default=[])
    parser.add_argument("--weapon-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    ready = json.loads(args.weapon_audit.read_text())["findings"]["ready_sound_tags"]
    controls = {"fire": r"sound\sfx\weapons\pistol\fire",
                "reload": r"sound\sfx\weapons\weapon_anims\pistol_reload",
                "impact": r"sound\sfx\impulse\impacts\metalhit",
                "announcer": r"sound\dialog\multiplayer1\slayer",
                "grenade_throw_class5": r"sound\sfx\weapons\frag grenade\throwgren"}
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = {"scope": "First-permutation fixture PCM from actual stock/converted cache files, through production sound-manager, DirectSound properties and full SDL mixer. This is not live session recording or subjective listening.",
                "source_functions": ["update_channel_for_impulse_sound", "dsound_channel_set_properties",
                                     "dsound_volume_from_gain", "gain_from_millibels", "mix_voice", "mix"],
                "fixture_source": "tools/test_performance_sound.py:channel_fixture", "cases": []}
    with tempfile.TemporaryDirectory(prefix="halo-cache-audio-") as temporary:
        folder = Path(temporary)
        source = folder / "fixture.c"
        source.write_text(channel_fixture())
        executable = folder / "fixture"
        subprocess.run(["clang", "-std=c11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                        "-Wno-unused-function", "-Wno-unused-variable", "-fsanitize=address,undefined",
                        "-I", str(GAME), "-iquote", str(ROOT / "port/linux/include"), str(source),
                        str(GAME / "performance_sound.c"), "-o", str(executable)], check=True)
        for kind, path in [("stock", args.stock_map)] + [("converted", p) for p in args.converted_map]:
            cache = Cache(path)
            cases = []
            for name, event in (("footstep", 1), ("jump", 4), ("landing", 5)):
                tag, material_index = cache.movement_tag(event)
                cases.append((name, tag, 1, 0, {"event": event, "material_index": material_index}))
            cases += [("ready_" + str(i + 1), tag, 2, 1, {}) for i, tag in enumerate(ready)]
            cases += [(name, tag, 0, 1, {}) for name, tag in controls.items()]
            for name, tag, role, scale, event in cases:
                pcm, metadata = cache.sample(tag)
                output = args.output / (kind + "_" + path.stem) / name
                output.mkdir(parents=True, exist_ok=True)
                pcm_file = folder / "input.pcm"
                pcm_file.write_bytes(pcm)
                result = subprocess.run([str(executable), str(pcm_file), str(output.resolve()), str(role),
                                         str(metadata["channels"]), str(metadata["rate"]),
                                         str(metadata["permutation_gain"]), str(metadata["definition_gain"]),
                                         str(metadata["zero_gain_modifier"]), str(metadata["one_gain_modifier"]),
                                         str(metadata["class_index"]), str(scale)], capture_output=True, text=True)
                if result.returncode:
                    raise RuntimeError(f"{path.name}/{name}: {result.stderr}")
                outputs = {}
                for mode in ("normal", "silent", "shared-control", "restored"):
                    raw_path = output / (mode + ".f32")
                    raw = raw_path.read_bytes()
                    samples = array.array("f")
                    samples.frombytes(raw)
                    peak = max(map(abs, samples))
                    samples16 = array.array("h", (max(-32768, min(32767, round(v * 32767))) for v in samples))
                    with wave.open(str(output / (mode + ".wav")), "wb") as wav:
                        wav.setnchannels(2)
                        wav.setsampwidth(2)
                        wav.setframerate(48000)
                        wav.writeframes(samples16.tobytes())
                    outputs[mode] = {"peak": peak, "frames": len(samples) // 2,
                                     "float_pcm_sha256": hashlib.sha256(raw).hexdigest()}
                    raw_path.unlink()
                assert outputs["normal"]["peak"] > 0, (path, name, "source silent")
                assert outputs["normal"] == outputs["shared-control"] == outputs["restored"], (path, name)
                assert outputs["silent"]["peak"] == 0 if role else outputs["silent"] == outputs["normal"], (path, name)
                manifest["cases"].append({"map_kind": kind, "map": str(cache.path), "map_sha256": cache.sha256,
                                          "case": name, "role": role, "scale": scale, **event, **metadata,
                                          "output": str(output.resolve()), "outputs": outputs})
    manifest["case_count"] = len(manifest["cases"])
    manifest["all_selected_roles_silent"] = True
    manifest["all_shared_control_uses_and_restoration_bit_identical"] = True
    manifest["all_ordinary_control_uses_unchanged"] = True
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Verified {manifest['case_count']} actual cache sample cases: selected roles silent, controls and restoration byte-identical.")


if __name__ == "__main__":
    main()
