/*
POSIX_FILES.C

glibc file system helpers for the platform layer (see posix.h). Built with
the host ABI and _FILE_OFFSET_BITS=64.
*/

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <strings.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <sys/types.h>
#include <unistd.h>

#include "posix.h"

static void split64(unsigned long long value, posix_ulong *low, posix_ulong *high)
{
	*low = (posix_ulong)(value & 0xffffffffULL);
	*high = (posix_ulong)(value >> 32);
}

static void fill_information(const struct stat *st, struct posix_file_information *information)
{
	memset(information, 0, sizeof(*information));
	if (S_ISDIR(st->st_mode))
		information->flags |= _posix_file_is_directory;
	if (!(st->st_mode & S_IWUSR))
		information->flags |= _posix_file_is_read_only;
	split64((unsigned long long)st->st_size, &information->size_low, &information->size_high);
	information->modification_seconds = (posix_ulong)st->st_mtim.tv_sec;
	information->modification_nanoseconds = (posix_ulong)st->st_mtim.tv_nsec;
	information->access_seconds = (posix_ulong)st->st_atim.tv_sec;
	information->access_nanoseconds = (posix_ulong)st->st_atim.tv_nsec;
	/* Linux has no portable creation time; the change time is the closest */
	information->creation_seconds = (posix_ulong)st->st_ctim.tv_sec;
	information->creation_nanoseconds = (posix_ulong)st->st_ctim.tv_nsec;
}

int posix_stat(const char *path, struct posix_file_information *information)
{
	struct stat st;

	if (stat(path, &st) != 0)
		return -1;
	fill_information(&st, information);
	return 0;
}

int posix_fstat(int descriptor, struct posix_file_information *information)
{
	struct stat st;

	if (fstat(descriptor, &st) != 0)
		return -1;
	fill_information(&st, information);
	return 0;
}

int posix_set_file_times(const char *path,
	posix_ulong access_seconds, posix_ulong access_nanoseconds,
	posix_ulong modification_seconds, posix_ulong modification_nanoseconds)
{
	struct timespec times[2];

	times[0].tv_sec = (time_t)access_seconds;
	times[0].tv_nsec = access_seconds ? (long)access_nanoseconds : UTIME_OMIT;
	times[1].tv_sec = (time_t)modification_seconds;
	times[1].tv_nsec = modification_seconds ? (long)modification_nanoseconds : UTIME_OMIT;
	return utimensat(AT_FDCWD, path, times, 0);
}

int posix_seek(int descriptor, posix_long offset_low, posix_long offset_high, int whence,
	posix_ulong *position_low, posix_ulong *position_high)
{
	off_t offset = (off_t)(((unsigned long long)(posix_ulong)offset_high << 32) | (posix_ulong)offset_low);
	off_t result = lseek(descriptor, offset, whence);

	if (result == (off_t)-1)
		return -1;
	split64((unsigned long long)result, position_low, position_high);
	return 0;
}

int posix_truncate(int descriptor, posix_ulong size_low, posix_ulong size_high)
{
	return ftruncate(descriptor, (off_t)(((unsigned long long)size_high << 32) | size_low));
}

int posix_disk_space(const char *path,
	posix_ulong *free_low, posix_ulong *free_high,
	posix_ulong *total_low, posix_ulong *total_high)
{
	struct statvfs st;

	if (statvfs(path, &st) != 0)
		return -1;
	split64((unsigned long long)st.f_bavail * st.f_frsize, free_low, free_high);
	split64((unsigned long long)st.f_blocks * st.f_frsize, total_low, total_high);
	return 0;
}

int posix_set_read_only(const char *path, int read_only)
{
	struct stat st;
	mode_t mode;

	if (stat(path, &st) != 0)
		return -1;
	mode = st.st_mode & 07777;
	mode = read_only ? (mode & ~(mode_t)0222) : (mode | S_IWUSR);
	return chmod(path, mode);
}

int posix_make_directory(const char *path)
{
#ifdef __ANDROID__
	/* readable by the shell user (adb), for managing saves in the app's
	external storage (port/android/host/host_main.c) */
	if (mkdir(path, 0775) != 0)
		return -1;
	chmod(path, 02775);
	return 0;
#else
	return mkdir(path, 0755);
#endif
}

