from pydantic import BaseModel, validator
from typing import Literal, List


class _ReconstructionModeSettings(BaseModel):
    reconstruct_birefringence: bool = True
    reconstruct_phase: bool = True
    reconstruction_dimension: Literal["2", "3"] = "2"

    @validator("reconstruct_phase")
    def either_birefringence_or_phase(cls, v, values):
        if (not v) and (not values["reconstruct_birefringence"]):
            raise ValueError(
                "either reconstruct_birefringence or reconstruct_phase must be True"
            )
        return v


########## transfer function settings ##########


class _CommonTransferFunctionSettings(BaseModel):
    # common among all transfer functions
    zyx_shape: List[float] = (10, 256, 256)
    wavelength_illumination: float = 0.532

    @validator("zyx_shape")
    def zyx_shape_has_three_elements(cls, v):
        if len(v) != 3:
            raise ValueError(
                f"zyx_shape must has three elements instead of {len(v)}"
            )


class _BirefringenceTransferFunctionSettings(BaseModel):
    swing: float = 0.1
    scheme: Literal["4-State", "5-State"] = "5-State"

    @validator("swing")
    def swing_range(cls, v):
        if v <= 0 or v >= 1.0:
            raise ValueError(f"swing = {v} should be between 0 and 1.")


class _PhaseTransferFunctionSettings(BaseModel):
    yx_pixel_size: float = 6.5 / 20
    z_pixel_size: float = 2.0
    z_padding: int = 0
    index_of_refraction_media: float = 1.3
    numerical_aperture_illumination: float = 0.5
    numerical_aperture_detection: float = 1.2

    @validator("z_padding")
    def z_pad(cls, v):
        if v < 0:
            raise ValueError(f"z_padding = {v} cannot be negative")

    @validator("numerical_aperture_illumination")
    def na_ill(cls, v, values):
        n = values["index_of_refraction_media"]
        if v >= n:
            raise ValueError(
                f"numerical_aperture_illumination = {v} must be less than index_of_refraction_media = {n}"
            )

    @validator("numerical_aperture_detection")
    def na_det(cls, v, values):
        n = values["index_of_refraction_media"]
        if v >= n:
            raise ValueError(
                f"numerical_aperture_detection = {v} must be less than index_of_refraction_media = {n}"
            )


class TransferFunctionSettings(
    _ReconstructionModeSettings,
):
    common_transfer_function_settings: _CommonTransferFunctionSettings = (
        _CommonTransferFunctionSettings()
    )
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
    orientation_flip: bool = False
    orientation_rotate: bool = False


class _PhaseApplyInverseSettings(BaseModel):
    reconstruction_algorithm: str = "Tikhonov"
    reconstruction_parameters: list = [0.0, 0.0]


class ApplyInverseSettings(_ReconstructionModeSettings):
    birefringence_apply_inverse_settings: _BirefringenceApplyInverseSettings = (
        _BirefringenceApplyInverseSettings()
    )
    phase_apply_inverse_settings: _PhaseApplyInverseSettings = (
        _PhaseApplyInverseSettings()
    )


########## reconstruction settings ##########


class ReconstructionSettings(TransferFunctionSettings, ApplyInverseSettings):
    pass
