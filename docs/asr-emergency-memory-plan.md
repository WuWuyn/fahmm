# ASR emergency memory protection

1. Before the spawned offline ASR worker begins inference, start a parent-side
   watchdog and obtain a system-wide available-memory sample. Do not impose
   the benchmark's 5 GiB admission requirement on ordinary recordings.
2. While that worker is active, sample `psutil.virtual_memory().available`
   every 0.2 seconds. Stop the owned worker immediately at or below 1536 MiB,
   or if memory cannot be measured; report distinct stable error codes.
3. Keep the input audio and existing transcript runs unchanged on either error;
   release the meeting activity and model lease as for other worker failures.
4. Exercise the thresholds and cleanup with mocked readings and lightweight
   workers, including worker startup, an emergency during work, and normal
   completion. Sampling cannot prevent exhaustion caused by an allocation
   faster than the sampling interval or by other applications.
