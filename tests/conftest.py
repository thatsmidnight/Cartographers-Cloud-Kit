# Standard Library
import os
import sys
import importlib.util
from pathlib import Path
from types import ModuleType

# Third Party
import boto3
import pytest
from moto import mock_aws


@pytest.fixture(scope="session")
def aws_credentials():
    """Mocked AWS Credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture(scope="function")
def mock_cognito(aws_credentials):
    """Fixture to mock AWS SSM service using moto."""
    with mock_aws():
        # Create a mocked Cognito client
        cognito_client = boto3.client("cognito-idp", region_name="us-east-1")

        # Create a user pool for testing
        user_pool = cognito_client.create_user_pool(
            PoolName="test-user-pool",
            Policies={
                "PasswordPolicy": {
                    "MinimumLength": 8,
                    "RequireUppercase": True,
                    "RequireLowercase": True,
                    "RequireNumbers": True,
                    "RequireSymbols": True,
                }
            },
        )

        # Create a user pool client
        cognito_client.create_user_pool_client(
            UserPoolId=user_pool["UserPool"]["Id"],
            ClientName="test-client",
            GenerateSecret=False,
        )

        # Create a test user
        cognito_client.admin_create_user(
            UserPoolId=user_pool["UserPool"]["Id"],
            Username="testuser",
            UserAttributes=[
                {"Name": "email", "Value": "HelloWorld!1"},
                {"Name": "email_verified", "Value": "true"},
            ],
        )

        yield cognito_client


def pytest_configure(config):
    """
    Configure pytest to add the src directory to sys.path for module imports.
    This allows importing modules from the src directory in tests.
    """
    # Get the absolute path to the project root
    project_root = Path(__file__).parent.parent

    # Add the src directory to sys.path
    src_path = project_root / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))

    # Set environment variables for testing
    os.environ["DOCUMENTS_BUCKET_NAME"] = "test-documents-bucket"
    os.environ["VECTOR_STORE_BUCKET_NAME"] = "test-vector-bucket"
    os.environ["BEDROCK_TEXT_GENERATION_MODEL_ID"] = (
        "amazon.titan-text-express-v1"
    )
    os.environ["BEDROCK_EMBEDDING_MODEL_ID"] = "amazon.titan-embed-text-v1"
    os.environ["QUERY_CACHE_TABLE_NAME"] = "test-query-cache-table"

    return config


def import_handler(module_name: str) -> ModuleType:
    """
    Import a handler.py module from a src subdirectory, even when the directory
    name contains hyphens that prevent normal Python imports.

    Parameters
    ----------
    module_name : str
        The name of the module directory under src/
        (e.g., "as-presigned-url-generator")

    Returns
    -------
    ModuleType
        The imported handler module

    Raises
    ------
    ImportError
        If the module cannot be found or imported
    """
    # Get the absolute path to the project root
    project_root = Path(__file__).parent.parent

    # Construct the path to the handler.py file
    handler_path = project_root / "src" / module_name / "handler.py"

    if not handler_path.exists():
        raise ImportError(f"Handler file {handler_path} does not exist")

    # Create a unique module name to avoid conflicts
    safe_module_name = f"test_import_{module_name.replace('-', '_')}_handler"

    # Load the module specification
    spec = importlib.util.spec_from_file_location(
        safe_module_name, handler_path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load spec for {handler_path}")

    # Create the module
    handler_module = importlib.util.module_from_spec(spec)

    # Save the original sys.path
    original_path = sys.path.copy()

    # Add the module directory to sys.path temporarily so internal imports work
    module_dir = str(handler_path.parent)
    sys.path.insert(0, module_dir)

    # Add parent directory (needed for package imports)
    parent_dir = str(handler_path.parent.parent)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

    # Register the module in sys.modules (needed for relative imports)
    sys.modules[safe_module_name] = handler_module

    try:
        # Execute the module code
        spec.loader.exec_module(handler_module)
        return handler_module
    except Exception:
        # Clean up in case of error
        if safe_module_name in sys.modules:
            del sys.modules[safe_module_name]
        raise
    finally:
        # Restore original sys.path
        sys.path = original_path
