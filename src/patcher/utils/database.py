import asyncio
import json
import re
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd

from ..models.app import AppTitle
from ..models.patch import PatchTitle
from .exceptions import PatcherError
from .logger import LogMe
from .scraper import Scraper


class DataManager:
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
                    title TEXT NOT NULL UNIQUE,
                    bundle_id TEXT,
                    team_id TEXT,
                    mas INTEGER NOT NULL, -- Boolean: 0 or 1
                    installomator_label TEXT,
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

            # Create cve_data table
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS cve_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_title_id INTEGER NOT NULL,
                    cve_id TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    FOREIGN KEY (app_title_id) REFERENCES app_titles(id),
                    UNIQUE(app_title_id, cve_id)
                )
            """
            )

            conn.commit()

    def _upsert(self, table: str, data: Dict[str, Any], unique_keys: List[str]):
        """Perform an upsert operations (insert or update) based on unique keys."""
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

        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(query, tuple(data.values()))
            conn.commit()

    def _get_id(self, table: str, conditions: Dict[str, Any]) -> Optional[int]:
        """Retrieve the ID of a record based on conditions."""
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            query: str = f"SELECT id FROM {table} WHERE " + " AND ".join(
                [f"{k} = ?" for k in conditions.keys()]
            )
            c.execute(query, tuple(conditions.values()))
            result = c.fetchone()
            return result[0] if result else None

    def _get_team_id(self, app_title_id: int) -> Optional[str]:
        """Fetches the current team_id for the given app_title_id."""
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT team_id FROM app_titles WHERE id = ?", (app_title_id,))
            result = c.fetchone()
            return result[0] if result else None

    def find_or_add_id(self, app_title: AppTitle) -> int:
        """Retrieve the ID of an AppTitle, or create it if it doesn't exist."""
        app_title_id = self._get_id(table="app_titles", conditions={"title": app_title.title})

        if app_title_id is None:
            # AppTitle doesn't exist, create it
            app_title_id = self.add_app(app_title=app_title)

        return app_title_id

    def add_app(self, app_title: AppTitle) -> int:
        """Inserts an AppTitle into the database and returns the ID of the new record."""
        data = {
            "title": app_title.title,
            "bundle_id": app_title.bundle_id,
            "team_id": app_title.team_id,
            "mas": int(app_title.mas),
            "installomator_label": app_title.installomator_label,
            "jamf_supported": int(app_title.jamf_supported),
        }
        self._upsert(table="app_titles", data=data, unique_keys=["title"])
        self.log.info(f"Added new app title: {app_title.title}")

        return self._get_id(table="app_titles", conditions={"title": app_title.title})

    def add_patch(self, app_title_id: int, patch_title: PatchTitle) -> None:
        """Inserts a PatchTitle into the database, linked to an AppTitle."""
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

    def add_cve(self, app_title_id: int, cve_ids: List[str], severity: str) -> None:
        """Inserts CVE data into the database, linked to an AppTitle."""
        for cve_id in cve_ids:
            data = {"app_title_id": app_title_id, "cve_id": cve_id, "severity": severity}
            self._upsert(table="cve_data", data=data, unique_keys=["app_title_id", "cve_id"])

    # Load dataframe object (return a pd.DataFrame object)
    def load_dataframe(self, table_name: str) -> Optional[pd.DataFrame]:
        """Loads a pandas DataFrame from the specified table in the database."""
        with sqlite3.connect(self.db_path) as conn:
            try:
                query = f"SELECT * FROM {table_name}"
                dataframe = pd.read_sql_query(query, conn)
                return dataframe if not dataframe.empty else None
            except sqlite3.Error as e:
                self.log.error(f"Error loading DataFrame from table {table_name}: {e}")
                raise PatcherError(f"Error loading DataFrame from table {table_name}: {e}")


