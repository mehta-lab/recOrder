from pathlib import Path
from typing import Tuple

import click
import numpy as np
import torch
from iohub.ngff import Position, open_ome_zarr
from iohub.ngff_meta import TransformationMeta
from numpy.typing import DTypeLike

CODEC_MAX_BYTES = 2147483647


def create_empty_hcs_zarr(
    store_path: Path,
    position_keys: list[Tuple[str]],
    shape: Tuple[int],
    scale: Tuple[float],
    channel_names: list[str],
    dtype: DTypeLike,
    chunks: Tuple[int] = None,
    max_chunk_size_bytes= 500e6,
) -> None:
    """If the plate does not exist, create an empty zarr plate.

    If the plate exists, append positions and channels if they are not
    already in the plate.

    Parameters
    ----------
    store_path : Path
        The path to the hcs plate.
    position_keys : list[Tuple[str]]
        The position keys to append if not present in the plate.
        Example: [("A", "1", "0"), ("A", "1", "1")]
    shape : Tuple[int]
        The shape of the plate.
    scale : Tuple[float]
        The scale of the plate.
    channel_names : list[str]
        The channel names to append if not present in the metadata.
    dtype : DTypeLike
        The data type of the plate.
    chunks : Tuple[int], optional
        The chunk size of the plate (ZYX). If None, it will be calculated based on the shape (ZYX) and max_chunk_size_bytes, by default None.
    max_chunk_size_bytes : float, optional
        The maximum chunk size in bytes, by default 500e6.
    """

    # Create plate
    output_plate = open_ome_zarr(
        str(store_path), layout="hcs", mode="a", channel_names=channel_names
    )

    bytes_per_pixel = np.dtype(dtype).itemsize

    # Limiting the chunking to max_chunk_size_bytes and CODEC_MAX_BYTES
    if chunks is None or np.prod(chunks) * bytes_per_pixel > CODEC_MAX_BYTES:
        chunk_zyx_shape = list(shape[-3:])
        # chunk_zyx_shape[-3] > 1 ensures while loop will not stall if single
        # XY image is larger than max_chunk_size_bytes
        while (
            chunk_zyx_shape[-3] > 1
            and np.prod(chunk_zyx_shape) * bytes_per_pixel > max_chunk_size_bytes
        ):
            chunk_zyx_shape[-3] = np.ceil(chunk_zyx_shape[-3] / 2).astype(int)
        chunk_zyx_shape = tuple(chunk_zyx_shape)
        chunks = 2 * (1,) + chunk_zyx_shape

        # Raise warning if chunks are too large
        if np.prod(chunks) * bytes_per_pixel > CODEC_MAX_BYTES:
            raise Warning(
                f"Chunks size is too large. Chunks size < {CODEC_MAX_BYTES} bytes. Changing chunks to {chunks}"
            )
    
    # Create positions
    for position_key in position_keys:
        position_key_string = "/".join(position_key)
        # Check if position is already in the store, if not create it
        if position_key_string not in output_plate.zgroup:
            position = output_plate.create_position(*position_key)

            _ = position.create_zeros(
                name="0",
                shape=shape,
                chunks=chunks,
                dtype=dtype,
                transform=[TransformationMeta(type="scale", scale=scale)],
            )
        else:
            position = output_plate[position_key_string]

        # Check if channel_names are already in the store, if not append them
        for channel_name in channel_names:
            # Read channel names directly from metadata to avoid race conditions
            metadata_channel_names = [
                channel.label for channel in position.metadata.omero.channels
            ]
            if channel_name not in metadata_channel_names:
                position.append_channel(channel_name, resize_arrays=True)


def apply_inverse_to_zyx_and_save(
    func,
    position: Position,
    output_path: Path,
    input_channel_indices: list[int],
    output_channel_indices: list[int],
    t_idx: int = 0,
    **kwargs,
) -> None:
    """Load a zyx array from a Position object, apply a transformation and save the result to file"""
    click.echo(f"Reconstructing t={t_idx}")

    # Load data
    czyx_uint16_numpy = position.data.oindex[t_idx, input_channel_indices]

    # convert to np.int32 (torch doesn't accept np.uint16), then convert to tensor float32
    czyx_data = torch.tensor(np.int32(czyx_uint16_numpy), dtype=torch.float32)

    # Apply transformation
    reconstruction_czyx = func(czyx_data, **kwargs)

    # Write to file
    # for c, recon_zyx in enumerate(reconstruction_zyx):
    with open_ome_zarr(output_path, mode="r+") as output_dataset:
        output_dataset[0].oindex[
            t_idx, output_channel_indices
        ] = reconstruction_czyx
    click.echo(f"Finished Writing.. t={t_idx}")
