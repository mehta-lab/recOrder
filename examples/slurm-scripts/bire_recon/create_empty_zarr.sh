#!/bin/bash

#SBATCH --job-name=ZARR_INIT
#SBATCH --time=0:10:00
#SBATCH --partition=cpu
#SBATCH --cpus-per-task=1
#SBATCH --mem-per-cpu=5G
#SBATCH --output=../slurm_output/bire/zarr-%A-%a.out
env | grep "^SLURM" | sort

module load anaconda
module load comp_micro
conda activate pyplay

RAW_DATA=$1
OUT_DIR=$2

now=$(date '+%y-%m-%d')
logpath=../logs/$now/bire
mkdir -p $logpath
rm $logpath/*.out
logfile="$logpath/Zarr.out"

echo  "raw:  $RAW_DATA " >> ${logfile}
echo "out: $OUT_DIR" >> ${logfile}
python -u ./empty_zarr.py --input "$RAW_DATA" --output "$OUT_DIR" &>> ${logfile}
 