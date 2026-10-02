"""Make a user-local timer audio pack from already-extracted, user-owned tags.

Only the reviewed single-pitch/single-permutation HEK sound layout is accepted.
Xbox ADPCM decoding follows port/linux/src/dsound_sdl.c. No downloads, map edits,
external executables or runtime asset conversion are involved. Existing files
are preserved; an identical pack can be imported again safely.
"""
from __future__ import annotations

import argparse
from array import array
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import wave

CUES = (
    ["timerbeep", "1_minute"]
    + [f"{i}_minutes" for i in range(2, 31)]
    + ["30_seconds_left", "20_seconds"]
    + [str(i) for i in range(10, 0, -1)]
    + ["rocket", "camo", "overshield"]
)
INDEX_TABLE = [-1, -1, -1, -1, 2, 4, 6, 8] * 2
STEP_TABLE = [
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37,
    41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130, 143, 157, 173,
    190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658,
    724, 796, 876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066,
    2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358, 5894,
    6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899, 15289,
    16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767,
]


def decode_xbox_adpcm(data: bytes, channels: int) -> bytes:
    """Decode the same 64-sample Xbox ADPCM blocks as the game mixer."""
    block_size = 36 * channels
    if channels not in (1, 2) or not data or len(data) % block_size:
        raise ValueError("Invalid Xbox ADPCM block size")
    output = array("h", [0]) * (len(data) // block_size * 64 * channels)
    for block_start in range(0, len(data), block_size):
        frame_start = block_start // block_size * 64 * channels
        for channel in range(channels):
            predictor, index, reserved = struct.unpack_from("<hBB", data, block_start + channel * 4)
            if index > 88 or reserved:
                raise ValueError("Invalid Xbox ADPCM predictor header")
            for group in range(8):
                offset = block_start + 4 * channels + (group * channels + channel) * 4
                for byte_index, value in enumerate(data[offset:offset + 4]):
                    for half, nibble in enumerate((value & 15, value >> 4)):
                        step = STEP_TABLE[index]
                        difference = step >> 3
                        if nibble & 1:
                            difference += step >> 2
                        if nibble & 2:
                            difference += step >> 1
                        if nibble & 4:
                            difference += step
                        predictor = max(-32768, min(32767, predictor + (-difference if nibble & 8 else difference)))
                        index = max(0, min(88, index + INDEX_TABLE[nibble]))
                        sample = group * 8 + byte_index * 2 + half
                        output[frame_start + sample * channels + channel] = predictor
    if sys.byteorder != "little":
        output.byteswap()
    return output.tobytes()


def decode_sound_tag(data: bytes) -> tuple[int, int, bytes]:
    """Reject unfamiliar layouts instead of guessing dependency/data offsets."""
    if not 424 <= len(data) <= 1024 * 1024:
        raise ValueError("Sound tag outside supported size bounds")
    if data[36:40] != b"snd!" or data[60:64] != b"blam" or struct.unpack_from(">H", data, 56)[0] != 4:
        raise ValueError("Expected a version 4 HEK sound tag")
    if struct.unpack_from(">I", data, 44)[0] != 64:
        raise ValueError("Unexpected HEK tag header size")
    root, pitch, permutation, samples_start = 64, 228, 300, 424
    rate_enum = struct.unpack_from(">H", data, root + 6)[0]
    channel_enum, compression = struct.unpack_from(">HH", data, root + 108)
    if rate_enum not in (0, 1) or channel_enum not in (0, 1) or compression != 1:
        raise ValueError("Expected 22/44 kHz mono/stereo Xbox ADPCM")
    if struct.unpack_from(">I", data, root + 120)[0] != 0:
        raise ValueError("Promotion sound dependencies are unsupported")
    if struct.unpack_from(">I", data, root + 152)[0] != 1 or struct.unpack_from(">I", data, pitch + 60)[0] != 1:
        raise ValueError("Expected one pitch range and one permutation")
    if struct.unpack_from(">H", data, pitch + 44)[0] != 1:
        raise ValueError("Expected one actual permutation")
    if struct.unpack_from(">HH", data, permutation + 40) != (1, 65535):
        raise ValueError("Unsupported permutation compression or chained sound")
    sample_size, mouth_size, subtitle_size = [
        struct.unpack_from(">I", data, permutation + offset)[0] for offset in (64, 84, 104)
    ]
    if samples_start + sample_size + mouth_size + subtitle_size != len(data):
        raise ValueError("Sound data lengths do not match file")
    if mouth_size > 8192 or subtitle_size > 512:
        raise ValueError("Unexpected mouth/subtitle data size")
    rate, channels = (22050, 44100)[rate_enum], channel_enum + 1
    pcm = decode_xbox_adpcm(data[samples_start:samples_start + sample_size], channels)
    if len(pcm) > min(1024 * 1024, rate * channels * 2 * 4):
        raise ValueError("Timer cue exceeds the four-second playback bound")
    return rate, channels, pcm


def canonical_wav(rate: int, channels: int, pcm: bytes) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(channels)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(pcm)
    return output.getvalue()


def prepare_pack(tags: Path) -> dict[str, bytes]:
    prepared = {}
    manifest = {"format": "halo-performance-audio-v1", "source": "user-owned extracted HEK tags", "cues": []}
    for cue in CUES:
        relative = Path("sound/timer") / ("beeps" if cue == "timerbeep" else "cortana") / f"{cue}.sound"
        source = tags / relative
        if source.stat().st_size > 1024 * 1024:
            raise ValueError(f"Source tag too large: {relative}")
        data = source.read_bytes()
        rate, channels, pcm = decode_sound_tag(data)
        wav = canonical_wav(rate, channels, pcm)
        prepared[f"{cue}.wav"] = wav
        manifest["cues"].append({
            "cue": cue, "source_tag": relative.as_posix(), "source_sha256": hashlib.sha256(data).hexdigest(),
            "wav_sha256": hashlib.sha256(wav).hexdigest(), "rate": rate, "channels": channels,
            "frames": len(pcm) // (2 * channels),
        })
    prepared["import-manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    return prepared


def write_pack(prepared: dict[str, bytes], destination: Path) -> tuple[int, int]:
    # Check every collision before creating any asset. Existing user files are
    # never silently replaced, even if they are malformed or from another pack.
    for name, data in prepared.items():
        path = destination / name
        if path.exists() and (path.is_symlink() or path.stat().st_size != len(data) or path.read_bytes() != data):
            raise ValueError(f"Preserving different existing file: {path}")
    destination.mkdir(parents=True, exist_ok=True)
    created = existing = 0
    for name, data in prepared.items():
        path = destination / name
        if path.exists():
            existing += 1
            continue
        try:
            with path.open("xb") as output:
                output.write(data)
        except FileExistsError:
            if path.is_symlink() or path.read_bytes() != data:
                raise ValueError(f"Preserving file created during import: {path}")
            existing += 1
        else:
            created += 1
    return created, existing


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tags", type=Path, required=True, help="Existing extracted tag directory")
    parser.add_argument("--destination", type=Path, required=True, help="Game Data/sounds/performance directory")
    args = parser.parse_args()
    try:
        prepared = prepare_pack(args.tags)
        created, existing = write_pack(prepared, args.destination)
    except (OSError, ValueError, struct.error) as error:
        parser.exit(1, f"Import failed: {error}\n")
    print(f"Timer audio: {len(CUES)} validated cues; {created} files created, {existing} identical files preserved.")


if __name__ == "__main__":
    main()
