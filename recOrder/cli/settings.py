import os
from pydantic import BaseModel, DirectoryPath, validator
from typing import Literal, List


class _UniversalSettings(BaseModel):
    # these parameters are used by each step:
    #  - compute-transfer-function
    #  - apply-inverse-transfer-function
    #  - reconstruct
    reconstruct_birefringence: bool = True
    reconstruct_phase: bool = True
    reconstruction_dimension: Literal[2, 3] = 2
    wavelength_illumination: float = 0.532

    @validator("reconstruct_phase")
    def either_birefringence_or_phase(cls, v, values):
        if (not v) and (not values["reconstruct_birefringence"]):
            raise ValueError(
                "either reconstruct_birefringence or reconstruct_phase must be True"
            )
        return v

    @validator("wavelength_illumination")
    def wavelength(cls, v):
        if v < 0:
            raise ValueError(
                f"wavelength_illumination = {v} cannot be negative"
            )
        return v


########## transfer function settings ##########


class _BirefringenceTransferFunctionSettings(BaseModel):
    swing: float = 0.1
    scheme: Literal["4-State", "5-State"] = "4-State"

    @validator("swing")
    def swing_range(cls, v):
        if v <= 0 or v >= 1.0:
            raise ValueError(f"swing = {v} should be between 0 and 1.")
        return v


class _PhaseTransferFunctionSettings(BaseModel):
    zyx_shape: List[int] = [16, 128, 256]
    yx_pixel_size: float = 6.5 / 20
    z_pixel_size: float = 2.0
    z_padding: int = 0
    index_of_refraction_media: float = 1.3
    numerical_aperture_illumination: float = 0.5
    numerical_aperture_detection: float = 1.2

    @validator("zyx_shape")
    def zyx_shape_has_three_elements(cls, v):
        if len(v) != 3:
            raise ValueError(
                f"zyx_shape must has three elements instead of {len(v)}"
            )
        return v

    @validator("z_padding")
    def z_pad(cls, v):
        if v < 0:
            raise ValueError(f"z_padding = {v} cannot be negative")
        return v

    @validator("numerical_aperture_illumination")
    def na_ill(cls, v, values):
        n = values["index_of_refraction_media"]
        if v > n:
            raise ValueError(
                f"numerical_aperture_illumination = {v} must be less than or equal to index_of_refraction_media = {n}"
            )
        return v

    @validator("numerical_aperture_detection")
    def na_det(cls, v, values):
        n = values["index_of_refraction_media"]
        if v > n:
            raise ValueError(
                f"numerical_aperture_detection = {v} must be less than or equal to index_of_refraction_media = {n}"
            )
        return v


class TransferFunctionSettings(BaseModel):
    universal_settings: _UniversalSettings = _UniversalSettings()
    birefringence_transfer_function_settings: _BirefringenceTransferFunctionSettings = (
        _BirefringenceTransferFunctionSettings()
    )
    phase_transfer_function_settings: _PhaseTransferFunctionSettings = (
        _PhaseTransferFunctionSettings()
    )

    # FIXME - how can I validate across settings classes?
    # See also: test_settings.py
    # @validator("yx_pixel_size")
    # def warn_unit_consistency(cls, v, values):
    #     lamb = values["wavelength_illumination"]
    #     ratio = v / lamb
    #     if ratio < 1.0 / 20 or ratio > 20:
    #         raise Warning(
    #             f"yx_pixel_size ({v}) / wavelength_illumination ({lamb}) = {ratio}. Did you use consistent units?"
    #         )


########## apply inverse transfer function settings ##########


class _BirefringenceApplyInverseSettings(BaseModel):
    background_path: str = ""
    remove_estimated_background: bool = False
    orientation_flip: bool = False
    orientation_rotate: bool = False

    @validator("background_path")
    def check_background_path(cls, v):
        if v == "":
            return v

        raw_dir = r"{}".format(v)
        if not os.path.isdir(raw_dir):
            raise ValueError(f"{v} is not a existing directory")
        return raw_dir


class _PhaseApplyInverseSettings(BaseModel):
    reconstruction_algorithm: Literal["Tikhonov", "TV"] = "Tikhonov"
    strength: float = 1e-3
    TV_rho_strength: float = 1e-3
    TV_iterations: int = 1

    @validator("strength")
    def check_strength(cls, v):
        if v < 0:
            raise ValueError(f"strength = {v} cannot be negative")
        return v

    @validator("TV_rho_strength")
    def check_TV_rho_strength(cls, v, values):
        if v < 0 and values["reconstruction_algorithm"] == "TV":
            raise ValueError(f"TV_rho_strength = {v} cannot be negative")
        return v

    @validator("TV_iterations")
    def check_TV_iterations(cls, v, values):
        if v < 1 and values["reconstruction_algorithm"] == "TV":
            raise ValueError(f"TV_iteration = {v} cannot be less than 1.")
        return v


class ApplyInverseSettings(BaseModel):
    birefringence_apply_inverse_settings: _BirefringenceApplyInverseSettings = (
        _BirefringenceApplyInverseSettings()
    )
    phase_apply_inverse_settings: _PhaseApplyInverseSettings = (
        _PhaseApplyInverseSettings()
    )


########## reconstruction settings ##########


class ReconstructionSettings(TransferFunctionSettings, ApplyInverseSettings):
    pass
