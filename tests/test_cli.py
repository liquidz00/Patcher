from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asyncclick.testing import CliRunner
from src.patcher.cli import main


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_components():
    with (
        patch("src.patcher.cli.ConfigManager") as mock_config_manager,
        patch("src.patcher.cli.TokenManager") as mock_token_manager,
        patch("src.patcher.cli.ApiClient") as mock_api_client,
        patch("src.patcher.cli.ExcelReport") as mock_excel_report,
        patch("src.patcher.cli.UIConfigManager") as mock_ui_config_manager,
        patch("src.patcher.cli.PDFReport") as mock_pdf_report,
        patch("src.patcher.cli.ReportManager") as mock_report_manager,
    ):

        mock_instance = MagicMock()
        mock_instance.process_reports = AsyncMock()
        mock_report_manager.return_value = mock_instance
        yield {
            "mock_config_manager": mock_config_manager,
            "mock_token_manager": mock_token_manager,
            "mock_api_client": mock_api_client,
            "mock_excel_report": mock_excel_report,
            "mock_ui_config_manager": mock_ui_config_manager,
            "mock_pdf_report": mock_pdf_report,
            "mock_report_manager": mock_instance,
        }


@pytest.mark.asyncio
async def test_cli_version(runner):
    result = await runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "version" in result.output


@pytest.mark.asyncio
async def test_cli_help(runner):
    result = await runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "Usage" in result.output
    assert "Options" in result.output


@pytest.mark.asyncio
async def test_main_function(runner, mock_components):
    result = await runner.invoke(main, ["--path", "~/", "--debug"])
    print("Test Output:", result.output)
    print("Exit Code:", result.exit_code)
    print("Mock Called:", mock_components["mock_report_manager"].process_reports.called)
    assert result.exit_code == 0
    assert mock_components["mock_report_manager"].process_reports.called


@pytest.mark.asyncio
async def test_main_function_invalid_path(runner, mock_components):
    with patch("os.makedirs", side_effect=OSError("Invalid path")):
        result = await runner.invoke(main, ["--path", "/invalid/path", "--debug"])
        print("Test Output:", result.output)
        print("Exit Code:", result.exit_code)
        assert result.exit_code == 1