#if !defined(__ANDROID__) && !defined(HALO_MACOS)
/* ---------- desktop save migration (host ABI only) */

/* Open each component itself; a linked folder cannot redirect a migration.
The user-selected HOME/XDG path may be relative, as the old defaults allowed. */
static int save_open_directory(const char *path, int create)
{
	const char *cursor = path;
	int directory = open(*path == '/' ? "/" : ".", O_RDONLY | O_DIRECTORY | O_CLOEXEC);

	if (directory < 0)
		return -1;
	while (*cursor)
	{
		char component[256];
		size_t length;
		int next;

		while (*cursor == '/') cursor++;
		length = strcspn(cursor, "/");
		if (!length) break;
		if (length >= sizeof(component))
		{
			close(directory);
			errno = ENAMETOOLONG;
			return -1;
		}
		memcpy(component, cursor, length);
		component[length] = 0;
		cursor += length;
		next = openat(directory, component, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
		if (next < 0 && errno == ENOENT && create)
		{
			if (mkdirat(directory, component, 0700) != 0 && errno != EEXIST)
			{
				int error = errno;
				close(directory);
				errno = error;
				return -1;
			}
			next = openat(directory, component, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
		}
		if (next < 0)
		{
			int error = errno;
			close(directory);
			errno = error;
			return -1;
		}
		close(directory);
		directory = next;
	}
	return directory;
}

static int save_source_unchanged(const struct stat *before, const struct stat *after)
{
	if (before->st_dev != after->st_dev || before->st_ino != after->st_ino ||
		before->st_size != after->st_size || before->st_mtime != after->st_mtime || before->st_ctime != after->st_ctime)
		return 0;
#ifdef __APPLE__
	return before->st_mtimespec.tv_nsec == after->st_mtimespec.tv_nsec &&
		before->st_ctimespec.tv_nsec == after->st_ctimespec.tv_nsec;
#else
	return before->st_mtim.tv_nsec == after->st_mtim.tv_nsec &&
		before->st_ctim.tv_nsec == after->st_ctim.tv_nsec;
#endif
}

static int save_destination_regular(int directory, const char *name)
{
	struct stat information;

	if (fstatat(directory, name, &information, AT_SYMLINK_NOFOLLOW) != 0)
		return -1;
	if (!S_ISREG(information.st_mode))
	{
		errno = EINVAL;
		return -1;
	}
	return 0;
}

/* Xbox path lookup ignores case. Prefer an existing exact spelling, then
its existing case-insensitive match, so a copied older profile cannot win by
creating a second spelling beside a newer profile. */
static int save_destination_name(int directory, const char *name, char *result, size_t size)
{
	struct stat information;
	DIR *stream;
	struct dirent *entry;
	int descriptor, error;

	if (strlen(name) + 1 > size) { errno = ENAMETOOLONG; return -1; }
	strcpy(result, name);
	if (fstatat(directory, name, &information, AT_SYMLINK_NOFOLLOW) == 0) return 0;
	if (errno != ENOENT) return -1;
	/* A fresh directory description starts at the beginning on every lookup. */
	descriptor = openat(directory, ".", O_RDONLY | O_DIRECTORY | O_CLOEXEC);
	if (descriptor < 0) return -1;
	stream = fdopendir(descriptor);
	if (!stream) { error = errno; close(descriptor); errno = error; return -1; }
	for (;;)
	{
		errno = 0;
		entry = readdir(stream);
		if (!entry) break;
		if (!strcasecmp(entry->d_name, name))
		{
			if (strlen(entry->d_name) + 1 > size) { errno = ENAMETOOLONG; break; }
			strcpy(result, entry->d_name);
			break;
		}
	}
	const int saved_error = errno;
	closedir(stream);
	errno = saved_error;
	return saved_error ? -1 : 0;
}

static int save_copy_file(int source_directory, int destination_directory, const char *name, const char *destination_name)
{
	static unsigned counter;
	char temporary[96], buffer[65536];
	struct stat before, after;
	int source = -1, destination = -1, result = -1, temporary_created = 0, attempt, error;
	ssize_t amount;
	off_t copied = 0;

	/* Even a source changed into a FIFO cannot block this startup copy. */
	source = openat(source_directory, name, O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC);
	if (source < 0) goto done;
	if (fstat(source, &before) != 0) goto done;
	if (!S_ISREG(before.st_mode)) { errno = EINVAL; goto done; }
	if (save_destination_regular(destination_directory, destination_name) == 0) { result = 0; goto done; }
	if (errno != ENOENT) goto done;
	for (attempt = 0; attempt < 32; attempt++)
	{
		snprintf(temporary, sizeof(temporary), ".halo-og-migration-%ld-%u.partial", (long)getpid(), ++counter);
		destination = openat(destination_directory, temporary,
			O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
		if (destination >= 0) break;
		if (errno != EEXIST) goto done;
	}
	if (destination < 0) goto done;
	temporary_created = 1;
	for (;;)
	{
		amount = read(source, buffer, sizeof(buffer));
		if (amount < 0 && errno == EINTR) continue;
		if (amount < 0) goto done;
		if (!amount) break;
		copied += amount;
		for (ssize_t written = 0; written < amount;)
		{
			ssize_t part = write(destination, buffer + written, (size_t)(amount - written));
			if (part < 0 && errno == EINTR) continue;
			if (part <= 0) { if (!part) errno = EIO; goto done; }
			written += part;
		}
	}
	if (fstat(source, &after) != 0) goto done;
	if (copied != before.st_size || !save_source_unchanged(&before, &after)) { errno = EAGAIN; goto done; }
	if (fsync(destination) != 0) goto done;
	if (close(destination) != 0) { destination = -1; goto done; }
	destination = -1;
	/* linkat is atomic and exclusive: even a racing game/publisher's file wins
	unchanged. Unsupported file systems cause visible legacy fallback. */
	if (linkat(destination_directory, temporary, destination_directory, destination_name, 0) != 0)
	{
		if (errno != EEXIST || save_destination_regular(destination_directory, destination_name) != 0) goto done;
	}
	result = 0;
done:
	error = errno;
	if (destination >= 0) close(destination);
	if (source >= 0) close(source);
	if (temporary_created) unlinkat(destination_directory, temporary, 0);
	errno = error;
	return result;
}

static int save_copy_tree(int source, int destination, unsigned depth)
{
	DIR *stream;
	struct dirent *entry;
	int duplicate, result = -1, error;

	if (depth >= 64) { errno = ELOOP; return -1; }
	duplicate = dup(source);
	if (duplicate < 0) return -1;
	stream = fdopendir(duplicate);
	if (!stream) { error = errno; close(duplicate); errno = error; return -1; }
	for (;;)
	{
		struct stat information;
		char destination_name[256];

		errno = 0;
		entry = readdir(stream);
		if (!entry) { if (!errno) result = 0; break; }
		if (!strcmp(entry->d_name, ".") || !strcmp(entry->d_name, "..")) continue;
		if (fstatat(source, entry->d_name, &information, AT_SYMLINK_NOFOLLOW) != 0) break;
		if (save_destination_name(destination, entry->d_name, destination_name, sizeof(destination_name)) != 0) break;
		if (S_ISDIR(information.st_mode))
		{
			int child_source = openat(source, entry->d_name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
			int child_destination = -1;
			int copied;

			if (child_source < 0) break;
			if (mkdirat(destination, destination_name, 0700) == 0 || errno == EEXIST)
				child_destination = openat(destination, destination_name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
			if (child_destination < 0) { error = errno; close(child_source); errno = error; break; }
			copied = save_copy_tree(child_source, child_destination, depth + 1);
			error = errno;
			close(child_source);
			close(child_destination);
			errno = error;
			if (copied != 0) break;
		}
		else if (!S_ISREG(information.st_mode)) { errno = EINVAL; break; }
		else if (save_copy_file(source, destination, entry->d_name, destination_name) != 0) break;
	}
	error = errno;
	closedir(stream);
	errno = error;
	return result;
}

int posix_migrate_save_directory(const char *legacy, const char *destination)
{
	int source, absent;
	int target, result, error;
	size_t legacy_length = strlen(legacy), destination_length = strlen(destination);

	/* The caller uses sibling defaults. Also refuse accidental direct calls
	with overlapping trees before creating anything inside a legacy root. */
	if (!strcmp(legacy, destination) ||
		(legacy_length < destination_length && !strncmp(legacy, destination, legacy_length) && destination[legacy_length] == '/') ||
		(destination_length < legacy_length && !strncmp(legacy, destination, destination_length) && legacy[destination_length] == '/'))
	{
		errno = EINVAL;
		return -1;
	}
	source = save_open_directory(legacy, 0);
	absent = source < 0 && errno == ENOENT;

	if (source < 0 && !absent) return -1;
	target = save_open_directory(destination, 1);
	if (target < 0) { error = errno; if (source >= 0) close(source); errno = error; return -1; }
	result = absent ? 1 : save_copy_tree(source, target, 0);
	error = errno;
	if (source >= 0) close(source);
	close(target);
	errno = error;
	return result;
}
#endif

#ifdef __LP64__
/* The Android port calls this file from 32-bit guest code, which cannot
hold a 64-bit DIR pointer: directory streams are small handles there. */
#include <pthread.h>

#define DIRECTORY_HANDLE_COUNT 64

static DIR *directory_handles[DIRECTORY_HANDLE_COUNT];
static pthread_mutex_t directory_handle_lock = PTHREAD_MUTEX_INITIALIZER;

static void *directory_handle_new(DIR *directory)
{
	unsigned long index;

	if (!directory)
		return NULL;
	pthread_mutex_lock(&directory_handle_lock);
	for (index = 0; index < DIRECTORY_HANDLE_COUNT; index++)
	{
		if (!directory_handles[index])
		{
			directory_handles[index] = directory;
			pthread_mutex_unlock(&directory_handle_lock);
			return (void *)(index + 1);
		}
	}
	pthread_mutex_unlock(&directory_handle_lock);
	closedir(directory);
	return NULL;
}

static DIR *directory_from_handle(void *handle, int release)
{
	unsigned long index = (unsigned long)handle - 1;
	DIR *directory = NULL;

	if (index >= DIRECTORY_HANDLE_COUNT)
		return NULL;
	pthread_mutex_lock(&directory_handle_lock);
	directory = directory_handles[index];
	if (release)
		directory_handles[index] = NULL;
	pthread_mutex_unlock(&directory_handle_lock);
	return directory;
}
#else
#define directory_handle_new(directory) ((void *)(directory))
#define directory_from_handle(handle, release) ((DIR *)(handle))
#endif

void *posix_directory_open(const char *path)
{
	return directory_handle_new(opendir(path));
}

int posix_directory_next(void *directory, char *name, posix_ulong name_size)
{
	DIR *stream = directory_from_handle(directory, 0);
	struct dirent *entry;

	if (!stream)
		return 0;
	while ((entry = readdir(stream)) != NULL)
	{
		if (!strcmp(entry->d_name, ".") || !strcmp(entry->d_name, ".."))
			continue;
		if (strlen(entry->d_name) + 1 > name_size)
			continue;
		strcpy(name, entry->d_name);
		return 1;
	}
	return 0;
}

void posix_directory_close(void *directory)
{
	DIR *stream = directory_from_handle(directory, 1);

	if (stream)
		closedir(stream);
}

int posix_find_entry_case_insensitive(const char *directory, const char *name,
	char *result, posix_ulong result_size)
{
	DIR *handle = opendir(*directory ? directory : ".");
	struct dirent *entry;
	int found = 0;

	if (!handle)
		return 0;
	while ((entry = readdir(handle)) != NULL)
	{
		if (!strcasecmp(entry->d_name, name) && strlen(entry->d_name) + 1 <= result_size)
		{
			strcpy(result, entry->d_name);
			found = 1;
			break;
		}
	}
	closedir(handle);
	return found;
}
