import importlib
import pytest

@pytest.fixture
def package():
    return importlib.import_module("codetracker_agent")

@pytest.fixture
def module_name():
    return "codetracker_agent"
