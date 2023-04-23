import pytest
from recOrder.cli import settings
from pydantic import ValidationError


def test_transfer_function_settings():
    tf_settings = settings.TransferFunctionSettings()
    assert tf_settings.phase_settings.yx_pixel_size == 6.5 / 20

    with pytest.raises(ValidationError):
        settings.TransferFunctionSettings(reconstruct_birefringence=10)

    test_settings = {
        "reconstruct_birefringence": False,
        "reconstruct_phase": False,
    }

    with pytest.raises(ValidationError):
        tf_settings = settings.TransferFunctionSettings(**test_settings)


def test_inverse_settings():
    inverse_settings = settings.ApplyInverseSettings()
    assert inverse_settings.reconstruct_phase == True


def test_recon_settings():
    recon_settings = settings.ReconstructionSettings()
    assert recon_settings.reconstruct_phase == True
