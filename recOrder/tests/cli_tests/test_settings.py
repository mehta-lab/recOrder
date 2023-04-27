import pytest
from recOrder.cli import settings
from pydantic import ValidationError


def test_reconstruction_mode_settings():
    test_settings = settings._UniversalSettings(reconstruction_dimension=2)

    with pytest.raises(ValidationError):
        test_settings = settings._UniversalSettings(reconstruction_dimension=1)


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
        settings._UniversalSettings(reconstruct_birefringence=10)

    test_settings = {
        "reconstruct_birefringence": False,
        "reconstruct_phase": False,
    }

    with pytest.raises(ValidationError):
        tf_settings = settings._UniversalSettings(**test_settings)


def test_inverse_settings():
    phase_inverse_settings = settings._PhaseApplyInverseSettings(
        reconstruction_algorithm="TV"
    )
    assert phase_inverse_settings.TV_iterations == 1
