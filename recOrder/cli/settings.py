from pydantic import BaseModel, validator


class _ReconstructionModeSettings(BaseModel):
    reconstruct_birefringence: bool = True
    reconstruct_phase: bool = True
    reconstruction_dimension: str = "2"  # or 3

    @validator("reconstruct_phase")
    def either_birefringence_or_phase(cls, v, values, **kwargs):
        if (not v) and (not values["reconstruct_birefringence"]):
            raise ValueError(
                "either reconstruct_birefringence or reconstruct_phase must be True"
            )
        return v


########## transfer function settings ##########


class _CommonTransferFunctionSettings(BaseModel):
    # common among all transfer functions
    zyx_shape: tuple = (10, 256, 256)  # 3-tuple
    wavelength_illumination: float = 0.532


class _BirefringenceTransferFunctionSettings(BaseModel):
    swing: float = 0.1  # TODO 0 < swing < 1
    scheme: str = "5-State"  # TODO string literal


class _PhaseTransferFunctionSettings(BaseModel):
    yx_pixel_size: float = 6.5 / 20
    z_pixel_size: float = 2.0
    z_padding: int = 0
    index_of_refraction_media: float = 1.3
    numerical_aperture_illumination: float = 0.5
    numerical_aperture_detection: float = 1.2


class TransferFunctionSettings(
    _ReconstructionModeSettings,
):
    common_settings: _CommonTransferFunctionSettings = (
        _CommonTransferFunctionSettings()
    )
    birefringence_transfer_function_settings: _BirefringenceTransferFunctionSettings = (
        _BirefringenceTransferFunctionSettings()
    )
    phase_transfer_function_settings: _PhaseTransferFunctionSettings = (
        _PhaseTransferFunctionSettings()
    )


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
