# Software Installation Guide

## User installation

(Optional but recommended) install [anaconda](https://www.anaconda.com/products/distribution) and create a virtual environment  

```sh
conda create -y -n recOrder python=3.9
conda activate recOrder
```

Install `napari` and `recOrder-napari`:

```sh
pip install "napari[all]" recOrder-napari
```

Open `napari` with `recOrder-napari`:

```sh
napari -w recOrder-napari
```

View command-line help by running

```sh
recOrder.help
```

## Developer installation

### Windows (x86_64)

1. Install [`git`](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git) and `conda` (either [anaconda](https://www.anaconda.com/products/distribution) or [miniconda](https://docs.conda.io/en/latest/miniconda.html)).

2. Create a conda environment dedicated to `recOrder`:

    ```sh
    conda create -y -n recOrder python=3.9
    conda activate recOrder
    ```

3. Clone this repository:

    ```sh
    git clone https://github.com/mehta-lab/recOrder.git
    ```

4. Install `recOrder` and its developer dependencies:

    ```sh
    cd recOrder
    pip install -e ".[dev]"
    ```

5. To acquire data via `Micro-Manager`, follow  [microscope installation guide](./microscope-installation-guide.md).

**Optional GPU**: `recOrder` supports NVIDIA GPU computation with the `cupy` package. Follow [these instructions](https://github.com/cupy/cupy) to install `cupy` and check its installation with ```import cupy```. To enable gpu processing, set ```use_gpu: True``` in the config files.

### Mac OS X on Apple Silicon (arm_64)

[Napari](napari.org) uses PyQt5 to draw its GUI, which is not currently compatible with `pip`. We have tested the following emulated development environment on Mac OS 12.5. (It is available natively  through [conda-forge](https://github.com/conda-forge/miniforge) if the user does not intend to edit the `recOrder-napari` source code.)

1. Install and enable [Rosetta](https://support.apple.com/en-us/HT211861) for your terminal of choice. To verify, enter command `arch` in shell and it should print 'i386' instead of 'arm64'; or  check if the terminal process is labeled as 'Type: Intel' in the Activity Monitor.

2. (Optional) For connection with `Micro-Manager`, install Java (JDK 8 `x86_64`) and make sure it is properly linked for your system Java wrappers. For example, OpenJDK 8 may be installed as follows if you have a `x86_64` installation of [Homebrew](https://brew.sh/):

    ```sh
    arch -x86_64 /usr/local/bin/brew install openjdk@8
    ```

3. Create a conda environment:

    ```sh
    CONDA_SUBDIR=osx-64 conda create -n [environment] python=3.9  # create a new environment
    conda activate [environment]
    conda env config vars set CONDA_SUBDIR=osx-64  # subsequent commands use intel packages
    ```

4. Clone this repository:

    ```sh
    git clone https://github.com/mehta-lab/recOrder.git
    ```

5. Install `recOrder` and its developer dependencies:

    ```sh
    cd recOrder
    pip install -e ".[dev]"
    ```
