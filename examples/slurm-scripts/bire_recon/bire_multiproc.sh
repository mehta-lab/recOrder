#!/bin/bash
#SBATCH --job-name=BIRE_CONV
#SBATCH --time=1:00:00
#SBATCH --partition=cpu
#SBATCH --cpus-per-task=1
#SBATCH --mem-per-cpu=16G
#SBATCH --output=../slurm_output/bire/bire-%A-%a.out
env | grep "^SLURM" | sort

RAW_DATA=$1
OUT_BIRE=$2
BG_DATA=$3

module load anaconda
module load comp_micro
conda activate pyplay

now=$(date '+%y-%m-%d')
logpath=../logs/$now/bire
mkdir -p $logpath
logfile="$logpath/bire_conv_$SLURM_ARRAY_TASK_ID.out"

echo  "raw:  $RAW_DATA " >> ${logfile}
echo "out: $OUT_BIRE " >> ${logfile}
echo "BG_DATA: $BG_DATA " >> ${logfile}
echo "out: $SLURM_ARRAY_TASK_ID " >> ${logfile}
python -u ./bire_mp.py --input "$RAW_DATA" --output "$OUT_BIRE" --bg "$BG_DATA" -p $SLURM_ARRAY_TASK_ID &>> ${logfile}