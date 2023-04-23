import pytest
from recOrder.cli import settings
from pydantic import ValidationError


def test_reconstruction_mode_settings():
    test_settings = settings._ReconstructionModeSettings(
        reconstruction_dimension="2"
    )

    with pytest.raises(ValidationError):
        test_settings = settings._ReconstructionModeSettings(
            reconstruction_dimension="1"
        )


def test_common_tf_settings():
    test_settings = settings._CommonTransferFunctionSettings(
        zyx_shape=(2, 3, 4)
    )

    with pytest.raises(ValidationError):
        test_settings = settings._CommonTransferFunctionSettings(zyx_shape=2)

    with pytest.raises(ValidationError):
        test_settings = settings._CommonTransferFunctionSettings(
            zyx_shape=(2, 3)
        )


def test_biref_tf_settings():
    test_settings = settings._BirefringenceTransferFunctionSettings(
        scheme="4-State", swing=0.1
    )

    with pytest.raises(ValidationError):
        test_settings = settings._BirefringenceTransferFunctionSettings(
            swing=1.1
        )

    with pytest.raises(ValidationError):
        test_settings = settings._BirefringenceTransferFunctionSettings(
            scheme="Test"
        )


def test_phase_tf_settings():
    with pytest.raises(ValidationError):
        test_settings = settings._PhaseTransferFunctionSettings(
            index_of_refraction_media=1.0, numerical_aperture_detection=1.1
        )


def test_transfer_function_settings():
    tf_settings = settings.TransferFunctionSettings()
    assert (
        tf_settings.phase_transfer_function_settings.yx_pixel_size == 6.5 / 20
    )

    with pytest.raises(ValidationError):
        settings.TransferFunctionSettings(reconstruct_birefringence=10)

    test_settings = {
        "reconstruct_birefringence": False,
        "reconstruct_phase": False,
    }

    with pytest.raises(ValidationError):
        tf_settings = settings.TransferFunctionSettings(**test_settings)

    # FIXME
    # See also: settings.py
    # with pytest.raises(Warning):
    #     ss = settings.TransferFunctionSettings(
    #         common_transfer_function_settings=settings._CommonTransferFunctionSettings(
    #             wavelength_illumination=532
    #         ),
    #         phase_transfer_function_settings=settings._PhaseTransferFunctionSettings(
    #             yx_pixel_size=0.25
    #         ),
    #     )


def test_inverse_settings():
    inverse_settings = settings.ApplyInverseSettings()
    assert inverse_settings.reconstruct_phase == True


def test_recon_settings():
    recon_settings = settings.ReconstructionSettings()
    assert recon_settings.reconstruct_phase == True
