import asyncio
import sqlite3
import subprocess
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd

from ..models.app import AppTitle
from ..models.label import Label
from ..models.patch import PatchTitle
from .exceptions import DatabaseError
from .logger import LogMe
from .scraper import Scraper
from .installomator import Installomator


class DataManager:
    """
    Manages database operations for handling app and patch data.

    Attributes:
        db_path (Path): Path to the SQLite database file.
        log (LogMe): Logger instance for logging operations.
    """

    def __init__(self):
        self.db_path = Path.home() / "Library" / "Application Support" / "Patcher" / ".patcher.db"
        self.log = LogMe(self.__class__.__name__)
        self._validate()

    def _validate(self):
        """Ensures the database file exists. If not, it creates it."""
        if not self.db_path.exists():
            self._create()

    def _create(self):
        """Creates the database and necessary tables"""
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            # Create app_titles table
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS app_titles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL UNIQUE COLLATE NOCASE,  -- Original, formatted version (Set case-insensitive)
                    normalized_title TEXT NOT NULL COLLATE NOCASE,  -- Normalized version for searching/querying
                    bundle_id TEXT,
                    mas INTEGER NOT NULL, -- Boolean: 0 or 1
                    jamf_supported INTEGER DEFAULT 0 -- Boolean: 0 or 1
                )
            """
            )

            # Create patch_titles table
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS patch_titles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_title_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    released TEXT,
                    hosts_patched INTEGER,
                    missing_patch INTEGER,
                    completion_percent REAL,
                    FOREIGN KEY (app_title_id) REFERENCES app_titles(id),
                    UNIQUE(app_title_id, title)
                )
            """
            )

            # Create installomator labels table
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS labels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_title_id INTEGER,  -- Allow NULL for labels with no associated AppTitle
                    name TEXT NOT NULL UNIQUE COLLATE NOCASE,  -- Ensure each label name is unique and case-insensitive
                    type TEXT,
                    team_id TEXT NOT NULL,
                    installomator_label TEXT,
                    FOREIGN KEY (app_title_id) REFERENCES app_titles(id)
                )
            """
            )

            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        """Establishes a connection to the SQLite database."""
        return sqlite3.connect(self.db_path)

    def _execute(self, query: str, params: Tuple = ()) -> Optional[List[sqlite3.Row]]:
        """Executes a database query and returns the results."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute(query, params)
            return c.fetchall()

    def _upsert(self, table: str, data: Dict[str, Any], unique_keys: List[str]) -> None:
        """
        Perform an upsert operation (insert or update) based on unique keys.

        :param table: Name of the table to perform the operation within.
        :type table: str
        :param data: Data dictionary to insert or update.
        :type data: Dict[str, Any]
        :param unique_keys: List of keys to ensure uniqueness.
        :type unique_keys: List[str]
        """
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        update_clause = ", ".join(
            [f"{k} = excluded.{k}" for k in data.keys() if k not in unique_keys]
        )

        query = f"""
            INSERT INTO {table} ({columns})
            VALUES ({placeholders})
            ON CONFLICT({", ".join(unique_keys)}) DO UPDATE SET {update_clause}
        """

        with self._connect() as conn:
            conn.execute(query, tuple(data.values()))
            conn.commit()

    def _get_id(self, table: str, conditions: Dict[str, Any]) -> Optional[int]:
        """
        Retrieve the ID of a record based on conditions.

        :param table: Name of the table to pull the ID from.
        :type table: str
        :param conditions: Dictionary of items to match.
        :type conditions: Dict[str, Any]
        :return: ID of the record if found, otherwise None.
        :rtype: Optional[int]
        """
        query = f"SELECT id FROM {table} WHERE " + " AND ".join(
            [f"{k} = ? COLLATE NOCASE" for k in conditions.keys()]
        )
        result = self._execute(query, tuple(conditions.values()))
        if result:
            row = result[0]
            return row["id"] if "id" in row.keys() else None
        return None

    @staticmethod
    def normalize_title(title: str) -> str:
        """
        Normalizes a title by converting to lowercase, stripping whitespace,
        and more. This is so case-sensitivity does not become an issue when
        querying the SQLite database.

        :param title: The title to normalize.
        :type title: str
        :return: The normalized title.
        :rtype: str
        """
        decoded_title = urllib.parse.unquote(title)
        return decoded_title.strip().lower()

    def find_or_add_id(self, app_title: AppTitle) -> int:
        """
        Retrieve the ID of an AppTitle, or create it if it doesn't exist.

        :param app_title: AppTitle object to find or add.
        :type app_title: AppTitle
        :return: ID of the AppTitle object
        :rtype: int
        """
        app_title_id = self._get_id(table="app_titles", conditions={"title": app_title.title})
        if app_title_id is None:
            app_title_id = self.add_app(app_title=app_title)
        return app_title_id

    def add_app(self, app_title: AppTitle) -> int:
        """
        Inserts an AppTitle into the database and returns the ID of the new record.

        :param app_title: AppTitle object to add.
        :type app_title: AppTitle
        :return: ID of the newly added AppTitle.
        :rtype: int
        """
        # Normalize title
        normalized_title = self.normalize_title(app_title.title)

        data = {
            "title": app_title.title,
            "normalized_title": normalized_title,
            "bundle_id": app_title.bundle_id,
            "mas": int(app_title.mas),
            "jamf_supported": int(app_title.jamf_supported),
        }
        self._upsert(table="app_titles", data=data, unique_keys=["title"])
        self.log.info(f"Added new app title: {app_title.title}")
        return self._get_id(
            table="app_titles",
            conditions={"title": app_title.title, "normalized_title": normalized_title},
        )

    def add_patch(self, app_title_id: int, patch_title: PatchTitle) -> None:
        """
        Inserts a PatchTitle into the database, linked to an AppTitle.

        :param app_title_id: ID of the associated AppTitle.
        :type app_title_id: int
        :param patch_title: PatchTitle object to add.
        :type patch_title: PatchTitle
        """
        data = {
            "app_title_id": app_title_id,
            "title": patch_title.title,
            "released": patch_title.released,
            "hosts_patched": patch_title.hosts_patched,
            "missing_patch": patch_title.missing_patch,
            "completion_percent": patch_title.completion_percent,
        }
        self._upsert(table="patch_titles", data=data, unique_keys=["app_title_id", "title"])
        self.log.info(f"Added new patch title: {patch_title.title} for app ID {app_title_id}")

    def add_label(self, label: Label) -> None:
        """
        Inserts a Label into the database. Associates the label with an AppTitle if a match is
        found, otherwise leaves `app_title_id` as NULL.

        :param label: Label object to add.
        :type label: Label
        """
        # Normalize label
        normalized_title = self.normalize_title(label.name)

        # Use normalized title for matching
        app_title_id = self._get_id(
            table="app_titles", conditions={"normalized_title": normalized_title}
        )

        # Check if a label with same name exists
        existing_label_id = self._get_id(table="labels", conditions={"name": label.name})
        if existing_label_id:
            self.log.warning(f"Label with name '{label.name}' already exists. Skipping.")
            return

        data = {
            "app_title_id": app_title_id,
            "name": label.name,
            "type": label.type,
            "team_id": label.expected_team_id,
            "installomator_label": label.installomator_label,
        }

        self._upsert(table="labels", data=data, unique_keys=["name"])
        if app_title_id is not None:
            self.log.info(f"Added new label: {label.name} associated with app ID {app_title_id}")
        else:
            self.log.info(f"Added new label: {label.name}")

    # Load dataframe object (return a pd.DataFrame object)
    def load_dataframe(self, table_name: str) -> Optional[pd.DataFrame]:
        """
        Loads a pandas DataFrame from the specified table in the database.

        :param table_name: Name of the table to load the data from.
        :type table_name: str
        :return: DataFrame containing the table data or None if empty.
        :rtype: Optional[pandas.DataFrame]
        """
        query = f"SELECT * FROM {table_name}"
        try:
            dataframe = pd.read_sql_query(query, self._connect())
            return dataframe if not dataframe.empty else None
        except sqlite3.Error as e:
            self.log.error(f"Error loading DataFrame from table {table_name}: {e}")
            raise DatabaseError(f"Error loading DataFrame from table {table_name}: {e}")


