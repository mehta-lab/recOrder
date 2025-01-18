from pathlib import Path

import time
import numpy as np
import shutil
import submitit
import sys


def _move_cursor_up(n_lines, doPrint=True):
    if doPrint:
        sys.stdout.write("\033[F" * n_lines)


def _print_status(jobs, position_dirpaths, elapsed_list, print_indices=None, doPrint=True):

    columns = [15, 30, 40, 50]

    # header
    if doPrint:
        sys.stdout.write(
            "\033[K"  # clear line
            "\033[96mID"  # cyan
            f"\033[{columns[0]}G WELL "
            f"\033[{columns[1]}G STATUS "
            f"\033[{columns[2]}G NODE "
            f"\033[{columns[2]}G ELAPSED\n"
        )

    if print_indices is None:
        print_indices = range(len(jobs))

    complete_count = 0

    for i, (job, position_dirpath) in enumerate(zip(jobs, position_dirpaths)):
        try:
            node_name = job.get_info()["NodeList"]  # slowest, so do this first
        except:
            node_name = "SUBMITTED"

        if job.state == "COMPLETED":
            color = "\033[32m"  # green
            complete_count += 1
        elif job.state == "RUNNING":
            color = "\033[93m"  # yellow
            elapsed_list[i] += 1  # inexact timing
        else:
            color = "\033[91m"  # red
        
        if i in print_indices:
            if doPrint:
                sys.stdout.write(
                    f"\033[K"  # clear line
                    f"{color}{job.job_id}"
                    f"\033[{columns[0]}G {'/'.join(position_dirpath.parts[-3:])}"
                    f"\033[{columns[1]}G {job.state}"
                    f"\033[{columns[2]}G {node_name}"
                    f"\033[{columns[3]}G {elapsed_list[i]} s\n"
                )
    sys.stdout.flush()
    if doPrint:
        print(
            f"\033[32m{complete_count}/{len(jobs)} jobs complete. " 
            "<ctrl+z> to move monitor to background. " 
            "<ctrl+c> twice to cancel jobs."
        )

    return elapsed_list


def _get_jobs_to_print(jobs, num_to_print):
    job_indices_to_print = []

    # if number of jobs is smaller than termanal size, print all
    if len(jobs) <= num_to_print:
        return list(range(len(jobs)))

    # prioritize incomplete jobs
    for i, job in enumerate(jobs):
        if not job.done():
            job_indices_to_print.append(i)
        if len(job_indices_to_print) == num_to_print:
            return job_indices_to_print

    # fill in the rest with complete jobs
    for i, job in enumerate(jobs):
        job_indices_to_print.append(i)
        if len(job_indices_to_print) == num_to_print:
            return job_indices_to_print

    # shouldn't reach here
    return job_indices_to_print


def monitor_jobs(jobs: list[submitit.Job], position_dirpaths: list[Path], doPrint=True):
    """Displays the status of a list of submitit jobs with corresponding paths.

    Parameters
    ----------
    jobs : list[submitit.Job]
        List of submitit jobs
    position_dirpaths : list[Path]
        List of corresponding position paths
    """
    NON_JOB_LINES = 3

    if not len(jobs) == len(position_dirpaths):
        raise ValueError(
            "The number of jobs and position_dirpaths should be the same."
        )

    elapsed_list = [0] * len(jobs)  # timer for each job

    # print all jobs once if terminal is too small
    if shutil.get_terminal_size().lines - NON_JOB_LINES < len(jobs):
        _print_status(jobs, position_dirpaths, elapsed_list, doPrint)

    # main monitor loop
    try:
        while not all(job.done() for job in jobs):
            terminal_lines = shutil.get_terminal_size().lines
            num_jobs_to_print = np.min(
                [terminal_lines - NON_JOB_LINES, len(jobs)]
            )

            job_indices_to_print = _get_jobs_to_print(jobs, num_jobs_to_print)

            elapsed_list = _print_status(
                jobs,
                position_dirpaths,
                elapsed_list,
                job_indices_to_print,
                doPrint,
            )

            time.sleep(1)
            _move_cursor_up(num_jobs_to_print + 2, doPrint)

        # Print final status
        time.sleep(1)
        _print_status(jobs, position_dirpaths, elapsed_list, doPrint=doPrint)

    # cancel jobs if ctrl+c
    except KeyboardInterrupt:
        for job in jobs:
            job.cancel()
        print("All jobs cancelled.\033[97m")

    # Print STDOUT and STDERR for first incomplete job
    incomplete_count = 0
    for job in jobs:
        if not job.done():
            if incomplete_count == 0:
                print("\033[32mSTDOUT")
                print(job.stdout())
                print("\033[91mSTDERR")
                print(job.stderr())

    print("\033[97m") # print white