class DBAgent(DataManager):
    def __init__(self):
        super().__init__()
        self.log = LogMe(self.__class__.__name__)
        self.label_path = Path.home() / "Library" / "Application Support" / "Patcher" / ".labels"
        self.installomator_url = (
            "https://api.github.com/repos/Installomator/Installomator/contents/fragments/labels"
        )
        self.scraper = Scraper()

    @property
    def has_patches(self) -> bool:
        """Checks if there are any PatchTitle objects saved in the database."""
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(1) FROM patch_titles")
            return c.fetchone()[0] > 0

    async def _fetch(self, command: List[str]) -> str:
        process = await asyncio.create_subprocess_exec(
            *command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            self.log.error(f"curl failed with error: {stderr.decode()}")
            raise PatcherError(message=f"curl failed with error: {stderr.decode()}")
        return stdout.decode()

    async def update(self) -> None:
        """Master update method to refresh AppTitle objects in the database."""
        # Fetch data needed
        installomator_labels = await self._fetch_installomator_labels()
        jamf_titles = await self._fetch_jamf_titles()
        installed_apps = self._get_installed_apps()

        # Iterate over installed applications to create AppTitle objects
        for app_name, app_path in installed_apps.items():
            bundle_id = self._get_bundle_ids(app_path).get(app_path)
            from_mas = self._mas(app_path)
            team_id, installomator_label = self._get_installomator_data(
                app_name, installomator_labels
            )

            # Create AppTitle object
            app = AppTitle(
                title=app_name,
                bundle_id=bundle_id,
                team_id=team_id,
                mas=from_mas,
                installomator_label=installomator_label,
                jamf_supported=(app_name in jamf_titles),
            )

            # Fetch and update CVE data for app
            await self._fetch_criticals(title=app_name)

            # Save the AppTitle object to the database
            self.add_app(app_title=app)

        self.log.info("Database update completed successfully.")

    @staticmethod
    def _get_installed_apps() -> Dict[str, str]:
        """Retrieve the names and paths of installed applications."""
        applications_folder = Path("/Applications")
        installed_apps = {}
        for app in applications_folder.glob("*.app"):
            installed_apps[app.stem] = str(app)
        return installed_apps

    @staticmethod
    def _mas(app_path: str) -> bool:
        """Determines if an app was installed from the Mac App Store."""
        return (Path(app_path) / "Contents/_MASReceipt").exists()

    async def _get_installomator_data(
        self, app_name: str, labels: List[str]
    ) -> Tuple[Optional[str], Optional[str]]:
        """Get the team ID and Installomator label for a given applications."""
        label_match = next((label for label in labels if label.lower() == app_name.lower()), None)

        if label_match:
            download_url = f"https://raw.githubusercontent.com/Installomator/Installomator/main/fragments/labels/{label_match}.sh"
            curl_command = ["/usr/bin/curl", "-s", download_url]
            response = await self._fetch(curl_command)
            app_data = self._extract_data(response)

            if app_data:
                team_id = app_data[1]
                return team_id, label_match

        return None, None

    async def _fetch_installomator_labels(self) -> Optional[List[str]]:
        """Fetch the list of Installomator labels from the repository."""
        if not self.label_path.exists():
            self.label_path.mkdir(parents=True, exist_ok=True)

        curl_command = ["/usr/bin/curl", "-s", self.installomator_url]

        response = await self._fetch(command=curl_command)

        try:
            data = json.loads(response)
            return [item["name"].replace(".sh", "") for item in data if item["type"] == "file"]
        except json.JSONDecodeError as e:
            self.log.error(f"Installomator labels response could not be decoded: {e}")
            return []

    # Fetch cve data using subprocess and curl
    async def fetch_cve_data(self, title: str, severities: List[str]) -> List[str]:
        """Fetches CVE data for a given title and a list of severities, and stores it in the database."""
        app_title_id = self._get_id(table="app_titles", conditions={"title": title})
        if app_title_id is None:
            self.log.error(f"No AppTitle found in the database for the title: {title}")
            raise PatcherError(f"No AppTitle found in the database for the title: {title}")

        all_cves = []

        url = "https://services.nvd.nist.gov/rest/json/cves/2.0"
        end_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        start_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime(
            "%Y-%m-%dT%H:%M:%S.%f"
        )[:-3] + "Z"

        for severity in severities:
            params = {
                "keywordSearch": title,
                "resultsPerPage": 20,
                "startIndex": 0,
                "pubStartDate": start_date,
                "pubEndDate": end_date,
                "cvssV3Severity": severity,
            }

            curl_command = [
                "/usr/bin/curl",
                "-s",
                url,
                "--data-urlencode",
                f"keywordSearch={params['keywordSearch']}",
                "--data-urlencode",
                f"resultsPerPage={params['resultsPerPage']}",
                "--data-urlencode",
                f"startIndex={params['startIndex']}",
                "--data-urlencode",
                f"pubStartDate={params['pubStartDate']}",
                "--data-urlencode",
                f"pubEndDate={params['pubEndDate']}",
                "--data-urlencode",
                f"cvssV3Severity={params['cvssV3Severity']}",
                "-H",
                "apiKey: c12c82dd-2205-425c-893a-407a583184a0",
            ]

            response = await self._fetch(command=curl_command)

            cves = self._parse_response(response)

            all_cves.extend(cves)
            self.add_cve(app_title_id=app_title_id, cve_ids=cves, severity=severity)

        return all_cves

    @staticmethod
    def _parse_response(response: str) -> List[str]:
        data = json.loads(response)
        return [cve["cve"]["id"] for cve in data.get("vulnerabilities", [])]

    async def _fetch_criticals(self, title: str) -> List[str]:
        return await self.fetch_cve_data(title=title, severities=["HIGH", "CRITICAL"])

    def _get_bundle_ids(self, path: Union[Path, str]) -> Optional[Dict[str, str]]:
        if isinstance(path, str):
            path = Path(path)
        if not path.exists():
            self.log.error(f"{path} does not exist. Cannot obtain bundle ID.")
            raise PatcherError(message=f"{path} does not exist. Cannot obtain bundle ID.")

        try:
            result = subprocess.run(
                ["/usr/bin/mdls", path], capture_output=True, text=True, check=True
            )
        except subprocess.CalledProcessError as e:
            self.log.error(f"Error encountered obtaining bundle ID: {e}")
            raise PatcherError(message=f"Error encountered obtaining bundle ID: {e}")

        bundle_ids = {}

        if result:
            for line in result.stdout.splitlines():
                if line.strip().startswith("kMDItemCFBundleIdentifier"):
                    bundle_id = line.split("=")[-1].strip().strip('"')
                    bundle_ids[str(path)] = bundle_id
            return bundle_ids
        return None

    async def _fetch_jamf_titles(self) -> List[str]:
        html = await self.scraper.fetch_html()
        return self.scraper.parse_software_titles(html=html)

    @staticmethod
    def _extract_data(fragment: str) -> Optional[Tuple[str, str]]:
        """Extracts the application title and team ID from the Installomator fragment."""
        name_match = re.search(r'^\s*name\s*=\s*"(.*?)"\s*$', fragment, re.MULTILINE)
        team_id_match = re.search(r'^\s*expectedTeamID\s*=\s*"(.*?)"\s*$', fragment, re.MULTILINE)

        name = name_match.group(1).strip() if name_match else None
        team_id = team_id_match.group(1).strip() if team_id_match else None

        if name and team_id:
            return str(name), str(team_id)
        else:
            return None

    def return_app_titles(self) -> List[AppTitle]:
        app_titles = []

        query = "SELECT title, bundle_id, team_id, mas, installomator_label, jamf_supported FROM app_titles"

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()

            for row in rows:
                app_title = AppTitle(**row)
                app_titles.append(app_title)

        return app_titles

    def return_all(self) -> List[PatchTitle]:
        titles = []

        query = """
            SELECT
                pt.title AS patch_title,
                pt.released,
                pt.hosts_patched,
                pt.missing_patch,
                pt.completion_percent,
                at.title AS app_title,
                at.bundle_id,
                at.team_id,
                at.mas,
                at.installomator_label,
                at.jamf_supported
            FROM
                patch_titles pt
            JOIN
                app_titles at ON pt.app_title_id = at.id
        """

        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(query)
            rows = c.fetchall()

            for row in rows:
                # Create AppTitle object
                app_title = AppTitle(
                    title=row["patch_title"],
                    bundle_id=row["bundle_id"],
                    team_id=row["team_id"],
                    mas=bool(row["mas"]),
                    installomator_label=row["installomator_label"],
                    jamf_supported=bool(row["jamf_supported"]),
                )

                # Create the PatchTitle object and associate the AppTitle object
                patch_title = PatchTitle(
                    title=row["title"],
                    released=row["released"],
                    hosts_patched=row["hosts_patched"],
                    missing_patch=row["missing_patch"],
                    completion_percent=row["completion_percent"],
                    app_title=app_title,
                )

                titles.append(patch_title)

        return titles
