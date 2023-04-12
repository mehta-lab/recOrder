#!/bin/bash
#SBATCH --job-name=PHASE_CONV
#SBATCH --time=2:00:00
#SBATCH --partition=gpu
#SBATCH --output=../slurm_output/phase/phaserecon-%A-%a.out
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --nodelist=gpu-c-1
#SBATCH --reservation=bignode
#SBATCH --gres=gpu:1
#SBATCH --mem=64GB

env | grep "^SLURM" | sort

RAW_DATA=$1
OUT_DATA=$2

module load anaconda
module load comp_micro
conda activate pyplay

now=$(date '+%y-%m-%d')
logpath=../logs/$now/phase
mkdir -p $logpath
logfile="$logpath/phase_conv_$SLURM_ARRAY_TASK_ID.out"

# echo $CUDA_VISIBLE_DEVICES
echo "raw:  $RAW_DATA " >> ${logfile}
echo "out: $OUT_DATA " >> ${logfile}
echo "out: $SLURM_ARRAY_TASK_ID " >> ${logfile}

python -u phase_mp.py --input "$RAW_DATA" --output "$OUT_DATA" -p $SLURM_ARRAY_TASK_ID  --gpu 0 >> ${logfile}
