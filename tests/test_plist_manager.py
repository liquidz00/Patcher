

def test_get_existing_section(mock_plist_manager):
    mock_plist_manager.get.return_value = {"HEADER_TEXT": "Header"}
    assert mock_plist_manager.get("UI") == {"HEADER_TEXT": "Header"}


def test_get_missing_section(mock_plist_manager):
    mock_plist_manager.get.return_value = None
    assert mock_plist_manager.get("NonExistent") is None


def test_set_new_section(mock_plist_manager):
    mock_plist_manager.set.return_value = None
    mock_plist_manager.set("UI", {"HEADER_TEXT": "Header"})
    mock_plist_manager.set.assert_called_with("UI", {"HEADER_TEXT": "Header"})


def test_remove_key_from_section(mock_plist_manager):
    mock_plist_manager.remove.return_value = None
    mock_plist_manager.remove("UI", "HEADER_TEXT")
    mock_plist_manager.remove.assert_called_with("UI", "HEADER_TEXT")


def test_reset_specific_section(mock_plist_manager):
    mock_plist_manager.reset.return_value = True
    assert mock_plist_manager.reset("UI") is True


def test_reset_full_plist(mock_plist_manager):
    mock_plist_manager.reset.return_value = True
    assert mock_plist_manager.reset() is True
