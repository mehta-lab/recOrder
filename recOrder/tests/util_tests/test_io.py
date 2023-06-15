import os
import pytest
import yaml

from recOrder.cli.settings import ReconstructionSettings
from recOrder.io.utils import model_to_yaml, yaml_to_model


@pytest.fixture
def model():
    # Create a sample model object
    return ReconstructionSettings()


@pytest.fixture
def yaml_path(tmpdir):
    # Create a temporary YAML file path
    return os.path.join(tmpdir, "model.yaml")


def test_model_to_yaml(model, yaml_path):
    # Call the function under test
    model_to_yaml(model, yaml_path)

    # Check if the YAML file is created
    assert os.path.exists(yaml_path)

    # Load the YAML file and verify its contents
    with open(yaml_path, "r") as f:
        yaml_data = yaml.safe_load(f)

    # Check if the YAML data is a dictionary
    assert isinstance(yaml_data, dict)

    # Check YAML data
    assert "input_channel_names" in yaml_data


def test_model_to_yaml_invalid_model():
    # Create an object that does not have a 'dict()' method
    invalid_model = "not a model object"

    # Call the function and expect a TypeError
    with pytest.raises(TypeError):
        model_to_yaml(invalid_model, "model.yaml")


class MockModel:
    def __init__(self, field1=None, field2=None):
        self.field1 = field1
        self.field2 = field2


def test_yaml_to_model(sample_yaml):
    # Call the function under test
    result = yaml_to_model(sample_yaml, MockModel)

    # Verify the result
    assert isinstance(result, MockModel)
    assert result.field1 == "value1"
    assert result.field2 == "value2"
