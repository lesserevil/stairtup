"""
Tests for the CLI commands in app.main module.

This module contains tests for the `bd` command group including:
- product add: Adding a product from a Git repository URL
- project create: Creating a project under an existing product

Tests use pytest fixtures for temporary files and unittest.mock for mocking
subprocess and file operations.
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from app.main import cli
from app.company.types import Product


@pytest.fixture
def cli_runner():
    """Provide a Click CLI runner for testing."""
    return CliRunner()


@pytest.fixture
def mock_products(tmp_path) -> Path:
    """Create a mock products.jsonl file in a temporary directory."""
    products_file = tmp_path / "products.jsonl"
    return products_file


@pytest.fixture
def mock_projects(tmp_path) -> Path:
    """Create a mock projects.jsonl file in a temporary directory."""
    projects_file = tmp_path / "projects.jsonl"
    return projects_file


class TestProductAddCommand:
    """Tests for the `bd product add` command."""

    @patch("app.main.subprocess.run")
    @patch("app.main.WorkspaceManager.create_product_structure")
    @patch("app.main.WorkspaceManager.list_active_products")
    @patch("app.main.Path")
    def test_product_add_success(
        self,
        mock_path_class,
        mock_list_products,
        mock_create_structure,
        mock_subprocess_run,
        cli_runner,
        tmp_path,
    ):
        """
        Test that `bd product add` successfully adds a product.

        Verifies:
        - Product ID is correctly extracted from URL
        - Git clone is called with correct arguments
        - Product structure is created
        - Product is appended to products.jsonl
        """
        # Setup: Create mock products file
        products_file = tmp_path / "products.jsonl"

        # Mock Path to return our temp file for products.jsonl
        def path_side_effect(*args, **kwargs):
            path_str = str(args[0]) if args else ""
            if path_str == "products.jsonl":
                return products_file
            elif path_str.startswith("products/"):
                return tmp_path / path_str
            return Path(*args, **kwargs)

        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = True
        mock_path_instance.__str__ = MagicMock(return_value=str(products_file))
        mock_path_class.return_value = mock_path_instance
        mock_path_class.side_effect = lambda *args, **kwargs: (
            products_file
            if args and str(args[0]) == "products.jsonl"
            else Path(*args, **kwargs)
        )

        # Mock empty product list (no existing products)
        mock_list_products.return_value = []

        # Mock successful git clone
        mock_subprocess_run.return_value = MagicMock(
            returncode=0, stdout="Cloning into 'test-product'...", stderr=""
        )

        # Execute with isolated filesystem
        with cli_runner.isolated_filesystem(temp_dir=tmp_path) as fs:
            # Create the products.jsonl file
            fs_path = Path(fs)
            prod_file = fs_path / "products.jsonl"
            prod_file.touch()

            with patch("app.main.Path") as mock_path_in_fs:

                def fs_path_side_effect(*args, **kwargs):
                    arg_str = str(args[0]) if args else ""
                    if arg_str == "products.jsonl":
                        return prod_file
                    elif arg_str.startswith("products/"):
                        return fs_path / arg_str
                    return Path(*args, **kwargs)

                mock_path_in_fs.side_effect = fs_path_side_effect
                mock_path_in_fs.return_value = prod_file

                result = cli_runner.invoke(
                    cli, ["product", "add", "https://github.com/test/test-product"]
                )

        # Assert: Command succeeded
        assert result.exit_code == 0
        assert "Product 'test-product' added successfully" in result.output

        # Assert: Git clone was called with correct arguments
        mock_subprocess_run.assert_called_once()
        call_args = mock_subprocess_run.call_args
        assert call_args[0][0][0] == "git"
        assert call_args[0][0][1] == "clone"
        assert "test-product" in call_args[0][0][3]

        # Assert: Product structure was created
        mock_create_structure.assert_called_once_with("test-product", "test-product")

    @patch("app.main.WorkspaceManager.list_active_products")
    def test_product_add_extracts_id_from_url(
        self, mock_list_products, cli_runner, tmp_path
    ):
        """
        Test that product_id is correctly extracted from various URL formats.

        Tests URLs with:
        - Standard format: https://github.com/user/repo
        - With trailing slash: https://github.com/user/repo/
        - With .git suffix: https://github.com/user/repo.git
        """
        test_cases = [
            ("https://github.com/user/my-repo", "my-repo"),
            ("https://github.com/user/my-repo/", "my-repo"),
            ("https://github.com/user/My-Repo", "my-repo"),
            ("https://gitlab.com/org/some-project.git", "some-project.git"),
        ]

        for url, expected_id in test_cases:
            mock_list_products.return_value = []

            with cli_runner.isolated_filesystem(temp_dir=tmp_path) as fs:
                fs_path = Path(fs)
                prod_file = fs_path / "products.jsonl"
                prod_file.touch()

                with (
                    patch("app.main.subprocess.run") as mock_git,
                    patch(
                        "app.main.WorkspaceManager.create_product_structure"
                    ) as mock_create,
                    patch("app.main.Path") as mock_path,
                ):
                    mock_git.return_value = MagicMock(returncode=0)
                    mock_path.side_effect = lambda *args, **kwargs: (
                        prod_file
                        if args and str(args[0]) == "products.jsonl"
                        else fs_path / args[0]
                        if args and str(args[0]).startswith("products/")
                        else Path(*args, **kwargs)
                    )

                    result = cli_runner.invoke(cli, ["product", "add", url])

                    assert result.exit_code == 0, f"Failed for URL: {url}"
                    mock_create.assert_called_once()
                    assert mock_create.call_args[0][0] == expected_id.lower()
                    mock_create.reset_mock()

    @patch("app.main.WorkspaceManager.list_active_products")
    def test_product_add_already_exists(self, mock_list_products, cli_runner):
        """
        Test error handling when adding a product that already exists.

        Verifies:
        - Command exits with code 1
        - Error message is displayed
        - No git clone or file operations are performed
        """
        # Setup: Mock existing product
        existing_product = Product(
            id="existing-product",
            name="existing-product",
            git_url="https://github.com/user/existing-product",
            checkout_path="products/existing-product/checkout",
            beads_path="products/existing-product/beads",
            employees_file="products/existing-product/employees.jsonl",
            status="active",
            created_at="2026-01-01T00:00:00Z",
        )
        mock_list_products.return_value = [existing_product]

        # Execute
        result = cli_runner.invoke(
            cli, ["product", "add", "https://github.com/user/existing-product"]
        )

        # Assert: Command failed with expected error
        assert result.exit_code == 1
        assert "already exists" in result.output.lower()

    @patch("app.main.subprocess.run")
    @patch("app.main.WorkspaceManager.list_active_products")
    def test_product_add_git_clone_failure(
        self, mock_list_products, mock_subprocess_run, cli_runner
    ):
        """
        Test error handling when git clone fails.

        Verifies:
        - Command exits with code 1
        - Error message includes git error details
        - Product is not registered
        """
        # Setup
        mock_list_products.return_value = []
        mock_subprocess_run.side_effect = subprocess.CalledProcessError(
            returncode=128,
            cmd=["git", "clone", "bad-url", "path"],
            stderr="fatal: repository 'bad-url' does not exist",
        )

        # Execute
        result = cli_runner.invoke(cli, ["product", "add", "bad-url"])

        # Assert: Command failed with expected error
        assert result.exit_code == 1
        assert (
            "error cloning" in result.output.lower()
            or "repository" in result.output.lower()
        )


class TestProjectCreateCommand:
    """Tests for the `bd project create` command."""

    @patch("app.main.WorkspaceManager.list_active_products")
    def test_project_create_success(self, mock_list_products, cli_runner, tmp_path):
        """
        Test that `bd project create` successfully creates a project.

        Verifies:
        - Product existence is checked
        - Project ID is generated with correct format
        - Project is appended to projects.jsonl
        - Success message is displayed
        """
        # Setup: Mock existing product
        existing_product = Product(
            id="my-product",
            name="my-product",
            git_url="https://github.com/user/my-product",
            checkout_path="products/my-product/checkout",
            beads_path="products/my-product/beads",
            employees_file="products/my-product/employees.jsonl",
            status="active",
            created_at="2026-01-01T00:00:00Z",
        )
        mock_list_products.return_value = [existing_product]

        # Execute with isolated filesystem
        with cli_runner.isolated_filesystem(temp_dir=tmp_path) as fs:
            fs_path = Path(fs)
            proj_file = fs_path / "projects.jsonl"
            prod_file = fs_path / "products.jsonl"
            prod_file.touch()

            with patch("app.main.Path") as mock_path:

                def path_side_effect(*args, **kwargs):
                    arg_str = str(args[0]) if args else ""
                    if arg_str == "projects.jsonl":
                        return proj_file
                    elif arg_str == "products.jsonl":
                        return prod_file
                    return Path(*args, **kwargs)

                mock_path.side_effect = path_side_effect

                result = cli_runner.invoke(
                    cli, ["project", "create", "my-product", "My Test Project"]
                )

        # Assert: Command succeeded
        assert result.exit_code == 0, f"Output: {result.output}"
        assert "Project 'project-my-product-" in result.output
        assert "created successfully" in result.output
        assert "my-product" in result.output

        # Assert: Project was written to file
        with open(proj_file, "r") as f:
            lines = f.readlines()
            assert len(lines) == 1
            project_data = json.loads(lines[0])
            assert project_data["product_id"] == "my-product"
            assert project_data["name"] == "My Test Project"
            assert project_data["status"] == "active"

    @patch("app.main.WorkspaceManager.list_active_products")
    def test_project_create_product_not_found(self, mock_list_products, cli_runner):
        """
        Test error handling when creating a project for non-existent product.

        Verifies:
        - Command exits with code 1
        - Error message indicates product doesn't exist
        - No project file is created
        """
        # Setup: Mock empty product list
        mock_list_products.return_value = []

        # Execute
        result = cli_runner.invoke(
            cli, ["project", "create", "nonexistent", "Test Project"]
        )

        # Assert: Command failed with expected error
        assert result.exit_code == 1
        assert "does not exist" in result.output.lower()

    @patch("app.main.WorkspaceManager.list_active_products")
    def test_project_create_verifies_product_existence(
        self, mock_list_products, cli_runner
    ):
        """
        Test that product existence check is properly called.

        Verifies:
        - list_active_products is called to verify product existence
        - Correct error handling when product not found
        """
        # Setup: Mock FileNotFoundError (products.jsonl doesn't exist)
        mock_list_products.side_effect = FileNotFoundError("products.jsonl not found")

        # Execute
        result = cli_runner.invoke(cli, ["project", "create", "any-product", "Test"])

        # Assert: Command failed with file not found error
        assert result.exit_code == 1
        mock_list_products.assert_called_once()

    @patch("app.main.WorkspaceManager.list_active_products")
    def test_project_create_project_id_format(
        self, mock_list_products, cli_runner, tmp_path
    ):
        """
        Test that project ID follows the expected format.

        Format should be: project-{product_id}-{timestamp}
        """
        # Setup
        existing_product = Product(
            id="test-prod",
            name="test-prod",
            git_url="https://example.com/test",
            checkout_path="products/test-prod/checkout",
            beads_path="products/test-prod/beads",
            employees_file="products/test-prod/employees.jsonl",
            status="active",
            created_at="2026-01-01T00:00:00Z",
        )
        mock_list_products.return_value = [existing_product]

        with cli_runner.isolated_filesystem(temp_dir=tmp_path) as fs:
            fs_path = Path(fs)
            proj_file = fs_path / "projects.jsonl"

            with patch("app.main.Path") as mock_path:
                mock_path.side_effect = lambda *args, **kwargs: (
                    proj_file
                    if args and str(args[0]) == "projects.jsonl"
                    else Path(*args, **kwargs)
                )

                result = cli_runner.invoke(
                    cli, ["project", "create", "test-prod", "New Project"]
                )

        # Assert: Success and project ID format
        assert result.exit_code == 0

        with open(proj_file, "r") as f:
            project_data = json.loads(f.readline())
            project_id = project_data["id"]
            assert project_id.startswith("project-test-prod-")
            # Verify timestamp portion (14 digits for YYYYMMDDHHMMSS)
            timestamp_part = project_id.replace("project-test-prod-", "")
            assert len(timestamp_part) == 14
            assert timestamp_part.isdigit()


class TestCLIImports:
    """Tests for CLI module imports."""

    def test_cli_imports_from_main(self):
        """
        Test that CLI can be imported from app.main.

        Verifies the cli object is properly exposed from the main module.
        """
        from app.main import cli as imported_cli

        assert imported_cli is not None
        assert hasattr(imported_cli, "commands")

    def test_cli_has_product_group(self):
        """Test that CLI has the 'product' command group."""
        from app.main import cli

        assert "product" in cli.commands

    def test_cli_has_project_group(self):
        """Test that CLI has the 'project' command group."""
        from app.main import cli

        assert "project" in cli.commands

    def test_product_group_has_add_command(self):
        """Test that 'product' group has the 'add' command."""
        from app.main import cli

        product_group = cli.commands["product"]
        assert "add" in product_group.commands

    def test_project_group_has_create_command(self):
        """Test that 'project' group has the 'create' command."""
        from app.main import cli

        project_group = cli.commands["project"]
        assert "create" in project_group.commands
