import numpy as np

from typing import Literal, Union
from colorspacious import cspace_convert
from matplotlib.colors import hsv_to_rgb
from skimage.color import hsv2rgb
from skimage.exposure import rescale_intensity


# Commenting for 0.3.0. Consider debugging or deleting for 1.0.0.
# def generic_hsv_overlay(
#     H, S, V, H_scale=None, S_scale=None, V_scale=None, mode="2D"
# ):
#     """
#     Generates a generic HSV overlay in either 2D or 3D

#     Parameters
#     ----------
#     H:          (nd-array) data to use in the Hue channel
#     S:          (nd-array) data to use in the Saturation channel
#     V:          (nd-array) data to use in the Value channel
#     H_scale:    (tuple) values at which to clip the hue data for display
#     S_scale:    (tuple) values at which to clip the saturation data for display
#     V_scale:    (tuple) values at which to clip the value data for display
#     mode:       (str) '3D' or '2D'

#     Returns
#     -------
#     overlay:    (nd-array) RGB overlay array of shape (Z, Y, X, 3) or (Y, X, 3)

#     """

#     if H.shape != S.shape or H.shape != S.shape or S.shape != V.shape:
#         raise ValueError(
#             f"Channel shapes do not match: {H.shape} vs. {S.shape} vs. {V.shape}"
#         )

#     if mode == "3D":
#         overlay_final = np.zeros((H.shape[0], H.shape[1], H.shape[2], 3))
#         slices = H.shape[0]
#     else:
#         overlay_final = np.zeros((1, H.shape[-2], H.shape[-1], 3))
#         H = np.expand_dims(H, axis=0)
#         S = np.expand_dims(S, axis=0)
#         V = np.expand_dims(V, axis=0)
#         slices = 1

#     for i in range(slices):
#         H_ = np.interp(H[i], H_scale, (0, 1))
#         S_ = np.interp(S[i], S_scale, (0, 1))
#         V_ = np.interp(V[i], V_scale, (0, 1))

#         hsv = np.transpose(np.stack([H_, S_, V_]), (1, 2, 0))
#         overlay_final[i] = hsv_to_rgb(hsv)

#     return overlay_final[0] if mode == "2D" else overlay_final


def ret_ori_overlay(
    czyx,
    ret_max: Union[float, Literal["auto"]] = 10,
    cmap: Literal["JCh", "HSV"] = "JCh",
):
    """
    Creates an overlay of retardance and orientation with two different colormap options.
    HSV is the standard Hue, Saturation, Value colormap while JCh is a similar colormap but is perceptually uniform.

    Parameters
    ----------
    czyx:                   (nd-array) czyx[0] is retardance in nanometers, czyx[1] is orientation in radians [0, pi],
                            czyx.shape = (2, ...)

    ret_max:                (float) maximum displayed retardance. Typically use adjusted contrast limits.

    cmap:                   (str) 'JCh' or 'HSV'

    Returns
    -------
    overlay                 (nd-array) RGB image with shape (3, ...)

    """
    if czyx.shape[0] != 2:
        raise ValueError(
            f"Input must have shape (2, ...) instead of ({czyx.shape[9]}, ...)"
        )

    retardance = czyx[0]
    orientation = czyx[1]

    if ret_max == "auto":
        ret_max = np.percentile(np.ravel(retardance), 99.99)

    # Prepare input and output arrays
    ret_ = np.clip(retardance, 0, ret_max)  # clip and copy
    # Convert 180 degree range into 360 to match periodicity of hue.
    ori_ = orientation * 360 / np.pi
    overlay_final = np.zeros_like(retardance)

    # FIX ME: this binning code leads to artifacts.
    # levels = 32
    # ori_binned = (
    #     np.round(orientation[i] / 180 * levels + 0.5) / levels - 1 / levels
    # ) # bin orientation into 32 levels.
    # ori_ = np.interp(ori_binned, (0, 1), (0, 360))

    if cmap == "JCh":
        noise_level = 1

        J = ret_
        C = np.ones_like(J) * 60
        C[ret_ < noise_level] = 0
        h = ori_

        JCh = np.stack((J, C, h), axis=-1)
        JCh_rgb = cspace_convert(JCh, "JCh", "sRGB1")

        JCh_rgb[JCh_rgb < 0] = 0
        JCh_rgb[JCh_rgb > 1] = 1

        overlay_final = JCh_rgb
    elif cmap == "HSV":
        I_hsv = np.moveaxis(
            np.stack(
                [
                    ori_ / 360,
                    np.ones_like(ori_),
                    ret_ / np.max(ret_),
                ]
            ),
            source=0,
            destination=-1,
        )
        overlay_final = hsv_to_rgb(I_hsv)
    else:
        raise ValueError(f"Colormap {cmap} not understood")

    return np.moveaxis(
        overlay_final, source=-1, destination=0
    )  # .shape = (3, ...)


def ret_ori_phase_overlay(
    czyx, channel_order, max_val_V: float = 1.0, max_val_S: float = 1.0
):
    """
    HSV encoding of retardance + orientation + phase image with hsv colormap (orientation in h, retardance in s, phase in v)
    Parameters
    ----------
        czyx        : numpy.ndarray
                    czyx[0] corresponds to the retardance image
                    czyx[1]is the orientation image (range from 0 to pi)
                    czyx[2] is the the phase image

        max_val_V   : float
                      raise the brightness of the phase channel by 1/max_val_V

        max_val_S   : float
                      raise the brightness of the retardance channel by 1/max_val_S

    Returns:
        RGB with HSV (rerientation, Retardance, Phase)
    """

    C, Z, Y, X = czyx.shape
    assert C == 3, "The input array must have 3 channels"

    czyx_out = np.zeros((3, Z, Y, X), dtype=np.float32)
    # Normalize the stack
    ordered_stack = np.stack(
        (
            # Normalize the first channel by dividing by pi
            czyx[channel_order[0]] / np.pi,
            # Normalize the second channel and rescale intensity
            rescale_intensity(
                czyx[channel_order[1]],
                in_range=(
                    np.min(czyx[channel_order[1]]),
                    np.max(czyx[channel_order[1]]),
                ),
                out_range=(0, 1),
            )
            / max_val_S,
            # Normalize the third channel and rescale intensity
            rescale_intensity(
                czyx[channel_order[2]],
                in_range=(
                    np.min(czyx[channel_order[2]]),
                    np.max(czyx[channel_order[2]]),
                ),
                out_range=(0, 1),
            )
            / max_val_V,
        ),
        axis=0,
    )
    czyx_out = hsv2rgb(ordered_stack, channel_axis=0)
    return czyx_out
