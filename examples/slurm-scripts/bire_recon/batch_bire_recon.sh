#!/bin/bash

# Download the file from the web
url=https://zenodo.org/record/6983916/files/recOrder_test_data.zip
zip_file=recOrder_test_data.zip

# Check if the file already exists
if [ -f $zip_file ]; then
    echo "File already exists, skipping download."
else
    # Download the file
    wget $url >> ./test.out
    # Unzip the downloaded file
    unzip $zip_file >> ./test.out
fi

# GLOBAL INPUTS for the reconstruction
RAW_DATA=$(pwd)/2022_08_04_recOrder_pytest_20x_04NA/2T_3P_16Z_128Y_256X_Kazansky_1
OUT_DIR=$(pwd)/2022_08_04_recOrder_pytest_20x_04NA/tmp_birefringence_recon.zarr
BG_DATA=$(pwd)/2022_08_04_recOrder_pytest_20x_04NA/BG
POSITIONS=3

# Load the venviornments
module load anaconda
module load comp_micro
# This assumes user has the latest and editable recOrder install into it's environment
conda activate recorder-dev

# #Setup an output log
logpath=../slurm_output/bire
mkdir -p $logpath
rm ../slurm_output/bire/*.out

#Run the scripts
RAW_ZARR=$(python convert_to_zarr.py --input $RAW_DATA)
ZARR_JOB_ID=$(sbatch --parsable create_empty_zarr.sh $RAW_ZARR $OUT_DIR)
BIRE_JOB_ID=$(sbatch --parsable --array=0-$((POSITIONS-1)) -d after:$ZARR_JOB_ID+1 bire_multiproc.sh $RAW_ZARR $OUT_DIR $BG_DATA)

