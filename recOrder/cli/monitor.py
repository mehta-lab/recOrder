from pathlib import Path

import time
import submitit
import sys


def _clear_status(jobs):
    for job in jobs:
        sys.stdout.write("\033[F")  # Move cursor up
        sys.stdout.write("\033[K")  # Clear line


def _print_status(jobs, position_dirpaths, elapsed_list):
    for i, (job, position_dirpath) in enumerate(zip(jobs, position_dirpaths)):
        if job.state == "COMPLETED":
            color = "\033[32m"  # green
        elif job.state == "RUNNING":
            color = "\033[93m"  # yellow
            elapsed_list[i] += 1  # inexact timing
        else:
            color = "\033[91m"  # red

        try:
            node_name = job.get_info()["NodeList"]
        except:
            node_name = "SUBMITTED"

        sys.stdout.write(
            f"{color}{job.job_id}"
            f"\033[15G {'/'.join(position_dirpath.parts[-3:])}"
            f"\033[30G {job.state}"
            f"\033[40G {node_name}"
            f"\033[50G {elapsed_list[i]} s\n"
        )
        sys.stdout.flush()
    return elapsed_list


def _print_header():
    sys.stdout.write(
        "\033[96mID\033[15G WELL \033[30G STATUS \033[40G NODE \033[50G ELAPSED\n"
    )
    sys.stdout.flush()


def monitor_jobs(jobs: list[submitit.Job], position_dirpaths: list[Path]):
    """Displays the status of a list of submitit jobs with corresponding paths.

    Parameters
    ----------
    jobs : list[submitit.Job]
        List of submitit jobs
    position_dirpaths : list[Path]
        List of corresponding position paths
    """
    if not len(jobs) == len(position_dirpaths):
        raise ValueError(
            "The number of jobs and position_dirpaths should be the same."
        )

    elapsed_list = [0] * len(jobs)  # timer for each job
    try:
        _print_header()
        _print_status(jobs, position_dirpaths, elapsed_list)
        while not all(job.done() for job in jobs):
            time.sleep(1)
            _clear_status(jobs)
            elapsed_list = _print_status(jobs, position_dirpaths, elapsed_list)

        # Print final status
        time.sleep(1)
        _clear_status(jobs)
        _print_status(jobs, position_dirpaths, elapsed_list)

    except KeyboardInterrupt:
        for job in jobs:
            job.cancel()
        print("All jobs cancelled.")

    # Print STDOUT and STDERR for single-job runs
    if len(jobs) == 1:
        print("\033[32mSTDOUT")
        print(jobs[0].stdout())
        print("\033[91mSTDERR")
        print(jobs[0].stderr())