class DBAgent(DataManager):
    """
    Extends DataManager to include operations specific to patches, updates, and CVE data.

    While the DataManager class is responsible for CRUD database operations, the DBAgent
    class is responsible for fetching the data DataManager will handle.

    Attributes:
        installomator (Installomator): Installomator instance for gathering Installomator data.
        scraper (Scraper): Scraper instance for web scraping Jamf Software Title catalog.
    """

    def __init__(self):
        super().__init__()
        self.log = LogMe(self.__class__.__name__)
        self.installomator = Installomator()
        self.scraper = Scraper()

    @property
    def has_patches(self) -> bool:
        """
        Checks if there are any PatchTitle objects saved in the database.

        :return: True if patches exist, otherwise False.
        :rtype: bool
        """
        result = self._execute("SELECT COUNT(1) FROM patch_titles")
        return result[0][0] > 0 if result else False

    async def _fetch(self, command: List[str]) -> str:
        """
        Executes a shell command asynchronously.

        This method will primarily be used to make external API calls via `curl`. This is a
        workaround to support AIA fetching in Python. See :class:`~patcher.client.api_client.ApiClient`.

        :param command: Command list to execute.
        :type command: List[str]
        :return: Decoded (standard) output of the command.
        :rtype: str
        :raises DatabaseError: If the command fails.
        """
        process = await asyncio.create_subprocess_exec(
            *command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            self.log.error(f"curl failed with error: {stderr.decode()}")
            raise DatabaseError(f"curl failed with error: {stderr.decode()}")
        return stdout.decode()

    @staticmethod
    def _get_installed_apps() -> Dict[str, str]:
        """
        Retrieves the names and paths of installed applications.

        :return: Dictionary of application names and their paths.
        :rtype: Dict[str, str]
        """
        applications_folder = Path("/Applications")
        return {app.stem: str(app) for app in applications_folder.glob("*.app")}

    @staticmethod
    def _mas(app_path: str) -> bool:
        """
        Determines if an app was installed from the Mac App Store (MAS).

        :param app_path: Path of the application to check against.
        :type app_path: str
        :return: True if installed from MAS, otherwise False.
        :rtype: bool
        """
        return (Path(app_path) / "Contents/_MASReceipt").exists()

    def _get_bundle_ids(self, path: Union[Path, str]) -> Optional[Dict[str, str]]:
        """
        Retrieves bundle IDs from the specified Applications.

        :param path: Path to the Application to parse.
        :type path: Union[Path, str]
        :return: Dictionary of paths and bundle IDs.
        :rtype: Optional[Dict[str, str]]
        :raises DatabaseError: If the bundle ID cannot be obtained.
        """
        path = Path(path) if isinstance(path, str) else path
        if not path.exists():
            self.log.error(f"{path} does not exist. Cannot obtain bundle ID.")
            raise FileNotFoundError(f"{path} does not exist. Cannot obtain bundle ID.")

        try:
            result = subprocess.run(
                ["/usr/bin/mdls", path], capture_output=True, text=True, check=True
            )
        except subprocess.CalledProcessError as e:
            self.log.error(f"Error encountered obtaining bundle ID: {e}")
            raise OSError(f"Error encountered obtaining bundle ID: {e}")

        bundle_ids = {}
        if result:
            for line in result.stdout.splitlines():
                if line.strip().startswith("kMDItemCFBundleIdentifier"):
                    bundle_id = line.split("=")[-1].strip().strip('"')
                    bundle_ids[str(path)] = bundle_id
            return bundle_ids
        return None

    async def _fetch_jamf_titles(self) -> List[str]:
        """
        Fetches the Jamf Software Title App Catalog via web scraping.

        :return: List of Jamf supported titles.
        :rtype: List[str]
        """
        return self.scraper.parse_software_titles(html=await self.scraper.fetch_html())

    def return_titles(self) -> List[AppTitle]:
        """
        Retrieves all AppTitles, associated PatchTitles, and their Installomator labels.

        :return: List of AppTitle objects with associated patches and labels.
        :rtype: List[AppTitle]
        """

        # Helper func
        def create_obj(row_name, object_type, field_mapping: dict):
            return object_type(
                **{key: row_name[db_field] for key, db_field in field_mapping.items()}
            )

        patch_fields = {
            "title": "patch_title",
            "released": "released",
            "hosts_patched": "hosts_patched",
            "missing_patch": "missing_patch",
            "completion_percent": "completion_percent",
        }

        label_fields = {
            "name": "label_name",
            "type": "label_type",
            # "downloadURL": "label_download_url",  # Property will be used in future versions
            "expected_team_id": "expected_team_id",
            "installomator_label": "installomator_label",
        }

        combined_rows = self._execute(
            """
            SELECT
                at.id AS app_title_id, at.title AS app_title, at.bundle_id, at.mas, at.jamf_supported,
                pt.id AS patch_id, pt.title AS patch_title, pt.released, pt.hosts_patched, pt.missing_patch, pt.completion_percent,
                l.id AS label_id, l.name AS label_name, l.type AS label_type, l.download_url AS label_download_url, 
                l.team_id AS expected_team_id, l.installomator_label AS installomator_label
            FROM app_titles at
            LEFT JOIN patch_titles pt ON at.id = pt.app_title_id
            LEFT JOIN labels l ON at.id = l.app_title_id
            """
        )

        patches_by_app = {}
        labels_by_app = {}

        for row in combined_rows:
            app_title_id = row["app_title_id"]
            if app_title_id:
                # Collect patches
                if row["patch_id"]:
                    patch = create_obj(row, PatchTitle, patch_fields)
                    patches_by_app.setdefault(app_title_id, []).append(patch)

                # Collect labels
                if row["label_id"]:
                    label = create_obj(row, Label, label_fields)
                    labels_by_app.setdefault(app_title_id, []).append(label)

        # Create and return AppTitle objects with associated patches and labels
        app_titles = [
            # Intentionally leaving normalized name property out of object creation
            # as it is not required for data analysis purposes
            AppTitle(
                title=row["app_title"],
                bundle_id=row["bundle_id"],
                mas=bool(row["mas"]),
                jamf_supported=bool(row["jamf_supported"]),
                patches=patches_by_app.get(row["app_title_id"], []),
                labels=labels_by_app.get(row["app_title_id"], []),
            )
            for row in combined_rows
        ]

        return app_titles

    async def update(self) -> None:
        """Master update method to refresh AppTitle objects in the database."""
        installomator_fragments = await self.installomator.fetch_fragments()
        if not await self.installomator.create_label_dir(installomator_fragments):
            self.log.error("Installomator fragments could not be saved locally.")
            raise DatabaseError(
                "Installomator fragments could not be saved locally. Database update unsuccessful."
            )

        jamf_titles = await self._fetch_jamf_titles()
        installed_apps = self._get_installed_apps()

        for app_name, app_path in installed_apps.items():
            bundle_id = self._get_bundle_ids(app_path).get(app_path)
            from_mas = self._mas(app_path)

            # Create AppTitle object
            app = AppTitle(
                title=app_name,
                bundle_id=bundle_id,
                mas=from_mas,
                jamf_supported=(app_name in jamf_titles),
            )

            # Add app object to database
            self.add_app(app_title=app)

        labels = await self.installomator.create_labels()
        for label in labels:
            self.add_label(label)

        self.log.info("Database update completed successfully.")
