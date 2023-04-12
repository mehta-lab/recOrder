#!/bin/bash

# GLOBAL INPUTS for the reconstruction
BF_TIFF=../bire_recon/2022_08_04_recOrder_pytest_20x_04NA_BF/2T_3P_16Z_128Y_256X_Kazansky_BF_1
OUT_DATA=$(pwd)/phase_reconstruction_tmp.zarr
BG_DATA=../bire_recon/2022_08_04_recOrder_pytest_20x_04NA/BG
POSITIONS=3

# # Load the venviornments
module load anaconda
module load comp_micro
# This assumes user has the latest and editable recOrder install into it's environment
conda activate recorder-dev

# Setup an output log
logpath=../slurm_output/phase
mkdir -p $logpath
rm ../slurm_output/phase/*.out

# Check if the reconstruction file exists
if [ -d $BF_TIFF ]; then
    echo "Folder exists"
    echo $BF_TIFF
else
    echo "File does not exist. Running birefringence reconstruction"
    $BIRE_BATCH=../bire_recon/batch_bire_recon.sh
    . $BIRE_BATCH
fi

BF_ZARR=$(python ./convert_to_zarr.py --input $BF_TIFF)
ZARR_JOB_ID=$(sbatch --parsable create_empty_zarr_phase.sh $BF_ZARR $OUT_DATA)
PHASE_JOB_ID=$(sbatch --parsable --array=0-$((POSITIONS-1)) -d after:$ZARR_JOB_ID+1 phase_multiproc.sh $BF_ZARR $OUT_DATA)



