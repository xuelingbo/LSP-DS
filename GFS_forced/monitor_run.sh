#!/usr/bin/env bash
# Wrap any command and record its resource usage (RSS/VSZ/CPU% over time,
# wall clock, peak memory) so we can answer "what machine do we need for
# this case" with actual numbers instead of guessing.
#
# Usage:
#   ./monitor_run.sh <log_prefix> -- <command> [args...]
#
# Produces:
#   <log_prefix>.csv          time series: timestamp,elapsed_s,rss_kb,vsz_kb,cpu_pct
#   <log_prefix>_summary.txt  peak RSS/VSZ, wall time, avg CPU%, host spec

set -uo pipefail

if [ $# -lt 3 ] || [ "$2" != "--" ]; then
    echo "Usage: $0 <log_prefix> -- <command> [args...]" >&2
    exit 1
fi

LOG_PREFIX="$1"
shift 2

CSV="${LOG_PREFIX}.csv"
SUMMARY="${LOG_PREFIX}_summary.txt"
INTERVAL=2

echo "timestamp,elapsed_s,rss_kb,vsz_kb,cpu_pct,tracked_procs" > "$CSV"

"$@" &
PID=$!

# Launchers like mpirun/srun fork worker processes (e.g. the N hrldas.exe
# ranks) as children/grandchildren of $PID. $PID itself barely uses any
# CPU/RAM, so we must walk the whole process tree and sum every descendant,
# not just the top PID, or the numbers only reflect the launcher.
descendant_pids() {
    local root="$1"
    ps -eo pid=,ppid= | awk -v root="$root" '
        { ppid[$1]=$2 }
        END {
            queue[1]=root; qn=1; qi=1; seen[root]=1
            print root
            while (qi<=qn) {
                cur=queue[qi]; qi++
                for (p in ppid) {
                    if (ppid[p]==cur && !(p in seen)) {
                        seen[p]=1; qn++; queue[qn]=p; print p
                    }
                }
            }
        }'
}

START=$(date +%s)
PEAK_RSS=0
PEAK_VSZ=0
CPU_SUM=0
SAMPLES=0

while kill -0 "$PID" 2>/dev/null; do
    PIDS=$(descendant_pids "$PID" | paste -sd, -)
    STATS=$(ps -o rss=,vsz=,pcpu= -p "$PIDS" 2>/dev/null)
    if [ -n "$STATS" ]; then
        RSS=$(echo "$STATS" | awk '{s+=$1} END{print s+0}')
        VSZ=$(echo "$STATS" | awk '{s+=$2} END{print s+0}')
        CPU=$(echo "$STATS" | awk '{s+=$3} END{print s+0}')
        NPROC=$(echo "$STATS" | wc -l)
        NOW=$(date +%s)
        ELAPSED=$((NOW - START))
        echo "$(date -Iseconds),${ELAPSED},${RSS},${VSZ},${CPU},${NPROC}" >> "$CSV"
        [ "$RSS" -gt "$PEAK_RSS" ] && PEAK_RSS=$RSS
        [ "$VSZ" -gt "$PEAK_VSZ" ] && PEAK_VSZ=$VSZ
        CPU_SUM=$(awk -v a="$CPU_SUM" -v b="$CPU" 'BEGIN{print a+b}')
        SAMPLES=$((SAMPLES + 1))
    fi
    sleep "$INTERVAL"
done

wait "$PID"
EXIT_CODE=$?
END=$(date +%s)
WALL=$((END - START))
AVG_CPU=$(awk -v s="$CPU_SUM" -v n="$SAMPLES" 'BEGIN{ if (n>0) printf "%.1f", s/n; else print "0" }')

{
    echo "Command:        $*"
    echo "Exit code:       $EXIT_CODE"
    echo "Wall time:       ${WALL}s ($(awk -v w="$WALL" 'BEGIN{printf "%.1f", w/60}') min)"
    echo "Peak RSS:        $((PEAK_RSS / 1024)) MB  (summed across all tracked processes, e.g. all MPI ranks)"
    echo "Peak VSZ:        $((PEAK_VSZ / 1024)) MB"
    echo "Avg CPU%:        ${AVG_CPU}%  (summed across processes; >100% means multiple cores busy)"
    echo "Samples:         ${SAMPLES} (every ${INTERVAL}s)"
    echo ""
    echo "Host: $(hostname)"
    echo "CPU cores:       $(nproc)"
    echo "System RAM:      $(free -h | awk '/Mem:/ {print $2}')"
    echo "System swap:     $(free -h | awk '/Swap:/ {print $2}')"
} | tee "$SUMMARY"

exit "$EXIT_CODE"
