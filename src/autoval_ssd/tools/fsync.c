#include <assert.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

typedef long long longlong;

double gettimeofday_sec() {
  struct timeval tv;
  gettimeofday(&tv, NULL);
  return tv.tv_sec + (double)tv.tv_usec * 1e-6;
}

void now(struct timeval* tv) {
  assert(!gettimeofday(tv, NULL));
}

long now_minus_then_usecs(
    struct timeval const* now,
    struct timeval const* then) {
  longlong now_usecs = (now->tv_sec * 1000000) + now->tv_usec;
  longlong then_usecs = (then->tv_sec * 1000000) + then->tv_usec;

  if (now_usecs >= then_usecs)
    return (long)(now_usecs - then_usecs);
  else
    return -1;
}

int longcmp(const void* aa, const void* bb) {
  const long *a = (const long*)aa, *b = (const long*)bb;
  return (*a < *b) ? -1 : (*a > *b);
}

int main(int argc, char** argv) {
  double t1, t2, t3, t4;
  unsigned int i = 0;
  int fd;

  if (argc < 3) {
    printf("Missing arguments. \n");
    return 1;
  }

  char* filepath = argv[1];
  long total_writes = atoi(argv[2]);
  int block_size = atoi(argv[3]);

  printf("Fsync %d bytes x %d times.\n", block_size, total_writes);
  time_t timer;
  struct tm* t_st;
  time(&timer);
  printf("Current Time: %s", ctime(&timer));

  char* str = malloc(block_size * sizeof(str));
  memset(str, 1, (size_t)block_size);

  fd = open64(filepath, O_WRONLY);
  if (fd == -1) {
    printf("error\n");
    return 1;
  }

  struct timeval start, stop;
  long latency;

  t1 = gettimeofday_sec();

  long fsync_stats[total_writes];
  for (i = 0; i < total_writes; i++) {
    now(&start);
    write(fd, str, block_size);
    fsync(fd);
    now(&stop);
    latency = now_minus_then_usecs(&stop, &start);
    fsync_stats[i] = latency;
    /*printf("%ld ", latency);
     */
  }
  close(fd);
  printf("\n");
  t2 = gettimeofday_sec();

  int total_time = t2 - t1;
  printf(
      "block_size: %d, %d fsync/sec\n", block_size, total_writes / total_time);
  qsort(fsync_stats, total_writes, sizeof(long), longcmp);
  long sum = 0;
  for (i = 0; i < total_writes; i++) {
    sum += fsync_stats[i];
  }
  long avg_lat = (long)(sum / total_writes);
  long p95_lat = fsync_stats[(int)(total_writes * .95)];
  long p99_lat = fsync_stats[(int)(total_writes * .99)];
  long max_lat = fsync_stats[total_writes - 1];
  printf(
      "Latency\nAvg: %ld, P95: %ld, P99: %ld, Max: %ld\n",
      avg_lat,
      p95_lat,
      p99_lat,
      max_lat);

  free(str);

  return 0;
}
