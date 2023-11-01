import pytest
from recOrder.cli import settings
from recOrder.io import utils
from pydantic import ValidationError


def test_reconstruction_settings():
    # Test defaults
    s = settings.ReconstructionSettings(
        reconstruction_type="Birefringence",
        reconstruction_settings=settings.BirefringenceSettings(),
    )
    assert len(s.input_channel_names) == 4
    assert s.reconstruction_settings.apply_inverse.background_path == ""

    # Test incorrect settings
    with pytest.raises(ValidationError):
        settings.ReconstructionSettings(input_channel_names=3)

    with pytest.raises(ValidationError):
        settings.ReconstructionSettings(reconstruction_dimension=1)

    # Test typo
    with pytest.raises(ValidationError):
        settings.ReconstructionSettings(
            flurescence=settings.FluorescenceSettings()
        )


def test_biref_tf_settings():
    settings.BirefringenceTransferFunctionSettings(swing=0.1)

    with pytest.raises(ValidationError):
        settings.BirefringenceTransferFunctionSettings(swing=1.1)

    with pytest.raises(ValidationError):
        settings.BirefringenceTransferFunctionSettings(scheme="Test")


def test_phase_tf_settings():
    settings.PhaseTransferFunctionSettings(
        index_of_refraction_media=1.0, numerical_aperture_detection=0.8
    )

    with pytest.raises(ValidationError):
        settings.PhaseTransferFunctionSettings(
            index_of_refraction_media=1.0, numerical_aperture_detection=1.1
        )

    # Inconsistent units
    with pytest.raises(Warning):
        settings.PhaseTransferFunctionSettings(
            yx_pixel_size=650, z_pixel_size=0.3
        )

    # Extra parameter
    with pytest.raises(ValidationError):
        settings.PhaseTransferFunctionSettings(zyx_pixel_size=650)


def test_fluor_tf_settings():
    settings.FluorescenceTransferFunctionSettings(
        wavelength_emission=0.500, yx_pixel_size=0.2
    )

    with pytest.raises(Warning):
        settings.FluorescenceTransferFunctionSettings(
            wavelength_emission=0.500, yx_pixel_size=2000
        )


def test_generate_example_settings():
    example_path = "./examples/"

    s0 = settings.ReconstructionSettings(
        reconstruction_type="Birefringence and Phase",
        reconstruction_settings=settings.BirefringenceAndPhaseSettings(),
    )
    s1 = settings.ReconstructionSettings(
        input_channel_names=["BF"],
        reconstruction_type="Phase",
        reconstruction_settings=settings.PhaseSettings(),
    )
    s2 = settings.ReconstructionSettings(
        reconstruction_type="Birefringence",
        reconstruction_settings=settings.BirefringenceSettings(),
    )
    s3 = settings.ReconstructionSettings(
        input_channel_names=["GFP"],
        reconstruction_type="Fluorescence",
        reconstruction_settings=settings.FluorescenceSettings(),
    )
    file_names = [
        "birefringence-and-phase.yml",
        "phase.yml",
        "birefringence.yml",
        "fluorescence.yml",
    ]
    settings_list = [s0, s1, s2, s3]

    # Save to examples folder and test roundtrip
    for file_name, settings_obj in zip(file_names, settings_list):
        utils.model_to_yaml(settings_obj, example_path + file_name)
        settings_roundtrip = utils.yaml_to_model(
            example_path + file_name, settings.ReconstructionSettings
        )
        assert settings_obj.dict() == settings_roundtrip.dict()
